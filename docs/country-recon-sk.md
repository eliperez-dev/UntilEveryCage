# Slovakia source reconnaissance

Status: row-free reconnaissance only. No facility rows, raw exports, coordinates, or production ingestion retained. Official routes checked 2026-09-16.

## Decision

Slovakia is a strong medium-effort candidate. The State Veterinary and Food Administration (ŠVPS/SVFA) publishes current approved food, ABP, veterinary, aquaculture and farm-related lists with dated updates; datasets and regional registers provide additional machine-readable routes. Corporate, environmental and statistical sources require separate verification.

The pipeline must be fully automated from scheduled retrieval through hashing, validation, provenance, normalization, privacy/review gates, and guarded ingestion. Browser-only/manual exports are fallbacks only.

## Source inventory

| Source | Route/findings | Format/cadence/IDs | Privacy/automation |
|---|---|---|---|
| Approved food/slaughter/ABP | [SVPS approved lists](https://zoznamy.svps.sk/?LANG=EN) and [SVPS datasets](https://svps.sk/datasety/) | Filtered lists expose dated updates; EU food, veterinary, ABP and feed categories; XSL/XLSX/list formats | Approval number, category/activity, town/region and address likely. Strong candidate, medium effort; verify direct downloads, terms and privacy. |
| Farms/aquaculture | SVPS datasets include aquaculture/farm categories and animal registers | Current export/API and coordinate fields unresolved | Treat holdings/owners as sensitive; no inferred rows. Medium/high effort. |
| Inspections/enforcement/experiments | SVPS control and animal-welfare systems | Public route not fully verified | Keep dated events/annual aggregates separate; high privacy. |
| Environment/corporate/statistics | National environmental permit, business-register and statistical portals require route verification | IDs/formats/cadence unresolved | Separate evidence products; identity-only crosswalk and aggregate statistics. |

## Gates

First implementation order: SVPS approved-list exports, then farm/aquaculture datasets and official statistics. Require contract capture, hashes/bytes, timestamps, content type, schema fingerprints, pagination/count checks, stable IDs, category preservation and drift quarantine. No geocoding or inferred identity authorized.

Blockers: direct file/API contracts, licensing, farm/aquaculture coverage, inspections/experimentation, environmental permits, corporate access and privacy/release review. Publication remains blocked pending ethics, rights, privacy, coverage and maintainer approval.

Recommended next country after Slovakia: Slovenia.
