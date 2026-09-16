# Armenia source reconnaissance

Status: metadata-only reconnaissance; no facility rows, raw exports, coordinates, or personal data were retained.

## Scope and safety

Armenia is not present in the source registry. This pass covers official food-safety, livestock/farm, environmental, corporate, and statistics discovery only. Fully automated acquisition through validation, quarantine, transformation, and ingestion remains the eventual requirement, but no live acquisition or publication occurs until source contracts, terms, privacy, and safety are verified. Public availability does not establish completeness, current operation, or project approval. Missing or stale records mean not observed, never closure. Do not geocode or retain facility addresses/coordinates during reconnaissance.

## Candidate inventory

| ID | Authority / scope | Verified route | Format/cadence | Disposition |
|---|---|---|---|---|
| `am.snund.approved-food` | Food Safety Inspection Body; slaughterhouses and food-chain operators, including animal-origin food | [Slaughterhouses](https://snund.am/en/page/operating-slaughterhouses/106), [registry](https://www.snund.am/en/page/registry/109), [requirements](https://www.snund.am/en/page/requirements-for-slaughterhouses/168) | Web pages and advertised registry/download resources; exact file/API, schema, IDs, cadence, terms, and privacy not pinned | Partial; blocked |
| `am.snund.farms-livestock` | Food Safety Inspection Body; food-chain business registration, veterinary controls, livestock-related operators | [FSIB portal](https://www.snund.am/en) and [business registration](https://snund.am/hy/business-registration) | Online services/registry routes; public bulk contract, stable IDs, cadence, location policy, and licensing not verified | Partial; blocked |
| `am.environment-permits` | Armenia environmental authority and permit/register services | [Ministry of Environment](https://env.am/) | Public service discovery only; exact permit API/export, geometry, cadence, license, and privacy not pinned | Partial; blocked |
| `am.e-register.organizations` | Government electronic register of Armenian legal entities | [Electronic Register](https://www.e-register.am/en/) | Search/extract service; full records may require sign-in/payment; authorized API/bulk route, fields, limits, cadence, and personal-address policy unknown | Partial; blocked |
| `am.armstat.livestock-statistics` | Statistical Committee (Armstat); livestock by marz/species/year and agriculture indicators | [PxWeb livestock table](https://statbank.armstat.am/pxweb/en/ArmStatBank/ArmStatBank__6%20Agriculture%2C%20forestry%20and%20fishing/AF-1-2024.px/), [agriculture tables](https://statbank.armstat.am/pxweb/en/ArmStatBank/ArmStatBank__6%20Agriculture%2C%20forestry%20and%20fishing/) | PxWeb supports table selection/query and machine-readable output; exact API contract, revision/cadence, licensing, and suppression rules require pinning | Partial; not run; aggregate-only |
| `am.snund.inspections-experiments` | Food-safety/veterinary inspections and any public animal-experimentation evidence | [FSIB inspection body](https://www.snund.am/en/page/inspection-body/50) | Dated plans/reports and service pages; no stable public experimentation/event master verified | Partial; blocked |

## Automation and release gates

Before live acquisition, pin the exact official endpoint/download, response format and schema fingerprint, pagination, stable identifiers and lifecycle semantics, freshness/cadence, attribution/license, rate limits, privacy/retention, and location-safety rules. A compliant job would fetch only an authorized snapshot, hash and quarantine it, validate schema/freshness, preserve provenance privately, and ingest only a reviewed safe projection. No raw artifacts or rows belong in this repository. Sensitive location, personal contact, or ambiguous operational data stops the run and is escalated.

## Recommendation

Armenia is not ingestion-ready. Armstat PxWeb is the lowest-risk next contract because it is aggregate and query-oriented. SNUND facility registers remain blocked until download/API details and terms are confirmed. The electronic legal-entity register may involve authentication or payment and must not be scraped around access controls. Recommend the next unreconned nearby country after inventory check: Azerbaijan.
