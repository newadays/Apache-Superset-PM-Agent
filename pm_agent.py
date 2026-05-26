#!/usr/bin/env python3
"""
PM Agent for Apache Superset.

Pipeline:
  1. Pull recent GitHub releases, issues, and discussions from apache/superset.
  2. Score every issue/discussion for priority using a transparent heuristic
     (bug-vs-feature, reactions/upvotes, comments, recency).
  3. Bucket items into P8 (highest) -> P3 (lowest).
  4. Call Claude (opus) to synthesize a PM report: top pain points, feature
     asks, and themes, ordered P8 -> P3.
  5. Write the report to report.md (and raw data to data/).

Auth:
  - GitHub: uses the `gh` CLI (must be authenticated: `gh auth status`).
  - Claude: uses the `claude` CLI in headless mode (`claude -p --model opus`).

Usage:
  python3 pm_agent.py --issues 250 --discussions 120 --top 70
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

REPO_OWNER = "apache"
REPO_NAME = "superset"
HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
NOW = dt.datetime.now(dt.timezone.utc)

# ----------------------------------------------------------------------------
# Shell helpers
# ----------------------------------------------------------------------------


def run(cmd: list[str], stdin: str | None = None, timeout: int = 180) -> str:
    """Run a command, return stdout, raise on non-zero exit."""
    proc = subprocess.run(
        cmd,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"command failed ({proc.returncode}): {' '.join(cmd[:4])}...\n"
            f"{proc.stderr.strip()[:800]}"
        )
    return proc.stdout


def gh_api(path: str, jq: str | None = None) -> str:
    cmd = ["gh", "api", path]
    if jq:
        cmd += ["--jq", jq]
    return run(cmd)


# ----------------------------------------------------------------------------
# Data model
# ----------------------------------------------------------------------------


@dataclass
class Item:
    kind: str  # "issue" | "discussion"
    number: int
    title: str
    url: str
    created_at: str
    updated_at: str
    comments: int
    reactions: int  # reactions (issues) or upvotes (discussions)
    labels: list[str] = field(default_factory=list)
    category: str = ""
    item_type: str = "other"  # bug | feature | question | other
    body_excerpt: str = ""
    # filled in by scoring
    score: float = 0.0
    priority: str = ""

    @property
    def days_since_update(self) -> float:
        try:
            t = dt.datetime.fromisoformat(self.updated_at.replace("Z", "+00:00"))
        except ValueError:
            return 999.0
        return max(0.0, (NOW - t).total_seconds() / 86400.0)

    @property
    def days_since_created(self) -> float:
        try:
            t = dt.datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))
        except ValueError:
            return 999.0
        return max(0.0, (NOW - t).total_seconds() / 86400.0)


# ----------------------------------------------------------------------------
# Fetchers
# ----------------------------------------------------------------------------


def fetch_releases(limit: int = 25) -> list[dict]:
    print(f"  fetching up to {limit} releases...", file=sys.stderr)
    raw = gh_api(f"repos/{REPO_OWNER}/{REPO_NAME}/releases?per_page={limit}")
    rels = json.loads(raw)
    out = []
    for r in rels:
        out.append(
            {
                "tag": r.get("tag_name"),
                "name": r.get("name"),
                "published_at": r.get("published_at"),
                "prerelease": r.get("prerelease"),
                "url": r.get("html_url"),
                "body": (r.get("body") or "")[:4000],
            }
        )
    return out


def classify_type(title: str, labels: list[str], category: str = "") -> str:
    text = (title + " " + " ".join(labels) + " " + category).lower()
    if any(k in text for k in ["bug", "regression", "broken", "error", "crash", "fail", "#bug"]):
        return "bug"
    if any(k in text for k in ["feat", "feature", "enhancement", "proposal", "ideas", "request", "support for"]):
        return "feature"
    if any(k in text for k in ["question", "q&a", "help", "how to", "how do"]):
        return "question"
    return "other"


def fetch_issues(limit: int = 250) -> list[Item]:
    # Use the search API: `is:issue` filters out PRs server-side, so we don't
    # waste the budget on pull requests (the plain issues endpoint mixes them).
    print(f"  fetching up to {limit} open issues via search (sorted by recent activity)...", file=sys.stderr)
    items: list[Item] = []
    per_page = 100
    page = 1
    query = "repo:apache/superset+is:issue+is:open"
    while len(items) < limit:
        raw = gh_api(
            f"search/issues?q={query}&sort=updated&order=desc"
            f"&per_page={per_page}&page={page}"
        )
        data = json.loads(raw)
        batch = data.get("items", [])
        if not batch:
            break
        for it in batch:
            labels = [l["name"] for l in it.get("labels", [])]
            title = it.get("title", "")
            items.append(
                Item(
                    kind="issue",
                    number=it["number"],
                    title=title,
                    url=it.get("html_url", ""),
                    created_at=it.get("created_at", ""),
                    updated_at=it.get("updated_at", ""),
                    comments=it.get("comments", 0),
                    reactions=it.get("reactions", {}).get("total_count", 0),
                    labels=labels,
                    item_type=classify_type(title, labels),
                    body_excerpt=re.sub(r"\s+", " ", (it.get("body") or ""))[:500],
                )
            )
            if len(items) >= limit:
                break
        page += 1
        if page > 10:  # search API hard-caps at 1000 results
            break
    print(f"    -> got {len(items)} issues", file=sys.stderr)
    return items


DISCUSSIONS_QUERY = """
query($cursor:String) {
  repository(owner:"%s", name:"%s") {
    discussions(first:50, after:$cursor, orderBy:{field:UPDATED_AT, direction:DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title url createdAt updatedAt upvoteCount
        comments { totalCount }
        category { name }
        reactions { totalCount }
        bodyText
      }
    }
  }
}
""" % (REPO_OWNER, REPO_NAME)


def fetch_discussions(limit: int = 120) -> list[Item]:
    print(f"  fetching up to {limit} discussions (most recently active)...", file=sys.stderr)
    items: list[Item] = []
    cursor = None
    while len(items) < limit:
        cmd = [
            "gh", "api", "graphql",
            "-f", f"query={DISCUSSIONS_QUERY}",
        ]
        if cursor:
            cmd += ["-f", f"cursor={cursor}"]
        raw = run(cmd)
        data = json.loads(raw)["data"]["repository"]["discussions"]
        for d in data["nodes"]:
            cat = (d.get("category") or {}).get("name", "")
            title = d.get("title", "")
            reactions = (d.get("reactions") or {}).get("totalCount", 0)
            upvotes = d.get("upvoteCount", 0)
            items.append(
                Item(
                    kind="discussion",
                    number=d["number"],
                    title=title,
                    url=d.get("url", ""),
                    created_at=d.get("createdAt", ""),
                    updated_at=d.get("updatedAt", ""),
                    comments=(d.get("comments") or {}).get("totalCount", 0),
                    reactions=max(upvotes, reactions),
                    category=cat,
                    item_type=classify_type(title, [], cat),
                    body_excerpt=re.sub(r"\s+", " ", (d.get("bodyText") or ""))[:500],
                )
            )
            if len(items) >= limit:
                break
        if not data["pageInfo"]["hasNextPage"]:
            break
        cursor = data["pageInfo"]["endCursor"]
    print(f"    -> got {len(items)} discussions", file=sys.stderr)
    return items


# ----------------------------------------------------------------------------
# Scoring
# ----------------------------------------------------------------------------

# Weights are deliberately simple and transparent so a PM can audit them.
W_REACTION = 3.0      # each reaction / upvote = strong signal of demand/pain
W_COMMENT = 1.5       # comments = engagement, but noisier than reactions
TYPE_WEIGHT = {       # bugs slightly upweighted: active pain > nice-to-have
    "bug": 1.20,
    "feature": 1.00,
    "question": 0.85,
    "other": 0.90,
}
RECENCY_HALFLIFE_DAYS = 75.0  # how fast stale items decay


def score_item(it: Item) -> float:
    engagement = (it.reactions * W_REACTION) + (it.comments * W_COMMENT)
    base = math.log1p(engagement) * 10.0 + 1.0  # log-dampen viral outliers
    recency = 0.4 + 0.6 * math.exp(-it.days_since_update / RECENCY_HALFLIFE_DAYS)
    return round(base * recency * TYPE_WEIGHT.get(it.item_type, 1.0), 3)


# P8 (highest) .. P3 (lowest). Top of distribution gets the urgent buckets.
PRIORITY_PERCENTILES = [
    (0.97, "P8"),  # top 3%
    (0.90, "P7"),  # next 7%
    (0.78, "P6"),  # next 12%
    (0.55, "P5"),  # next 23%
    (0.28, "P4"),  # next 27%
    (0.00, "P3"),  # bottom 28%
]


def assign_priorities(items: list[Item]) -> None:
    if not items:
        return
    for it in items:
        it.score = score_item(it)
    ranked = sorted(items, key=lambda x: x.score)
    n = len(ranked)
    for idx, it in enumerate(ranked):
        pct = idx / max(1, n - 1)
        for threshold, label in PRIORITY_PERCENTILES:
            if pct >= threshold:
                it.priority = label
                break


# ----------------------------------------------------------------------------
# Claude synthesis
# ----------------------------------------------------------------------------


def build_prompt(items: list[Item], releases: list[dict], top_n: int) -> str:
    top = sorted(items, key=lambda x: x.score, reverse=True)[:top_n]

    rel_lines = []
    for r in releases[:12]:
        tag = r.get("tag") or ""
        date = (r.get("published_at") or "")[:10]
        pre = " (prerelease)" if r.get("prerelease") else ""
        rel_lines.append(f"- {tag}{pre} — {date}")
    releases_block = "\n".join(rel_lines)

    rows = []
    for it in top:
        rows.append(
            {
                "ref": f"{it.kind} #{it.number}",
                "priority": it.priority,
                "score": it.score,
                "type": it.item_type,
                "title": it.title,
                "reactions": it.reactions,
                "comments": it.comments,
                "days_old": round(it.days_since_created),
                "days_since_update": round(it.days_since_update),
                "labels": it.labels[:8],
                "category": it.category,
                "url": it.url,
                "excerpt": it.body_excerpt,
            }
        )
    items_json = json.dumps(rows, indent=1)

    type_counts: dict[str, int] = {}
    for it in items:
        type_counts[it.item_type] = type_counts.get(it.item_type, 0) + 1

    return f"""You are a senior Product Manager for Apache Superset (open-source data
exploration & dashboarding platform). You have been handed pre-scored signal
mined from the GitHub repository. Produce a crisp, executive-ready PM report.

