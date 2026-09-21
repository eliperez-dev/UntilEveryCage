# Estonia source reconnaissance

Status: row-free reconnaissance only. No facility rows, raw exports, coordinates, or production ingestion retained. Official routes checked 2026-09-16.

## Decision

Estonia is a strong medium-effort candidate. The Agriculture and Food Board (PTA) exposes approved/registered food and animal-sector registers; PRIA publishes public animal-register and geospatial establishment data; Keskkonnaamet exposes environmental permit systems; Äriregister provides corporate identifiers; and Statistics Estonia provides PxWeb tables. Approval, farm location, aquaculture, permits, inspections, corporate identity, and statistics must remain separate evidence products.

The pipeline must be fully automated from scheduled retrieval through hashing, validation, provenance, normalization, privacy/review gates, and guarded ingestion. Browser-only/manual exports are fallbacks, not production routes.

## Source inventory

| Source | Official route and findings | Cadence / format / identifiers | Location, terms, privacy, automation |
|---|---|---|---|
| Approved food/slaughter establishments | [PTA registers and datasets](https://pta.agri.ee/riiklikud-registrid-ja-andmekogud) provides notified/licensed food operators and animal-sector lists; EU approved-establishment links are also surfaced | Current list/download formats require capture; approval/registry numbers, operator, activity and address expected | Verify current CSV/XLSX/API and licence. Medium effort; names/addresses need privacy review. |
| Farms and intensive animal sites | [PRIA public data](https://www.pria.ee/registrid/avalikud-andmed) and [spatial-data documentation](https://www.pria.ee/sites/default/files/2024-06/pindalatoetuste_ja_loomade_registri_tegevuskohade_ruumiandmed_25062024.pdf) | Public establishment data include location ID, activity/status, registration number, county/municipality/address, coordinates and species; prior-day data is described | Strong candidate but animal/property data can expose sensitive locations. Verify current download/service, CRS, terms and field suppression; medium/high effort. |
| Aquaculture | PRIA animal-register public establishment data; EU veterinary registers for approved sites | Same register categories include aquaculture establishments; current aquaculture-specific bulk contract unresolved | Keep aquaculture separate from farms/food approvals; no inferred rows. |
| Animal experimentation | PTA/official animal-welfare and research guidance | No public facility master or stable animal-use statistics route verified | High privacy; keep research institutions/protocols aggregated and separate. |
| Inspections/enforcement | PTA register/control surface and official notices | No national row-level inspection/enforcement export verified | Model events separately; absence is not closure. High effort/fragmented. |
| Environmental permits | [Keskkonnaamet permit notices/KOTKAS](https://keskkonnaamet.ee/keskkonnateadlikkus-avalikustamised/raagi-kaasa/lubade-eelnoude-avalik-valjapanek) | KOTKAS contains post-2017 complex permits and post-2020 environmental permits; searchable documents, cadence route-specific | Strong permit evidence candidate but UI/document extraction is high effort. Verify terms, identifiers, geometry and sensitive-site exposure. |
| Corporate identifiers | Estonian commercial register / Äriregister route; current public API contract not verified in this pass | Business registry code is expected stable identifier; format/auth unresolved | Identity-only crosswalk; suppress personal/sole-trader/residential data. Medium effort. |
| Slaughter/animal-use statistics | [Statistics Estonia PM190](https://andmed.stat.ee/en/stat/majandus__pellumajandus__pellumajandussaaduste-tootmine__loomakasvatussaaduste-tootmine/PM190) and [livestock statistics metadata](https://stat.ee/et/metaandmed/21203) | PM190 is monthly slaughter in approved meat establishments; Statistics Estonia open data states CC BY-SA 4.0; PxWeb route/table IDs require pinning | Aggregate only; preserve dimensions/revisions. Low/medium effort. |

## Automation and gates

First implementation order: verify PTA approved-establishment exports, then PRIA establishment geospatial/public data, corporate IDs, and Statistics Estonia aggregates. Require URL/API contract, hash/bytes, timestamps, content type, schema fingerprints, pagination/count checks, stable IDs, CRS/precision checks and quarantine on drift. No geocoding or inferred identity is authorized.

Blockers: current PTA bulk routes and terms; PRIA current service/download contract and privacy/CRS semantics; aquaculture-specific scope; public research/inspection routes; environmental document extraction; and corporate API access. Publication remains blocked pending ethics, rights, privacy, coverage, and maintainer approval.

Recommended next country after Estonia: Latvia, using separate food, farm/aquaculture, environmental, corporate and statistics authorities.
