# United States source reconnaissance (V2)

Scope/date: private reconnaissance of checked-in V1 material and current primary routes, observed 2026-09-13 UTC. No row-level names, contacts, addresses, coordinates, or raw artifacts are retained here. This is not publication approval or a healthy-pipeline claim.

## Finding

V1’s “USDA” layer is the FSIS Meat, Poultry and Egg Product Inspection (MPI) Directory, not a generic USDA register. The checked-in `static_data/us/locations.csv` contains 7,101 legacy rows and the older file contains 7,099; this is an inventory comparison, not a validated current-vs-current change. The lab concept is APHIS Animal Care research facilities. APHIS annual-use, inspection-report, and older compiled/scraped artifacts are distinct populations and must not be joined or presented as one dataset.

## Source matrix

| V1 component | Primary route | Evidence / readiness | Caveats and blocker |
|---|---|---|---|
| FSIS establishments/demographics | [FSIS MPI Directory](https://www.fsis.usda.gov/inspection/establishments) and [inspected establishments](https://www.fsis.usda.gov/inspection/fsis-inspected-establishments) | Official page exposes downloadable CSV directory/demographic files and documentation; not privately fetched and no hash/bytes claimed | Weekly replacement; no API/rate contract verified; FSIS coverage is not all slaughter/processing sites and state programs are separate |
| APHIS research annual use | [Annual Usage Summary](https://www.aphis.usda.gov/awa/research-facility-report/annual-summary), [Public Search Tool](https://direct.aphis.usda.gov/animal-care/awa-services/usda-animal-care-public-search-tool), [annual reports](https://efile.aphis.usda.gov/PublicSearchTool/s/annual-reports) | Official fiscal-year/search routes identified; not privately fetched | Interactive/UI-mediated, no documented bulk API/rate contract; amended annual reports may differ; use sanctioned route only |
| APHIS inspections/registrants | [AWA inspections and annual reports](https://www.aphis.usda.gov/awa/annual-inspection-reports) | Separate public-search/inspection population identified; not reproduced | Redactions/changes and FOIA boundary; absence/presence does not prove operation or violation |

## V1 aggregate crosswalk

Legacy FSIS activity strings are multi-valued and overlap: Meat Slaughter 1,103; Poultry Slaughter 420; Meat Processing 5,479; Poultry Processing 4,212; Egg Product 157; Imported Product 215. These are string-presence counts, not mutually exclusive totals or current coverage. APHIS annual-use rows are fiscal-year reports, not a laboratory census and not equivalent to inspection rows.

## Safe automation boundary

Acquire only official FSIS downloads or documented APHIS public-search/export workflows with UTC retrieval, effective/publication date, byte size, SHA-256, URL, and adapter/config version. Validate content type, signatures, headers, IDs, dates, coordinates, duplicates, and category vocabulary; quarantine HTML/login responses and sharp changes. Preserve raw/parsed layers separately in ignored restricted staging, keep source values/identifiers, avoid names/phones in logs, and never fuzzy-merge FSIS, APHIS annual reports, and inspections. Suppress personal names, direct contacts, residential/private locations, and precise points where ETHICS.md requires. A successful fetch is not publication approval.

## Blockers and recommendation

No safe bounded private fetch was performed, so current hashes/bytes and deterministic reproduction are intentionally unavailable. FSIS is the strongest automation candidate because recurring CSV downloads and source descriptions are available. APHIS is secondary/manual/UI-mediated and should be an explicitly versioned, human-reviewed annual-report adapter or restricted manual input. Do not build a laboratory-supplier layer from APHIS records without a separately identified, licensed source. Existing Selenium/compiler code is not production-grade: obsolete selectors, no provenance manifest, quarantine, terms/schema/privacy gates, and unsafe duplicate handling.
