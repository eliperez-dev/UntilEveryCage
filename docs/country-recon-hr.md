# Croatia source reconnaissance

Status: row-free reconnaissance only; no facility rows, raw exports, or production ingestion artifacts are committed.

## Scope and automation requirement

Croatia has a useful official open-data surface for animal-origin establishments, aquaculture permits, environmental permits, business identity, and aggregate statistics. The production pipeline must remain fully automated from source discovery/scraping through acquisition, validation, normalization, provenance, quarantine, and ingestion; this reconnaissance does not authorize publication or replace maintainer review.

## Strongest candidates

| Source | Verified surface | Automation assessment | Main unresolved items |
| --- | --- | --- | --- |
| `hr.approved-food` | National CKAN catalogue exposes an approved animal-origin food-establishment register as a public WEB resource, and related registered-establishment data as XLS. | Medium: catalogue discovery can be automated; WEB/export contract needs probing. | Stable direct URL, schema, update cadence, approval IDs, address/coordinate semantics, license and privacy. |
| `hr.aquaculture-permits` | CKAN exposes the Ministry aquaculture permit register as XLS and states the ministry maintains and publishes it under the Aquaculture Act. | Low–medium: scheduled XLS retrieval and hash/version tracking are plausible. | Direct resource URL, schema, cadence, identifiers, coordinates and terms. |
| `hr.environment-permits` | National CKAN lists environmental permit/decision registers, including integrated environmental conditions. | Medium–high: CKAN metadata/resources are machine-discoverable, but documents may require extraction. | Current publisher, complete animal-facility coverage, document/API route, geometry, licensing and privacy. |
| `hr.business-register` | Croatian Court Register provides a public API surface with MBS, OIB, status, company, registered office/address and legal form; registration is required. | Medium: REST XML/JSON ingestion is automatable after account credentials are provisioned. | Credentials/quotas, terms, legal-person-only matching and address-use policy. |
| `hr.statistics` | Croatian Bureau of Statistics publishes official statistical registers and data services; CKAN includes business-register time series. | Low–medium for aggregates: table/API identifiers and revision metadata must be pinned. | Slaughter and animal-use table IDs, API contracts, cadence, licensing and aggregate-only handling. |
| `hr.inspections-experiments` | State Inspectorate and Ministry/official statistical surfaces identify control and animal-experimentation responsibilities. | High for reports/aggregates; low for facility-level extraction until a public register is confirmed. | Public facility/event route, stable IDs, publication scope, privacy and retention constraints. |

## Compliance and ingestion notes

- Treat catalogue metadata as government-sourced evidence, not project approval or proof of current operation.
- Preserve source URL, retrieval timestamp, content hash, byte size, supplied publication/effective date, adapter/configuration version, and source values.
- Keep raw, parsed, normalized, enriched, reviewed, and released layers separate. Use synthetic fixtures only; do not commit rows or raw artifacts.
- Represent unavailable cadence, coordinates, IDs, licensing, and privacy decisions explicitly. A missing source snapshot means “not observed,” not closure.
- Facility addresses and coordinates require privacy/safety screening; corporate registered offices are not automatically operating sites.
- Candidate adapters should fail closed on changed schemas, missing IDs, suspicious count changes, and inaccessible resources, retaining the previous validated release.

## Official evidence

- [Croatian CKAN agriculture organization](https://data.gov.hr/ckan/en/organization/ministarstvo-poljoprivrede?_tags_limit=0&publisher_type=public_sector&tags=poljopriveda)
- [Approved animal-origin food establishments dataset](https://data.gov.hr/ckan/en/dataset/upisnik-odobrenih-objekata-u-poslovanju-s-hranom-za-zivotinje)
- [Aquaculture permits dataset](https://data.gov.hr/ckan/hr/dataset/registar-dozvola-u-akvakulturi)
- [Sanitary food-register guidance](https://inspektorat.gov.hr/ustrojstvo-77/7-sektor-sanitarne-inspekcije/evidentiranje-i-vodjenje-registra-subjekta-i-pripadajucih-objekta-u-poslovanju-s-hranom-iz-nadleznosti-iz-nadleznosti-sanitarne-inspekcije/431)
- [Court Register public API](https://sudreg-data.gov.hr/ords/r/srn_rep/vanjski-srn-rep/home)
- [Croatian Bureau of Statistics publishing programme](https://dzs.gov.hr/usluge/objavljivanje/program-publiciranja-2026/2439)

## Effort and blockers

Initial source reconnaissance: approximately 2–4 engineering days to pin the approved-food and aquaculture routes, build deterministic acquisition/validation adapters, and produce sanitized fixtures; 3–7 additional days for environmental-document extraction and inspection/animal-experimentation coverage. The main blockers are unstable or undocumented resource URLs, undefined refresh cadence, possible registration/authentication for the Court Register API, and unresolved privacy/licensing/coordinate semantics.

Recommended next country: Romania, subject to checking the existing country inventory before delegation.
