# Albania source reconnaissance

Status: row-free reconnaissance only; no facility rows, raw exports, or production ingestion artifacts are committed.

## Scope and automation requirement

Albania has national authority surfaces through the National Food Authority (AKU), National Business Center (QKB), environmental authority, INSTAT, and the government open-data ecosystem. The production pipeline must be fully automated from source discovery/scraping through acquisition, validation, normalization, provenance, quarantine, and ingestion. This reconnaissance does not authorize publication or replace maintainer review.

## Strongest candidates

| Source | Verified surface | Automation assessment | Main unresolved items |
| --- | --- | --- | --- |
| `al.aku.approved-food` | AKU publishes registers for approved animal-origin food establishments, EU-export establishments, registered retail, primary producers and dairy-farm risk categorization. | Medium: official pages expose downloadable/linked content, but direct file routes and formats need pinning. | Stable file IDs, schema, update cadence, approval IDs, addresses/coordinates, license and privacy. |
| `al.aku.farms-aquaculture` | AKU animal and veterinary surfaces cover primary producers and animal establishments; agriculture/fisheries authority routes are needed for aquaculture permits. | Medium for linked files; low–medium for undocumented interactive registers. | Complete farm/aquaculture coverage, identifiers, coordinates, cadence, terms and privacy. |
| `al.environment-permits` | National environmental permit/licence publication is integrated with the QKB permits/licences/authorizations surface; environmental authority routes remain relevant for permits outside QKB. | Medium after direct query/export contract is verified. | Complete facility coverage, API/export, permit IDs, documents, geometry, license and privacy. |
| `al.qkb.organizations` | QKB exposes Business Register and permits/licences/authorizations search; official guidance says registered data are publicly accessible except restricted personal data, including individuals’ addresses. | Medium–high for authorized public search/API if available; avoid personal-address fields. | API/bulk route, rate limits, cadence, stable identifiers, terms and legal-entity/site matching. |
| `al.instat.statistics` | INSTAT publishes official agriculture, livestock and slaughter statistics and statistical data services. | Medium–high for aggregate tables after table IDs/API routes are pinned. | Exact slaughter/animal-use tables, formats, cadence, revisions, license and aggregate-only handling. |
| `al.aku.inspections-experiments` | AKU animal-welfare page lists a register of institutions breeding/supplying experimental animals and institutions conducting experiments, alongside slaughterhouse and veterinary registers. | Medium if linked files are stable; high privacy sensitivity. | Current file/API, fields, IDs, inspection outcomes, animal-use categories, privacy and retention. |

## Compliance and ingestion notes

- Treat AKU, QKB, environmental and statistical sources as government-sourced evidence, not proof of current operation or project approval.
- Preserve source URL, retrieval timestamp, content hash, byte size, supplied publication/effective date, adapter/configuration version, and source values.
- Keep raw, parsed, normalized, enriched, reviewed, and released layers separate. Use synthetic fixtures only; do not commit rows or raw artifacts.
- Represent unavailable cadence, IDs, coordinates, licensing, and privacy decisions explicitly. A source outage or disappearance means “not observed,” not closure.
- Registered offices, farm addresses and permit locations are not automatically safe public facility locations; remove or restrict personal-address material and apply privacy/safety review.
- Adapters must fail closed on changed schemas, missing identifiers, personal-address exposure, suspicious count changes, authentication/captcha, and service failures.

## Official evidence

- [AKU animal-origin food registers](https://aku.gov.al/)
- [AKU animal health and welfare registers](https://aku.gov.al/)
- [QKB Business Register and services](https://qkb.gov.al/en/home-3/)
- [QKB permits, licences and authorizations register](https://qkb.gov.al/en/permits-licenses-authorizations/)
- [QKB privacy policy](https://qkb.gov.al/en/privacy-policy/)
- [INSTAT](https://www.instat.gov.al/en/)
- [Albanian environmental authority](https://akm.gov.al/)

## Effort and blockers

Initial reconnaissance: approximately 2–4 engineering days to pin AKU file routes and QKB public/API access, then build deterministic acquisition and validation adapters; 4–8 additional days for environmental permits, aquaculture, experimentation registers and statistical table mapping. Main blockers are undocumented AKU download routes, incomplete aquaculture coverage, uncertain environmental API/export, QKB automation/rate limits, exact INSTAT table IDs, and licensing/privacy/coordinate semantics.

Recommended next country: Kosovo, subject to checking the existing country inventory before delegation.
