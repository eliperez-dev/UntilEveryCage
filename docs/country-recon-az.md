# Azerbaijan source reconnaissance

Status: metadata-only reconnaissance; no facility rows, raw exports, coordinates, operational details, or personal data were retained.

## Scope and safety

Azerbaijan is not present in the source registry. This pass covers official food-safety, livestock, environmental, corporate, and statistics discovery. Fully automated acquisition through validation, quarantine, transformation, and ingestion remains the eventual requirement, but acquisition is gated until source contracts, access controls, terms, privacy, and regional/conflict safety are verified. Do not bypass authentication, payment, robots, or technical restrictions. Public availability does not establish completeness or current operation; disappearance is not closure. Do not geocode or retain facility locations during reconnaissance.

## Candidate inventory

| ID | Authority / scope | Verified route | Format/cadence | Disposition |
|---|---|---|---|---|
| `az.afsa.food-subjects` | Azerbaijan Food Safety Agency (AFSA/AQTA); registered food subjects and activities, including animal-origin food | [Food subjects search](https://afsa.gov.az/az/qida-subyektleri), [AFSA portal](https://afsa.gov.az/) | Search service exposes query fields; bulk/API route, schema, stable IDs, cadence, licensing, and privacy not pinned | Partial; blocked |
| `az.afsa.livestock-traceability` | AFSA; animal identification/registration and farm-to-table traceability | [Animal identification notice](https://afsa.gov.az/az/heyvan-saglamligi-ve-bioloji-tehlukesizlik/xeberler/heyvanlarin-identiklesdirilmesi-baytarliq-nezaretinin-effektivliyini-artirir), [AQTIS login](https://hiqs.afsa.gov.az/Airs.Web/Account/Login.aspx) | Electronic system exists; login-protected route and sensitive individual/farm records; no automated access or public export verified | Partial; blocked |
| `az.eco.environment-permits` | Ministry of Ecology and Natural Resources; environmental permits/registers | [Ministry site](https://eco.gov.az/) | Public service discovery; exact permit API/export, geometry, cadence, license, privacy, and safety not pinned | Partial; blocked |
| `az.taxes.organizations` | State Tax Service; commercial legal-entity and taxpayer registration data | [State registration](https://www.taxes.gov.az/en/page/qeydiyyat), [public database](https://taxes.gov.az/en/page/ictimai-aciq-melumat-bazasi) | Search/statistical pages and public database; access, fields, cadence, terms, and personal-data boundaries require verification | Partial; blocked |
| `az.stat.livestock-statistics` | State Statistical Committee; aggregate livestock, slaughter, meat, milk, and fishery indicators | [Agriculture statistics](https://www.stat.gov.az/source/agriculture/?lang=en), [2025 agriculture yearbook](https://www.stat.gov.az/menu/6/statistical_yearbooks/source/agriculture_2025.pdf) | Annual tables/yearbooks; current machine API, table IDs, revision/cadence, licensing, and suppression rules not pinned | Partial; not run; aggregate-only |
| `az.afsa.inspections-enforcement` | AFSA inspections, violations, veterinary control, and any public experimentation evidence | [AFSA portal](https://afsa.gov.az/) | Dated notices/reports and search services; stable event API, retention, privacy, and experimentation coverage not verified | Partial; blocked |

## Automation and release gates

Before live acquisition, pin the exact authorized endpoint/download, schema fingerprint, pagination/query contract, stable identifiers and lifecycle semantics, freshness/cadence, attribution/license, rate limits, privacy/retention, and location-safety rules. A compliant job would fetch only an authorized public snapshot, hash and quarantine it, validate schema/freshness, preserve provenance privately, and ingest only a reviewed safe projection. Sensitive farm or facility locations, personal contacts, or vulnerable operational details stop the run and are escalated.

## Recommendation

Azerbaijan is not ingestion-ready. The aggregate State Statistical Committee tables are the lowest-risk candidate. AFSA food-subject search is not an authorization for scraping, and the animal-identification system is login-protected and potentially sensitive. Keep all six candidates blocked/not-run until contracts and safety review are complete. Recommend the next unreconned nearby country after inventory check: Turkey.
