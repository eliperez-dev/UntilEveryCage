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

## Latest private rehearsal

The owner-authorized 2026-09-15 live-country rehearsal remains the historical synthetic/private baseline. On 2026-09-17, current official Germany and Belgium artifacts were captured privately, parsed through the live-schema adapters, and kept publication-blocked. See the row-free [Germany/Belgium candidate manifest](../data/manifests/de-be-private-candidates-2026-09-17.json), plus the detailed country packets.

## Ireland reconnaissance update

The 2026-09-16 Ireland reconnaissance verified the current FSAI/DAFM/HSE/SFPA source topology and adjacent EPA, planning, CRO, CSO, funding, enforcement, and welfare context. It captured only bounded browser observations: HSE 72 distinct approval-number nodes, SFPA 184 approved-establishment entries, 50 freezer-vessel entries, and 1 factory-vessel entry. DAFM’s three workbook links were verified from the publication page, but workbook bytes, headers, and counts were not captured. See [Ireland reconnaissance](country-recon-ie.md), the [Ireland crosswalk](countries/ireland/v1-field-crosswalk.json), and the [Ireland artifact manifest](../data/manifests/ireland-source-artifacts.json). All 16 Ireland sources remain publication-blocked; no adapter or release artifact exists.

## Current baseline

| Source ID | Metadata | Acquisition | Runtime health | Publication | Evidence / next action |
|---|---|---|---|---|---|
| `br.sif.registered` | verified | verified | not_run | blocked | Current MAPA SIF registered CSV captured privately with schema/count/hash provenance; repeated activity rows, status semantics, terms, privacy, reconciliation, and project approval remain open; see `docs/country-recon-br.md` |
| `br.sif.export` | verified | verified | not_run | blocked | Current MAPA SIF export-authorized CSV captured privately; model country/product authorizations as dated observations, not facility rows, and complete terms/privacy/reconciliation review; see `docs/country-recon-br.md` |
| `br.sisbi.public` | verified | artifact_private_only | not_run | blocked | Public e-SISBI JSON/GIS routes returned bounded samples; pagination, code lists, ID lifecycle, status/effective-date semantics, terms, privacy, and cadence remain unresolved; see `docs/country-recon-br.md` |
| `br.trase.facilities` | verified | artifact_private_only | not_run | blocked | Current Trase GeoJSON/methodology captured privately as secondary evidence; keep separate from MAPA and review source lineage, geocoding, constructed IDs, terms, privacy, and coverage; see `docs/country-recon-br.md` |
| `be.locations` | verified | artifact_private_only | not_run | blocked | Current official operator/codebook pair parsed privately: 310,660 input, 310,640 normalized, 20 quarantined; names are not supplied by this snapshot and privacy/terms/classification/project approval remain open; see `docs/review-packet-belgium.md` |
| `fr.dgal.section-i` | verified | not_run | not_run | blocked | DGAL Section I private adapter/refresh is implemented; run only with approved terms or authorized capture, then review category semantics, address privacy, schema drift, and release approval |
| `fr.dgal.section-ii` | verified | not_run | not_run | blocked | DGAL Section II remains a separate private adapter/refresh scope; review species/category semantics, address privacy, schema drift, and release approval |
| `it.853-2004` | verified | artifact_private_only | not_run | blocked | Catalog acquisition, shared lifecycle, source-category/activity diagnostics, private candidate import, and guarded API checks remain review-gated; repeated activity identity, coordinate/address privacy, coverage, and project approval remain open; see `docs/review-packet-italy.md` |
| `it.1069-2009` | verified | not_run | not_run | blocked | Separate by-products catalog candidate; no adapter or integration decision; assess scope, schema, terms, identity links, and privacy |
| `mx.locations` | verified | blocked | not_run | blocked | DENUE/SENASICA/DGSIAP reconnaissance; resolve token, directory, terms, and schema |
| `nz.locations` | verified | blocked | not_run | blocked | MPI/Stats NZ reconnaissance; resolve 403/access and aggregate-vs-facility boundaries |
| `uk.locations` | partial | artifact_private_only | unknown | blocked | FSA and FSS private V2 lifecycle paths, nation-qualified identity, coordinate precision states, and synthetic handoff tests pass; no real UK candidate has been imported or previewed; privacy/coordinate, source-rights, duplicate, coverage, and release review remain open; NI/Scotland stay separate; see `docs/review-packet-united-kingdom.md` |
| `dk.smiley` | verified | verified | unknown | blocked | Shared private lifecycle and registered adapter are validated on synthetic/retained evidence with explicit not-observed semantics; coverage/effective-date uncertainty and terms/privacy/release review remain open; see `docs/review-packet-denmark.md` |
| `de.locations` | partial | artifact_private_only | not_run | blocked | Current public general-list export parsed privately: 15,788 input, 2,691 normalized, 13,097 quarantined; session-bound export route, unknown effective date, terms/privacy/coverage and project approval remain unresolved; see `docs/review-packet-germany.md` |
| `ca.ontario.meat-plants` | verified | not_run | not_run | blocked | Ontario private adapter/refresh is implemented; keep plant/contact/coordinate fields restricted pending privacy and licence review, and do not generalize Ontario coverage nationally |
| `ca.cfia.federal-meat` | verified | not_run | not_run | blocked | CFIA federal private adapter/refresh is implemented; validate live export schema/function codes, keep federal scope separate from provincial scope, and retain publication gates |
| `es.locations` | partial | blocked | not_run | blocked | AESAN RGSEAA and MAPA sector routes are documented, but direct acquisition was refused; rights, export/schema, effective dates, sector coverage, privacy, and legacy/source boundaries remain unresolved |
| `us.fsis` | verified | blocked | not_run | blocked | Private adapter and assisted-capture contract are implemented; current CSV access returned 403, so obtain an authorized export and record provenance/schema/privacy/reconciliation before test-only handoff |
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

