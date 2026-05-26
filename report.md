# Apache Superset — PM Signal Report

_Generated 2026-05-26 17:23 UTC • 250 issues + 150 discussions analyzed • top 70 fed to Claude (opus)_

Priority scale: **P8 = highest, P3 = lowest.** Priority distribution across corpus: `{"P5": 92, "P8": 12, "P3": 112, "P7": 28, "P6": 48, "P4": 108}`

---

## 1. Executive Summary

- **Deployment is the #1 source of pain.** Four of the eleven P8 items are Helm/Kubernetes blockers, and the chart is **stuck on appVersion 5.0.0 five months after 6.0.0 shipped** (#36763, #38456). Users cannot officially deploy the current release — this is the single most important thing to fix next.
- **6.0.0 introduced a cluster of regressions** now surfacing in production: embedding/guest-token auth broke (#39682), remote-user auth broke (#36117), time-series table sorting broke (#37892), plus ClickHouse/Oracle query regressions (#39951, #35414). The 6.x upgrade path is the dominant theme in recent (low `days_old`) bug reports.
- **The new MCP service is shipping bugs**, with auth/context failures in both 6.1.0 and 6.1.0rc1 (#40225, #38806) — a young feature that needs hardening before it's trusted.
- **Latent demand is concentrated in data governance**: five separate SIPs ask for versioning/archiving/soft-delete (#33044, #36145, #39492, #39464, #37427). This is a clear roadmap signal the community is converging on independently.
- **Charting correctness** (not just cosmetics) is a steady drip of trust-eroding bugs — wrong stacked-bar totals (#33882), tooltip format ignored (#33757), pivot subtotals wrong (#32260). These quietly undermine confidence in the numbers.
- **Sentiment**: operators are frustrated (deployment + upgrade friction); analysts hit nagging chart/filter bugs; the contributor community is actively proposing strategic direction (semantic layer, versioning). Stabilize 6.x and unblock Helm, then invest in governance features.

---

## 2. Top Pain Points

### Theme A — Helm/K8s deployment is broken or stale *(highest aggregate pain)*
| Ref | Issue | Signal |
|---|---|---|
| #31026 (P8) | psycopg2 no longer bundled in lean image, breaks upgrade | 19👍 / 25💬 |
| #31431 (P8) | `ModuleNotFoundError: psycopg2` on k8s install | 13👍 / 16💬 |
| #36763 (P8) | Helm chart still on 5.0.0, no 6.0.0 support | 28👍 |
| #38456 (P8) | 6.0.0 Helm chart not available / not published | 26👍 |
| #35461 (P6) | 0.15.1 released but never published (Bitnami deprecation) | — |
| #35174 (P7) | Helm 0.15.0 broken with bring-your-own-DB | — |
| #25825 (P7) | Example data loads into single pod only | 38💬 |
| #38310 (P6) | Build fails on sqlglot incompatibility | — |

**Root causes:** missing DB driver in lean image, and a broken/stalled chart publishing pipeline (Bitnami repo deprecation, #35461). High reaction counts = many silent sufferers.

### Theme B — 6.0.0 upgrade regressions
| Ref | Area | Note |
|---|---|---|
| #39682 (P8) | Embedding/guest token → 403 | regression label, 19💬 |
| #36117 (P7) | `AUTH_REMOTE_USER` broke vs 5.0.0 | reverted to 5.0.0 |
| #37892 (P7) | Time-series table sorts only first column | regression |
| #35414 (P7) | Oracle positional `GROUP BY` fails | 6.0rc2 |
| #39951 (P6) | ClickHouse "could not convert string to numeric" | regression |
| #34784 (P6) | Calculated column generates wrong SQL (ClickHouse) | — |
| #36776 (P6) | Drill-to-detail by date wrong SQL (ClickHouse) | — |

### Theme C — MCP service instability (new in 6.x)
- #40225 (P7): MCP user resolution fails in **6.1.0** (Keycloak/JWT). #38806 (P7): Flask app-context error in **6.1.0rc1**. Both block the headline new capability.

### Theme D — Charting correctness & cosmetics
- **Correctness (erodes trust):** #33882 stacked-bar totals, #33757 tooltip format ignored, #32260 pivot subtotal math, #21734 forecast interval clipping, #20459 deck.gl color mismatch.
- **Cosmetic/layout:** #31033 chart padding, #35833 double scrollbar, #33896 treemap tooltip, #26254 bar spillover, #33737 heatmap cutoff (several tagged *good first issue*).

### Theme E — SQL Lab & data connectivity friction
- #34997 (P7) table metadata fetch fails, #34130 (P7) "database could not be found", #25307 (P8) Trino/Iceberg preview, #32879 (P7) multi-space field names, #33235 (P7) Snowflake boolean filter SQL, #29378/#37114 Jinja edge cases.

### Theme F — Filters UX
- #33361 (P7) "Clear All Filters" breaks required time filter, #24511 (P6) stale dependent-filter values, #34135 (P6) dropdown obscured on small screens, #33206 (P6) numeric precision filtering.

---

## 3. Top Feature Asks

| Ref | Ask | Demand signal |
|---|---|---|
| #27607 (P8) | **Download records from Drill-to-detail** | 34👍 / 24💬 — strongest single feature |
| #35003 (P8) | **SIP-182 Semantic Layer support** | 23👍, strategic |
| #18451 (P8) | Disable "force refreshing" toast | 16👍 / 20💬 |
| #33044 / #36145 / #39492 / #39464 / #37427 | **Versioning / archive / soft-delete / git-backed datasets** | 5 SIPs, converging demand |
| #39965 (P7) | SIP-212 Browser-print PDF reports | fixes screenshot-PDF limits |
| #31982 (P7) | `target="_blank"` in Markdown links | 13👍 |
| #30575 (P6) | Sort categorical x-axis by another variable | 9👍 |
| #22836 (P6) | Native filters → annotation layers | 10👍 |
| #39209 (P6) | SIP-207 Redux → Zustand/TanStack (frontend health) | tech-debt |

---

## 4. Cross-Cutting Themes

| Theme | What's driving it | Item refs |
|---|---|---|
| **Deployment / Helm** | Chart stuck on 5.0.0; broken publishing pipeline; missing DB drivers in lean image. Blocks adoption of current release. | #31026, #31431, #36763, #38456, #35461, #35174, #25825, #38310, #34422 |
| **6.x Upgrade Stability** | Multiple regressions across auth, tables, and DB engines tied directly to 6.0.0. | #39682, #36117, #37892, #35414, #39951, #34784, #36776, #34998 |
| **Auth / RBAC / Embedding** | Guest-token, remote-user, JWT, and permission-UI failures — several are regressions. | #39682, #36117, #31872, #39834, #39967, #32836, #40225 |
| **Data Governance & Versioning** | Independent, repeated SIPs for archive/version/restore/soft-delete. Clear roadmap convergence. | #33044, #36145, #39492, #39464, #37427 |
| **Charting Correctness** | Wrong totals/formats/forecasts silently undermine trust in dashboards. | #33882, #33757, #32260, #21734, #20459, #33905 |
| **Export / Reporting** | Download gaps + perf (UI freeze) + document-quality PDF. | #27607, #28713, #38926, #39965, #24290 |
| **MCP Maturity** | New AI-integration service failing on auth/context in current releases. | #40225, #38806 |

---

## 5. Prioritized Backlog (P8 → P3)

### 🔴 P8 — Drop everything
| Finding | Rationale | Refs | PM Action |
|---|---|---|---|
| **Publish & fix the 6.x Helm chart** | Current release is undeployable via official chart 5 months post-GA; highest reactions in corpus. | #36763, #38456, #35461, #31026, #31431 | Treat as release-blocker. Fix publishing pipeline (Bitnami dependency), restore psycopg2 in lean image, ship `appVersion: 6.1.0`. Communicate timeline publicly. |
| **6.0.0 embedding/auth regression** | Production embedding broke on upgrade (403). Auth regressions block enterprise upgrades. | #39682, #36117 | Hotfix into 6.1.x patch; add guest-token + remote-user regression tests to CI. |
| **Drill-to-detail download** | #1 feature by engagement; small scope, high satisfaction. | #27607 | Scope as a fast-follow win; commit to a 6.x minor. |
| **SIP-182 Semantic Layer** | Strategic platform direction; active SIP. | #35003 | Drive SIP to vote; align with versioning roadmap. |

### 🟠 P7 — High priority this cycle
| Finding | Rationale | Refs | PM Action |
|---|---|---|---|
| **6.x regression sweep** | Cluster of upgrade-induced breakage across tables & DB engines. | #37892, #35414, #34998 | Open a "6.x regression" tracking epic; prioritize by reaction/install share. |
| **MCP hardening** | Headline AI feature failing on auth in 6.1.0. | #40225, #38806 | Bug-bash MCP auth/context before promoting MCP in marketing. |
| **Data-governance SIPs** | Converging community demand for versioning/archive. | #33044, #36145, #39492 | Consolidate overlapping SIPs into one roadmap thread to avoid fragmentation; pick a lead design. |
| **SQL Lab / connectivity reliability** | Repeated metadata/connection failures block core workflow. | #34997, #34130, #25307, #32879, #33235 | Triage as reliability epic; many are engine-specific. |
| **Filter UX correctness** | "Clear all filters" breaks dashboards. | #33361 | Fix required-filter handling; quick trust win. |
| **PDF reports / export** | Document-quality reporting gap. | #39965, #28713 | Advance SIP-212; pair with export-image perf fix. |

### 🟡 P6 — Important, schedule deliberately
| Finding | Rationale | Refs | PM Action |
|---|---|---|---|
| **Auth/RBAC API regressions** | JWT admin returns count:0; permission UI broken in 6.1.0rc. | #39834, #39967 | Verify fixed before 6.1.0 GA promotion. |
| **ClickHouse SQL generation bugs** | Multiple wrong-SQL reports for a popular engine. | #39951, #34784, #36776 | Group as ClickHouse engine-spec hardening. |
| **Charting correctness bugs** | Wrong numbers in stacked bars/pivots/tooltips. | #33882, #33757, #32260, #21734 | Batch into a "viz correctness" sprint; higher trust impact than cosmetics. |
| **Frontend state refactor (SIP-207)** | Long-term maintainability. | #39209 | Keep as architectural track; gate behind regression risk review. |
| **Export performance** | 6s UI freeze on image download. | #38926 | Move rendering off main thread. |
| **Filter/data edge cases** | Dependent filters, numeric precision, jinja. | #24511, #33206, #29378, #37114 | Backlog with good-first-issue tagging. |

### 🟢 P5 — Targeted improvements *(no items scored explicitly P5; folding adjacent low-impact UX here)*
| Finding | Rationale | Refs | PM Action |
|---|---|---|---|
| **Sorting & axis flexibility** | Common analyst ask, moderate demand. | #30575, #33905 | Bundle into charting backlog. |
| **Markdown link target** | Small, well-understood fix. | #31982 | Tag good-first-issue. |

### ⚪ P4 / P3 — Backlog & polish
| Finding | Rationale | Refs | PM Action |
|---|---|---|---|
| **Cosmetic chart/layout bugs** | Low severity, good first issues. | #31033, #35833, #33896, #26254, #33737 | Route to community contributors. |
| **API naming / minor cleanups** | Nice-to-have, breaking-change risk. | #24290 | Defer to next major. |
| **Environment / questions** | M1 Mac support recurring question; mostly resolved by multi-arch images. | #20271 | Doc fix / FAQ, not eng work. |
| **Latent niche features** | Low-frequency asks. | #18477, #22836 | Keep open, watch for upvotes. |

---

### Note on signal quality
Several high-`days_old` items (#20459 1435d, #18451 1922d) carry P8 by engagement but are *aged latent demand*, not active fires — distinguish from recent regressions (#39682 29d, #40225 8d) which are **fresh, release-correlated, and should outrank them operationally**. The scoring rewards reactions; the 6.x regressions have low reaction counts only because they're new — weight them up.
