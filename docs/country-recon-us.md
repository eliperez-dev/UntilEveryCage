# United States source reconnaissance (V2)

Scope/date: private reconnaissance of checked-in V1 material and current primary routes, observed 2026-09-13 UTC. No row-level names, contacts, addresses, coordinates, or raw artifacts are retained here. This is not publication approval or a healthy-pipeline claim.

## Finding

V1’s “USDA” layer is the FSIS Meat, Poultry and Egg Product Inspection (MPI) Directory, not a generic USDA register. The checked-in `static_data/us/locations.csv` contains 7,101 legacy rows and the older file contains 7,099; this is an inventory comparison, not a validated current-vs-current change. The lab concept is APHIS Animal Care research facilities. APHIS annual-use, inspection-report, and older compiled/scraped artifacts are distinct populations and must not be joined or presented as one dataset.

## Source matrix

| V1 component | Primary route | Evidence / readiness | Caveats and blocker |
|---|---|---|---|
| FSIS establishments/demographics | [FSIS MPI Directory](https://www.fsis.usda.gov/inspection/establishments) and [inspected establishments](https://www.fsis.usda.gov/inspection/fsis-inspected-establishments) | Official page observed in a normal browser on 2026-09-17; current page update observed as 2026-09-14 and three CSV routes exposed, but exact CSV routes returned HTTP 403 to bounded direct acquisition; no current raw hash/bytes claimed | Weekly replacement; FSIS coverage is not all slaughter/processing sites and state programs are separate; use operator-assisted capture contract |
| APHIS research annual use | [Annual Usage Summary](https://www.aphis.usda.gov/awa/research-facility-report/annual-summary), [Public Search Tool](https://direct.aphis.usda.gov/animal-care/awa-services/usda-animal-care-public-search-tool), [annual reports](https://efile.aphis.usda.gov/PublicSearchTool/s/annual-reports) | Official fiscal-year/search routes identified; not privately fetched | Interactive/UI-mediated, no documented bulk API/rate contract; amended annual reports may differ; use sanctioned route only |
| APHIS inspections/registrants | [AWA inspections and annual reports](https://www.aphis.usda.gov/awa/annual-inspection-reports) | Separate public-search/inspection population identified; not reproduced | Redactions/changes and FOIA boundary; absence/presence does not prove operation or violation |

## V1 aggregate crosswalk

Legacy FSIS activity strings are multi-valued and overlap: Meat Slaughter 1,103; Poultry Slaughter 420; Meat Processing 5,479; Poultry Processing 4,212; Egg Product 157; Imported Product 215. These are string-presence counts, not mutually exclusive totals or current coverage. APHIS annual-use rows are fiscal-year reports, not a laboratory census and not equivalent to inspection rows.

## Safe automation boundary

Acquire only official FSIS downloads or documented APHIS public-search/export workflows with UTC retrieval, effective/publication date, byte size, SHA-256, URL, and adapter/config version. Validate content type, signatures, headers, IDs, dates, coordinates, duplicates, and category vocabulary; quarantine HTML/login responses and sharp changes. Preserve raw/parsed layers separately in ignored restricted staging, keep source values/identifiers, avoid names/phones in logs, and never fuzzy-merge FSIS, APHIS annual reports, and inspections. Suppress personal names, direct contacts, residential/private locations, and precise points where ETHICS.md requires. A successful fetch is not publication approval.

## 2026-09-14 FSIS access blocker

The official FSIS MPI Directory route remains the identified source, but the
current CSV links could not be safely acquired on 2026-09-14: ordinary direct
and browser page access returned HTTP 403. Stale 2025 links were not used, and
no artifact, byte count, or hash was retained. This is an access blocker, not
evidence that the source is unavailable or that its terms permit reuse.

Next step: obtain an authorized current FSIS export route or access context,
then privately record the final URL, retrieval time, effective/publication date,
content type, byte size, SHA-256, terms, and schema before any adapter or
publication decision.

## Blockers and recommendation

No safe bounded private fetch was performed, so current hashes/bytes and deterministic reproduction are intentionally unavailable. FSIS is the strongest automation candidate because recurring CSV downloads and source descriptions are available. APHIS is secondary/manual/UI-mediated and should be an explicitly versioned, human-reviewed annual-report adapter or restricted manual input. Do not build a laboratory-supplier layer from APHIS records without a separately identified, licensed source. Existing Selenium/compiler code is not production-grade: obsolete selectors, no provenance manifest, quarantine, terms/schema/privacy gates, and unsafe duplicate handling.

## 2026-09-15 recovery slice

## 2026-09-18 state MPI reconnaissance

FSIS identifies 29 cooperative State Meat and Poultry Inspection programs and
10 states with a Cooperative Interstate Shipment (CIS) overlay. State sources
are not a single national directory: they range from dated PDF/XLSX/CSV/HTML
rosters and interactive maps to contact-mediated licensing routes, and many
mix official inspected, CIS, custom-exempt, retail/handler, warehouse,
rendering, and exemption populations. The row-free state route, identifier,
cadence, scale, access, address/coordinate and automation crosswalk is in
[`docs/countries/us/state-mpi-source-recon.md`](countries/us/state-mpi-source-recon.md).
No state roster or CIS workbook was acquired. State coverage remains
documentation-only and publication-blocked; absence from a later list is
`not_observed`, not closure.

The private implementation is in `pipeline/sources/us/`. FSIS now has a bundle adapter and refresh command with a sanctioned operator-assisted capture contract: one directory export plus the supplemental demographic export are reconciled only by exact source-native IDs/numbers, and source-provided coordinates, slaughter species/activity fields, processing fields, size, and inspection attributes remain private pending review. APHIS now has one adapter with explicit `registrations`, `annual_reports`, and `inspections` profiles. All three APHIS populations remain observations, not a laboratory or facility master, and no identity merge with FSIS is performed.

The row-free V1 inventory and field/category crosswalk is [`docs/countries/us/v1-field-crosswalk.json`](countries/us/v1-field-crosswalk.json). It records 7,101 rows and 269 columns, maps identity/location/contact/administrative/slaughter/processing/inspection-system/derived fields, and records overlapping legacy field-presence counts. Since no authorized current FSIS artifact was available, current-versus-V1 reconciliation remains blocked; the existing exact-key crosswalk reports `not_observed`, never closure.

Focused adapter, lifecycle, registry, status, and contract tests pass. No raw artifact, current source hash, or publication candidate from a real US source was created. Publication remains blocked pending authorized capture, terms, schema, privacy, coverage, review, and test-only import checks.

## 2026-09-18 US real-data proof boundary

The official MPI page was re-observed in the normal in-app browser. It showed
`Last Updated: Sep 14, 2026`, the directory-by-name CSV, directory-by-number
CSV, and establishment-demographic CSV, plus a Tableau dashboard updated
`9/14/2026 2:30:33 PM`. The dashboard's aggregate count export showed 7,241
establishments. This is a current aggregate observation only; it is not a
replacement for the row-level CSV bundle.

The two direct CSV routes still returned HTTP 403 to a bounded read-only
request. No access-control bypass was attempted. The current-source manifest
therefore remains `not_captured`, and current row-level totals, current
coordinates, current species/activity distributions, and current-vs-V1
identity continuity remain `not_observed` rather than zero or closure
evidence.

For continuity and private pipeline proof only, the retained legacy FSIS
directory plus demographic snapshot was rerun through the bundle adapter. It
contained 7,099 directory rows and 7,105 demographic rows; 7,089 demographic
rows matched exact source-native IDs/numbers, 16 were orphaned, and 3 had
identity conflicts. The private lifecycle produced 7,096 normalized rows and
19 quarantined rows (`conflicting_demographic_identity`: 3,
`unmatched_demographic_identity`: 16). The run kept raw, parsed, normalized,
quarantined, and handoff layers separate, retained SHA-256/byte provenance,
disabled geocoding, and kept `release_state=not-created`,
`publication_state=private-candidate`, and publication blocked. These numbers
describe the retained legacy snapshot, not the September 2026 source.

The bundle join now indexes exact native keys before reconciliation, and the
handoff records both the importer-verifiable directory artifact and the
separate bundle/file provenance. This fixes the real-bundle candidate handoff
path without changing identity semantics or publication gates.

The disposable candidate runner reached the test-only preview after the full
first import, confirming that candidate rows were not visible through the
ordinary public profile. Its row-level replay and teardown exceeded the
practical execution window, so the import evidence is recorded as partial;
no database or release was retained, and no public promotion occurred.
