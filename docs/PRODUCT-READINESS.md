# Product readiness and V2 roadmap

**Canonical authority:** this document is the sole product-level readiness and overall V2 roadmap authority.

**Owner:** project maintainer. **Updated:** 2026-10-26, Pacific.
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
| Cluster persistence | Implemented in the reviewed integration: identity-bound worker-index reuse, bounded tile caching and local world baselines; hosted verification belongs to the integration receipt below |

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
The consolidated frontend, contribution redesign and persistent-map integration
uses ignored `data/staging/frontend-render-integration-20261026/acceptance.json`.
The encrypted inbox remains development-only; production activation and email
are not part of that deployment. Dataset membership and database controls are unchanged.
The source inventory owns graph package/runtime details and source-specific evidence.

## Launch gates

All items below remain required before replacing the original website.

| Work | State | Done when |
| --- | --- | --- |
| Documentation consolidation | Complete | 46 obsolete/duplicate documents removed; one current roadmap/source inventory/frontend guide; local links and 28 documentation-contract checks passed; no application code changed |
| Persistent cluster index | Implemented; local current-release and V0 browser checks passed, with final CI/hosted state in the integration receipt | Reload reuses the built index, with release/profile/manifest/restriction invalidation; cached point bytes alone do not qualify |
| Languages | Generated Spanish facility labels and activities repaired; hosted verification belongs to the current acceptance receipt | Preserve source names, original classifications and attribution. Remaining German, French, Italian, Dutch and Danish use the same system; routes, filters and selection survive switching. Secondary API/community text is not fully translated |
| Light/dark interface and map controls | FAQ, zoom-9 default and Tools relocation deployed. Public approximate-pin centering fix shipped after four focused cases, green CI and a real hosted pin check | Preserve readable English/Spanish copy, theme behavior and Tools controls. Exact and approximate pins must select and center with Search map collapsed or expanded |
| France, broader Spain, Germany, Mexico | France shared live refresh and map membership verified; national AESAN municipality enrichment now verified across its full eligible cohort; Germany address staging and a larger finite geocoding batch verified; Mexico acquisition blocked | Use the exact counts, precision, rights and remaining jobs in the source inventory to prepare the new dated dataset. These private cohorts have not changed public dataset membership |
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

France transforms source-declared coordinate systems. National Spain separately
joins AESAN registration/province evidence to official IGN municipality points;
those points remain approximate. Germany validates address, postcode and locality
context before displaying provider points. Its usable unqueried address cohort
has completed a first pass; unmatched attempts remain recorded in the existing queue for a later
release. Complete geocoding is not a launch requirement. The BLtU reuse licence is identified in the official federal catalogue,
with attribution evidence retained. Mexico's attachment/token route remains
blocked. The source inventory owns measured counts and unresolved cases.

The backend-only country sprint preserves the frontend branch and public API
contracts. A fresh Spain refresh, importer replay, enrichment replay and exact
map-feed membership checks passed. The shared-runner acquisition/import run-ID
mismatch, stale private enrichment states and German display-cache disagreement
were repaired. Source business labels are retained for the release bridge.
The older German private candidate cache is still unnamed; its retained handoff
contains the business labels. The measured row-free release input inventory is
retained at `D:/UntilEveryCage-Operations/release-preparation/country-coverage-20261025/candidate-inventory.json`
(digest `888f7005ce63a1a29c7edfd22639dfe689602a8c6ee326f37e896a2baceb1d6f`).
It is preparation evidence, not a frozen or promoted release.

## Roadmap

1. Documentation cleanup is complete.
2. Retain the implemented UI consistency, current-mode theme
   toggle and copy feedback without redesigning the interface. Keep APHIS
   recovery and Spanish support. Persistent cluster reuse remains deferred;
   the remaining launch languages still need translation.
   Keep the deployed Swagger/FAQ contrast and generated Spanish record-label
   translations, Tools map controls, and exact/approximate pin centering.
   The cluster cutoff defaults to camera zoom 9.0 with radius 50 px.
   Use focused visual/translation checks for these nits, not repeated full
   integration suites after each small edit.
3. Deliver missing country coverage through source-specific lanes using the
   existing shared runner and separate enrichment jobs. Complete Spain address
   matching and scale its verified municipality enrichment. Carry Germany's
   completed first pass into release preparation without repeating unchanged
   matches; unfinished geocoding is deferred. Continue Mexico acquisition. UK and New Zealand
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
