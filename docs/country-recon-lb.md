# Lebanon source reconnaissance

Status: metadata-only reconnaissance; no facility rows, raw exports, coordinates, traceability data, operational details, or personal data were retained.

## Scope and safety

This pass covers official Lebanese sources for slaughter/animal-product establishments, livestock and farms, environmental permits/EIA, corporate identity, and aggregate statistics. Lebanon's conflict, displacement, and operational-security context requires heightened safeguards: do not retain or publish facility-level locations, farm/animal traceability, worker or owner information, or details that could increase risk to people or vulnerable operations. Public availability does not establish completeness, current operation, factual accuracy, project approval, or publication eligibility. A missing source record means “not observed,” never closure.

## Candidate inventory

| ID | Authority / scope | Verified route | Format/cadence | Disposition |
|---|---|---|---|---|
| `lb.moa.approved-food` | Ministry of Agriculture; sanitary registration of poultry/livestock slaughterhouses and animal-origin food factories/warehouses | [Animal-wealth regulatory decisions](https://www.agriculture.gov.lb/Subjects/Animal-Wealth/laws), [Directorate of Animal Resources](https://agriculture.gov.lb/adminstrative-transactions/DirectorateOfAnimalResources) | Arabic web pages and linked decisions/PDFs; no authorized bulk/API contract, stable identifier, cadence, terms, or safe location boundary pinned | Partial; blocked |
| `lb.moa.farms-livestock` | Ministry of Agriculture; health registration of poultry and dairy cattle/sheep/goat farms; farmer registry | [Animal-wealth decisions](https://www.agriculture.gov.lb/Subjects/Animal-Wealth/laws), [2025 farmer-registry summary](https://www.agriculture.gov.lb/Media/News/2025/Summary-Report-%E2%80%93-Farmers-Registry-in-Lebanon) | Web guidance and aggregate announcement; registry fields, export/API, IDs, cadence, licensing, privacy and displacement/safety controls unknown | Partial; blocked; aggregate context only |
| `lb.moe.environment-eia` | Ministry of Environment; environmental review, prior screening/EIA and facility investment controls | [Environment Protection Law 444](https://moe.gov.lb/%D8%A7%D9%84%D9%88%D8%B2%D8%A7%D8%B1%D8%A9/%D8%A7%D9%84%D9%82%D9%88%D8%A7%D9%86%D9%8A%D9%86-%D9%88%D8%A7%D9%84%D8%A7%D9%86%D8%B8%D9%85%D8%A9/%D8%A7%D9%84%D9%82%D9%88%D8%A7%D9%86%D9%8A%D9%86/%D9%82%D8%A7%D9%86%D9%88%D9%86-%D8%B1%D9%82%D9%85-444-%D8%AD%D9%85%D8%A7%D9%8A%D8%A9-%D8%A7%D9%84%D8%A8%D9%8A%D9%8A%D8%A9.aspx), [SEA in Lebanon](https://www.moe.gov.lb/MOE%20Site/SEA/SEA%20in%20Lebanon.htm) | Legal/framework pages; no current public permit register/export, schema, identifiers, cadence, licensing, or safe geometry route pinned | Partial; blocked |
| `lb.justice.companies` | Ministry of Justice; commercial register and company/trader search | [Commercial Register](https://cr.justice.gov.lb/index.aspx) | Interactive search; Beirut joint-stock coverage is explicitly limited; machine route, fees, fields, cadence, terms and personal-address policy unknown | Partial; blocked; do not bypass access controls |
| `lb.industry.food-guide` | Ministry of Industry; licensed food factories, including meat/slaughterhouse activity categories | [Industrial Guide](https://www.industry.gov.lb/IndustrialStatistics/IndustrialGuide) | Web guide and 2022 licensed-factory lists; download/schema/IDs, update cadence, reuse terms, and address safety require review | Partial; blocked |
| `lb.cas.livestock-statistics` | Central Administration of Statistics; aggregate livestock/agriculture indicators | [CAS](https://www.cas.gov.lb/) | Official publications and tables; table/API identifiers, revision cadence, terms and suppression rules not pinned | Partial; not run; aggregate-only |

## Automation and release gates

Before any live acquisition, pin the exact official endpoint or download, format/schema fingerprint, pagination, stable identifiers and lifecycle semantics, freshness/cadence, attribution/licence, rate limits, access controls, privacy/retention rules, and conflict-sensitive location policy. Any compliant future job must use authorized bounded retrieval, private provenance, quarantine, schema validation, and a reviewed safe projection. No facility rows, raw artifacts, coordinates, traceability or operational details belong in this repository. Stop and escalate on authentication, payment, CAPTCHA, robots restrictions, sensitive material, or ambiguous exposure.

## Recommendation

Lebanon is not ingestion-ready. CAS aggregate statistics are the lowest-risk follow-up contract. Ministry of Agriculture regulatory pages can support a later assisted metadata review, but establishment/farm acquisition remains blocked pending a safe authorized route and human review. Recommend the next unreconned country only after orchestrator inventory review; do not infer Lebanon coverage from these sources.
