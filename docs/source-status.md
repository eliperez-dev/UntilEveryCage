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

## Latest strict live private E2E — 2026-09-27

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

## Ireland reconnaissance update

The 2026-09-16 Ireland reconnaissance verified the current FSAI/DAFM/HSE/SFPA source topology and adjacent EPA, planning, CRO, CSO, funding, enforcement, and welfare context. It captured only bounded browser observations: HSE 72 distinct approval-number nodes, SFPA 184 approved-establishment entries, 50 freezer-vessel entries, and 1 factory-vessel entry. DAFM’s three workbook links were verified from the publication page, but workbook bytes, headers, and counts were not captured. See [Ireland reconnaissance](country-recon-ie.md), the [Ireland crosswalk](countries/ireland/v1-field-crosswalk.json), and the [Ireland artifact manifest](../data/manifests/ireland-source-artifacts.json). All 16 Ireland sources remain publication-blocked; no adapter or release artifact exists.

## Current baseline

| Source ID | Metadata | Acquisition | Runtime health | Publication | Evidence / next action |
|---|---|---|---|---|---|
| `br.sif.registered` | verified | verified | not_run | blocked | Current MAPA SIF registered CSV captured privately with schema/count/hash provenance; repeated activity rows, status semantics, terms, privacy, reconciliation, and project approval remain open; see `docs/country-recon-br.md` |
| `br.sif.export` | verified | verified | not_run | blocked | Current MAPA SIF export-authorized CSV captured privately; model country/product authorizations as dated observations, not facility rows, and complete terms/privacy/reconciliation review; see `docs/country-recon-br.md` |
| `br.sisbi.public` | verified | artifact_private_only | not_run | blocked | Public e-SISBI JSON/GIS routes returned bounded samples; pagination, code lists, ID lifecycle, status/effective-date semantics, terms, privacy, and cadence remain unresolved; see `docs/country-recon-br.md` |
| `br.trase.facilities` | verified | artifact_private_only | not_run | blocked | Current Trase GeoJSON/methodology captured privately as secondary evidence; keep separate from MAPA and review source lineage, geocoding, constructed IDs, terms, privacy, and coverage; see `docs/country-recon-br.md` |
| `au.sa.epa.licensed-activities` | verified | verified | not_run | blocked | Strict live private E2E certified 2026-10-01: 4,531 input features, 43 accepted observations, 4,488 out of scope, and 41 licence-grouped candidates. All 41 map-visible points have unspecified approximate precision; public rows remain zero. The disposable DB persisted 41 ambiguous source-native `uec-taxonomy-v1` assignment sets with zero confirmed activity mappings. Exact raw/normalized hashes and taxonomy counts are recorded in `docs/countries/australia/artifact-metadata.json`. One-time evidence only; licence-level aggregation, multi-activity children, privacy, terms, and publication remain review gates. |
| `be.locations` | verified | verified | not_run | blocked | Strict live private E2E reacquired 2026-10-01: 4,032 observations / 1,794 candidates, 1,793 coarse map-visible and 1 unresolved municipality; source counts equal retained baseline. `uec-taxonomy-v1` grouped-candidate projection: 1,794 direct mapped sets, 2,290 assignment rows, 363 multi-activity candidate sets. Zero public rows; one-time evidence only; privacy/safety and release gates remain open; see `docs/country-recon-be.md` and `data/manifests/source-evidence-be-uk-20261001.json` |
| `fr.dgal.section-i` | verified | verified | not_run | blocked | Strict live private E2E verified: 1,449 observations and 1,449 candidates from the official live text source; one-time run only, with no recurring monitor configured. Keep Section I separate; terms, category/identity, address privacy, geospatial review, project review, and public release approval remain open; see `docs/country-recon-fr.md` and `docs/countries/france/dgal-853-pipeline.md` |
| `fr.dgal.section-ii` | verified | verified | not_run | blocked | Strict live private E2E verified: 1,069 observations and 1,068 candidates from the separate official live text source; one-time run only, with no recurring monitor configured. Keep Section II distinct; terms, category/species semantics, address privacy, geospatial review, project review, and public release approval remain open; see `docs/country-recon-fr.md` and `docs/countries/france/dgal-853-pipeline.md` |
| `it.853-2004` | verified | verified | not_run | blocked | Strict live private E2E verified: 40,912 observations and 24,751 candidates from the official catalog-discovered live CSV; one-time run only, with no recurring monitor configured. Public release is not authorized; repeated activity identity, category/terms, coordinate/address privacy, coverage, and project approval remain open; see `docs/country-recon-it.md` |
| `it.1069-2009` | verified | verified | not_run | blocked | Latest strict live private E2E (2026-10-01): 9,960 observations / 6,538 candidates (+2/+2 against retained preview); 5,296 source-coordinate map-visible and 1,242 city/postal-only; zero row quarantine/public rows. `uec-taxonomy-v1` persisted 6,538 Unclassified assignment sets. One-time evidence, not recurring health or publication approval; keep separate from 853 and review the CSV/PDF schema difference, status/category, coordinates, terms, and privacy; see [manifest](../data/manifests/italy-1069-preview-e2e-20261001.json) |
| `mx.locations` | verified | blocked | not_run | blocked | DENUE/SENASICA/DGSIAP reconnaissance; resolve token, directory, terms, and schema |
| `nz.locations` | verified | blocked | not_run | blocked | MPI/Stats NZ reconnaissance; resolve 403/access and aggregate-vs-facility boundaries |
| `uk.locations` | partial | artifact_private_only | unknown | blocked | Legacy umbrella only. The England/Wales FSA and Scotland/Northern Ireland FSS identities remain separate; see `docs/country-recon-uk.md` |
| `fsa_approved_establishments` | verified | verified | not_run | blocked | Strict live private E2E reacquired 2026-10-01: same official 2026-09-01 snapshot (5,342 inputs, 4,291 accepted/candidates, 1,051 quarantined; zero source-count delta), idempotent replay passed. Grouped `uec-taxonomy-v1`: 4,291 derived assignment sets, 3,204 partial and 1,087 unmapped; 402 multi-activity candidates. Zero coordinates/map pins and public rows. One-time private evidence only; England and Wales; FSS remains separate; see `pipeline/sources/uk/fsa_approved/README.md` and `data/manifests/source-evidence-be-uk-20261001.json` |
| `fss_approved_establishments` | verified | verified | not_run | blocked | One current Scotland-only strict private E2E (2026-10-02): 728 inputs, 595 accepted/listable candidates, 133 quarantined, zero coordinates/map-visible/public rows; 595 taxonomy assignment sets / 696 assignment rows; replay passed. One-time only; FSA England/Wales and Northern Ireland remain separate. Privacy, completeness, recurring retrieval and release remain unapproved; see [manifest](../data/manifests/fss-approved-establishments-e2e-20261002.json) |
| `au.npi.facilities` | verified | verified | not_run | blocked | Strict live private E2E certified 2026-10-01: 8,140 source rows, 8,116 accepted/listable and 24 quarantined; exact same-database importer replay passed. Zero map-visible and public rows. The disposable DB persisted 8,116 ambiguous source-native `uec-taxonomy-v1` assignment sets with zero confirmed activity mappings. Latest raw/normalized hashes and taxonomy counts are recorded in `docs/countries/australia/artifact-metadata.json`. One-time evidence only; not complete facility coverage or publication approval; see `docs/country-recon-au.md` |
| `es.cat.feed-sandach` | verified | verified | not_run | blocked | Latest strict live private E2E (2026-10-01): 12,341 input rows, 12,117 accepted, 224 quarantined, 4,367 candidates; zero source coordinates/map-visible/public rows. `uec-taxonomy-v1` persisted 4,367 Unclassified assignment sets. Catalonia only, not Spain-wide; no privacy or publication approval; see [manifest](../data/manifests/catalonia-preview-e2e-20261001.json) and `docs/country-recon-es.md` |
| `dk.smiley` | verified | verified | not_run | blocked | Latest strict private-preview E2E verified 2026-10-01 04:01:38Z: 58,815 parsed, 58,765 accepted private candidates, 50 quarantined, 0 mapped and 58,765 unmapped. Configured as private-preview eligible, but not included in the active preview DB. All accepted candidates remain held for privacy review; address privacy, category review, source currentness, and publication gates remain open. One-time E2E only, not recurring health or completeness; see `pipeline/sources/denmark/README.md` |
| `de.locations` | partial | artifact_private_only | not_run | blocked | Current public general-list export parsed privately: 15,788 input, 2,691 normalized, 13,097 quarantined; session-bound export route, unknown effective date, terms/privacy/coverage and project approval remain unresolved; see `docs/germany-source-assessment.md` and `data/manifests/de-be-private-candidates-2026-09-17.json` |
| `ca.ontario.meat-plants` | verified | not_run | not_run | blocked | Ontario private adapter/refresh is implemented; keep plant/contact/coordinate fields restricted pending privacy and licence review, and do not generalize Ontario coverage nationally |
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
| `nl.nvwa.approved-food` | verified | artifact_private_only | not_run | blocked | Current control XML and eight SOAP list captures are private; repeated observation semantics, terms, privacy and adapter contract remain open; see `docs/country-recon-nl.md` |
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
