# Bosnia and Herzegovina source reconnaissance

Status: row-free reconnaissance only; no facility rows, raw exports, or production ingestion artifacts are committed.

## Scope and automation requirement

Bosnia and Herzegovina is structurally fragmented: state-level coordination coexists with the Federation of BiH, its cantons, Republika Srpska, and Brčko District. The pipeline must model source authority and coverage by administrative entity, not assume one national register. Production acquisition must be fully automated from source discovery/scraping through validation, normalization, provenance, quarantine, and ingestion; this reconnaissance does not authorize publication or replace maintainer review.

## Strongest candidates

| Source | Verified surface | Automation assessment | Main unresolved items |
| --- | --- | --- | --- |
| `ba.veterinary.approved-food` | State/entity and FBiH veterinary/food-control authorities publish approval and inspection materials; FBiH’s veterinary inspectorate documents food/feed/farm controls. | Medium–low: national completeness requires federated adapters and entity-level discovery. | State list, entity/cantonal coverage, slaughter categories, stable IDs, addresses/coordinates, cadence, license and privacy. |
| `ba.farm-aquaculture` | FBiH official inspection mandate explicitly covers primary animal production, livestock registrations, feed, aquaculture, fishponds and fisheries; RS/Brčko counterparts must be mapped. | Low–medium: entity portals and documents may be interactive or inconsistent. | All-authority holding/aquaculture exports, identifiers, coordinates, cadence, terms and privacy. |
| `ba.environment-permits` | Environmental permitting is divided among state/entity authorities; FBiH and RS environmental ministries/agencies are relevant, but a unified machine-readable permit register was not verified. | Low–medium until entity-specific public APIs/exports are confirmed. | Complete coverage, document/API routes, permit IDs, geometry, licensing and privacy. |
| `ba.bizreg.organizations` | The state judicial BIZREG portal searches separate registers for Brčko, Federation BiH and Republika Srpska; RNS is described as unique, permanent and unrepeatable. | Medium for browser/query automation; API/bulk contract and rate limits are unverified. | Entity-specific fields, stable endpoints, automation permissions, cadence, terms and registered-office privacy. |
| `ba.bhas.statistics` | Agency for Statistics of BiH and entity statistical offices provide official agriculture/livestock/slaughter aggregates; national/entity dimensions must be preserved. | Medium–high for downloadable statistical tables after table IDs are pinned. | Exact slaughter/animal-use tables, entity coverage, API/download route, revisions, license and aggregate-only handling. |
| `ba.inspections-experiments` | FBiH veterinary/food inspectorates publish control plans and responsibilities; animal-experimentation facility data were not found as a stable public national register. | High for published reports/aggregates; low for facility/event extraction. | Entity/cantonal control events, stable IDs, outcomes, animal-use categories, privacy and retention. |

## Compliance and ingestion notes

- Record `state`, `entity`, `canton`, and `Brčko District` authority scope for every source; never merge records solely by name/address.
- Treat government and entity-level records as government-sourced evidence, not proof of current operation or project approval.
- Preserve source URL, retrieval timestamp, content hash, byte size, supplied publication/effective date, adapter/configuration version, and source values.
- Keep raw, parsed, normalized, enriched, reviewed, and released layers separate. Use synthetic fixtures only; do not commit rows or raw artifacts.
- Represent unavailable cadence, IDs, coordinates, licensing, and privacy decisions explicitly. A source outage or disappearance means “not observed,” not closure.
- Registered offices, farm addresses, permit locations and cantonal records are not automatically safe public facility locations; apply privacy and safety review before releasing addresses or coordinates.
- Adapters must fail closed on changed schemas, missing identifiers, duplicate cross-authority entities, suspicious count changes, and service failures, retaining the previous validated release.

## Official evidence

- [FBiH Federal Veterinary Inspectorate](https://fuzip.gov.ba/federalni-veterinarski-inspektorat/)
- [FBiH inspection mandate for agriculture, livestock and aquaculture](https://fuzip.gov.ba/unutrasnja-organizacija/federalni-poljoprivredni-inspektorat/)
- [FBiH veterinary/food control plans](https://fuzip.gov.ba/plan-sluzbenih-kontrola-farmi-imanja-goveda-ovaca-koza-i-dr-u-fbih-za-2025-godinu/)
- [BiH BIZREG federated business-register portal](https://bizreg.pravosudje.ba/pls/apex/f?p=186%3A%3A2313976059615753%3A%3ANO%3A%3A)
- [BIZREG explanation of entity/Brčko registers](https://bizreg.pravosudje.ba/pls/apex/f?p=186%3A20%3A4513352517506%3A%3ANO%3A%3AP20_SEKCIJA_TIP%3AKAKO_RADI)
- [Agency for Statistics of BiH](https://bhas.gov.ba/)

## Effort and blockers

Initial reconnaissance: approximately 4–7 engineering days to inventory state/entity/cantonal authorities and build source-discovery plus deterministic adapters for the strongest veterinary/statistical routes; 7–14 additional days for environmental permits, BIZREG integration and cross-authority reconciliation. Main blockers are fragmented authority, absence of a verified unified facility register, inconsistent entity/cantonal publishing, unverified public APIs, possible document-only routes, and unresolved licensing/privacy/coordinate semantics.

Recommended next country: North Macedonia, subject to checking the existing country inventory before delegation.
