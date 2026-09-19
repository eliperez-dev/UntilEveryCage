# Serbia source reconnaissance

Status: row-free reconnaissance only; no facility rows, raw exports, or production ingestion artifacts are committed.

## Scope and automation requirement

Serbia exposes relevant official surfaces through the Ministry of Agriculture/veterinary authority, the national open-data portal, the Statistical Office, environmental authorities, and the Serbian Business Registers Agency (APR). The production pipeline must be fully automated from source discovery/scraping through acquisition, validation, normalization, provenance, quarantine, and ingestion. This reconnaissance does not authorize publication or replace maintainer review.

## Strongest candidates

| Source | Verified surface | Automation assessment | Main unresolved items |
| --- | --- | --- | --- |
| `rs.veterinary.approved-food` | Ministry/veterinary authority and EU/official control frameworks cover approved food establishments and slaughterhouses; a stable national bulk/API route was not pinned. | Medium if an official export is found; otherwise interactive/browser acquisition. | Current national list/API, stable approval IDs, status/categories, addresses/coordinates, cadence, license and privacy. |
| `rs.farm-aquaculture` | Serbia’s open-data portal publishes farm aggregates and agriculture resources; aquaculture permit/site coverage needs authority-specific confirmation. | Medium for catalogued CSV/XLS/JSON; low–medium for interactive registers. | Establishment-level farm scope, aquaculture permits, IDs, coordinates, cadence, terms and privacy. |
| `rs.environment-permits` | Environmental permitting is handled through official environmental systems and agencies; a complete public read/export contract was not verified. | Medium after a stable public route is confirmed; otherwise document extraction. | Permit/API route, national coverage, availability, geometry, licensing and privacy. |
| `rs.apr.organizations` | APR provides public browser/web-service access to centralized electronic business registers; bulk/automated access is restricted and some data services are fee-based. | Low–medium: automation must use authorized web services and respect anti-automated-download terms. | API contract, fees, quotas, allowed automation, fields, cadence and registered-office privacy. |
| `rs.stat.statistics` | Statistical Office open-data resources provide machine-readable JSON/CSV APIs with dataset IDs, including livestock/farm aggregates; slaughter table IDs need pinning. | High for official aggregate APIs after table discovery. | Exact slaughter/animal-use tables, cadence, revisions, license and aggregate-only handling. |
| `rs.inspections-experiments` | Official veterinary control plans/reports and relevant authorities provide inspection/enforcement evidence; public animal-experimentation facility master was not verified. | High for published aggregates; low for facility/event extraction until a public route is confirmed. | Public event/facility route, stable IDs, outcomes, animal-use categories, privacy and retention. |

## Compliance and ingestion notes

- Treat government and open-data records as government-sourced evidence, not proof of current operation or project approval.
- Preserve source URL, retrieval timestamp, content hash, byte size, supplied publication/effective date, adapter/configuration version, and source values.
- Keep raw, parsed, normalized, enriched, reviewed, and released layers separate. Use synthetic fixtures only; do not commit rows or raw artifacts.
- Represent unavailable cadence, IDs, coordinates, licensing, and privacy decisions explicitly. A source outage or disappearance means “not observed,” not closure.
- Registered offices, farm addresses and permit locations are not automatically safe public facility locations; apply privacy and safety review before releasing addresses or coordinates.
- Adapters must fail closed on changed schemas, missing identifiers, suspicious count changes, unauthorized automation, and service failures, retaining the previous validated release.

## Official evidence

- [Serbian open-data portal](https://data.gov.rs/)
- [Machine-readable Statistical Office farm dataset](https://data.gov.rs/sr/datasets/broj-gazdinstava-i-grla-stoke-po-vrstama-i-broj-uslovnih-grla-prema-tipu-proizvodnje/)
- [APR data-search terms and access](https://www.apr.gov.rs/registers/media/data-search.1728.html)
- [APR electronic data services](https://www.apr.gov.rs/services/e-data-on-request/status-and-other-business-data.4270.html)
- [Ministry of Agriculture](https://www.minpolj.gov.rs/)
- [Environmental Protection Agency](https://www.sepa.gov.rs/)
- [Statistical Office of the Republic of Serbia](https://www.stat.gov.rs/)

## Effort and blockers

Initial reconnaissance: approximately 2–4 engineering days to pin Statistical Office APIs and any veterinary/agriculture exports, then build deterministic acquisition and validation adapters; 4–8 additional days for environmental documents, APR integration, and inspection/animal-experimentation coverage. Main blockers are the undocumented national veterinary establishment route, incomplete farm/aquaculture export verification, environmental read/API uncertainty, APR restrictions/fees on automated access, and unresolved licensing/privacy/coordinate semantics.

Recommended next country: Bosnia and Herzegovina, subject to checking the existing country inventory before delegation.
