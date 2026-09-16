# Latvia source reconnaissance

Status: row-free reconnaissance only. No facility rows, raw exports, coordinates, or production ingestion retained. Official routes checked 2026-09-16.

## Decision

Latvia is a strong medium-effort candidate. The Food and Veterinary Service (PVD/FVS) publishes machine-readable approved/registered enterprise data and many XLSX lists; the Agricultural Data Centre/LDC exposes slaughterhouse and livestock registers; the environmental authority publishes permit datasets; and the official statistics portal provides a machine-readable API. Farm and aquaculture locations require separate privacy treatment.

The pipeline must be fully automated from scheduled retrieval through hashing, validation, provenance, normalization, privacy/review gates, and guarded ingestion. Browser-only/manual exports are fallbacks, not production routes.

## Source inventory

| Source | Route and findings | Cadence / format / identifiers | Location, terms, privacy, automation |
|---|---|---|---|
| Approved food/slaughter establishments | [PVD/FVS registers](https://registri.pvd.gov.lv/en/cr) and [machine-readable enterprise export](https://pakalpojumi.pvd.gov.lv/en/opendata_files/ipvd_object_opendata) | PVD lists animal-origin Sections 0–XV and ABP/feed categories as XLSX; enterprise register offers `ur-csv.zip`, free and machine-readable | Approval/registration IDs, operator/activity/address expected; coordinates unresolved. Strong candidate, medium effort; verify CC/terms and suppress mixed residential addresses. |
| Slaughterhouses | [LDC public slaughterhouse register](https://registri.ldc.gov.lv/en/slaughterhouses) | Public filtered register; exact export/API/cadence unresolved | Separate from PVD approval lists; verify stable IDs, address and terms. Medium/high effort. |
| Farms/intensive agriculture | [LDC registers](https://registri.ldc.gov.lv/) and agricultural statistics | Herd/location register and livestock statistics are exposed; public facility export scope requires verification | Animal-holder/property data can identify individuals and sensitive sites. Do not ingest rows until authorization/privacy review. |
| Aquaculture | Official aquaculture establishment lists are linked through PVD/LDC registers | XLSX/list routes exist but current direct contract unresolved | Treat locations and permits separately; coordinates/terms require capture. Medium effort after contract verification. |
| Environment/permits | [Environmental permits dataset](https://data.gov.lv/dati/dataset/izsniegtas-atlaujas-un-licences) and [VVD registers](https://www.vvd.gov.lv/lv/registri) | Dataset states CC0 1.0; public online registers include permits, environmental decisions and inspections | Strong permit candidate; verify resource schema, cadence, identifiers and geometry. Medium effort. |
| Animal experimentation/inspections | PVD and official veterinary-control surfaces | No stable national public animal-use facility master or row-level inspection API verified | Keep research and enforcement as dated aggregate/events; high privacy and fragmented route risk. |
| Corporate identifiers | Latvian enterprise register route; current public API contract not verified | Registration number expected stable; format/auth unresolved | Identity-only crosswalk; suppress personal/sole-trader data. Medium effort. |
| Slaughter/statistics | [Official Statistics Portal API v2](https://stat.gov.lv/en/api-un-kodu-vardnicas/api-v2) | API supports XLSX, CSV, JSON, JSON-stat2 and PX; max 10,000 cells/request and 30 requests/10 seconds/IP | [Animal production metadata](https://stat.gov.lv/en/meta/21203) and LDC statistics are aggregate. Low/medium effort; preserve table IDs/revisions. |

## Gates

First implementation order: PVD enterprise/approved XLSX/ZIP routes, environmental CC0 datasets, then LDC slaughter and statistics. Require URL/API contract, hash/bytes, timestamps, content type, schema fingerprints, pagination/count checks, stable IDs, category preservation and quarantine on drift. No geocoding or inferred identity is authorized.

Blockers: PVD list/version semantics and terms, LDC export/API, farm/aquaculture privacy and coverage, research/inspection routes, corporate API access, and environmental resource schemas. Publication remains blocked pending ethics, rights, privacy, coverage and maintainer approval.

Recommended next country after Latvia: Lithuania, using separate food, farm/aquaculture, environmental, corporate and statistics sources.
