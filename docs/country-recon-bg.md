# Bulgaria source reconnaissance

Status: row-free reconnaissance only; no facility rows, raw exports, or production ingestion artifacts are committed.

## Scope and automation requirement

Bulgaria has authoritative surfaces through the Bulgarian Food Safety Agency (BFSA/BАБХ), the national open-data catalogue, environmental systems, the Registry Agency, and the National Statistical Institute. The production pipeline must be fully automated from source discovery/scraping through acquisition, validation, normalization, provenance, quarantine, and ingestion. This reconnaissance does not authorize publication or replace maintainer review.

## Strongest candidates

| Source | Verified surface | Automation assessment | Main unresolved items |
| --- | --- | --- | --- |
| `bg.bfsa.approved-food` | BFSA maintains public national registers for approved/registered food and feed establishments; its official material links feed approvals to the European Commission list. | Medium: public register discovery is clear, but direct bulk/API format needs probing. | Current establishment list/API, slaughter categories, stable approval IDs, status, addresses/coordinates, cadence, license and privacy. |
| `bg.farm-aquaculture` | BFSA materials identify official registration/control of livestock holdings; agriculture and fisheries authorities are the likely source for aquaculture permits. | Medium for public files; low–medium where portals are interactive or undocumented. | National farm/holding export, aquaculture permit register, identifiers, coordinates, cadence, terms and privacy. |
| `bg.environment-permits` | Ministry/Executive Environment Agency systems provide environmental authorization and integrated-control workflows; public machine-readable read access is not yet pinned. | Medium after a public API/export is confirmed; otherwise document/browser extraction. | Permit/decision API, national coverage, current public availability, geometry, licensing and privacy. |
| `bg.registry-agency.organizations` | Bulgarian Registry Agency’s Commercial Register exposes EIK-keyed company information and public service surfaces; automated bulk/API contract is not verified. | Medium: likely automatable after endpoint/terms are pinned, but CAPTCHAs/auth may constrain it. | Stable API/query route, fields, rate limits, terms, update cadence and registered-office privacy. |
| `bg.nsi.statistics` | National Statistical Institute publishes official agriculture, livestock and slaughter aggregates and statistical data services. | Medium–high for aggregate tables once table IDs/API contracts are pinned. | Exact slaughter/animal-use tables, API/download route, cadence, revisions, license and aggregate-only handling. |
| `bg.inspections-experiments` | BFSA official-control plans/reports document inspection and enforcement responsibilities; a stable public animal-experimentation facility master was not verified. | High for aggregate reports; low for facility/event extraction until a public route is confirmed. | Public inspection/event data, stable IDs, outcomes, animal-use categories, privacy and retention. |

## Compliance and ingestion notes

- Treat BFSA, registry, environmental and statistical sources as government-sourced evidence, not proof of current operation or project approval.
- Preserve source URL, retrieval timestamp, content hash, byte size, supplied publication/effective date, adapter/configuration version, and source values.
- Keep raw, parsed, normalized, enriched, reviewed, and released layers separate. Use synthetic fixtures only; do not commit rows or raw artifacts.
- Represent unavailable cadence, IDs, coordinates, licensing, and privacy decisions explicitly. A source outage or disappearance means “not observed,” not closure.
- Registered offices, farm addresses, and environmental work points are not automatically safe public facility locations; apply privacy and safety review before releasing addresses or coordinates.
- Adapters must fail closed on changed schemas, missing identifiers, suspicious count changes, CAPTCHAs/authentication, and service failures, retaining the previous validated release.

## Official evidence

- [BFSA official registers](https://bfsa.egov.bg/wps/portal/bfsa-web/registers)
- [BFSA official-control programme/report evidence](https://bfsa.egov.bg/)
- [European Commission approved feed establishments](https://food.ec.europa.eu/safety/animal-feed/feed-hygiene/approved-establishments_en)
- [Bulgarian national open-data catalogue](https://data.egov.bg/)
- [Executive Environment Agency / environmental system](https://eea.government.bg/)
- [Registry Agency](https://www.registryagency.bg/)
- [National Statistical Institute](https://www.nsi.bg/)

## Effort and blockers

Initial reconnaissance: approximately 2–4 engineering days to pin BFSA registers and any agriculture/aquaculture exports, then build deterministic acquisition and validation adapters; 4–8 additional days for environmental documents, registry integration, and inspection/animal-experimentation coverage. Main blockers are undocumented or interactive BFSA routes, incomplete public farm/aquaculture export verification, uncertain environmental read/API access, possible CAPTCHA/authentication on corporate services, and unresolved licensing/privacy/coordinate semantics.

Recommended next country: Serbia, subject to checking the existing country inventory before delegation.
