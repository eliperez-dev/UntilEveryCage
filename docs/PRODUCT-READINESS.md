# Product readiness and V2 roadmap

**Canonical authority:** this document is the sole product-level readiness and overall V2 roadmap authority.

**Owner:** project maintainer. **Updated:** 2026-10-27, Pacific.
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

The reviewed frontend delivery is merged with the country-release backend
checkpoint. It includes the mobile workspace, additional languages, map tools,
area search, raster handoff and cold-navigation fixes. Required CI has six
passing jobs but still fails two 3D browser checks; rollout remains pending
while their trace-backed test corrections are verified. Exact revisions,
results and deployment state are retained in ignored
`data/staging/app-review-20261027/acceptance.json`. The currently hosted dataset
and serving database are unchanged.

## Launch gates

All items below remain required before replacing the original website.

| Work | State | Done when |
| --- | --- | --- |
| Documentation consolidation | Complete | 46 obsolete/duplicate documents removed; one current roadmap/source inventory/frontend guide; local links and 28 documentation-contract checks passed; no application code changed |
| Persistent cluster index | Implemented; local current-release and V0 browser checks passed, with final CI/hosted state in the integration receipt | Reload reuses the built index, with release/profile/manifest/restriction invalidation; cached point bytes alone do not qualify |
| Languages | Generated Spanish facility labels and activities repaired; hosted verification belongs to the current acceptance receipt | Preserve source names, original classifications and attribution. Remaining German, French, Italian, Dutch and Danish use the same system; routes, filters and selection survive switching. Secondary API/community text is not fully translated |
| Light/dark interface and map controls | FAQ, zoom-9 default and Tools relocation deployed. Public approximate-pin centering fix shipped after four focused cases, green CI and a real hosted pin check | Preserve readable English/Spanish copy, theme behavior and Tools controls. Exact and approximate pins must select and center with Search map collapsed or expanded |
| France, broader Spain, Germany, Mexico | France and Spain private map checks passed; Germany first-pass geocoding retained; Mexico national capture and private database/API checks passed | Use the source inventory to prepare the new dated dataset. These private cohorts have not changed public dataset membership |
| United Kingdom and New Zealand | UK FSA/FSS fresh capture, import and private API checks passed. NZ supplied MPI export has 1,638 programme records and 321 audited address points after 486 requests; real API checks passed | Include the verified cohorts in the final dated dataset. NZ export automation remains unverified; programme rows are not a premises census. Report jurisdiction and mapped coverage explicitly |
| APHIS history | Reliability and on-demand historical recovery implemented | Six real endpoint cases passed locally: two eligible facilities return pre-2025 annual and inspection links, sampled PDFs open, and the original no-report case returns an empty page; sample history reaches 2014, not a complete archive audit |
| New default dated dataset | Private candidate assembled: 124,264 records across 19 sources, 93,058 coordinate points | Complete source-scoped release checks, current restrictions, graph/report projection and serving-package/API acceptance before publication |
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
with attribution evidence retained. Mexico now has a scoped national DENUE
capture with 5,377 source-coordinate records. New Zealand's supplied MPI export
has passed private staging, but supplies programme records rather than a
one-row-per-premises census and contains no coordinates. Both passed local
database/API acceptance; NZ enrichment and release integration remain. The source inventory owns
measured counts and unresolved cases.

The backend-only country sprint preserves the frontend branch and public API
contracts. A fresh Spain refresh, importer replay, enrichment replay and exact
map-feed membership checks passed. The shared-runner acquisition/import run-ID
mismatch, stale private enrichment states and German display-cache disagreement
were repaired. Source business labels are retained for the release bridge.
The older German private candidate cache is still unnamed; its retained handoff
contains the business labels. The measured row-free release input inventory is
retained at `D:/UntilEveryCage-Operations/release-preparation/country-coverage-20261027/candidate-inventory-uk-geocoded.json`
(digest `39849bc852183d668ad2367ef49b54018193a0520f0ddb8e1e81f8b1098f1504`).
It is preparation evidence, not a frozen or promoted release.

Country-release assembly completed on an isolated copy of the current
release. The corrected private candidate `release-2026-10-27-r2` has 124,264
members, 114,919 named records and 93,058 coordinate points across 19 sources.
These are candidate counts, not approved public/map totals. Twenty French
out-of-scope points remain searchable but unmapped; their source evidence is
retained. Existing candidates and public releases were not rewritten.
UK enrichment queried 714 addresses and retained 32 audited matches;
682 unmatched attempts remain available for later work. The secondary account
has 701 requests left. The seven source cohorts passed read-only handoff and
taxonomy checks. Their input selection and retained raw
artifact hashes are frozen locally; public dataset membership is unchanged.
The copy retains the current 60,263 connections, 1,024 report references and V0.

## Roadmap

1. Documentation cleanup is complete.
2. Retain the implemented UI consistency, current-mode theme
   toggle and copy feedback without redesigning the interface. Keep APHIS
   recovery and Spanish support. Persistent cluster reuse and additional
   languages are implemented in the reviewed integration; hosted acceptance
   remains required.
   Keep the deployed Swagger/FAQ contrast and generated Spanish record-label
   translations, Tools map controls, and exact/approximate pin centering.
   The cluster cutoff defaults to camera zoom 9.0 with radius 50 px.
   Use focused visual/translation checks for these nits, not repeated full
   integration suites after each small edit.
3. Deliver missing country coverage through source-specific lanes using the
   existing shared runner and separate enrichment jobs. Complete Spain address
   matching and scale its verified municipality enrichment. Carry Germany's
   completed first pass into release preparation without repeating unchanged
   matches; unfinished geocoding is deferred. Mexico capture is complete. UK and New Zealand
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
