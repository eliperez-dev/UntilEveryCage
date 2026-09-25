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

## Latest strict live private E2E — 2026-09-24

Seven named official sources completed strict live private E2E through acquisition,
candidate processing, disposable-database import, and run verification. The
combined SQL-verified result is 64,701 observations, 42,875 candidates, 41,110
map-visible candidates, and 1,765 listable but unmapped candidates. The public
projection contained zero rows. This verifies a one-time source-scoped private
run; a recurring operational monitor has not yet run or been configured, and
public release is not authorized. Source-specific rights, privacy, identity,
classification, factual review, and release gates remain separate.

All seven rows remain `runtime_health=not_run` because no recurring operational
monitor is configured, and `publication_eligibility=blocked`. Here,
`acquisition=verified` records the strict live private E2E and replay evidence;
it does not imply that public rows exist or may be released. The 2026-09-15
synthetic rehearsal and 2026-09-17 Germany/Belgium capture remain historical
evidence, not the current baseline; see [archive index](archive/README.md).

## Ireland reconnaissance update

The 2026-09-16 Ireland reconnaissance verified the current FSAI/DAFM/HSE/SFPA source topology and adjacent EPA, planning, CRO, CSO, funding, enforcement, and welfare context. It captured only bounded browser observations: HSE 72 distinct approval-number nodes, SFPA 184 approved-establishment entries, 50 freezer-vessel entries, and 1 factory-vessel entry. DAFM’s three workbook links were verified from the publication page, but workbook bytes, headers, and counts were not captured. See [Ireland reconnaissance](country-recon-ie.md), the [Ireland crosswalk](countries/ireland/v1-field-crosswalk.json), and the [Ireland artifact manifest](../data/manifests/ireland-source-artifacts.json). All 16 Ireland sources remain publication-blocked; no adapter or release artifact exists.

## Current baseline

| Source ID | Metadata | Acquisition | Runtime health | Publication | Evidence / next action |
|---|---|---|---|---|---|
| `br.sif.registered` | verified | verified | not_run | blocked | Current MAPA SIF registered CSV captured privately with schema/count/hash provenance; repeated activity rows, status semantics, terms, privacy, reconciliation, and project approval remain open; see `docs/country-recon-br.md` |
| `br.sif.export` | verified | verified | not_run | blocked | Current MAPA SIF export-authorized CSV captured privately; model country/product authorizations as dated observations, not facility rows, and complete terms/privacy/reconciliation review; see `docs/country-recon-br.md` |
| `br.sisbi.public` | verified | artifact_private_only | not_run | blocked | Public e-SISBI JSON/GIS routes returned bounded samples; pagination, code lists, ID lifecycle, status/effective-date semantics, terms, privacy, and cadence remain unresolved; see `docs/country-recon-br.md` |
| `br.trase.facilities` | verified | artifact_private_only | not_run | blocked | Current Trase GeoJSON/methodology captured privately as secondary evidence; keep separate from MAPA and review source lineage, geocoding, constructed IDs, terms, privacy, and coverage; see `docs/country-recon-br.md` |
| `au.sa.epa.licensed-activities` | verified | verified | not_run | blocked | Strict live private E2E verified: 43 observations and 41 candidates from the official live GeoJSON network route; one-time run only, with no recurring monitor configured. Public release is not authorized; validate licence-level aggregation, multi-activity child rows, approximate-point semantics, privacy, and terms; see `docs/country-recon-au.md` and `docs/countries/australia/source-crosswalk.json` |
| `be.locations` | verified | verified | not_run | blocked | Strict live private E2E verified: 4,033 observations and 1,793 candidates from official FASFC operator/activity and Statbel sources; one-time run only, with no recurring monitor configured. Public release is not authorized; codebook/category coverage, privacy/safety, factual review, and release gates remain open; see `docs/country-recon-be.md` and `data/manifests/be-fasfc-live-refresh-2026-09-23.json` |
| `fr.dgal.section-i` | verified | verified | not_run | blocked | Strict live private E2E verified: 1,449 observations and 1,449 candidates from the official live text source; one-time run only, with no recurring monitor configured. Keep Section I separate; terms, category/identity, address privacy, geospatial review, project review, and public release approval remain open; see `docs/country-recon-fr.md` and `docs/countries/france/dgal-853-pipeline.md` |
| `fr.dgal.section-ii` | verified | verified | not_run | blocked | Strict live private E2E verified: 1,069 observations and 1,068 candidates from the separate official live text source; one-time run only, with no recurring monitor configured. Keep Section II distinct; terms, category/species semantics, address privacy, geospatial review, project review, and public release approval remain open; see `docs/country-recon-fr.md` and `docs/countries/france/dgal-853-pipeline.md` |
| `it.853-2004` | verified | verified | not_run | blocked | Strict live private E2E verified: 40,912 observations and 24,751 candidates from the official catalog-discovered live CSV; one-time run only, with no recurring monitor configured. Public release is not authorized; repeated activity identity, category/terms, coordinate/address privacy, coverage, and project approval remain open; see `docs/country-recon-it.md` |
| `it.1069-2009` | verified | verified | not_run | blocked | Strict live private E2E verified: 9,955 observations and 6,533 candidates from the official catalog-discovered live CSV; one-time run only, with no recurring monitor configured. Keep 1069 distinct from 853, resolve the PDF dictionary/CSV schema mismatch, and review category/status, coordinate privacy/provenance, terms, and release gates; see `data/manifests/italy-1069-preview-e2e-20260924.json` and `docs/country-recon-it.md` |
| `mx.locations` | verified | blocked | not_run | blocked | DENUE/SENASICA/DGSIAP reconnaissance; resolve token, directory, terms, and schema |
| `nz.locations` | verified | blocked | not_run | blocked | MPI/Stats NZ reconnaissance; resolve 403/access and aggregate-vs-facility boundaries |
| `uk.locations` | partial | artifact_private_only | unknown | blocked | FSA and FSS private V2 lifecycle paths, nation-qualified identity, coordinate precision states, and synthetic handoff tests pass; no real UK candidate has been imported or previewed; privacy/coordinate, source-rights, duplicate, coverage, and release review remain open; NI/Scotland stay separate; see `docs/country-recon-uk.md` and `docs/countries/uk/fss-approved-establishments-source-assessment.md` |
| `dk.smiley` | verified | verified | unknown | blocked | Shared private lifecycle and registered adapter are validated on synthetic/retained evidence with explicit not-observed semantics; coverage/effective-date uncertainty and terms/privacy/release review remain open; see `docs/countries/denmark/denmark-data-flow.md` and `pipeline/sources/denmark/README.md` |
| `de.locations` | partial | artifact_private_only | not_run | blocked | Current public general-list export parsed privately: 15,788 input, 2,691 normalized, 13,097 quarantined; session-bound export route, unknown effective date, terms/privacy/coverage and project approval remain unresolved; see `docs/germany-source-assessment.md` and `data/manifests/de-be-private-candidates-2026-09-17.json` |
| `ca.ontario.meat-plants` | verified | not_run | not_run | blocked | Ontario private adapter/refresh is implemented; keep plant/contact/coordinate fields restricted pending privacy and licence review, and do not generalize Ontario coverage nationally |
| `ca.cfia.federal-meat` | verified | verified | not_run | blocked | Strict live private E2E verified once: 874 workbook rows, 858 accepted/listable and 16 quarantined; no coordinates/map pins and zero public rows. Coverage remains unresolved against the page's 891 establishments; listing is stale and disclaimed as a convenience reference. No completeness, privacy-clearance, recurring-health, or publication claim; see `docs/countries/canada/meat-plants-pipeline.md` |
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