## Australia additions (2026-09-16)

Australia is represented by 22 source-local evidence layers in `source-status.json` and `pipeline/source_registry.json`. All remain `publication_eligibility=blocked`; no runtime health is claimed. The bounded private artifacts are the NPI CSV (8,140 rows) and the earlier SA EPA GeoJSON capture (4,541 features / 1,695 licences). The detailed route, schema, identity, map/graph, privacy, terms, and blocker crosswalk is [`docs/countries/australia/source-crosswalk.json`](countries/australia/source-crosswalk.json); the decision report is [`docs/country-recon-au.md`](country-recon-au.md).

The machine-readable file is the source of truth for these statuses. Legacy `.locations` paths may represent composite coverage, but source identities are split where the evidence establishes separate feeds: France Section I/II, Canada Ontario/CFIA, Italy 853/2004/1069/2009, and Australia’s state/federal/environment/animal-use layers. Candidate feeds mentioned in reconnaissance documents are not silently conflated into a single healthy source. Country reconnaissance documents provide evidence and next actions; they do not override this status vocabulary or authorize publication.

## Poland additions (2026-09-16)

Poland reconnaissance added GIW approved-food, registered-food, ABP and RRW sources; GUS slaughter statistics; GIOŚ/WIOŚ integrated permits; GDOŚ EIA; Geoportal Urban Register; ARiMR processing support; KRS and REGON identity routes; and the EU TRACES mirror. The GIW HTML views were verified with current displayed counts, but the XLS body was not acquired because shell HTTP was refused and the browser export timed out. The run therefore records a private metadata-only artifact, not a source-data capture. All Poland entries remain `publication_eligibility=blocked`, with runtime health `not_run`; GDOŚ and REGON acquisition are additionally blocked pending the source’s access/authorization conditions. See [`docs/country-recon-pl.md`](country-recon-pl.md), [`docs/countries/pl/source-crosswalk.json`](countries/pl/source-crosswalk.json), and [`data/manifests/pl-source-artifacts.json`](../data/manifests/pl-source-artifacts.json).

## Portugal reconnaissance (2026-09-17)

Portugal adds six source-local scopes: DGAV approved food, DGAV animal by-products, DGAV feed, APA TUA permits, restricted IFAP/DGAV SNIRA animal/holding data, and INE aggregate animal-production statistics. DGAV’s current pages link the +SIPACE listing family and document NCV/NII concepts, while the legacy SIPACE HTML list remains available for consultation during transition. No stable bulk/API export was verified, no row-level artifact was retained, and all six entries remain `publication_eligibility=blocked` with runtime health `not_run`. The recommended next implementation is a private, section-aware assisted capture for `pt.dgav.approved-food`, followed by separately validated ABP/feed sections; SNIRA remains access-controlled and INE remains aggregate-only. See [`docs/country-recon-pt.md`](country-recon-pt.md).
