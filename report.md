# Apache Superset — PM Signal Report

_Generated 2026-05-26 19:56 UTC • 250 issues + 120 discussions analyzed • top 70 fed to Claude (opus)_

Priority scale: **P8 = highest, P3 = lowest.** Priority distribution across corpus: `{"P5": 85, "P8": 12, "P3": 104, "P7": 25, "P6": 45, "P4": 99}`

---

## 1. Executive summary

- **Sentiment is dominated by deployment friction, not the product itself.** The single highest-scored cluster is Helm/Kubernetes packaging — the `psycopg2`-missing breakage (issue #31026, P8, 19👍/25💬), the unpublished/broken charts (issue #38456, issue #35461, issue #35174), and the unmet demand for a 6.0.0-compatible chart (discussion #36763, 28👍). New users cannot get a working install, which poisons first impressions.
- **The 6.0.0 release (Dec 18, 2025) is generating a regression tail.** Multiple high/medium items are explicitly tagged `#bug:regression` against 6.0.0/6.1.0: broken embedding (issue #39682), JWT admin list returning `count:0` (issue #39834), Time-series Table sorting (issue #37892), remote-user auth (issue #36117), and MCP user resolution (issue #40225). These are upgrade-blockers for existing production users.
- **Charting/viz correctness is a steady, broad source of pain** — wrong stacked-bar totals (issue #33882), forecast intervals clipped at zero (issue #21734), pivot subtotal math (issue #32260), tooltip format regressions (issue #33757), plus a long tail of cosmetic/layout bugs.
- **Latent demand centers on governance & lifecycle**: a wave of SIPs for version history, archiving, and soft-delete (issue #33044, issue #36145, issue #39492, issue #39464, issue #37427) signals enterprise users want safety nets around assets.
- **Biggest single action:** stand up a reliable, published Helm chart for 6.x with `psycopg2` bundled (or documented) and fix the 6.0.0 auth/embedding regressions. This unblocks both new installs and the existing base trying to upgrade — the two largest, most acute pools of frustration.

## 2. Top pain points

| Theme | What users hit | Refs |
|---|---|---|
| **Helm / K8s install broken** | `psycopg2` not in lean image breaks upgrades & fresh installs; charts released but not published; no 6.x chart | issue #31026, discussion #31431, issue #35174, issue #38456, issue #35461 |
| **6.0.0 upgrade regressions** | Embedding/guest-token 403s, JWT admin sees empty lists, remote-user auth broken, table sort broken, MCP auth broken | issue #39682, issue #39834, issue #36117, issue #37892, issue #40225, issue #38806 |
| **Charting correctness** | Stacked-bar totals wrong, forecast intervals clipped, pivot % subtotals wrong, tooltip ignores format, last month missing on axis | issue #33882, issue #21734, issue #32260, issue #33757, issue #33905 |
| **DB-engine SQL generation** | Oracle positional GROUP BY, Snowflake boolean `IS true`, ClickHouse calc-columns/numeric casts, multi-space field names | issue #35414, issue #33235, issue #34784, issue #39951, issue #32879 |
| **Filters & drill-down** | Clear-all breaks required time filter, dependent-filter stale values, numeric precision filtering, drill-to-detail date SQL | issue #33361, issue #24511, issue #33206, issue #36776 |
| **Export / image rendering** | Chart image export fails or freezes UI ~6s; PDF reports clipped | issue #28713, issue #38926, issue #39965 |
| **Cosmetic/layout polish** | Inconsistent chart padding, double scrollbars, treemap tooltip, heatmap clipping, filter dropdown overlap | issue #31033, issue #35833, issue #33896, issue #33737, issue #34135 |

## 3. Top feature asks

| Rank | Ask | Signal | Refs |
|---|---|---|---|
| 1 | **Download drill-to-detail records** | 34👍/24💬 — high, sustained | discussion #27607 |
| 2 | **Asset version history / restore / archive / soft-delete** (governance cluster) | 5 active SIPs | issue #33044, issue #36145, issue #39492, issue #39464, issue #37427 |
| 3 | **Semantic layer support** | SIP-182, 23👍 | issue #35003 |
| 4 | **Suppress "force refreshing" toast** | 16👍/20💬, long-standing | discussion #18451 |
| 5 | **Markdown `target="_blank"` links** | 13👍, low effort | discussion #31982 |
| 6 | **Sort categorical x-axis by custom order/metric** | 9👍 | discussion #30575 |
| 7 | **Frontend re-architecture (Zustand + TanStack Query)** | SIP-207 | issue #39209 |
| 8 | **Browser-native PDF reports** | SIP-212 | issue #39965 |

## 4. Cross-cutting themes

1. **Deployment & packaging (Helm/K8s)** — The most acute and highest-scored theme. Driven by the lean image dropping `psycopg2`, broken/unpublished charts, Bitnami deprecation, and no 6.x chart. Blocks both new and upgrading users. *Refs:* issue #31026, discussion #31431, issue #35174, issue #38456, issue #35461, discussion #36763.

2. **6.0.0 release-quality / regression containment** — A concentrated tail of regressions correlated directly with the Dec 2025 6.0.0 release and 6.1.0 (May 2026). Auth/embedding and API regressions are the most damaging. *Refs:* issue #39682, issue #39834, issue #36117, issue #37892, issue #40225, issue #38806, issue #39951.

3. **Auth, RBAC & embedding** — Guest-token/embedding 403s, JWT admin list emptiness, remote-user auth, role-permission dropdown, public-dashboard login leak. Enterprise-blocking. *Refs:* issue #39682, issue #31872, issue #39834, issue #36117, issue #39967, issue #32836, issue #40225.

4. **Charting & query correctness** — Wrong numbers and bad SQL erode trust in the core product. Spans viz math and DB-engine SQL generation. *Refs:* issue #33882, issue #21734, issue #32260, issue #33757, issue #35414, issue #33235, issue #34784, issue #39951.

5. **Asset governance & lifecycle** — The dominant *feature* narrative: version history, archive, soft-delete, git-backed datasets. Strong enterprise pull, currently fragmented across overlapping SIPs. *Refs:* issue #33044, issue #36145, issue #39492, issue #39464, issue #37427.

6. **Export & reporting fidelity** — Image export reliability/perf and document-grade PDF output. *Refs:* issue #28713, issue #38926, issue #39965, discussion #27607.

## 5. Prioritized backlog (P8 → P3)

### P8 — Drop everything
| Finding | Rationale | Refs | PM action |
|---|---|---|---|
| **Helm/K8s install is broken & no 6.x chart** | Highest-scored cluster; blocks new installs AND upgrades; reputational | issue #31026, discussion #31431, issue #38456, issue #35461, issue #35174, discussion #36763 | Bundle/document `psycopg2`; fix the publish pipeline; ship & publish a 6.x chart this cycle. Single owner, dated milestone. |
| **6.0.0 embedding broken (regression)** | Was working in 4.1.4; guest-token 403; embed is a flagship enterprise use case | issue #39682, issue #31872 | Hotfix into 6.1.x; add embedding to release regression suite. |
| **Drill-to-detail download** | Top feature by engagement (34👍); recurring | discussion #27607 | Scope as near-term feature; pairs with export theme. |
| **Semantic layer (SIP-182)** | Strategic, high-engagement direction-setter | issue #35003 | Drive SIP to a vote; confirm 6.x roadmap slot. |

### P7 — High priority this cycle
| Finding | Rationale | Refs | PM action |
|---|---|---|---|
| **6.0.0/6.1.0 auth & API regressions** | JWT admin empty lists, remote-user auth, MCP auth — block upgrades for SSO/API users | issue #39834, issue #36117, issue #40225, issue #38806 | Bundle into a "6.x upgrade-blocker" workstream; backport fixes. |
| **Table/viz regressions in 6.0.0** | Time-series table sort broken; data display | issue #37892 | Quick win (`good first issue`); patch release. |
| **Asset governance SIP cluster** | 4 overlapping SIPs = clear demand but fragmented | issue #33044, issue #36145, issue #39492, issue #39464, issue #37427 | Consolidate into one version-history+archive initiative; pick one SIP as canonical, fold others. |
| **Charting correctness (visible wrong numbers)** | Stacked-bar totals, tooltip format, forecast intervals | issue #33882, issue #33757, issue #21734 | Batch into a "viz correctness" sprint. |
| **DB-engine SQL generation** | Oracle/Snowflake/MSSQL query failures lose those user segments | issue #35414, issue #32879 | Triage by engine; assign to DB-spec owners. |

### P6 — Important, schedule soon
| Finding | Rationale | Refs | PM action |
|---|---|---|---|
| **Filter/drill-down correctness** | Clear-all breaks required filters; stale dependent values; precision filtering | issue #33361, issue #24511, issue #33206, issue #36776 | Group as native-filters reliability epic. |
| **ClickHouse data/SQL issues** | Calc columns, numeric cast regressions | issue #34784, issue #39951 | Engine-specific fix + regression test. |
| **Export reliability & PDF reports** | Image export fails/freezes UI; SIP-212 for real PDFs | issue #28713, issue #38926, issue #39965 | Fix freeze bug now; review SIP-212 for next cycle. |
| **Jinja/templating edge cases** | ORDER BY rendering, multi-param cache miss | issue #29378, issue #34543 | Backlog with owner. |
| **Frontend re-architecture (SIP-207)** | Large strategic refactor; needs sequencing | issue #39209 | Architectural review; gate behind release planning. |
| **User-delete IntegrityError (MariaDB)** | 6.0.0 data-integrity bug | issue #38629 | Fix FK cleanup in patch. |

### P5 — Quality-of-life & smaller bugs
| Finding | Rationale | Refs | PM action |
|---|---|---|---|
| **High-demand small features** | Low-effort, high-goodwill | discussion #18451 (force-refresh toast), discussion #31982 (`target="_blank"`), discussion #30575 (custom x-axis sort) | Bundle as a "community quick wins" batch. |
| **Trino/Deck.gl data gaps** | Data preview & GeoJSON rendering | issue #25307, issue #34748, issue #20459 | Triage; assign to viz/data owners. |
| **Misc config/infra bugs** | Config attr resolution, sqlglot build, async 422, i18n 404 | issue #34422, issue #38310, issue #37114, issue #35581 | Backlog, batch triage. |

### P4 — Polish / cosmetic
| Finding | Rationale | Refs | PM action |
|---|---|---|---|
| **Cosmetic & layout bugs** | Many flagged `good first issue` / `#bug:cosmetic` | issue #31033, issue #35833, issue #33896, issue #33737, issue #34135, issue #26254 | Curate a `good first issue` sprint for new contributors. |
| **SQL Lab error UX** | Confusing metadata/parse errors | issue #34997, issue #34130 | Improve error messaging. |

### P3 — Backlog / process
| Finding | Rationale | Refs | PM action |
|---|---|---|---|
| **API naming / minor debt** | `supersetCanCSV` rename, dataset name disambiguation | issue #24290, discussion #18477 | Backlog; address opportunistically (breaking-change care). |
| **Contributor/AI-PR policy** | Community process, not product | discussion #39784 | Hand to maintainers/governance, not product backlog. |

---
**Note on release correlation:** The P7/P6 regression items (embedding, auth, table sort, ClickHouse, user-delete) cluster tightly around the **6.0.0 (2025-12-18)** and **6.1.0 (2026-05-13)** releases — a 6.x stabilization track should be treated as a coherent program rather than scattered bug fixes.
