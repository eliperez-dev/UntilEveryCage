# Product readiness and V2 roadmap

**Canonical authority:** this document is the sole product-level readiness and overall V2 roadmap authority.

**Owner:** project maintainer. **Updated:** 2026-10-25, Pacific.
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
Render service and manual deployment from `eli/v2` after CI. The latest UI
consistency and source-readiness work does not change dataset membership, the serving
database or the domain. Exact CI/deployment identifiers and hosted acceptance
are recorded with the aggregate acceptance receipt below.

Aggregate acceptance is retained locally in ignored
`data/staging/launch-fidelity-20261024/acceptance.json`.
The current UI/source acceptance is retained in ignored
`data/staging/launch-ui-source-readiness-20261025/acceptance.json`.
The subsequent country/compact-UI integration, CI and hosted verification are
recorded in ignored `data/staging/launch-country-polish-20261025/acceptance.json`;
read its actual CI/deploy state rather than assuming local verification is hosted.
The source inventory owns graph package/runtime details and source-specific evidence.

## Launch gates

All items below remain required before replacing the original website.

| Work | State | Done when |
| --- | --- | --- |
| Documentation consolidation | Complete | 46 obsolete/duplicate documents removed; one current roadmap/source inventory/frontend guide; local links and 28 documentation-contract checks passed; no application code changed |
| Persistent cluster index | Deferred from the current sprint | Reload reuses the built index, with release/profile/manifest/restriction invalidation; cached point bytes alone do not qualify |
| Languages | Generated Spanish facility labels and activities repaired; hosted verification belongs to the current acceptance receipt | Preserve source names, original classifications and attribution. Remaining German, French, Italian, Dutch and Danish use the same system; routes, filters and selection survive switching. Secondary API/community text is not fully translated |
| Light/dark interface and map controls | FAQ repairs, zoom-9 default and Tools relocation integrated and locally tested; real-data selection passed; CI/deployment verification remains separate | Readable FAQ links in both themes and complete English/Spanish sentences. Street/Satellite and 2D/3D controls operate inside Tools, with no floating Map View. Pin selection works with Search map collapsed or expanded. Preserve theme/copy feedback and existing camera behavior |
| France, broader Spain, Germany, Mexico | France capture/import and private source points verified; Germany taxonomy and bounded address enrichment verified; national Spain still unmapped; Mexico acquisition blocked | Actual missing coverage acquired, normalized, enriched where needed and verified on the map; an adapter, address queue or existing Catalonia refresh is not new mapped national coverage |
| United Kingdom and New Zealand | Required launch-dataset targets added by the maintainer; fresh end-to-end and final-release verification pending | UK source cohorts and a permitted New Zealand source pass fresh acquisition, normalization, import, location enrichment and actual map/API checks, then appear in the final dated launch dataset. Existing UK released rows or legacy V1 New Zealand data alone do not satisfy this gate; report jurisdiction and source coverage explicitly |
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

France now transforms explicitly declared source coordinates and has passed
fresh-capture retained-artifact import and map acceptance. Broader Spain has a
national AESAN import, verified municipality lookup and corrected-address queue,
but its geocoding pilots have not yet added map points. Germany now has automated
official acquisition, private taxonomy assignments and tested address enrichment;
only a bounded subset has been geocoded, not the whole source. Mexico's current
official attachment/token access remains blocked. Inspect the source inventory before
promising counts or dates. Compare intended recovery with the original V1
sources; do not silently count legacy rows as newly acquired data.

## Roadmap

1. Documentation cleanup is complete.
2. Retain the implemented UI consistency, current-mode theme
   toggle and copy feedback without redesigning the interface. Keep APHIS
   recovery and Spanish support. Persistent cluster reuse remains deferred;
   the remaining launch languages still need translation.
   Keep the deployed Swagger/link contrast and generated Spanish record-label
   translations. Finish FAQ contrast/localization, move map style/view controls
   into Tools, and repair pin selection while Search map is collapsed. Default
   the cluster cutoff to camera zoom 9.0, retaining radius 30 px.
   Use focused visual/translation checks for these nits, not repeated full
   integration suites after each small edit.
3. Deliver missing country coverage through source-specific lanes using the
   existing shared runner and separate enrichment jobs. Complete Spain address
   matching and repeat the shared France live refresh; finish Germany enrichment
   and Mexico acquisition. UK and New Zealand
   must also pass fresh end-to-end source/map checks and be included in the final
   launch dataset. Extend languages through the same system.
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
