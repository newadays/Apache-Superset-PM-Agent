#!/usr/bin/env python3
"""
Citation Faithfulness eval for the Superset PM Agent.

The agent's prompt tells Claude to "cite item refs" and "tie claims to the data
given". This script audits the generated report against the items that were
actually fed to Claude, in two layers:

  Layer 1 — ref grounding (deterministic, free):
    Every `#NNNNN` cited in the report is classified as
      - grounded     : the ref is among the top-N items fed to Claude
      - not-in-fed   : a real Superset item that was mined but NOT fed (weak —
                       Claude leaned on context it wasn't given)
      - fabricated   : the ref exists nowhere in the corpus (likely hallucinated)

  Layer 2 — claim support (LLM-as-judge, opt-in via --judge):
    For each report line that cites a fed item, judge whether the cited item's
    content actually supports the claim: supported / partial / unsupported.

Inputs are the artifacts a normal run already writes:
  data/prompt.txt        -> the exact items fed to Claude (the "fed" set)
  data/scored_items.json -> the full mined corpus (to tell fabricated from not-fed)
  report.md              -> the report under audit

Usage:
  python3 evals.py                       # Layer 1 only
  python3 evals.py --judge               # + LLM-as-judge claim support
  python3 evals.py --judge --out data/eval_report.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Reuse the agent's hardened `claude` CLI runner for the judge call.
from pm_agent import run

HERE = Path(__file__).resolve().parent
REF_RE = re.compile(r"#(\d{2,})")  # bare refs like (#39682); skips footnote "#1"


# ----------------------------------------------------------------------------
# Loading the fed set + corpus
# ----------------------------------------------------------------------------


def load_fed_docs(prompt_path: Path) -> dict[int, dict]:
    """Parse the JSON array under '## Scored items (JSON)' in the prompt.

    Returns {item_number: {ref, title, excerpt, score, priority, type}}.
    These are precisely the items Claude was given.
    """
    text = prompt_path.read_text()
    start = text.index("## Scored items (JSON)")
    arr_start = text.index("[", start)
    arr_end = text.index("## Your task", arr_start)
    rows = json.loads(text[arr_start:arr_end].strip())
    fed: dict[int, dict] = {}
    for r in rows:
        m = REF_RE.search(r.get("ref", ""))
        if m:
            fed[int(m.group(1))] = r
    return fed


def load_corpus_numbers(corpus_path: Path) -> set[int]:
    """All item numbers mined this run (fed or not) — to separate fabricated
    refs from real-but-not-fed ones."""
    data = json.loads(corpus_path.read_text())
    return {int(d["number"]) for d in data}


# ----------------------------------------------------------------------------
# Layer 1 — deterministic ref grounding
# ----------------------------------------------------------------------------


def audit_refs(report: str, fed: dict[int, dict], corpus: set[int]) -> dict:
    grounded, not_in_fed, fabricated = [], [], []
    for line in report.splitlines():
        # skip the agent's own header/metadata block (priority distribution etc.)
        if line.startswith("_Generated") or line.startswith("Priority scale"):
            continue
        for m in REF_RE.finditer(line):
            n = int(m.group(1))
            if n in fed:
                grounded.append(n)
            elif n in corpus:
                not_in_fed.append(n)
            else:
                fabricated.append(n)
    total = len(grounded) + len(not_in_fed) + len(fabricated)
    return {
        "total_refs_cited": total,
        "unique_refs_cited": len({*grounded, *not_in_fed, *fabricated}),
        "grounded": len(grounded),
        "not_in_fed": sorted(set(not_in_fed)),
        "fabricated": sorted(set(fabricated)),
        "grounding_rate": round(len(grounded) / total, 3) if total else 1.0,
    }


# ----------------------------------------------------------------------------
# Layer 2 — LLM-as-judge claim support
# ----------------------------------------------------------------------------


def extract_claims(report: str, fed: dict[int, dict]) -> list[dict]:
    """Each report line citing >=1 fed item becomes a claim with its sources."""
    claims = []
    for line in report.splitlines():
        clean = line.strip().lstrip("-*| ").strip()
        if not clean:
            continue
        nums = {int(m.group(1)) for m in REF_RE.finditer(clean)}
        fed_nums = [n for n in nums if n in fed]
        if not fed_nums:
            continue
        sources = [
            {
                "ref": fed[n]["ref"],
                "title": fed[n].get("title", ""),
                "excerpt": (fed[n].get("excerpt") or "")[:300],
            }
            for n in fed_nums
        ]
        claims.append({"claim": clean, "sources": sources})
    return claims


JUDGE_SYSTEM = """You audit a Product Manager report's citations against the \
source GitHub items it cites. For each entry, decide whether the CLAIM is \
supported by its cited SOURCE item(s).

