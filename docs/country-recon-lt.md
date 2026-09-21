# Lithuania source reconnaissance

Status: row-free reconnaissance only. No facility rows, raw exports, coordinates, or production ingestion retained. Official routes checked 2026-09-16.

## Decision

Lithuania is a strong medium-effort candidate. VMVT publishes open machine-readable veterinary-control and food-establishment data; the national open-data portal exposes API/CSV/JSON/JSONL resources; PRIA-equivalent agricultural registers and environmental permit systems provide separate farm/environment evidence; and Statistics Lithuania provides official statistical tables. Approval, farm/aquaculture, permits, inspections, corporate identity, and statistics remain distinct.

The pipeline must be fully automated from scheduled retrieval through hashing, validation, provenance, normalization, privacy/review gates, and guarded ingestion. Browser/manual exports are fallbacks only.

## Source inventory

| Source | Route/findings | Format/cadence/IDs | Privacy/automation |
|---|---|---|---|
| Approved food/slaughter establishments | [VMVT open data/registers](https://vmvt.lrv.lt/lt/atviri-vmvt-duomenys-ir-registrai/atviri-duomenys/) and [open control dataset](https://data.gov.lt/dataset/valstybines-veterinarines-kontroles-subjektai) | Public food/animal-origin registers; dataset offers API, CSV, JSON and JSONL; update cadence varies | Contains subject IDs, approval/registration numbers, activity, address and geolocation. Strong candidate, medium effort; verify current terms and suppress personal/mixed addresses. |
| Farms/intensive agriculture/aquaculture | [PRIA public data](https://www.pria.ee/registrid/avalikud-andmed) is Estonia; Lithuania’s VMVT open animal registers expose herd/control data | Current Lithuanian facility export and farm coordinate contract require capture | Treat animal-holder/property data as sensitive; no inferred farm rows. Medium/high effort. |
| Environmental permits | Lithuanian environmental permit/open-data routes require verification | Format/cadence/IDs unresolved | Keep permits separate; high effort until stable bulk/API route. |
| Animal experimentation | VMVT/official animal-welfare guidance | No public facility master verified | Aggregate and anonymize; high privacy. |
| Inspections/enforcement | VMVT open control dataset includes inspection and subject identifiers, dates, deviations and measures | API/CSV/JSON/JSONL; variable update cadence | Model dated events separately from approvals; medium effort after schema/version validation. |
| Corporate identifiers | Lithuanian JAR/company register route, current public API not verified | Legal-person code expected stable | Identity-only crosswalk; suppress personal/sole-trader/residential data. Medium effort. |
| Slaughter/statistics | Statistics Lithuania official PxWeb tables; VMVT annual control reports | Machine-readable statistical tables; table IDs/cadence require pinning | Aggregate only; preserve revisions/dimensions. Low/medium effort. |

## Gates

First implementation order: VMVT approved/control API resources, then statistics and reviewed corporate identity links. Require URL/API contract, hash/bytes, timestamps, content type, schema fingerprints, pagination/count checks, stable IDs, category preservation, coordinate CRS/precision checks and quarantine on drift. No geocoding or inferred identity authorized.

Blockers: exact VMVT resource contracts/terms, farm/aquaculture coverage, environmental permits, research facilities, corporate API access and publication/privacy review. Publication remains blocked pending ethics, rights, privacy, coverage and maintainer approval.

Recommended next country after Lithuania: Poland, using separate food, farm, environment, corporate and statistics authorities.
