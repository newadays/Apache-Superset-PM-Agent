#!/usr/bin/env python3
"""
Priority Scoring eval for the Superset PM Agent.

Validates the heuristic that turns raw engagement into a P8..P3 priority, in two
parts:

  Part A — formula correctness (deterministic, free):
    Independently re-derive each item's score and priority bucket from the
    documented formula and compare to the values stored in data/scored_items.json.
    Catches implementation bugs / data drift. Only the tunable *constants*
    (weights, half-life, percentile table) are imported from pm_agent — the
    *structure* (engagement -> recency decay -> type weight -> percentile bucket)
    is reimplemented here, so a broken formula is caught even though a deliberate
    re-tuning of a constant is not falsely flagged.

  Part B — ranking quality (LLM-as-judge, opt-in via --judge):
    An LLM acting as a Superset PM rates each sampled item's importance 1-10 from
    its content ALONE (it never sees the heuristic score or priority). We then
    report rank correlation (Spearman / Kendall) between the judge's importance
    and the heuristic score, plus mean judge rating per priority bucket. Because
    the priority buckets are relative percentiles, ranking agreement — not
    absolute-label match — is the meaningful signal.

Inputs are artifacts a normal run already writes:
  data/scored_items.json  -> every item with its stored score + priority
  report.md               -> the '_Generated ... UTC_' line gives the run's "now"
                             (needed to reproduce the recency decay)

Usage:
  python3 score_eval.py                              # Part A only
  python3 score_eval.py --judge --sample 40          # + LLM ranking eval
  python3 score_eval.py --judge --out data/score_eval.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import sys
from pathlib import Path

# Reuse the agent's `claude` runner and the tunable scoring constants. We import
# the CONSTANTS (the knobs a PM tunes) but reimplement the FORMULA STRUCTURE.
from pm_agent import (
    run,
    W_REACTION,
    W_COMMENT,
    TYPE_WEIGHT,
    RECENCY_HALFLIFE_DAYS,
    PRIORITY_PERCENTILES,
)

HERE = Path(__file__).resolve().parent


# ----------------------------------------------------------------------------
# Reference time (the run's "now", to reproduce recency decay)
# ----------------------------------------------------------------------------


def reference_now(report_path: Path) -> dt.datetime:
    """Recover the run's NOW from report.md's '_Generated YYYY-MM-DD HH:MM UTC_'."""
    try:
        m = re.search(r"_Generated (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) UTC", report_path.read_text())
        if m:
            return dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M").replace(tzinfo=dt.timezone.utc)
    except FileNotFoundError:
        pass
    print("  ! could not read report timestamp; using current time (recency may drift)", file=sys.stderr)
    return dt.datetime.now(dt.timezone.utc)


def days_since(ts: str, now: dt.datetime) -> float:
    try:
        t = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return 999.0
    return max(0.0, (now - t).total_seconds() / 86400.0)


# ----------------------------------------------------------------------------
# Part A — deterministic formula correctness
# ----------------------------------------------------------------------------


def recompute_score(item: dict, now: dt.datetime) -> float:
    """Independent reimplementation of pm_agent.score_item's structure."""
    engagement = item["reactions"] * W_REACTION + item["comments"] * W_COMMENT
    base = math.log1p(engagement) * 10.0 + 1.0
    recency = 0.4 + 0.6 * math.exp(-days_since(item["updated_at"], now) / RECENCY_HALFLIFE_DAYS)
    return round(base * recency * TYPE_WEIGHT.get(item["item_type"], 1.0), 3)


def recompute_priority_for_rank(idx: int, n: int) -> str:
    """Independent reimplementation of pm_agent.assign_priorities' bucketing."""
    pct = idx / max(1, n - 1)
    for threshold, label in PRIORITY_PERCENTILES:
        if pct >= threshold:
            return label
    return PRIORITY_PERCENTILES[-1][1]