## Context

Recent releases (newest first):
{releases_block}

Corpus analyzed: {len(items)} items total — type breakdown: {json.dumps(type_counts)}.
Below are the top {len(top)} highest-scored issues & discussions. Each already
carries a heuristic priority (P8 highest .. P3 lowest) and an engagement score
derived from reactions, comments, recency, and bug-vs-feature weighting.

## Scored items (JSON)
{items_json}

## Your task

Write a Markdown PM report with these sections:

1. **Executive summary** — 4-6 bullets: the state of user sentiment and the
   single most important thing the team should do next.

2. **Top pain points** — the recurring problems/bugs users hit. Cluster related
   items into themes; don't just relist issues.

3. **Top feature asks** — the most demanded capabilities/enhancements.

4. **Cross-cutting themes** — 3-6 themes that span pain points + feature asks
   (e.g. "Dashboard performance", "RBAC/Security", "SQL Lab UX", "Charting
   gaps", "Deployment/Helm"). For each: a name, what's driving it, and which
   item refs feed it.

5. **Prioritized backlog (P8 → P3)** — group the themes/findings into priority
   buckets P8 (drop-everything) down to P3 (backlog). For EACH bucket, list the
   theme(s)/finding(s) with: a one-line rationale, supporting item refs (use the
   `ref` field, e.g. "issue #12345"), and a suggested PM action. Order strictly
   P8, P7, P6, P5, P4, P3. Omit a bucket only if genuinely empty.

Rules:
- Be specific and cite item refs. Tie claims to the data given.
- Distinguish bugs (active pain) from feature requests (latent demand).
- Note when something correlates with a recent release.
- Keep it skimmable. Use tables where they help. No fluff.
"""


def call_claude(prompt: str, model: str = "opus", timeout: int = 600) -> str:
    print(f"  calling Claude ({model}) to synthesize report...", file=sys.stderr)
    cmd = ["claude", "-p", "--model", model]
    return run(cmd, stdin=prompt, timeout=timeout).strip()


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="PM Agent for Apache Superset")
    ap.add_argument("--issues", type=int, default=250)
    ap.add_argument("--discussions", type=int, default=120)
    ap.add_argument("--releases", type=int, default=25)
    ap.add_argument("--top", type=int, default=70, help="top-N items to feed Claude")
    ap.add_argument("--model", default="opus")
    ap.add_argument("--out", default=str(HERE / "report.md"))
    ap.add_argument("--skip-llm", action="store_true", help="fetch+score only")
    args = ap.parse_args()

    DATA_DIR.mkdir(exist_ok=True)

    print("[1/4] Fetching GitHub data...", file=sys.stderr)
    releases = fetch_releases(args.releases)
    issues = fetch_issues(args.issues)
    discussions = fetch_discussions(args.discussions)
    items = issues + discussions

    print("[2/4] Scoring & prioritizing...", file=sys.stderr)
    assign_priorities(items)

    # Persist raw + scored data for auditability.
    (DATA_DIR / "releases.json").write_text(json.dumps(releases, indent=2))
    scored = sorted((asdict(i) for i in items), key=lambda x: x["score"], reverse=True)
    (DATA_DIR / "scored_items.json").write_text(json.dumps(scored, indent=2))

    dist: dict[str, int] = {}
    for it in items:
        dist[it.priority] = dist.get(it.priority, 0) + 1
    print(f"    priority distribution: {json.dumps(dist)}", file=sys.stderr)

    if args.skip_llm:
        print("[3/4] --skip-llm set; wrote data/ only.", file=sys.stderr)
        return 0

    print("[3/4] Synthesizing report with Claude...", file=sys.stderr)
    prompt = build_prompt(items, releases, args.top)
    (DATA_DIR / "prompt.txt").write_text(prompt)
    report_body = call_claude(prompt, model=args.model)

    print("[4/4] Writing report...", file=sys.stderr)
    # The script supplies its own title/metadata header, so drop a duplicate
    # top-level H1 (and any leading "*Generated...*" subtitle) from the model.
    lines = report_body.splitlines()
    while lines and (
        lines[0].startswith("# ")
        or lines[0].strip() in ("", "---")
        or lines[0].lstrip().startswith("*Generated")
    ):
        lines.pop(0)
    report_body = "\n".join(lines).strip()
    header = (
        f"# Apache Superset — PM Signal Report\n\n"
        f"_Generated {NOW.strftime('%Y-%m-%d %H:%M UTC')} • "
        f"{len(issues)} issues + {len(discussions)} discussions analyzed • "
        f"top {args.top} fed to Claude ({args.model})_\n\n"
        f"Priority scale: **P8 = highest, P3 = lowest.** "
        f"Priority distribution across corpus: `{json.dumps(dist)}`\n\n"
        f"---\n\n"
    )
    Path(args.out).write_text(header + report_body + "\n")
    print(f"\n✅ Report written to {args.out}", file=sys.stderr)
    print(f"   Raw + scored data in {DATA_DIR}/", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
