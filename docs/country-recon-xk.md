# Kosovo source reconnaissance

Status: row-free reconnaissance only; no facility rows, raw exports, or production ingestion artifacts are committed.

## Scope and automation requirement

Kosovo’s Food and Veterinary Agency (AUVK) provides the clearest national source surface in this round, with approved animal-origin businesses, slaughterhouses, fishponds, feed establishments, animal registration and experimental-animal resources. The production pipeline must be fully automated from source discovery/scraping through acquisition, validation, normalization, provenance, quarantine, and ingestion. This reconnaissance does not authorize publication or replace maintainer review.

## Strongest candidates

| Source | Verified surface | Automation assessment | Main unresolved items |
| --- | --- | --- | --- |
| `xk.auvk.approved-food` | AUVK publishes category-specific approved-business registers for meat processing/slaughter, cold stores, fish processing, dairy, eggs, honey and other animal-origin foods. | Medium: WordPress download pages are discoverable and can be scheduled, but direct files and freshness need pinning. | Stable file URLs, schema, update cadence, approval IDs, addresses/coordinates, license and privacy. |
| `xk.auvk.farms-aquaculture` | AUVK lists fishpond register resources and explains nationwide animal/holding registration and traceability; livestock sources are distributed through veterinary practices. | Medium for linked files; low–medium for incomplete or field/portal-driven holding data. | Current holding export, aquaculture file, IDs, coordinates, cadence, terms and privacy. |
| `xk.environment-permits` | Kosovo environmental authority/ministry publishes permitting and environmental documents; a stable machine-readable national permit API was not verified. | Medium after route confirmation; otherwise document extraction. | Public API/export, complete facility coverage, permit IDs, geometry, license and privacy. |
| `xk.arbk.organizations` | Kosovo Business Registration Agency (ARBK) maintains the Business Organizations Registry and has online/admin surfaces; current public bulk/API access was not verified. | Low–medium pending an authorized service contract; avoid scripted access to login-only surfaces. | Public API/query route, rate limits, cadence, identifiers, terms and registered-office privacy. |
| `xk.ask.statistics` | Kosovo Agency of Statistics publishes official agriculture/livestock/slaughter aggregates and data services. | Medium–high for aggregate tables after table IDs/routes are pinned. | Exact slaughter/animal-use tables, formats, cadence, revisions, license and aggregate-only handling. |
| `xk.auvk.inspections-experiments` | AUVK publishes official-control summaries and lists experimental-animal institutions among animal-health/welfare registers. | Medium for documents; high privacy sensitivity. | Current experimentation register, stable fields/IDs, inspection outcomes, privacy and retention. |

## Compliance and ingestion notes

- Treat AUVK, ARBK, environmental and statistical records as government-sourced evidence, not proof of current operation or project approval.
- Preserve source URL, retrieval timestamp, content hash, byte size, supplied publication/effective date, adapter/configuration version, and source values.
- Keep raw, parsed, normalized, enriched, reviewed, and released layers separate. Use synthetic fixtures only; do not commit rows or raw artifacts.
- Represent unavailable cadence, IDs, coordinates, licensing, and privacy decisions explicitly. A source outage or disappearance means “not observed,” not closure.
- Registered offices, farm addresses, permit locations and fishpond sites are not automatically safe public facility locations; apply privacy and safety review before releasing addresses or coordinates.
- Adapters must fail closed on changed schemas, stale files, missing identifiers, personal-address exposure, suspicious count changes, authentication, and service failures.

## Official evidence

- [AUVK approved animal-origin businesses](https://auvk.rks-gov.net/en/approved-businesses-for-food-of-animal-origin/)
- [AUVK animal health registers](https://auvk.rks-gov.net/shendeti-i-kafsheve/)
- [AUVK veterinary inspection responsibilities](https://auvk.rks-gov.net/kontrolli-i-brendshem/veterinar/)
- [AUVK business information/downloads](https://auvk.rks-gov.net/en/business-information/)
- [Kosovo Business Registration Agency](https://arbk.rks-gov.net/)
- [Kosovo Agency of Statistics](https://ask.rks-gov.net/)
- [Kosovo environmental authority](https://mmphi.rks-gov.net/)

## Effort and blockers

Initial reconnaissance: approximately 2–4 engineering days to pin AUVK download files and build deterministic approved-food/fishpond adapters; 4–8 additional days for holding data, environmental permits, ARBK access, experimentation registers and statistical table mapping. Main blockers are stale or undocumented AUVK file routes, incomplete holding exports, uncertain environmental/API coverage, ARBK access restrictions, exact ASK table IDs, and licensing/privacy/coordinate semantics.

Recommended next country: Moldova, subject to checking the existing country inventory before delegation.
