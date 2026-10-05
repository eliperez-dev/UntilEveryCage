# Source status baseline

The joined country/source platform view is documented in
[`architecture/country-source-platform.md`](architecture/country-source-platform.md)
and validated offline with `python scripts/dev.py platform-registry`. This
baseline remains evidence-backed status, not runtime health or publication
approval; every derived lane stops at `awaiting-owner-review` until an
authorized owner records a decision.

This is the canonical human-readable view of [`source-status.json`](source-status.json). It records repository evidence and reconnaissance state; it is not a live monitor, acquisition log, pipeline health dashboard, release approval, or publication authorization.

## How to read it

- `metadata` describes whether a source route/scope was documented from repository or reconnaissance evidence.
- `acquisition` describes only bounded acquisition evidence. `not_run` and `blocked` do not mean zero rows or source failure.
- `runtime_health` is `not_run` unless a repeatable current pipeline check is recorded. No source here is claimed healthy.
- `publication_eligibility` is separate from source origin and metadata. These sources remain `blocked` until privacy, terms, validation, review, release, and maintainer approval gates are satisfied.

No last-success timestamp is invented. Private artifacts are not proof of a public release. “Government-sourced” does not mean current, complete, project-approved, or safe to expose.

## Legacy archive boundary

The checked-in V1-era inventory is maintained by
[`build-legacy-manifest.ps1`](../pipeline/scripts/maintenance/build-legacy-manifest.ps1).
The companion [`legacy-status.json`](../data/manifests/legacy-status.json) is a
metadata-only ledger: it records artifact presence, checksum verification,
unknown lineage/currentness, and the database boundary. The current ledger
certifies 63 present, SHA-256-verified artifacts (153,228,521 bytes); all are
`metadata_only_not_migrated` into the V2 database. Some V2 rehearsals use
separate retained private handoffs, but that does not retroactively classify a
checked-in V1 file as a migrated V2 record. No legacy artifact is
publication-eligible from its presence in this repository.

The ledger contains repository-relative paths and aggregate metadata only. It
does not copy legacy rows, addresses, coordinates, or source payloads. Unknown
source dates remain unknown, and the manifest generation time is not a source
currentness claim.

## Current private-preview source imports — 2026-10-04

The latest-per-source metadata in the retained `uec-offline-fsis-private-postgres-1/uec`
preview database verifies imported source manifests and observation/candidate
counts for the recent import lanes below. The complete fifteen-source measured
state is in the [taxonomy-reconciled inventory](../data/manifests/v0-candidate-20261004-taxonomy-inventory.json).
The same frozen cohort has also been [staged successfully](../data/manifests/v0-candidate-20261004-r3-staging-custom-plan.json)
in isolated `uec_v0_review_r3`: 187,940 canonical observations and 124,414
candidate release members across fifteen sources. A [fresh read-only staged inventory](../data/manifests/v0-candidate-20261005-r3-staged-inventory.json)
confirms one candidate release, no release manifest or promoted release, and
zero rows in the measured public projections. This is not another acquisition,
proof of recurring live readiness, public approval or graph activation; the
retained preview still has no release rows or members.
These are private, source-qualified
observations and provisional candidates—not approved or published facilities.
At source-import time, the UK, DK and NL lanes had zero source-coordinate/map-visible
candidates, and the public projection had zero rows. The map counter is a
snapshot-import measure only: separate private provider/geocoder display
processing may change current private-map availability without changing
acquisition counts or creating a public release. DK processing of the 565
eligible core addresses completed: 422 accepted results and 143 uncertain
results. Acquisition evidence for one run does not establish recurring
operational health, so
`runtime_health` remains `not_run`; `publication_eligibility` remains
`blocked`.

