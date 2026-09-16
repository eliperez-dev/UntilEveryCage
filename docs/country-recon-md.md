# Moldova source reconnaissance

Status: row-free reconnaissance only; no facility rows, raw exports, or production ingestion artifacts are committed.

## Scope and automation requirement

Moldova has a strong national food-safety authority surface through ANSA, supported by environmental, statistical and Public Services Agency systems. The production pipeline must be fully automated from source discovery/scraping through acquisition, validation, normalization, provenance, quarantine, and ingestion. This reconnaissance does not authorize publication or replace maintainer review.

## Strongest candidates

| Source | Verified surface | Automation assessment | Main unresolved items |
| --- | --- | --- | --- |
| `md.ansa.approved-food` | ANSA publishes authorized animal-origin food units by categories including meat, fish, dairy, eggs, honey, small producers and slaughter-related units. | Medium: official pages expose list links, but direct files/formats and freshness need pinning. | Stable file URLs, schema, cadence, approval IDs, addresses/coordinates, license and privacy. |
| `md.ansa.farms-aquaculture` | ANSA animal-health materials cover authorized veterinary units and animal establishments; official checklists explicitly cover fish farms, cattle, laying hens, broilers and pigs. | Medium for linked files; low–medium for register routes not yet pinned. | Complete holding/aquaculture exports, IDs, coordinates, cadence, terms and privacy. |
| `md.environment-permits` | Moldovan environmental authority and permitting systems publish environmental information and authorization routes; public machine-readable permit export was not verified. | Medium after API/export confirmation; otherwise document extraction. | Public read/API, facility coverage, permit IDs, geometry, licensing and privacy. |
| `md.asp.organizations` | Public Services Agency provides state legal-entity register extracts and contracted Web/ACCES-Web/statistical access; IDNO is the core identifier. | Medium for authorized service integration; fees/contracts and personal data require strict controls. | API/service contract, fees, fields, cadence, legal-entity/site matching and privacy. |
| `md.stat.statistics` | National Bureau of Statistics publishes official agriculture/livestock/slaughter aggregates and statistical data services. | Medium–high for aggregate tables after table IDs/routes are pinned. | Exact slaughter/animal-use tables, formats, cadence, revisions, license and aggregate-only handling. |
| `md.ansa.inspections-experiments` | ANSA publishes risk-based official-control checklists and animal-health materials; public experimental-animal facility master was not verified. | High for published checklists/aggregates; low for facility/event extraction. | Public experimentation register, stable IDs, inspection outcomes, animal-use categories, privacy and retention. |

## Compliance and ingestion notes

- Treat ANSA, ASP, environmental and statistical records as government-sourced evidence, not proof of current operation or project approval.
- Preserve source URL, retrieval timestamp, content hash, byte size, supplied publication/effective date, adapter/configuration version, and source values.
- Keep raw, parsed, normalized, enriched, reviewed, and released layers separate. Use synthetic fixtures only; do not commit rows or raw artifacts.
- Represent unavailable cadence, IDs, coordinates, licensing, and privacy decisions explicitly. A source outage or disappearance means “not observed,” not closure.
- Registered offices, farmer-household addresses, permit sites and farm locations are not automatically safe public facility locations; suppress personal/household data and apply privacy review.
- ASP’s contracted information services and beneficial-owner fields are not unrestricted ingestion sources; adapters must fail closed unless authorized and privacy-eligible.

## Official evidence

- [ANSA animal-origin food safety](https://www.ansa.gov.md/siguranta-alimentelor.html)
- [ANSA animal health and welfare](https://www.ansa.gov.md/sanatatea-si-bunastarea-animalelor.html)
- [ANSA control checklists](https://ansa.gov.md/conducerea/liste-de-verificare.html)
- [Public Services Agency business information](https://asp.gov.md/en/servicii/persoane-juridice/informatii-afaceri)
- [ASP electronic information services](https://www.asp.gov.md/ro/servicii/alte-servicii/servicii-informationale-electronice/611)
- [National Bureau of Statistics](https://statistica.gov.md/en)
- [Environmental authority](https://www.mediu.gov.md/)

## Effort and blockers

Initial reconnaissance: approximately 2–4 engineering days to pin ANSA lists and build deterministic approved-food adapters; 4–8 additional days for holding/aquaculture, environmental permits, ASP authorization, experimentation registers and statistical table mapping. Main blockers are undocumented ANSA file routes, incomplete aquaculture exports, uncertain environmental API/export, ASP contracts/fees and personal-data fields, exact statistical table IDs, and licensing/privacy/coordinate semantics.

Recommended next country: Ukraine, subject to checking the existing country inventory before delegation.