def check_formula(items: list[dict], now: dt.datetime, tol: float) -> dict:
    # --- score recompute ---
    score_mismatch = []
    for it in items:
        got = recompute_score(it, now)
        if abs(got - it["score"]) > tol:
            score_mismatch.append({"ref": f"{it['kind']} #{it['number']}", "stored": it["score"], "recomputed": got})

    # --- priority bucketing recompute (rank by stored score, ascending) ---
    ranked = sorted(items, key=lambda x: x["score"])
    n = len(ranked)
    score_counts: dict[float, int] = {}
    for it in items:
        score_counts[it["score"]] = score_counts.get(it["score"], 0) + 1
    real_pri_mismatch, tie_pri_mismatch = [], []
    for idx, it in enumerate(ranked):
        expected = recompute_priority_for_rank(idx, n)
        if expected != it["priority"]:
            rec = {"ref": f"{it['kind']} #{it['number']}", "stored": it["priority"], "expected": expected, "score": it["score"]}
            # A mismatch at a duplicated score is a benign tie-ordering artifact:
            # scored_items.json is sorted by score and loses the original
            # insertion order pm_agent used to break ties.
            (tie_pri_mismatch if score_counts[it["score"]] > 1 else real_pri_mismatch).append(rec)

    return {
        "n": len(items),
        "score_tol": tol,
        "score_matches": len(items) - len(score_mismatch),
        "score_mismatches": score_mismatch,
        "priority_matches": n - len(real_pri_mismatch) - len(tie_pri_mismatch),
        "priority_real_mismatches": real_pri_mismatch,
        "priority_tie_mismatches": len(tie_pri_mismatch),
    }


# ----------------------------------------------------------------------------
# Part B — ranking quality vs LLM PM judge
# ----------------------------------------------------------------------------


def stratified_sample(items: list[dict], k: int) -> list[dict]:
    """Pick k items evenly across the score range so the judge sees the full
    spread (good for correlation), not just the head."""
    ranked = sorted(items, key=lambda x: x["score"], reverse=True)
    if k >= len(ranked):
        return ranked
    step = (len(ranked) - 1) / (k - 1)
    idxs = sorted({round(i * step) for i in range(k)})
    return [ranked[i] for i in idxs]


JUDGE_SYSTEM = """You are a senior Product Manager for Apache Superset (open-source
data exploration & dashboarding). Rate how important each GitHub item is to
address, on a 1-10 scale, using ONLY the item's content and engagement signals.

Rubric:
 9-10 : critical — active regression / data-loss / security / broad blocking impact, or overwhelming demand
 7-8  : important — a real bug many users hit, or a high-demand feature
 5-6  : moderate — useful fix/feature, bounded audience
 3-4  : minor — niche, cosmetic, or low-impact
 1-2  : trivial / unclear / noise

Judge on substance and demand. Do NOT assume an ordering from the input order.

Return ONLY a JSON array, one object per item, no prose:
[{"id": <id>, "importance": <int 1-10>, "why": "<=12 words"}]"""


def run_judge(sample: list[dict], model: str) -> dict[int, dict]:
    entries = [
        {
            "id": i,
            "type": it["item_type"],
            "title": it["title"],
            "excerpt": (it.get("body_excerpt") or "")[:300],
            "labels": it.get("labels", [])[:8],
            "category": it.get("category", ""),
            "reactions": it["reactions"],
            "comments": it["comments"],
        }
        for i, it in enumerate(sample)
    ]
    prompt = f"{JUDGE_SYSTEM}\n\nITEMS (JSON):\n{json.dumps(entries, indent=1)}\n"
    print(f"  judging {len(entries)} items with {model} (no score/priority shown)...", file=sys.stderr)
    raw = run(["claude", "-p", "--model", model], stdin=prompt, timeout=600).strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    arr = json.loads(raw[raw.find("[") : raw.rfind("]") + 1])
    return {v["id"]: v for v in arr}


# --- rank statistics (no scipy dependency) ---


def _ranks(vals: list[float]) -> list[float]:
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    ranks = [0.0] * len(vals)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0  # average rank for ties (1-based)
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _pearson(x: list[float], y: list[float]) -> float:
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(x, y))
    vx = math.sqrt(sum((a - mx) ** 2 for a in x))
    vy = math.sqrt(sum((b - my) ** 2 for b in y))
    return cov / (vx * vy) if vx and vy else 0.0


def spearman(x: list[float], y: list[float]) -> float:
    return _pearson(_ranks(x), _ranks(y))


def kendall_tau(x: list[float], y: list[float]) -> float:
    c = d = tx = ty = 0
    n = len(x)
    for i in range(n):
        for j in range(i + 1, n):
            dx, dy = x[i] - x[j], y[i] - y[j]
            if dx == 0 and dy == 0:
                continue
            if dx == 0:
                tx += 1
            elif dy == 0:
                ty += 1
            elif (dx > 0) == (dy > 0):
                c += 1
            else:
                d += 1
    denom = math.sqrt((c + d + tx) * (c + d + ty))
    return (c - d) / denom if denom else 0.0


