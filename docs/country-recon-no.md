# Norway source reconnaissance

Status: row-free reconnaissance only. No facility rows, raw exports, coordinates, or production ingestion were retained. Official routes checked 2026-09-16.

## Decision

Norway is a strong medium-effort candidate for automated integration. Mattilsynet publishes approved food/feed/animal-by-product lists as CSV-backed pages, Fiskeridirektoratet exposes aquaculture APIs and a point feature service, Brønnøysundregistrene publishes organization-number APIs, and Statistics Norway (SSB) provides open Statbank APIs. Approval, aquaculture authorization, corporate identity, environmental permits, inspections, and statistics remain separate evidence products.

The required pipeline is fully automated end-to-end: scheduled retrieval, artifact hashing, schema validation, provenance, normalization, privacy/review gates, and guarded ingestion. Browser searches/manual exports are reconnaissance or assisted fallbacks, not production routes.

## Source inventory

| Source | Official route and findings | Cadence / format / identifiers | Location, terms, privacy, automation |
|---|---|---|---|
| Approved animal-origin establishments | [Mattilsynet approved products/businesses](https://www.mattilsynet.no/godkjente-produkter-og-virksomheter), including [Section 0 CSV](https://www.mattilsynet.no/godkjente-produkter-og-virksomheter/food-of-animal-origin-section-0-general-activity-establishment) and [Section VI CSV](https://www.mattilsynet.no/godkjente-produkter-og-virksomheter/food-of-animal-origin-section-VI-meat-products) | Most lists state daily updates; CSV fields include approval-from date, organization/town, activities, associated activities, municipality, approval ID, category and list IDs | Address/town and organization names present; no coordinates observed. Confirm file-specific terms and privacy. Strong candidate, medium effort, drift alarms required. |
| Feed and ABP | [Mattilsynet feed-sector/TSE list](https://www.mattilsynet.no/godkjente-produkter-og-virksomheter/forvarefeed-sector-approved-and-registered-feed-companies-tse) | Sectioned approved/registered lists covering slaughter, processing, PAP and aquaculture feed; CSV/HTML links | Official approval/registration number expected; coordinates unknown. Separate categories; verify terms/completeness. Medium effort. |
| Aquaculture | [Fiskeridirektoratet Aquaculture Register](https://www.fiskeridir.no/registre/akvakulturregisteret), [API catalogue](https://api.fiskeridir.no/catalog/), [locality feature layer](https://gis.fiskeridir.no/server/rest/services/Yggdrasil/Akvakulturregisteret/MapServer/0) | Live public ArcGIS REST Feature Layer; GeoJSON, unique-object-ID enumeration and bounded object-ID batches. Layer metadata allows 2,000 records/query; adapter requests 500/query and WGS84 output. Native CRS EPSG:25833; output coordinates explicitly EPSG:4326. | Fiskeridirektoratet states all data use NLOD and requires source attribution without implying endorsement ([terms](https://www.fiskeridir.no/statistikk-tall-og-analyse/lisens-for-bruk-av-fiskeridirektoratets-data), [NLOD 2.0](https://data.norge.no/nlod/en/2.0)). The locality layer reports registered aquaculture permit localities, not holder mailing addresses. Points remain source-precision-unknown and privacy/release-gated. |
| Farm/intensive agriculture | [Landbruksregisteret](https://www.landbruksdirektoratet.no/nb/jordbruk/kart-og-register/landbruksregisteret) and [farm/livestock statistics](https://www.landbruksdirektoratet.no/nb/statistikk-og-utviklingstrekk/utvikling-i-jordbruket/jordbruksforetak-jordbruksareal-og-husdyr) | Register covers farms, persons, enterprises and national identifiers; public aggregate/downloadable data, but no public facility-level export verified | Property/person relationships are sensitive. Do not infer intensive-farm rows from aggregate reports; blocked pending authorized route. |
| Animal experimentation | [Mattilsynet annual reports](https://www.mattilsynet.no/dyr/forsoksdyr/bruk-av-dyr-i-forsok) | Annual reports; ALURES EEA/EU context; underlying reporting system authenticated | No public research-facility master verified. Keep protocols, institutions and locations separate/aggregated. Medium/high effort. |
| Inspections/enforcement | Mattilsynet approved-business and control surfaces | No national row-level inspection/enforcement API verified | Model events separately from approvals; absence is not closure. High effort/fragmented. |
| Environmental permits/releases | [Norwegian Environment Agency PRTR reference](https://www.miljodirektoratet.no/globalassets/publikasjoner/M138/M138.pdf) | Public route, cadence/API/export unresolved | No national permit master or coordinate route verified. High effort; terms, coverage and sensitive-site review required. |
| Corporate identifiers | [Brønnøysundregistrene open-data API](https://data.brreg.no/enhetsregisteret/api/dokumentasjon/en/index.html) and [Nordic lookup](https://www.brreg.no/en/use-of-data-from-the-bronnoysund-register-centre/datasets-and-api/data-about-nordic-businesses/) | REST JSON, CSV/gzip/XLSX; organization number; update feeds; Nordic lookup requires API key | NLOD 2.0 stated. Identity-only crosswalk; suppress person roles, birth numbers, sole-trader/mixed residential addresses. Low/medium effort. |
| Slaughter and animal-use statistics | [SSB meat production](https://www.ssb.no/en/jord-skog-jakt-og-fiskeri/jordbruk/statistikk/kjotproduksjon), [meat tables](https://www.ssb.no/en/statbank1/list/slakt), [SSB APIs](https://www.ssb.no/en/api), [Mattilsynet animal-use reports](https://www.mattilsynet.no/dyr/forsoksdyr/bruk-av-dyr-i-forsok) | PxWeb/StatBank open API; SSB states CC BY 4.0 and daily update schedule; animal-use annual reports | Aggregate only, no facility coordinates. Preserve table IDs, dimensions and revision markers. Low/medium effort. |

## Automation and release gates

First implementation order: (1) scheduled Mattilsynet section-CSV retrieval; (2) Fiskeridirektoratet aquaculture API/GeoJSON; (3) Brønnøysundregistrene identity crosswalk; (4) SSB aggregates. Require URL/API contract capture, hash/bytes, timestamps, content type, schema fingerprints, pagination checks, approval-ID validation, category preservation, CRS/precision checks, and quarantine on drift. No geocoding or inferred identity is authorized.

### Aquaculture locality layer — bounded private preview, 2026-10-20

The live layer metadata and official licence page were checked over normal
HTTPS. The public layer returned HTTP 200 with ArcGIS JSON metadata; the feature
query returned the complete layer through four bounded GeoJSON pages. The
count-only result and unique object-ID list both contained 1,781 entries, all
of which were retrieved exactly once. Every feature had point geometry within
the broad Norway WGS84 validation envelope; coordinates were checked locally
and are not reproduced here. The layer advertises EPSG:25833 as its native
spatial reference; the query explicitly requested EPSG:4326 output.

The private preview normalized 1,684 animal-locality candidates and quarantined
97 rows: 95 algal-only records and 2 records without a species scope. This is a
source-view observation, not a unique-facility census or a publication count.
The adapter excludes permit-holder names, avoids mailing-address inference,
does not geocode, and keeps the source locality point pending precision,
privacy, and maintainer review. Raw response pages, source IDs, and coordinates
remain only in ignored private staging. The run produced a private candidate
handoff; no release or public exposure was created.

Blockers: file-specific Mattilsynet reuse terms and complete section coverage; exact CSV URLs/headers; aquaculture API versioning beyond the verified layer contract; public farm/intensive-facility scope; inspection/enforcement and environmental permit exports; and research-facility privacy boundaries. Aquaculture publication remains blocked pending privacy, coordinate precision, coverage, and maintainer approval even though acquisition and NLOD attribution terms are documented. Publication remains blocked pending ethics, rights, privacy, coverage, and maintainer approval.

Recommended next country after Norway: Finland, using separate food-authority, aquaculture/farm, environmental, corporate, and statistics routes.
