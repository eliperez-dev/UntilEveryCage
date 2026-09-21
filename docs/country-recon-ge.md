# Georgia source reconnaissance

Status: metadata-only reconnaissance; no facility rows, raw exports, coordinates, or personal data were retained.

## Scope and safety

Georgia is not yet in the source registry. This pass covers official food-safety, farm/livestock, environmental, corporate, and statistics discovery only. Fully automated acquisition through validation, quarantine, transformation, and ingestion remains the eventual requirement; no automation may acquire or publish facility-level data until the source contract, terms, privacy, and publication review are complete. A public list is not proof of current operation or completeness. Missing or stale records are recorded as not observed, never inferred as closure. Do not geocode or retain addresses/coordinates during reconnaissance.

## Candidate inventory

| ID | Authority / scope | Verified route | Format/cadence | Disposition |
|---|---|---|---|---|
| `ge.nfa.approved-food` | National Food Agency (NFA); registered slaughterhouses and recognized animal-origin food operators | [Registered slaughterhouses](https://nfa.gov.ge/Ge/Page/List%20of%20Slaughterhouses%20Registered%20in%20Georgia), [recognition guidance](https://nfa.gov.ge/Ge/Page/Guidelines%20for%20Recognition), [veterinary-control registers](https://www.nfa.gov.ge/Ge/Page/Veterinary%20Control) | Periodically updated downloadable files are advertised; exact URL, format, schema, stable ID, cadence, terms, and privacy policy not pinned | Partial; blocked |
| `ge.nfa.farms-livestock` | NFA primary-production controls, livestock identification/registration, feed and recognized primary-production operators | [Primary production control](https://nfa.gov.ge/Ge/Page/Primary%20production%20control) and [NFA English portal](https://www.nfa.gov.ge/en) | Linked lists/registers and electronic services; bulk/API contract, scope, cadence, IDs, and location-sensitivity not verified | Partial; blocked |
| `ge.nea.environment-permits` | National Environment Agency; environmental permits and related public environmental information | [NEA official site](https://nea.gov.ge/) | Public services/register routes require endpoint and export verification; format, cadence, geometry, license, and privacy not pinned | Partial; blocked |
| `ge.napr.organizations` | National Agency of Public Registry; entrepreneur and legal-entity identifiers | [NAPR](https://www.napr.gov.ge/) | Online extracts/services are discoverable; authorized bulk/API access, fields, fees, rate limits, cadence, and personal-address policy not verified | Partial; blocked |
| `ge.geostat.slaughter-statistics` | National Statistics Office of Georgia; aggregate livestock slaughterhouse, meat-production, and related agricultural indicators | [Geostat agriculture](https://www.geostat.ge/en/modules/categories/755/section-5-livestock-poultry-and-beehives), [slaughterhouse survey](https://www.geostat.ge/en/single-news/3781/survey-results-for-livestock-slaughterhouses-elevators-and-cold-storage-facilities-2025) | Recurring quarterly/annual publications, often PDF/XLS; table IDs, machine API, revision policy, and suppression rules not pinned | Partial; not run; aggregate-only |
| `ge.nfa.inspections-experiments` | NFA veterinary/food-control findings and any public animal-experimentation evidence | [Veterinary control](https://www.nfa.gov.ge/Ge/Page/Veterinary%20Control) | Dated control results and registers are published as resources; stable event API, retention, privacy, and experimentation coverage not verified | Partial; blocked |

## Automation and release gates

Before live acquisition, pin the exact official download/API route, schema fingerprint, pagination, stable identifiers and lifecycle semantics, observed cadence/freshness, attribution/license, rate limits, privacy/retention terms, and whether facility locations may be retained. A compliant job would fetch only an authorized public snapshot, hash and quarantine it, validate schema/freshness, preserve source provenance privately, and ingest only a reviewed safe projection. No raw artifacts or facility rows belong in this repository. Any sensitive location, personal contact, or ambiguous operational record stops the run and is escalated.

## Recommendation

Georgia is not ingestion-ready. The lowest-risk next step is an aggregate-only Geostat adapter contract; NFA facility lists should remain blocked until the download links and publication terms are captured and safety-reviewed. NAPR and NEA should be treated as separate services, not silently joined to NFA records. Recommend the next unreconned nearby country only after checking the orchestrator inventory.