def check_ranking(items: list[dict], k: int, model: str) -> dict:
    sample = stratified_sample(items, k)
    verdicts = run_judge(sample, model)
    rows = []
    for i, it in enumerate(sample):
        v = verdicts.get(i)
        if not v:
            continue
        rows.append(
            {
                "ref": f"{it['kind']} #{it['number']}",
                "title": it["title"],
                "score": it["score"],
                "priority": it["priority"],
                "importance": float(v["importance"]),
                "why": v.get("why", ""),
            }
        )
    heur = [r["score"] for r in rows]
    judge = [r["importance"] for r in rows]
    rho, tau = spearman(heur, judge), kendall_tau(heur, judge)

    # mean judge rating per bucket (should rise P3 -> P8)
    by_bucket: dict[str, list[float]] = {}
    for r in rows:
        by_bucket.setdefault(r["priority"], []).append(r["importance"])
    bucket_means = {b: round(sum(v) / len(v), 2) for b, v in by_bucket.items()}

    # biggest rank disagreements (heuristic rank vs judge rank)
    hr = {id(r): rk for r, rk in zip(rows, _ranks(heur))}
    jr = {id(r): rk for r, rk in zip(rows, _ranks(judge))}
    for r in rows:
        r["_rank_gap"] = abs(hr[id(r)] - jr[id(r)])
    disagreements = sorted(rows, key=lambda r: r["_rank_gap"], reverse=True)[:5]

    return {
        "n": len(rows),
        "spearman": round(rho, 3),
        "kendall": round(tau, 3),
        "bucket_mean_importance": bucket_means,
        "disagreements": [
            {"ref": d["ref"], "priority": d["priority"], "score": d["score"], "importance": d["importance"], "why": d["why"]}
            for d in disagreements
        ],
    }


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="Priority Scoring eval")
    ap.add_argument("--corpus", default=str(HERE / "data" / "scored_items.json"))
    ap.add_argument("--report", default=str(HERE / "report.md"))
    ap.add_argument("--tol", type=float, default=0.05, help="score recompute tolerance")
    ap.add_argument("--judge", action="store_true", help="run the LLM ranking eval")
    ap.add_argument("--sample", type=int, default=40, help="items to judge (Part B)")
    ap.add_argument("--model", default="opus")
    ap.add_argument("--out", default="", help="optional path to write JSON scorecard")
    args = ap.parse_args()

    items = json.loads(Path(args.corpus).read_text())
    now = reference_now(Path(args.report))

    print("\n=== Priority Scoring Eval ===")
    print(f"items: {len(items)}   reference now: {now:%Y-%m-%d %H:%M UTC}")

    a = check_formula(items, now, args.tol)
    print("\n[Part A] Formula correctness (deterministic)")
    print(f"  score recompute    : {a['score_matches']}/{a['n']} match (tol {args.tol})")
    if a["score_mismatches"]:
        for m in a["score_mismatches"][:5]:
            print(f"      ✗ {m['ref']}: stored {m['stored']} vs recomputed {m['recomputed']}")
    print(f"  priority bucketing : {a['priority_matches']}/{a['n']} match"
          f"   (real mismatches: {len(a['priority_real_mismatches']) or '—'},"
          f" {a['priority_tie_mismatches']} benign tie-boundary)")
    for m in a["priority_real_mismatches"][:5]:
        print(f"      ✗ {m['ref']}: stored {m['stored']} vs expected {m['expected']} (score {m['score']})")

    scorecard = {"part_a_formula": a}

    if args.judge:
        b = check_ranking(items, args.sample, args.model)
        print(f"\n[Part B] Ranking quality vs LLM PM judge (n={b['n']})")
        print(f"  Spearman ρ (heuristic score vs judge importance): {b['spearman']:+.3f}")
        print(f"  Kendall  τ                                      : {b['kendall']:+.3f}")
        print("  mean judge importance by bucket (should rise P3→P8):")
        order = ["P3", "P4", "P5", "P6", "P7", "P8"]
        print("    " + "  ".join(f"{b_}:{b['bucket_mean_importance'][b_]}" for b_ in order if b_ in b["bucket_mean_importance"]))
        print("  biggest rank disagreements:")
        for d in b["disagreements"]:
            print(f"    • {d['priority']} (score {d['score']}) but judge {d['importance']:.0f}/10 — {d['ref']}: {d['why']}")
        scorecard["part_b_ranking"] = b

    if args.out:
        Path(args.out).write_text(json.dumps(scorecard, indent=2))
        print(f"\nscorecard -> {args.out}", file=sys.stderr)

    # Gate CI on a genuine formula bug (not tie artifacts, not judge correlation).
    return 1 if (a["score_mismatches"] or a["priority_real_mismatches"]) else 0


if __name__ == "__main__":
    sys.exit(main())
