# Czechia source reconnaissance

Status: row-free reconnaissance only. No facility rows, raw exports, coordinates, or production ingestion retained. Official routes checked 2026-09-16.

## Decision

Czechia is a medium-effort candidate. The State Veterinary Administration (SVS) publishes registered and approved establishment lists, including EU food, ABP, feed and aquaculture categories; the government and statistical registers provide corporate and aggregate statistics; environmental permits require separate registry work.

The pipeline must be fully automated from scheduled retrieval through hashing, validation, provenance, normalization, privacy/review gates, and guarded ingestion. Browser-only/manual exports are fallbacks only.

## Source inventory

| Source | Route/findings | Format/cadence/IDs | Privacy/automation |
|---|---|---|---|
| Approved food/slaughter establishments | [SVS registered/approved establishments](https://en.svs.gov.cz/registered-subjects/) | Lists cover EU food, conditional approval, ABP, feed-related, transport and aquaculture; filters and update dates are exposed, exact bulk contract requires capture | Approval number, activity, region and address expected; no coordinates verified. Strong candidate, medium effort; confirm terms/privacy. |
| Farms/intensive/aquaculture | SVS animal registers and [aquaculture list category](https://en.svs.gov.cz/registered-subjects/) | Public aquaculture/animal establishment categories; national intensive-farm export not verified | Treat holdings and locations as sensitive; no inferred rows. Medium/high effort. |
| Inspections/enforcement and experiments | SVS control/animal-welfare surfaces | No stable national public facility-level experiment/enforcement dataset verified | Keep events/annual aggregates separate; high privacy. |
| Environmental permits | Czech environmental permit/document routes require separate verification | Format/API/cadence unresolved | High effort; verify identifiers, geometry, licensing and sensitive sites. |
| Corporate/statistics | [gov.cz statistical registers](https://portal.gov.cz/sluzby-vs/ziskani-zverejnenych-informaci-ze-statistickych-registru-S4953) and Czech Statistical Office | Open CSV/company register exports and official aggregate tables; table/API contracts require pinning | Identity-only corporate crosswalk; aggregate slaughter/animal-use statistics separate. Medium effort. |

## Gates

First implementation order: SVS approved-establishment exports, then corporate/statistics sources. Require URL/API contract, hash/bytes, timestamps, content type, schema fingerprints, pagination/count checks, stable IDs, category preservation and quarantine on drift. No geocoding or inferred identity authorized.

Blockers: exact SVS file URLs/headers/terms, farm/aquaculture coverage, public inspections/experiments, environmental permit API, corporate access, and privacy/release review. Publication remains blocked pending ethics, rights, privacy, coverage and maintainer approval.

Recommended next country after Czechia: Slovakia, using separate veterinary, farm, environmental, corporate and statistics authorities.
