# Ukraine source reconnaissance

Status: metadata-only reconnaissance; no facility rows, raw exports, coordinates, or operationally sensitive records were retained.

## Safety and scope

Ukraine requires heightened review because public registries can expose operational locations during an active war, records can be stale or incomplete because of displacement and temporarily occupied territories, and a missing record does not prove closure. The pipeline must remain fully automated from source discovery/scraping through validation, quarantine, transformation, and ingestion, but automation must stop before acquisition when a source's publication, security, privacy, or terms are unresolved. Do not geocode, publish addresses, retain facility rows, or infer current operational status from an unavailable or stale source. Escalate immediately if a source exposes sensitive facility-level data or if access controls, wartime restrictions, or lawful-use terms are unclear.

## Candidate inventory

| ID | Authority / scope | Verified route | Format/API and cadence | Conservative disposition |
|---|---|---|---|---|
| `ua.dpss.approved-food` | State Production and Consumer Service (Держпродспоживслужба); registered food-market operators and facilities, including animal-origin food | [Registry and registration guidance](https://dpss.gov.ua/diyalnist/bezpechnist-harchovih-produktiv-ta-veterinarna-medicina/reyestri) and [registration route](https://dpss.gov.ua/diyalnist/bezpechnist-harchovih-produktiv-ta-veterinarna-medicina/dozvoly-ta-reiestratsiia-dlia-biznesu-u-sferakh-veterynarnoi-medytsyny-bezpechnosti-kharchovykh-produktiv-ta-kormiv/derzhavna-reiestratsiia-potuzhnostei) | Interactive search is discoverable; bulk route, schema, stable identifier, update cadence, terms, and privacy controls not pinned | Partial; blocked pending authorized, safety-reviewed export/API contract |
| `ua.farm-aquaculture` | DPSS livestock facilities/operators, including the stated aquaculture registration scope | [Livestock facilities and operators](https://dpss.gov.ua/diyalnist/bezpechnist-harchovih-produktiv-ta-veterinarna-medicina/dozvoly-ta-reiestratsiia-dlia-biznesu-u-sferakh-veterynarnoi-medytsyny-bezpechnosti-kharchovykh-produktiv-ta-kormiv/tvarynnytski-potuzhnosti/derzhavna-reiestratsiia-tvarynnytskykh-potuzhnostei-ta-operatoriv-rynku) | Electronic registration is described; no safe public bulk export/API, cadence, stable ID, coordinate policy, or reuse terms verified | Partial; blocked |
| `ua.environment-permits` | Ministry of Environmental Protection / EcoSystem environmental registers and permits | [Ministry environmental monitoring/open-register background](https://mepr.gov.ua/) | Public web platform and registers are discoverable; exact permit API/export, geometry, cadence, license, and security policy not pinned | Partial; blocked |
| `ua.edr.organizations` | Unified State Register of legal entities and organizations | [National open-data portal](https://data.gov.ua/) | Official catalog is the discovery point; current authorized API/download route, field-level personal-address policy, cadence, and rate limits not verified | Partial; blocked |
| `ua.ukrstat.statistics` | State Statistics Service aggregate livestock, animal-production, and slaughter indicators | [Official livestock series example](https://www.vn.ukrstat.gov.ua/index.php/component/content/article/741/7954--1995-2024.html) and [Ukrstat publications](https://ukrstat.gov.ua/) | Published tables/PDF/HTML; exact current table IDs, machine API, revision/cadence contract, and regional suppression rules not pinned | Partial; not run; aggregate-only candidate |
| `ua.inspections-experiments` | DPSS controls/enforcement and any public animal-experimentation evidence | [DPSS registers and services](https://dpss.gov.ua/diyalnist/bezpechnist-harchovih-produktiv-ta-veterinarna-medicina/reyestri) | No safe, stable public facility/event master verified; reports and control evidence are resource-specific | Partial; blocked; retain only aggregate evidence until authorized |

## Automation acceptance gates

Before any live run, the orchestrator must pin a stable source URL/API, response format and schema fingerprint, pagination/query behavior, stable identifiers and lifecycle semantics, observed cadence/freshness, attribution/license, privacy and retention rules, and a documented prohibition on sensitive geolocation. A compliant job would acquire only an authorized public snapshot, hash and quarantine it, validate schema and freshness, normalize without exposing rows, and ingest only after the safety and publication gates pass. Failed access, disappearance, or stale data must be recorded as an observation—not converted into a closure or status change.

## Recommendation

Ukraine is not ingestion-ready. Keep all six candidates publication-blocked and do not create a facility dataset from the interactive DPSS search. A future pass should begin with aggregate Ukrstat tables, then request an authorized, safety-reviewed DPSS metadata/export contract. Any facility-level acquisition should require explicit human approval and a wartime security review.
