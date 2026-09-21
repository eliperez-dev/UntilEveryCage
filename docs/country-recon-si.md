# Slovenia source reconnaissance

Status: row-free reconnaissance only. No facility rows, raw exports, coordinates, or production ingestion retained. Official routes checked 2026-09-16.

## Decision

Slovenia is a strong medium-effort candidate. UVHVVR publishes approved food/feed registers and animal-sector systems; OPSI exposes agricultural datasets; environmental and statistical portals provide separate permit and slaughter evidence. Farm, aquaculture, experimentation, inspection and corporate data require distinct privacy and access review.

The pipeline must be fully automated from scheduled retrieval through hashing, validation, provenance, normalization, privacy/review gates, and guarded ingestion. Browser/manual exports are fallbacks only.

## Source inventory

| Source | Route/findings | Format/cadence/IDs | Privacy/automation |
|---|---|---|---|
| Approved food/slaughter establishments | [GOV.SI approved food establishment service](https://www.gov.si/zbirke/storitve/odobritev-zivilskega-obrata/) | Official approved-establishment PDF/list routes; current direct file/API and update cadence require capture | Approval numbers, activity and address expected; no coordinates assumed. Medium effort; verify terms/privacy. |
| Feed | [GOV.SI feed business registers](https://www.gov.si/teme/poslovanje-s-krmo/) | Approved/registered lists, current PDF updates | Separate feed categories; PDF extraction brittle; verify reuse and addresses. Medium/high effort. |
| Farms/aquaculture | [OPSI agricultural datasets](https://podatki.gov.si/) and UVHVVR animal registers | Public datasets include animal/holding registers; exact current farm/aquaculture export must be verified | Holding/property/person data sensitive; no facility rows without authorization. Medium/high effort. |
| Inspections/experiments/environment | UVHVVR systems and environmental permit routes | Public control/permit contracts unresolved | Model events/documents separately; high privacy/coverage risk. |
| Statistics/corporate | [Slovenia livestock slaughter PxWeb](https://pxweb.stat.si/SiStatData/pxweb/en/Data/-/H202S.px) and national business register | PxWeb annual slaughter table; corporate identifier route requires verification | Aggregate stats and identity-only crosswalk. Low/medium statistics effort. |

## Gates

First implementation order: approved food/feed lists, then PxWeb statistics and reviewed agricultural datasets. Require contract capture, hashes/bytes, timestamps, schema fingerprints, stable IDs, category preservation, CRS/precision checks and drift quarantine. No geocoding or inferred identity authorized.

Blockers: exact files/API/terms, farm/aquaculture scope, inspections/experiments, environmental permits, corporate access, and privacy/release approval. Publication remains blocked pending ethics, rights, privacy, coverage and maintainer approval.

Recommended next country after Slovenia: Croatia.
