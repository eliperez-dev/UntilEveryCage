# North Macedonia source reconnaissance

Status: row-free reconnaissance only; no facility rows, raw exports, or production ingestion artifacts are committed.

## Scope and automation requirement

North Macedonia has a comparatively clear national Food and Veterinary Agency (FVA) register surface, alongside environmental, statistical, open-data and Central Registry systems. The production pipeline must be fully automated from source discovery/scraping through acquisition, validation, normalization, provenance, quarantine, and ingestion. This reconnaissance does not authorize publication or replace maintainer review.

## Strongest candidates

| Source | Verified surface | Automation assessment | Main unresolved items |
| --- | --- | --- | --- |
| `mk.fva.approved-food` | FVA lists approved animal-origin establishments under Regulation 853/2004, including meat, fish, dairy, egg, honey and other categories, plus export-approved and registered operators. | Medium: register pages link documents hosted through Google Drive; scheduled discovery/download is plausible once stable file IDs are pinned. | Direct file IDs, schema, update cadence, stable approval IDs, addresses/coordinates, license and privacy. |
| `mk.fva.farms-aquaculture` | FVA animal-health page lists slaughterhouses, livestock markets, controlled pig holdings and related animal registers; fisheries/aquaculture coverage needs route confirmation. | Medium for linked files; low–medium for interactive or incomplete registers. | Farm/aquaculture export, IDs, coordinates, cadence, terms and privacy. |
| `mk.environment-permits` | Ministry of Environment and Physical Planning is the relevant national authority for environmental permissions and public notices; machine-readable permit route was not pinned. | Medium after API/export confirmation; otherwise document extraction. | Permit API/export, facility coverage, IDs, geometry, license and privacy. |
| `mk.crm.organizations` | Central Registry provides an online distribution system for legal-entity current/historical status and electronic confirmations; terms restrict commercial reproduction without consent. | Medium for authorized paid service; do not scrape or republish outside permitted use. | API/service contract, fees, commercial permission, fields, cadence and registered-office privacy. |
| `mk.stat.statistics` | State Statistical Office publishes official agriculture/livestock and slaughter aggregates and data services. | Medium–high for aggregate tables after table IDs and formats are pinned. | Exact slaughter/animal-use tables, API/download route, cadence, revisions and license. |
| `mk.fva.inspections-experiments` | FVA explicitly lists a register of institutions breeding/supplying experimental animals and user institutions conducting experiments, alongside official control registers. | Medium if linked register files are stable; high privacy sensitivity. | Current file/API, fields, stable IDs, inspection outcomes, animal-use categories, privacy and retention. |

## Compliance and ingestion notes

- Treat FVA and ministry data as government-sourced evidence, not proof of current operation or project approval.
- Preserve source URL, retrieval timestamp, content hash, byte size, supplied publication/effective date, adapter/configuration version, and source values.
- Keep raw, parsed, normalized, enriched, reviewed, and released layers separate. Use synthetic fixtures only; do not commit rows or raw artifacts.
- Represent unavailable cadence, IDs, coordinates, licensing, and privacy decisions explicitly. A source outage or disappearance means “not observed,” not closure.
- Registered offices, farm addresses and permit locations are not automatically safe public facility locations; apply privacy and safety review before releasing addresses or coordinates.
- The Central Registry’s commercial-use restriction is a hard acquisition/publication gate; adapters must fail closed if authorization or terms are unclear.

## Official evidence

- [FVA animal-origin food registers](https://fva.gov.mk/mk/registri-hrana-zivotinsko-poteklo)
- [FVA approved establishments register](https://fva.gov.mk/mk/registar-odobreni-objekti)
- [FVA animal-health and welfare registers](https://fva.gov.mk/mk/zdravstvena-zastita-blagosostojba-zivotni-1)
- [Central Registry online distribution system](https://www.crm.com.mk/en/professional-users/lessors/access-to-data-via-the-online-distribution-system)
- [Central Registry commercial-use terms](https://www.crm.com.mk/en/professional-users/accountants)
- [State Statistical Office](https://www.stat.gov.mk/)
- [Ministry of Environment and Physical Planning](https://www.moepp.gov.mk/)

## Effort and blockers

Initial reconnaissance: approximately 2–4 engineering days to pin FVA document IDs and build deterministic register adapters; 4–8 additional days for environmental permits, animal-experimentation fields, statistical table mapping and authorized Central Registry integration. Main blockers are Google Drive-backed register links, undefined refresh cadence, unverified farm/aquaculture exports, environmental API uncertainty, Central Registry commercial-use restrictions/fees, and privacy/coordinate semantics.

Recommended next country: Albania, subject to checking the existing country inventory before delegation.