Australia is represented by 22 source-local evidence layers in `source-status.json` and `pipeline/source_registry.json`. All remain `publication_eligibility=blocked`; no recurring runtime monitor is claimed. `au.sa.epa.licensed-activities` has a verified one-time strict live private E2E result of 43 observations and 41 candidates; this does not authorize release. The earlier NPI CSV (8,140 rows) and SA EPA GeoJSON capture (4,541 features / 1,695 licences) remain separate historical artifacts. The detailed route, schema, identity, map/graph, privacy, terms, and blocker crosswalk is [`docs/countries/australia/source-crosswalk.json`](countries/australia/source-crosswalk.json); the source research is [`docs/country-recon-au.md`](country-recon-au.md).

The NPI source now has a deterministic synthetic/local-artifact adapter and shared-runner registration. This proves private parsing, quarantine, provenance, and candidate handoff only; it does not authorize acquisition, publication, or completeness claims.

The machine-readable file is the source of truth for these statuses. Legacy `.locations` paths may represent composite coverage, but source identities are split where the evidence establishes separate feeds: France Section I/II, Canada Ontario/CFIA, Italy 853/2004/1069/2009, and Australia’s state/federal/environment/animal-use layers. Candidate feeds mentioned in reconnaissance documents are not silently conflated into a single healthy source. Country reconnaissance documents provide evidence and next actions; they do not override this status vocabulary or authorize publication.

## Poland additions (2026-09-16)

Poland reconnaissance added GIW approved-food, registered-food, ABP and RRW sources; GUS slaughter statistics; GIOŚ/WIOŚ integrated permits; GDOŚ EIA; Geoportal Urban Register; ARiMR processing support; KRS and REGON identity routes; and the EU TRACES mirror. The GIW HTML views were verified with current displayed counts, but the XLS body was not acquired because shell HTTP was refused and the browser export timed out. The run therefore records a private metadata-only artifact, not a source-data capture. All Poland entries remain `publication_eligibility=blocked`, with runtime health `not_run`; GDOŚ and REGON acquisition are additionally blocked pending the source’s access/authorization conditions. See [`docs/country-recon-pl.md`](country-recon-pl.md), [`docs/countries/pl/source-crosswalk.json`](countries/pl/source-crosswalk.json), and [`data/manifests/pl-source-artifacts.json`](../data/manifests/pl-source-artifacts.json).

## Portugal reconnaissance (2026-09-17)

Portugal adds six source-local scopes: DGAV approved food, DGAV animal by-products, DGAV feed, APA TUA permits, restricted IFAP/DGAV SNIRA animal/holding data, and INE aggregate animal-production statistics. DGAV’s current pages link the +SIPACE listing family and document NCV/NII concepts, while the legacy SIPACE HTML list remains available for consultation during transition. No stable bulk/API export was verified, no row-level artifact was retained, and all six entries remain `publication_eligibility=blocked` with runtime health `not_run`. The recommended next implementation is a private, section-aware assisted capture for `pt.dgav.approved-food`, followed by separately validated ABP/feed sections; SNIRA remains access-controlled and INE remains aggregate-only. See [`docs/country-recon-pt.md`](country-recon-pt.md).
