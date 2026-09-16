# Romania source reconnaissance

Status: row-free reconnaissance only; no facility rows, raw exports, or production ingestion artifacts are committed.

## Scope and automation requirement

Romania exposes relevant official surfaces through data.gov.ro, ANSVSA/DSVSA veterinary systems, ANPM environmental systems, ONRC corporate data, and INSSE statistics. The production pipeline must be fully automated from source discovery/scraping through acquisition, validation, normalization, provenance, quarantine, and ingestion. This reconnaissance does not authorize publication or replace maintainer review.

## Strongest candidates

| Source | Verified surface | Automation assessment | Main unresolved items |
| --- | --- | --- | --- |
| `ro.ansvsa.approved-food` | ANSVSA is the competent veterinary authority; national open-data/search surfaces and EU approval frameworks are relevant to approved animal-origin establishments and slaughterhouses. | Medium–high if a stable list/export is confirmed; otherwise portal/browser automation may be required. | Current national list/API, approval IDs, activity/status semantics, addresses/coordinates, cadence, license and privacy. |
| `ro.farm-aquaculture` | Romanian agriculture/open-data catalogues expose agriculture records; ANPM IBIS includes official “Crescătorii”/authorizations surfaces, while aquaculture permit coverage needs authority confirmation. | Medium for catalogued files; low–medium for authenticated or legacy portals. | National farm/holding register scope, aquaculture permit export, stable IDs, coordinates, terms and privacy. |
| `ro.environment-permits` | ANPM’s SIM/eFORM is an official environmental authorization system with operator, work-point, coordinates and authorization fields; ANPM currently reports the integrated system as technically nonfunctional. | Medium once public read access is restored; currently blocked for dependable automated acquisition. | Public read/export API, completeness, document route, current availability, license and geometry semantics. |
| `ro.onrc.organizations` | data.gov.ro publishes ONRC company snapshots as CSV, including registered-office, status and authorized-activity information; the catalogue exposes CKAN API metadata. | High for scheduled CSV snapshots and hash/version tracking. | Current snapshot cadence, field dictionary, OIB/CUI linkage, registered-office privacy and license scope. |
| `ro.insse.statistics` | INSSE is the official statistical authority; Romanian official statistics provide aggregate livestock/slaughter and related animal-use context. | Medium–high for table/API downloads after table IDs are pinned. | Exact current table IDs/API, cadence, revisions, licensing and aggregate-only handling. |
| `ro.inspections-experiments` | ANSVSA/DSVSA and ANPM systems support official control/authorization workflows; a public facility-level animal-experimentation master was not verified. | High for published aggregate reports; low for facility-level extraction until a public route is confirmed. | Public event/facility register, stable IDs, inspection outcomes, animal-use categories, privacy and retention. |

## Compliance and ingestion notes

- Treat government portals and catalogue records as government-sourced evidence, not proof of current operation or project approval.
- Preserve source URL, retrieval timestamp, content hash, byte size, supplied publication/effective date, adapter/configuration version, and source values.
- Keep raw, parsed, normalized, enriched, reviewed, and released layers separate. Use synthetic fixtures only; do not commit rows or raw artifacts.
- Represent unavailable cadence, IDs, coordinates, licensing, and privacy decisions explicitly. A source outage or disappearance means “not observed,” not closure.
- Registered offices, operator addresses, farms, and work points are not automatically safe public facility locations; apply privacy and safety review before any coordinates or addresses are released.
- Adapters must fail closed on changed schemas, missing identifiers, suspicious count changes, and authentication/service failures, retaining the previous validated release.

## Official evidence

- [Romanian national open-data catalogue](https://data.gov.ro/)
- [ONRC company snapshots and CKAN API surface](https://data.gov.ro/dataset?organiza=&organization=onrc&res_format=csv)
- [ANSVSA veterinary portal](https://portal.ansvsa.ro/)
- [ANPM integrated environmental system](https://raportare.anpm.ro/)
- [ANPM system status notice](https://raportare.anpm.ro/irj/servlet/prt/portal/prteventname/Navigate/prtroot/pcd%213aportal_content%212fevery_user%212fgeneral%212fdefaultAjaxframeworkContent)
- [INSSE official statistics portal](https://insse.ro/cms/)

## Effort and blockers

Initial reconnaissance: approximately 2–4 engineering days to pin ONRC snapshots and any approved-establishment/aquaculture exports, then build deterministic acquisition and validation adapters; 4–8 additional days for ANPM document/API recovery and inspection/animal-experimentation coverage. Main blockers are the absence of a clearly documented national ANSVSA bulk/API contract, authenticated or legacy environmental systems, ANPM’s reported outage, unresolved update cadence, and privacy/licensing/coordinate semantics.

Recommended next country: Bulgaria, subject to checking the existing country inventory before delegation.