Labels:
- supported   : the source item(s) clearly back the claim
- partial     : related, but the claim overstates or embellishes the source
- unsupported : the source does not back the claim, or it is misattributed

Return ONLY a JSON array, one object per entry, no prose:
[{"i": <index>, "label": "supported|partial|unsupported", "why": "<=15 words"}]"""


def run_judge(claims: list[dict], model: str) -> list[dict]:
    entries = [
        {"i": i, "claim": c["claim"], "sources": c["sources"]}
        for i, c in enumerate(claims)
    ]
    prompt = (
        f"{JUDGE_SYSTEM}\n\nENTRIES (JSON):\n{json.dumps(entries, indent=1)}\n"
    )
    print(f"  judging {len(entries)} cited claims with {model}...", file=sys.stderr)
    raw = run(["claude", "-p", "--model", model], stdin=prompt, timeout=600).strip()
    # tolerate ```json fences
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    start, end = raw.find("["), raw.rfind("]")
    verdicts = json.loads(raw[start : end + 1])
    by_i = {v["i"]: v for v in verdicts}
    out = []
    for i, c in enumerate(claims):
        v = by_i.get(i, {"label": "unsupported", "why": "no verdict returned"})
        out.append({**c, "label": v.get("label"), "why": v.get("why")})
    return out


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="Citation Faithfulness eval")
    ap.add_argument("--report", default=str(HERE / "report.md"))
    ap.add_argument("--prompt", default=str(HERE / "data" / "prompt.txt"))
    ap.add_argument("--corpus", default=str(HERE / "data" / "scored_items.json"))
    ap.add_argument("--judge", action="store_true", help="run the LLM-as-judge layer")
    ap.add_argument("--model", default="opus")
    ap.add_argument("--out", default="", help="optional path to write JSON scorecard")
    args = ap.parse_args()

    report = Path(args.report).read_text()
    fed = load_fed_docs(Path(args.prompt))
    corpus = load_corpus_numbers(Path(args.corpus))

    layer1 = audit_refs(report, fed, corpus)

    print("\n=== Citation Faithfulness ===")
    print(f"fed items: {len(fed)}   corpus: {len(corpus)}")
    print("\n[Layer 1] Ref grounding")
    print(f"  refs cited        : {layer1['total_refs_cited']} ({layer1['unique_refs_cited']} unique)")
    print(f"  grounding rate    : {layer1['grounding_rate']:.1%} (cited & in fed set)")
    print(f"  not-in-fed (weak) : {layer1['not_in_fed'] or '—'}")
    print(f"  FABRICATED        : {layer1['fabricated'] or '—'}")

    scorecard = {"layer1_ref_grounding": layer1}

    if args.judge:
        claims = extract_claims(report, fed)
        verdicts = run_judge(claims, args.model)
        counts: dict[str, int] = {}
        for v in verdicts:
            counts[v["label"]] = counts.get(v["label"], 0) + 1
        n = len(verdicts) or 1
        print("\n[Layer 2] Claim support (LLM-as-judge)")
        print(f"  claims judged     : {len(verdicts)}")
        for label in ("supported", "partial", "unsupported"):
            print(f"  {label:13s} : {counts.get(label, 0)} ({counts.get(label, 0)/n:.0%})")
        print(f"  support rate      : {counts.get('supported', 0)/n:.1%}")
        weak = [v for v in verdicts if v["label"] != "supported"]
        if weak:
            print("\n  flagged claims:")
            for v in weak:
                refs = ", ".join(s["ref"] for s in v["sources"])
                print(f"   • [{v['label']}] {v['why']}  ({refs})")
                print(f"       claim: {v['claim'][:120]}")
        scorecard["layer2_claim_support"] = {"counts": counts, "verdicts": verdicts}

    if args.out:
        Path(args.out).write_text(json.dumps(scorecard, indent=2))
        print(f"\nscorecard -> {args.out}", file=sys.stderr)

    # Exit non-zero if anything looks fabricated, so this can gate CI.
    return 1 if layer1["fabricated"] else 0


if __name__ == "__main__":
    sys.exit(main())
