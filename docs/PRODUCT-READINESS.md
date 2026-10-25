# Product readiness and V2 roadmap

**Canonical authority:** this document is the sole product-level readiness and overall V2 roadmap authority.

**Owner:** project maintainer. **Updated:** 2026-10-24, Pacific.
This is the only product roadmap. Source readiness belongs in
[source-status.json](source-status.json); current frontend instructions belong
in [frontend/README.md](frontend/README.md). [ETHICS.md](ETHICS.md) governs data work.

V2 is the product. Application version `2.0.0` comes from the Rust crate.
Datasets use release dates, not application versions. Earlier v0/v1 names refer
to datasets; legacy V1 refers to the original website.

## Current state

The product is running at <https://untileverycage.onrender.com/>.
The original website has not been replaced. Existing dataset approvals are
complete; do not request another generic approval stamp.

| Area | Last verified state |
| --- | --- |
| Current dataset | `release-2026-10-18`: 69,220 records, 53,107 mapped, 16,113 unmapped, 14 sources |
| Historical v0 | Still accessible; current restrictions leave 63,421 records and 48,576 mapped locations |
| Map and database | Clustering, category PNG pins, approximate locations, search/filters, full facility pages, CSV and paginated API |
| Map views | Street/Satellite and native 2D/3D terrain; camera and release context survive navigation |
| Public graph | Selected serving projection has 60,263 connections: 23,874 exact and 36,389 inferred; 1,420 cross-source edges across 14 endpoint sources |
| Real graph check | Known FSIS/Tyson case returns 38 distinct neighbors; bounded hosted API acceptance passed, not a complete graph crawl |
| Contributions | Five record-contribution forms and separate bug-report intake implemented; final operating/retention handoff remains part of cutover |
| Frontend repair | Requested navigation, concise copy, About counter, control alignment, full-record links and empty Connections state deployed |
| Languages and themes | English/Spanish primary UI and persistent light/dark preferences implemented; some secondary community/operator and generated API text remains English |
| Cluster persistence | Point-feed caching exists; persistent reuse of the built cluster index is not implemented |

The table describes integrated product behavior. Hosting uses the existing
Render service and manual deployment from `eli/v2` after CI. The language,
theme and APHIS sprint does not change dataset membership, the serving
database or the domain. Exact CI/deployment identifiers and hosted acceptance
are recorded with the aggregate acceptance receipt below.

Aggregate acceptance is retained locally in ignored
`data/staging/launch-fidelity-20261024/acceptance.json`.
The current language/theme/APHIS acceptance is retained in ignored
`data/staging/launch-aphis-language-theme-20261025/acceptance.json`.
The source inventory owns graph package/runtime details and source-specific evidence.

## Launch gates

All items below remain required before replacing the original website.

| Work | State | Done when |
| --- | --- | --- |
| Documentation consolidation | Complete | 46 obsolete/duplicate documents removed; one current roadmap/source inventory/frontend guide; local links and 28 documentation-contract checks passed; no application code changed |
| Persistent cluster index | Deferred from the current sprint | Reload reuses the built index, with release/profile/manifest/restriction invalidation; cached point bytes alone do not qualify |
| Languages | Spanish primary UI implemented and locally tested | Remaining German, French, Italian, Dutch and Danish use the same system; complete remaining English fallbacks; routes, filters and selection survive switching; source evidence stays in its original language |
| Light/dark interface | Implemented; local visual acceptance passed after mobile spacing correction | Persistent preferences, readable controls/panels and unchanged basemap/category semantics; retain browser regression coverage |
| France, broader Spain, Germany, Mexico | Incomplete | Actual missing coverage acquired, normalized, enriched where needed and verified on the map; an adapter or an existing Catalonia refresh is not new national coverage |
| APHIS history | Reliability and on-demand historical recovery implemented | Six real endpoint cases passed locally: two eligible facilities return pre-2025 annual and inspection links, sampled PDFs open, and the original no-report case returns an empty page; sample history reaches 2014, not a complete archive audit |
| New default dated dataset | Not started | Fresh acquisition and required location enrichment for included cohorts, measured map membership/counts, retained history and current restrictions |
| Final cutover | Not started | Maintainer frontend/data acceptance; verified monitoring, recovery and contribution operations; domain/canonical/redirect checks and rollback |

Country implementation and UI features may run in independent lanes. Do not
start another general backend overhaul or graph-expansion sprint in place of
these launch requirements.

## Coverage: what the recent work did not deliver

The latest Catalonia work made a fresh refresh/import plus separate locality
enrichment and private map acceptance repeatable. It did not add broader
Spanish coverage or publish more locations. Its resulting candidate count is
not an additive increase to the existing dataset. Follow the exact run and
counts in [the source inventory](source-status.json), not copied sprint totals.

France still has source-specific location work, including an unresolved ICPE
coordinate-reference question. Germany and Mexico have acquisition/access and
source-mapping work. Inspect the source inventory and country research before
promising counts or dates. Compare intended recovery with the original V1
sources; do not silently count legacy rows as newly acquired data.

## Roadmap

1. Documentation cleanup is complete.
2. Ship and retain APHIS report recovery, Spanish, and light/dark mode without
   redesigning approved frontend behavior. Persistent cluster reuse is deferred
   from this sprint; the remaining launch languages still need translation.
3. Next, deliver missing country coverage through source-specific lanes using
   the existing shared runner and separate enrichment jobs; extend languages
   through the same translation system.
4. Build the new dated launch dataset; preserve current and historical releases.
5. Complete the maintainer pass and production handoff, then switch the domain.

Countries and source coverage are not guaranteed merely by registration.
Do not add a country by publishing unverified geometry or calling a small
regional source national coverage. No percentage-complete estimate is used.

## After launch

Preserve these ideas without treating them as current implementation:

- More countries and source families through the shared adapter/refresh path.
- Improved accessible pin artwork; category palette changes only with approval.
- Heatmaps, activity/coverage layers, globe view and map-drawn relationship edges.
- Richer graph visualization and multi-hop exploration.
- Historical imagery and optional panorama providers where available.
- Broader evidence/event/organization pages, source documents and record timelines.
- Community dataset publication and contributor accounts if actual use warrants
  them; intake alone does not publish submissions.
- Scale-story experiments and deeper performance work when measurements justify them.

## Evidence and update rules

Update current facts in place with the relevant integrated change. Link a
commit, aggregate receipt or test result for completion claims; distinguish
local implementation, hosted behavior and published data. Do not append sprint
history or reopen completed approvals. Past plans and checkpoints are in Git.

### D6.2 — Backend architecture closure and contract freeze

D6.2 integration froze major backend redesign while allowing source additions
and measured maintenance. The historical 5,000 probabilistic-candidate analysis
was not a storage cap. Human adjudication is not a graph connection state or a prerequisite
for exact/inferred edge persistence. These retained contract invariants do not
override the current launch checklist.
