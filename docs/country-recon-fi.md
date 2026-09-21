# Finland source reconnaissance

Status: row-free reconnaissance only. No facility rows, raw exports, coordinates, or production ingestion were retained. Official routes checked 2026-09-16.

## Decision

Finland is a strong medium-effort candidate. The Finnish Food Authority (Ruokavirasto) publishes approved establishments and animal-sector registers; the Finnish Transport and Communications Agency/Environmental Institute provide environmental and geospatial surfaces; PRH/YTJ provides corporate identifiers; and Statistics Finland exposes PxWeb statistics. Aquaculture, farms, approvals, inspections, permits, and statistics must remain separate evidence products.

The required pipeline is fully automated end-to-end: scheduled retrieval, hashing, schema validation, provenance, normalization, privacy/review gates, and guarded ingestion. Browser-only searches/manual exports are reconnaissance fallbacks, not production routes.

## Source inventory

| Source | Route and findings | Cadence / format / identifiers | Location, terms, privacy, automation |
|---|---|---|---|
| Approved animal-origin establishments/slaughterhouses | [Ruokavirasto approved establishments](https://www.ruokavirasto.fi/en/companies/food-sector/food-establishments/approved-establishments/) and EU approved-establishment context | Authority pages link establishment lists and approval guidance; exact current bulk file/API and section headers require capture | Approval number, operator/site and activity fields expected; address/coordinates unresolved. Verify Finnish/EU reuse terms and mixed-address privacy. Medium effort candidate. |
| Feed and animal-by-products | [Ruokavirasto feed and ABP guidance/register surface](https://www.ruokavirasto.fi/en/companies/feed/) | Register/list formats and cadence require live verification | Keep registration/approval categories separate; no coordinates assumed. Terms and coverage unresolved. Medium/high effort. |
| Farms/intensive agriculture | [Natural Resources Institute Finland (Luke) statistics](https://www.luke.fi/en/statistics) and Finnish agriculture registers | Public statistics are aggregate; a public national intensive-farm facility export was not verified | Farm/property/person data are sensitive. Do not infer facility rows from livestock totals; blocked pending authorized route. |
| Aquaculture | [Luke aquaculture statistics](https://www.luke.fi/en/statistics/aquaculture) and Finnish environmental/geospatial services | Statistics and possible geospatial datasets; current permit/site API not verified | Separate production statistics from licensed sites. Coordinates/terms/API contract unresolved; medium/high effort. |
| Animal experimentation | [Animal Experiment Board / Finnish Food Authority guidance](https://www.ruokavirasto.fi/en/animals/animal-experiments/) | Annual reports/guidance; no public facility master verified | Keep institutions, protocols and locations restricted/aggregated. High privacy and medium/high automation effort. |
| Inspections/enforcement | Ruokavirasto control and food-establishment guidance | Annual/authority reports; no national row-level enforcement API verified | Model observations/events separately from approvals; absence is not closure. High effort/fragmented. |
| Environmental permits/releases | [Finnish Environment Institute](https://www.syke.fi/en-US/Open_information) and environmental permit services | Open environmental datasets/services exist, but a stable national animal-facility permit export was not verified | Verify license, geometry precision, permit identity and sensitive-site exposure. Medium/high effort. |
| Corporate identifiers | [PRH/YTJ open data](https://www.prh.fi/en/uutislistaus/uutiset/2020/P_23520.html) | Organization/business IDs and downloadable/API routes require current access verification | Identity-only crosswalk; suppress personal/sole-trader and residential details. Low/medium effort. |
| Slaughter/animal-use statistics | [Statistics Finland PxWeb](https://stat.fi/en/services/statistical-data-services/statistical-databases) and Luke statistics | Open PxWeb/API or downloads; table IDs, cadence and license need pinning | Aggregate only; preserve dimensions/revisions and do not create facility entities. Low/medium effort. |

## Automation and release gates

First implementation order: verify Ruokavirasto approved-establishment exports, then corporate ID crosswalk and statistics; treat aquaculture/environment as separate adapters. Require URL/API contract capture, hash/bytes, timestamps, content type, schema fingerprints, pagination checks, stable IDs, category preservation, CRS/precision checks, and quarantine on drift. No geocoding or inferred identity is authorized.

Open blockers: current bulk routes and exact schemas for approved food/feed/ABP lists; national farm/intensive-site scope; aquaculture permit/site API; inspection/enforcement and environmental permit exports; research-facility privacy; and source-specific licensing. Publication remains blocked pending ethics, rights, privacy, coverage, and maintainer approval.

Recommended next country after Finland: Estonia, with separate food, agricultural, environmental, corporate and statistics routes.