| Source | Latest private import | Location and interpretation |
|---|---|---|
| `dk.smiley` | 58,848 parsed; 58,795 observations/candidates; 53 quarantined | 565 candidates are in core source scope and 58,230 are optional/out of default scope. The retained source artifact was retrieved at 2026-10-04 00:39:16Z (UTC; 2026-10-03 PDT), then replayed into the DB at 2026-10-04 21:30:17Z. The latest DB run is explicitly marked `fresh_live_run=false` / `verified_retained_artifact_replay`; this is not a second acquisition. Provider display evidence is separate from import counts. |
| `fsa_approved_establishments` | 5,342 input rows; 4,291 observations/candidates; 1,051 quarantined | England and Wales only. The 2026-10-04 strict live private E2E used the recurring-health acquisition path and imported into the retained private preview. Location processing remains separate from approval or publication. |
| `fss_approved_establishments` | 728 input rows; 595 observations/candidates; 133 quarantined | Scotland only. The 2026-10-04 strict live private E2E used the recurring-health acquisition path and imported into the retained private preview. Keep separate from FSA England/Wales and any Northern Ireland source. |
| `nl.nvwa.approved-food` | 1,259 observations; 1,176 source-qualified candidate groups; 0 quarantined | Eight approved-food lists; repeated activity/species observations are preserved. 1,259 is not a unique-facility count. NVWA supplies no coordinates; source address evidence remains private and geocoding is separate. |
| `au.sa.epa.licensed-activities` | 43 observations; 41 licence groups; 4,488 out of scope/quarantined | Live reacquisition and isolated/retained imports verified 2026-10-04; 41 source-point groups of unspecified precision. |
| `br.sif.registered` | 36,639 observations; 3,143 SIF groups; 0 quarantined | Live reacquisition and isolated/retained imports verified 2026-10-04; no current display geometry. |
| `it.1069-2009` | 9,962 observations; 6,539 source groups; 0 quarantined | Live reacquisition and isolated/retained imports verified 2026-10-04; 5,297 source-coordinate groups and 1,242 unmapped groups. |

The machine-readable run IDs, snapshot and artifact hashes, and import-time
geometry counter basis are in [`source-status.json`](source-status.json).
DK scope counts come from its [row-free replay manifest](../data/manifests/denmark-private-v0-refresh-2026-10-04.json);
the NL [row-free source manifest](../data/manifests/nl-nvwa-approved-food-v0.json)
documents an earlier capture, not the latest certified/imported snapshot.
UK address/geocoding outcomes and later private provider-display evidence
remain separate from source acquisition and candidate counts: UK has six
accepted provider results; NL has 602 accepted and 574 uncertain results.
The taxonomy-reconciled inventory measures 187,940 observations, 124,414 source-qualified
groups and 50,611 currently private-map-served groups across fifteen snapshots.
It is not a globally deduplicated facility or rendered-marker count. No source
in this section is approved for release.

The [append-only reconciliation receipt](../data/manifests/v0-taxonomy-reconciliation-20261004.json)
records successful application to the retained preview after the isolated copy
passed. All 124,414 current groups now have `uec-source-crosswalk-v2` assignment
sets under the unchanged `uec-taxonomy-v1` categories. Entire original candidate
rows, source observations and v1 assignment history were checked unchanged.
The new inventory digest is
`23adeac2487ee163e78918ba53f8aa01d274e2900cc4a8bf8b26e60cbd566d21`.
This repairs interpretation/projection consistency; it does not add source
observations, improve location precision, approve release, or establish live
readiness of archived routes. See the canonical roadmap for staging status.

## Historical strict live private E2E checkpoint — 2026-09-27

Ten named official sources completed strict live private E2E through acquisition,
candidate processing, disposable-database import, and run verification. The
combined SQL-verified result is 89,225 observations, 59,649 candidates, 41,110
map-visible candidates, and 18,539 listable but unmapped candidates. The FSA
snapshot contributed 4,291 unmapped candidates. AU NPI contributed 8,116
listable candidates and Catalonia contributed 4,367 municipality-grouped
candidates; both had zero map-visible candidates. Exact same-database importer
replay verified idempotency for AU NPI, FSA, and Catalonia. The public
projection contained zero rows. This verifies a one-time source-scoped private
run; a recurring operational monitor has not yet run or been configured, and
public release is not authorized. Source-specific rights, privacy, identity,
classification, factual review, and release gates remain separate.

All ten rows remain `runtime_health=not_run` because no recurring operational
monitor is configured, and `publication_eligibility=blocked`. Here,
`acquisition=verified` records the strict live private E2E and replay evidence;
it does not imply that public rows exist or may be released. The 2026-09-15
synthetic rehearsal and 2026-09-17 Germany/Belgium capture remain historical
evidence, not the current baseline; see [archive index](archive/README.md).

## Standalone FSS Scotland E2E — 2026-10-02

The current official FSS Scotland CSV passed one strict live private E2E run:
728 source rows, 595 accepted observations/candidates, and 133 quarantined;
same-database replay was idempotent. All 595 candidates are listable but
unmapped because no coordinates were supplied, so the map has zero visible
records. Taxonomy persisted 595 assignment sets / 696 activity assignment
rows. The disposable PostGIS database and public projections were empty/removed
after certification. This isolated run did not modify the authoritative
retained preview database and does not establish ongoing health, completeness,
privacy clearance, recurring retrieval, or release approval. It covers
Scotland only; FSA England/Wales and any Northern Ireland feed remain separate.
See the [row-free E2E manifest](../data/manifests/fss-approved-establishments-e2e-20261002.json)
and [FSS source assessment](countries/uk/fss-approved-establishments-source-assessment.md).
This dated isolated-database result did not change the retained preview then;
the separate 2026-10-04 import is summarized above.

