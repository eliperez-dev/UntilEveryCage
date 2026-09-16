# Cyprus source reconnaissance

Status: metadata-only; Republic of Cyprus jurisdiction only. No facility rows, raw exports, coordinates, traceability data, operational details, or personal data retained.

## Territorial scope and safety

This inventory describes sources issued by the Republic of Cyprus and its authorities. It does not claim coverage, authority, or data completeness for northern Cyprus or areas administered by other authorities. Do not silently merge jurisdictions or treat absence from Republic of Cyprus sources as absence elsewhere. Fully automated acquisition-to-ingestion remains required eventually, but acquisition is gated by source contracts, terms, privacy, and safety review. Do not bypass access controls; missing or stale records are not closure; do not geocode during reconnaissance.

## Candidates

| ID | Authority/scope | Route | Format/cadence | Disposition |
|---|---|---|---|---|
| `cy.vs.approved-food` | Republic of Cyprus Ministry of Agriculture Veterinary Services; approved animal-origin establishments/slaughterhouses | [Approved establishments](https://www.moa.gov.cy/moa/vs/vs.nsf/All/9F6A5DB7308579ACC225764D001D01AF?OpenDocument=&print=), [registered establishments](https://www.moa.gov.cy/moa/vs/vs.nsf/vs14_en/vs14_en) | Dated PDF/HTML documents; exact full set, schema, stable IDs, update cadence, licensing, privacy not pinned | Partial; blocked |
| `cy.vs.farms-livestock` | Republic of Cyprus Veterinary Services and agriculture authorities; livestock holdings/animal identification | [Veterinary Services](https://www.moa.gov.cy/moa/vs/vs.nsf) | Web/service routes; public machine export, IDs, cadence, privacy, and territorial coverage not verified | Partial; blocked |
| `cy.environment-permits` | Republic of Cyprus environmental/EIA and waste-permit authorities | [Department of Environment](https://www.moa.gov.cy/moa/environment/environment.nsf) | Register/service discovery; exact permit API/export, geometry, cadence, license and privacy not pinned | Partial; blocked |
| `cy.companies.registry` | Republic of Cyprus Registrar of Companies and Intellectual Property | [Companies Section](https://www.companies.gov.cy/en/) | eSearch/services and statistics; bulk/API, access terms, stable IDs and personal-data policy not verified | Partial; blocked |
| `cy.cystat.livestock-meat` | Statistical Service of Cyprus; aggregate livestock and meat production | [Production of meat PxWeb](https://cystatdb.cystat.gov.cy/pxweb/en/8.CYSTAT-DB/8.CYSTAT-DB__Agriculture%2C%20Livestock%2C%20Fishing__Livestock/0320031E.px/), [farm survey](https://www.gov.cy/en/economy-and-finance/results-of-the-farm-structure-survey-of-agricultural-and-livestock-holdings-2023/) | PxWeb/table and recurring survey publications; API/query contract, revisions, licensing, suppression not fully pinned | Partial; not run; aggregate-only |
| `cy.vs.inspections-enforcement` | Republic of Cyprus Veterinary Services inspection/enforcement and public animal-use evidence | [Veterinary Services](https://www.moa.gov.cy/moa/vs/vs.nsf) | Reports/services; stable event/experimentation master, retention, privacy not verified | Partial; blocked |

## Gates

Pin exact authorized endpoints/documents, format/schema fingerprint, stable IDs/lifecycle, freshness/cadence, attribution/license, rate limits, privacy/retention, and Republic-of-Cyprus territorial scope. Hash and quarantine authorized snapshots, validate them, preserve provenance privately, and ingest only a reviewed safe projection. Sensitive locations, personal contacts, or cross-jurisdiction ambiguity stop and escalate.

Cyprus is not ingestion-ready. CYSTAT aggregate tables are the lowest-risk follow-up. Veterinary documents remain blocked until machine contracts, terms, privacy, and territorial completeness are reviewed. Recommend next unreconned nearby country after inventory check: Lebanon.
