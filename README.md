# Superset PM Agent

A small product-management (PM) agent that mines GitHub signal from
[apache/superset](https://github.com/apache/superset), scores it for priority,
and uses **Claude (opus)** to synthesize an executive PM report of the top pain
points, feature asks, and themes — ordered **P8 (highest) → P3 (lowest)**.

## What it does

1. **Pulls data** from `apache/superset`:
   - recent **releases** (`/releases`)
   - **open issues** via the search API (`is:issue`, sorted by recent activity — PRs excluded server-side)
   - **discussions** via the GraphQL API (sorted by recent activity)
2. **Scores** every issue/discussion with a transparent heuristic:
   - engagement: `reactions×3 + comments×1.5`, log-dampened so viral outliers don't dominate
   - recency: exponential decay (75-day half-life on last-activity date)
   - type weight: bugs ×1.20, features ×1.00, questions ×0.85
   - items are bucketed by percentile into **P8…P3**
3. **Synthesizes** a Markdown report by feeding the top-N scored items + release
   list to Claude opus (via the `claude` CLI, headless `-p` mode).

## Requirements

- [`gh`](https://cli.github.com/) CLI, authenticated (`gh auth status`)
- [`claude`](https://claude.com/claude-code) CLI, logged in (used for the opus call — no API key needed)
- Python 3.10+

## Usage

```bash
python3 pm_agent.py                          # defaults: 250 issues, 120 discussions, top 70
python3 pm_agent.py --issues 300 --discussions 200 --top 90
python3 pm_agent.py --skip-llm               # fetch + score only, no report
python3 pm_agent.py --model opus --out report.md
```

## Outputs

| Path | Contents |
|---|---|
| `report.md` | The final PM report (P8 → P3). |
| `data/scored_items.json` | Every fetched item with its score + priority (audit trail). |
| `data/releases.json` | Raw release metadata. |
| `data/prompt.txt` | The exact prompt sent to Claude. |

## Tuning

Scoring weights live at the top of the *Scoring* section in `pm_agent.py`
(`W_REACTION`, `W_COMMENT`, `TYPE_WEIGHT`, `RECENCY_HALFLIFE_DAYS`) and the
`PRIORITY_PERCENTILES` table. They're intentionally simple so a PM can audit and
adjust them.