## Italy 1069 and Catalonia evidence recovery — 2026-10-01

Fresh source-scoped acquisitions for `it.1069-2009` and `es.cat.feed-sandach`
passed isolated private API and disposable-database certification. Italy
contained 9,960 observations / 6,538 candidates, two more than the retained
preview baseline; 5,296 candidates had source coordinates and 1,242 were
city/postal-only. Catalonia remained at 12,117 accepted observations / 4,367
candidates, with 224 quarantined rows and no coordinates or map-visible
candidates. The current `uec-taxonomy-v1` import wrote Unclassified assignment
sets for both sources. Row-level artifacts remain under ignored local
`target/real-preview/runs/` storage; tracked source manifests contain only
aggregate counts and hashes. These runs did not modify the retained
authoritative preview database or authorize publication. See the [Italy
1069 manifest](../data/manifests/italy-1069-preview-e2e-20261001.json) and
[Catalonia manifest](../data/manifests/catalonia-preview-e2e-20261001.json).

## Retained private preview taxonomy projection — 2026-10-01

The authoritative retained private preview database (`uec` in
`uec-offline-fsis-private-postgres-1`) received migrations 054 activity contract,
055 versioned UEC assignments, and 056 real-preview assignments at
2026-10-01 19:05:21 UTC. This is a distinct offline corpus checkpoint, not a
replacement for the strict live E2E baseline above: latest-per-source totals
remain 90,164 observations, 60,218 candidates, and 38,633 map-visible groups
(36,840 numeric and 1,793 coarse). The additive projection contains 35,073
candidate assignment sets and 35,674 assignment rows; 2,516 candidate sets are
mapped. Per-source scope is recorded in [product readiness](PRODUCT-READINESS.md#retained-private-preview-taxonomy-application--2026-10-01).

Only the exact normalized packets for FR DGAL sections I/II, IT 853, and FSIS
were recovered with deterministic representative-observation joins. France
was mapped; Italy 853 remains explicitly unclassified; FSIS has 7,082 unmapped
and 159 unclassified candidates, with no positive primary assignments. No
taxonomy rows were written for `au.npi.facilities`,
`au.sa.epa.licensed-activities`, `be.locations`, `es.cat.feed-sandach`,
`fsa_approved_establishments`, or `it.1069-2009` because their exact source
artifacts were unavailable. These six sources require artifact recovery before
reprojection. The verified backup is
`D:\UntilEveryCage-backups\database\taxonomy-pre-reprojection-authoritative-20261001-113806\uec.logical.dump`
(SHA-256 `2EF936FCB99CB973618AAF74AE1655EC874DA799EDE2C6F426DDBD6D22162A93`).
Live preview API/browser verification was unavailable in the application
context; this application does not change source runtime-health, publication,
privacy, terms, or factual-review status.

## Source evidence recovery follow-up — 2026-10-01

The six recovered runs are now the latest source evidence in the authoritative
private database. Latest-per-source totals are 90,166 observations, 60,220
candidates, and 38,634 map-visible groups (36,841 numeric, 1,793 coarse); all
60,220 candidate assignment sets and 61,775 assignment rows are retained, with
zero public rows. Belgium has 1,794 exact direct LAP/PAP-mapped grouped
candidates (363 multi-activity sets); UK FSA has 3,204 partial and 1,087
unmapped derived groups (402 multi-activity sets). IT 1069 (6,538 candidate
sets), Spain (4,367), Australia NPI (8,116), and SA EPA (41) remain
unclassified or ambiguous, with no confirmed positive primary assignments.
FR I/II, IT 853, and FSIS assignment sets remain unchanged. The six current
run IDs, evidence hashes, quarantine counts, and recovery validation are in the
[integration manifest](../data/manifests/source-evidence-integration-20261001.json).

## Strict E2E cohort integration — 2026-10-02

The certified Brazil SIF Registered, Ontario Meat Plants, and Food Standards
Scotland runs were imported into the authoritative private preview database
with the shared importer and replayed with the same immutable handoffs.
Latest-per-source totals are 115,395 observations, 64,422 candidates, and
38,634 map-visible locations (36,841 numeric and 1,793 coarse). The new three
sources add no map-visible locations because their coordinates are withheld or
not supplied. All 64,422 candidate taxonomy sets and 66,639 assignment rows
reconcile; release, public map, and public preview rows remain zero.

Brazil contributes 24,174 observations and 3,147 municipality-listable
candidates, all conservatively Unmapped from source activity codes. Ontario
contributes 460 observations/candidates; 453 candidate sets have derived
activity mappings and 7 remain Unclassified (1,021 assignment rows). FSS
Scotland contributes 595 observations/candidates from 728 input rows after
133 quarantines; its 696 derived assignment rows have 192 mapped, 424 partial,
and 80 unmapped statuses (counts are assignment rows, not candidate sets).
The source-scoped manifests preserve run hashes and limits. Authenticated local
API counts, source-scoped list/search/detail, and map-feed behavior passed for
all three sources; none adds map features without coordinates. The fresh
pre-import backup is `D:\UntilEveryCage-backups\database\source-cohort-pre-import-20261002-023930\uec.dump`
(SHA-256 `19F20A50417FF98A6771C012AEA3CE19D4FDC97573FB744B173565A97CC69B5B`).
These are one-time private E2E certifications, not recurring health,
completeness, privacy clearance, or public-release approval.

## Ireland reconnaissance update

The 2026-09-16 Ireland reconnaissance verified the current FSAI/DAFM/HSE/SFPA source topology and adjacent EPA, planning, CRO, CSO, funding, enforcement, and welfare context. It captured only bounded browser observations: HSE 72 distinct approval-number nodes, SFPA 184 approved-establishment entries, 50 freezer-vessel entries, and 1 factory-vessel entry. DAFM’s three workbook links were verified from the publication page, but workbook bytes, headers, and counts were not captured. See [Ireland reconnaissance](country-recon-ie.md), the [Ireland crosswalk](countries/ireland/v1-field-crosswalk.json), and the [Ireland artifact manifest](../data/manifests/ireland-source-artifacts.json). All 16 Ireland sources remain publication-blocked; no adapter or release artifact exists.

## Current baseline

As of 2026-10-02, the authoritative retained private preview has 115,419
latest-source observations and 64,446 candidate groups: 45,417 numeric and
4,163 coarse points are map-visible (49,580 total); 14,866 candidates have no
rendered point. The API's `unmapped_candidate_count` is narrower: 4,886
unmapped-location-class candidates. The dated 2026-10-02 cohort figures above
are a historical pre-geospatial-replay checkpoint. NPI, Ontario, and Catalonia
were verified by hash-checked archived replay, not fresh acquisition; see the
[row-free replay manifest](../data/manifests/geospatial-replay-integration-20261002.json).
NPI has 24 current-snapshot address-enrichment targets. The bounded
source-scoped Geoapify activation and private display bridge are implemented.
The 2026-10-03 first pass made 24 requests, all rejected for authentication.
After explicit user authorization and key correction, the daily limit was
raised from 24 to 48 without resetting the 24 prior reservations; 24 bounded
recovery requests authenticated but produced 22 `review_required` and 2
`unresolved` outcomes. Their categories were 13 ambiguous multiple results,
9 unsupported address/locality matches, and 2 unresolved. No address or
approximate locality point met the existing display rule, so the latest
49,580 map-visible count is unchanged and provider display evidence remains
zero. Three additional diagnostic lookups (outside the worker reservation
ledger) sampled withheld results; none changed matching policy or preview
data. No public rows were created. The row-free [pilot manifest](../data/manifests/au-npi-geoapify-pilot-20261003.json)
records the backup and aggregate outcome. The prior 32-hex key-format check
was only a heuristic; successful recovery requests confirm provider
authentication without recording the key.
The row-free backlog audit found 2,021 address-bearing candidates (NPI 24 and
Catalonia 1,997; only the NPI 24 are in this pilot), 7,959 locality-only
candidates, and 4,886 with neither address nor locality (FSA 4,291; FSS 595).
Catalonia's 2,370 local
reference placements are coarse, with 1,997 still unresolved. Public/release
rows remain zero and publication is not authorized.

| Source ID | Metadata | Acquisition | Runtime health | Publication | Evidence / next action |
|---|---|---|---|---|---|
| `br.sif.registered` | verified | verified | not_run | blocked | Reacquired and imported privately 2026-10-04: 36,639 observations / 3,143 source-qualified groups, zero quarantines, mapped groups or public rows. Exact raw/normalized/graph provenance and isolated then retained import reconciliation passed; [current inventory](../data/manifests/v0-candidate-20261004-reacquired-inventory.json). This is not recurring health, global deduplication or public approval. The [2026-10-02 strict run](../data/manifests/br-sif-registered-preview-e2e-20261002.json) is historical. Status, rights, privacy, municipality display and release gates remain open. |
| `br.sif.export` | verified | verified | not_run | blocked | Current MAPA SIF export-authorized CSV captured privately; model country/product authorizations as dated observations, not facility rows, and complete terms/privacy/reconciliation review; see `docs/country-recon-br.md` |
| `br.sisbi.public` | verified | artifact_private_only | not_run | blocked | Public e-SISBI JSON/GIS routes returned bounded samples; pagination, code lists, ID lifecycle, status/effective-date semantics, terms, privacy, and cadence remain unresolved; see `docs/country-recon-br.md` |
| `br.trase.facilities` | verified | artifact_private_only | not_run | blocked | Current Trase GeoJSON/methodology captured privately as secondary evidence; keep separate from MAPA and review source lineage, geocoding, constructed IDs, terms, privacy, and coverage; see `docs/country-recon-br.md` |
| `au.sa.epa.licensed-activities` | verified | verified | not_run | blocked | Reacquired and imported privately 2026-10-04: 4,531 input features, 43 accepted observations, 4,488 out of scope/quarantined, and 41 licence-grouped candidates with source-supplied points of unspecified precision; zero public rows. Exact raw/normalized/graph provenance and isolated then retained import reconciliation passed; [current inventory](../data/manifests/v0-candidate-20261004-reacquired-inventory.json). The 2026-10-01 strict run remains historical evidence. No recurring-health or publication claim; licence aggregation, activity semantics, privacy and release gates remain separate. |
| `be.locations` | verified | verified | not_run | blocked | Strict live private E2E reacquired 2026-10-01: 4,032 observations / 1,794 candidates, 1,793 coarse map-visible and 1 unresolved municipality; source counts equal retained baseline. `uec-taxonomy-v1` grouped-candidate projection: 1,794 direct mapped sets, 2,290 assignment rows, 363 multi-activity candidate sets. Zero public rows; one-time evidence only; privacy/safety and release gates remain open; see `docs/country-recon-be.md` and `data/manifests/source-evidence-be-uk-20261001.json` |
| `fr.dgal.section-i` | verified | verified | not_run | blocked | Strict live private E2E verified: 1,449 observations and 1,449 candidates from the official live text source; one-time run only, with no recurring monitor configured. Keep Section I separate; terms, category/identity, address privacy, geospatial review, project review, and public release approval remain open; see `docs/country-recon-fr.md` and `docs/countries/france/dgal-853-pipeline.md` |
| `fr.dgal.section-ii` | verified | verified | not_run | blocked | Strict live private E2E verified: 1,069 observations and 1,068 candidates from the separate official live text source; one-time run only, with no recurring monitor configured. Keep Section II distinct; terms, category/species semantics, address privacy, geospatial review, project review, and public release approval remain open; see `docs/country-recon-fr.md` and `docs/countries/france/dgal-853-pipeline.md` |
| `it.853-2004` | verified | verified | not_run | blocked | Strict live private E2E verified: 40,912 observations and 24,751 candidates from the official catalog-discovered live CSV; one-time run only, with no recurring monitor configured. Public release is not authorized; repeated activity identity, category/terms, coordinate/address privacy, coverage, and project approval remain open; see `docs/country-recon-it.md` |
| `it.1069-2009` | verified | verified | not_run | blocked | Reacquired and imported privately 2026-10-04: 9,962 observations / 6,539 source-qualified groups, 5,297 source-coordinate groups and 1,242 unmapped groups, zero quarantines/public rows. Exact raw/normalized/graph provenance and isolated then retained import reconciliation passed; [current inventory](../data/manifests/v0-candidate-20261004-reacquired-inventory.json). Restricted-network failures were resolved by the network-enabled existing runner. The [2026-10-01 strict run](../data/manifests/italy-1069-preview-e2e-20261001.json) is historical; no recurring-health or publication claim. Keep separate from 853 and review category/status, CSV/PDF semantics, coordinates, terms and privacy. |
| `mx.locations` | verified | blocked | not_run | blocked | DENUE/SENASICA/DGSIAP reconnaissance; resolve token, directory, terms, and schema |
| `nz.locations` | verified | blocked | not_run | blocked | MPI/Stats NZ reconnaissance; resolve 403/access and aggregate-vs-facility boundaries |
| `uk.locations` | partial | artifact_private_only | unknown | blocked | Legacy umbrella only. The England/Wales FSA and Scotland/Northern Ireland FSS identities remain separate; see `docs/country-recon-uk.md` |
| `fsa_approved_establishments` | verified | verified | not_run | blocked | Strict live private E2E reacquired 2026-10-01: same official 2026-09-01 snapshot (5,342 inputs, 4,291 accepted/candidates, 1,051 quarantined; zero source-count delta), idempotent replay passed. Grouped `uec-taxonomy-v1`: 4,291 derived assignment sets, 3,204 partial and 1,087 unmapped; 402 multi-activity candidates. Zero coordinates/map pins and public rows. One-time private evidence only; England and Wales; FSS remains separate; see `pipeline/sources/uk/fsa_approved/README.md` and `data/manifests/source-evidence-be-uk-20261001.json` |
| `fss_approved_establishments` | verified | verified | not_run | blocked | Scotland-only strict private E2E (2026-10-02) imported into the authoritative private preview: 728 inputs, 595 accepted/listable candidates, 133 quarantined, zero coordinates/map-visible/public rows; 595 taxonomy sets / 696 derived assignment rows (192 mapped, 424 partial, 80 unmapped); same-database replay passed. FSA England/Wales and Northern Ireland remain separate. Privacy, completeness, recurring retrieval and release remain unapproved; see [manifest](../data/manifests/fss-approved-establishments-e2e-20261002.json) |
| `au.npi.facilities` | verified | verified | not_run | blocked | Latest retained artifact was hash-verified and archived-replayed (not freshly acquired): 8,140 observations/candidates, 8,116 source-coordinate points and 24 persistent address jobs. First-pass 24 authentication failures were followed by 24 user-authorized recovery requests: 22 review-required (13 ambiguous, 9 unsupported matches), 2 unresolved, 0 displayed points; current map remains 49,580 and public rows remain 0. Three separate diagnostic lookups sampled withheld cases; no matching rule was loosened. See the [pilot manifest](../data/manifests/au-npi-geoapify-pilot-20261003.json), [geospatial replay manifest](../data/manifests/geospatial-replay-integration-20261002.json), and [Australia NPI notes](country-recon-au.md). |
| `es.cat.feed-sandach` | verified | verified | not_run | blocked | Latest retained artifact was hash-verified and archived-replayed (not freshly acquired): 12,117 observations / 4,367 candidates; local ICGC exact-code matching resolved 2,370 coarse locality references and left 1,997 unresolved; zero external geocoder calls or public rows. Catalonia only; see [geospatial replay manifest](../data/manifests/geospatial-replay-integration-20261002.json) |
| `dk.smiley` | verified | verified | not_run | blocked | Current retained import: 58,795 observations/candidates, 53 quarantined; verified retained-artifact replay 2026-10-04, not another acquisition. Of 565 core candidates, 422 have accepted private provider points and 143 remain uncertain; 58,230 optional/out-of-default candidates remain separate. Included in the active preview DB, not public. See current import section and [inventory](../data/manifests/v0-candidate-20261004-reacquired-inventory.json); category, currentness, rights, privacy and release gates remain separate. |
| `de.locations` | partial | artifact_private_only | not_run | blocked | Current public general-list export parsed privately: 15,788 input, 2,691 normalized, 13,097 quarantined; session-bound export route, unknown effective date, terms/privacy/coverage and project approval remain unresolved; see `docs/germany-source-assessment.md` and `data/manifests/de-be-private-candidates-2026-09-17.json` |
| `ca.ontario.meat-plants` | verified | verified | not_run | blocked | Latest retained artifact was hash-verified and archived-replayed (not freshly acquired): 460 observations/candidates and 460 private source-coordinate map features. Positional precision is unspecified and disclosed as approximate; location evidence stays private, project approval is false, publication is not published. Ontario only; see [geospatial replay manifest](../data/manifests/geospatial-replay-integration-20261002.json) |
| `ca.cfia.federal-meat` | verified | verified | not_run | blocked | Latest strict private-preview E2E verified 2026-10-01 03:54:16Z: 874 parsed, 858 accepted private candidates, 16 quarantined, 0 mapped and 858 unmapped. Configured as private-preview eligible, but not included in the active preview DB. The one-time isolated E2E imported candidates only into its disposable DB; a temporary restricted geocode queue was removed and no external request was made. Source effective date/Last-Modified is absent; no completeness, privacy-clearance, recurring-health, or publication claim; see `docs/countries/canada/meat-plants-pipeline.md` |
| `es.locations` | partial | blocked | not_run | blocked | AESAN RGSEAA and MAPA sector routes are documented, but direct acquisition was refused; rights, export/schema, effective dates, sector coverage, privacy, and legacy/source boundaries remain unresolved |
| `us.fsis` | verified | verified | not_run | blocked | Strict live private E2E verified: 7,240 observations and 7,240 candidates from official current CSVs acquired through an authorized bounded browser download; one-time run only, with no recurring monitor configured. Public release is not authorized; source terms, identity, location/privacy, reconciliation, project review, and release gates remain open; see `docs/country-recon-us.md` and `docs/countries/us/README.md` |
| `us.state-mpi` | verified | not_run | not_run | blocked | FSIS identifies 29 state MPI programs and 10 CIS states; state roster routes are documented in `docs/countries/us/state-mpi-source-recon.md`, but no state roster/CIS workbook was acquired. Keep official, CIS, custom-exempt, retail/handler, and inactive/expired populations separate; obtain authorized current exports and review terms/schema/privacy before any test-only handoff |
| `us.aphis` | verified | not_run | not_run | blocked | Profile-explicit private adapter and assisted-capture contract cover registrations, annual reports, and inspections; capture current exports and review terms/schema/privacy |
| `us.inspections` | verified | not_run | not_run | blocked | APHIS inspections profile is implemented as observation evidence; capture current export and use explicit reviewable identity links only |
| `us.nih.reporter` | verified | not_run | not_run | blocked | NIH RePORTER API/ExPORTER is documented as the first funding/project integration; exact award and organization keys remain separate from animal-use counts |
| `us.nih.olaw-assurances` | verified | not_run | not_run | blocked | OLAW assured-institutions lookup is current institutional assurance evidence; validate assisted capture and branch/affiliate scope without inferring protocols or counts |
| `us.aaalac.accredited` | verified | not_run | not_run | blocked | AAALAC directory is voluntary unit-level accreditation evidence; review terms and identity before private capture |
| `us.fda.glp-animal-research` | verified | not_run | not_run | blocked | FDA MOU/facility/policy surfaces are manual evidence only; no national facility/count route was verified and openFDA adverse events are out of scope |
| `us.va.animal-research` | verified | not_run | not_run | blocked | VA program and ORO pages document oversight but no national public facility/count route; keep local observations separate |
| `us.dod.acuro` | verified | not_run | not_run | blocked | ACURO protocol/site oversight pages are manual and privacy-sensitive; do not infer facilities from awardee addresses |
| `us.nsf.awards` | verified | not_run | not_run | blocked | NSF Award Search is a funding/project adjunct only; animal relevance and performance-site semantics require review |
| `us.nasa.nspires` | verified | not_run | not_run | blocked | NASA NSPIRES is funding/project evidence only; no public animal-use route was verified |
| `us.ca.cdph-lab-animals` | verified | not_run | not_run | blocked | California CDPH LAB 139 is a state pilot with prior-year count fields and federal exemptions; no public bulk registry and no national denominator |
| `nl.nvwa.approved-food` | verified | verified | not_run | blocked | Eight lists acquired and imported 2026-10-04: 1,259 observations, 1,176 source groups, zero quarantines/public rows. Included in retained preview; 602 accepted private provider points and 574 uncertain results. Repeated activity/species observations are not unique facilities. See current import section and [inventory](../data/manifests/v0-candidate-20261004-reacquired-inventory.json); rights, privacy, lifecycle and release gates remain separate. |
| `nl.nvwa.welfare-enforcement` | verified | artifact_private_only | not_run | blocked | Current 2025 welfare/animal-experiment pages and dated 2024/2023 PDFs captured privately; keep effective periods and evidence types separate |
| `nl.cokz.dairy-eggs` | verified | artifact_private_only | not_run | blocked | Current COKZ HTML register captured privately; register-family coverage, terms and overlap with NVWA remain open |
| `nl.rvo.ir` | verified | blocked | not_run | blocked | RVO I&R is authorization-gated; no public scrape or restricted UBN/location data exposure |
| `nl.kvk.hvds` | verified | not_run | not_run | blocked | KVK route and privacy/terms review remain open; use only for reviewed identity links, never UBO or facility proof |
| `nl.cbs.slaughter` | verified | artifact_private_only | not_run | blocked | Current monthly aggregate OData captured privately; keep outside facility tables and preserve status flags |
| `nl.cbs.livestock` | verified | artifact_private_only | not_run | blocked | Current twice-yearly aggregate OData captured privately; agricultural-business scope is not a facility master |
| `eu.eurostat.nl-slaughter` | verified | artifact_private_only | not_run | blocked | Current NL aggregate mirror captured privately; use only as harmonized context and do not double-count CBS |
| `nl.pdok.omgevingswet` | verified | artifact_private_only | not_run | blocked | Current OGC metadata/collections captured privately; resolve DSO legal/document context before permit evidence |
| `nl.koop.local-permits` | verified | artifact_private_only | not_run | blocked | Initial SRU request returned unsupported-field diagnostics; implement collection-specific CQL and retain local coverage limits |
| `eu.traces.approved-establishments` | verified | not_run | not_run | blocked | EU mirror context verified; no separate NL artifact; never merge as additional facilities |

## Australia additions (2026-09-16; current status 2026-09-24)

Australia is represented by 22 source-local evidence layers in `source-status.json` and `pipeline/source_registry.json`. All remain `publication_eligibility=blocked`; no recurring runtime monitor is claimed. On 2026-10-01, AU NPI and SA EPA were each reacquired from their current official catalogue routes and certified through a disposable private database/API run. NPI produced 8,116 candidates with source coordinates withheld from map/API locations; SA EPA produced 41 licence-grouped candidates with approximate, unspecified-precision points shown only in private preview. The disposable database persisted 8,116 NPI and 41 SA EPA assignment sets under `uec-taxonomy-v1`; every set remains an ambiguous source-native candidate with zero confirmed current-operation mappings. Raw and normalized lineage is retained privately, and no public row was created. Detailed hash, count, and artifact-path metadata is in [`docs/countries/australia/artifact-metadata.json`](countries/australia/artifact-metadata.json); this does not authorize release. The detailed route, schema, identity, map/graph, privacy, terms, and blocker crosswalk is [`docs/countries/australia/source-crosswalk.json`](countries/australia/source-crosswalk.json); the source research is [`docs/country-recon-au.md`](country-recon-au.md).

The NPI source has a deterministic adapter and shared-runner registration. Its latest strict live private E2E is dated 2026-10-01: 8,116 listable candidates, zero map-visible candidates, and zero public rows. This is one-time evidence only; it does not authorize publication or completeness claims.

The machine-readable file is the source of truth for these statuses. Legacy `.locations` paths may represent composite coverage, but source identities are split where the evidence establishes separate feeds: France Section I/II, Canada Ontario/CFIA, Italy 853/2004/1069/2009, and Australia’s state/federal/environment/animal-use layers. Candidate feeds mentioned in reconnaissance documents are not silently conflated into a single healthy source. Country reconnaissance documents provide evidence and next actions; they do not override this status vocabulary or authorize publication.

## Poland additions (2026-09-16)

Poland reconnaissance added GIW approved-food, registered-food, ABP and RRW sources; GUS slaughter statistics; GIOŚ/WIOŚ integrated permits; GDOŚ EIA; Geoportal Urban Register; ARiMR processing support; KRS and REGON identity routes; and the EU TRACES mirror. The GIW HTML views were verified with current displayed counts, but the XLS body was not acquired because shell HTTP was refused and the browser export timed out. The run therefore records a private metadata-only artifact, not a source-data capture. All Poland entries remain `publication_eligibility=blocked`, with runtime health `not_run`; GDOŚ and REGON acquisition are additionally blocked pending the source’s access/authorization conditions. See [`docs/country-recon-pl.md`](country-recon-pl.md), [`docs/countries/pl/source-crosswalk.json`](countries/pl/source-crosswalk.json), and [`data/manifests/pl-source-artifacts.json`](../data/manifests/pl-source-artifacts.json).

## Portugal reconnaissance (2026-09-17)

Portugal adds six source-local scopes: DGAV approved food, DGAV animal by-products, DGAV feed, APA TUA permits, restricted IFAP/DGAV SNIRA animal/holding data, and INE aggregate animal-production statistics. DGAV’s current pages link the +SIPACE listing family and document NCV/NII concepts, while the legacy SIPACE HTML list remains available for consultation during transition. No stable bulk/API export was verified, no row-level artifact was retained, and all six entries remain `publication_eligibility=blocked` with runtime health `not_run`. The recommended next implementation is a private, section-aware assisted capture for `pt.dgav.approved-food`, followed by separately validated ABP/feed sections; SNIRA remains access-controlled and INE remains aggregate-only. See [`docs/country-recon-pt.md`](country-recon-pt.md).
