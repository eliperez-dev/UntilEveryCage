# India accountability-source reconnaissance

Status: row-free reconnaissance only. No facility rows, raw exports, personal data, or production ingestion artifacts are committed. Checked 2026-09-17 against `AGENTS.md` and `docs/ETHICS.md` (policy v1.0, reviewed 2026-09-12).

## Why India

India is not represented by a country adapter or existing `country-recon-in.md`. It is a high-value accountability graph candidate because food-business licensing, corporate identity, environmental compliance, and national livestock statistics are administered by different authorities. The sources can support relationships among a regulated premise, its legal entity, applicable authority, and regional animal-production context without treating an aggregate count as a facility fact.

## Source assessment

| Source | Evidence and shape | Linkage value | Difficulty/status |
| --- | --- | --- | --- |
| FSSAI FoSCoS | Public Food Safety Compliance System; FSSAI states that FBOs can be searched/verified and the portal exposes licensing/registration statistics. Expected fields: FSSAI number, premise/business name, kind of business, state, validity/status. [Portal](https://foscos.fssai.gov.in/) · [FSSAI FAQ](https://www.fssai.gov.in/upload/uploadfiles/files/FAQs_Licensing_Registration_26_07_2022.pdf) | Primary regulated-premise identifier; join candidate to company name, state and business category | Medium; blocked pending authorized search/export contract, code lists, terms, privacy and rate limits |
| DAHD livestock statistics | Animal Husbandry Statistics division publishes annual Basic Animal Husbandry Statistics and quinquennial livestock census, including species, use, sex/age and state-level production/population. [Official page](https://dahd.gov.in/schemes/programmes/animal-husbandry-statistics) | Independent regional/species context; detects implausible interpretations but cannot identify a facility | Low–medium; not-run pending stable table/download IDs and revision metadata |
| MCA company master | Ministry of Corporate Affairs describes public company/LLP master information, including legal status, incorporation and registered-office fields. [MCA](https://www.mca.gov.in/) · [MCA compendium](https://www.mca.gov.in/Ministry/pdf/Compendium.pdf) | CIN/LLPIN and legal name can corroborate FSSAI operator identity and continuity | High; public lookup is not a verified bulk/API contract; personal/director fields must be excluded |
| CPCB/environmental compliance | CPCB publishes national environmental monitoring/compliance material and technology-provider policy; environmental control is also implemented by State Pollution Control Boards. [CPCB](https://cpcb.nic.in/) · [data policy](https://cpcb.nic.in/upload/thrust-area/DATA-POLICY.pdf) | Permit/consent/monitoring/enforcement edges can connect regulated premises to environmental authority and time | High; no single national facility export verified; state coverage and identifiers unresolved |

## Accountability graph and sequencing

1. Establish a bounded, authorized FoSCoS observation contract. Preserve FSSAI number, raw status, validity dates, state, business category and source timestamp; do not assume a license proves current operation or animal agriculture.
2. Resolve only organization-level MCA fields needed to corroborate the operator. Keep registered-office addresses distinct from operating premises and never publish director or residential information.
3. Map CPCB and State PCB public routes as separate authority families. A consent, inspection, monitoring record or enforcement action is not interchangeable with an FSSAI license; preserve authority, document, date and status separately.
4. Add DAHD aggregates as a context layer keyed by state/district, species, measure and reference period. Never allocate an aggregate to a named company or reverse-engineer small cells.

## Provenance, privacy and publication gates

Future acquisition must record URL, retrieval timestamp, HTTP method/status, content type, byte size, SHA-256, supplied publication/effective date, schema fingerprint and adapter/configuration version. Raw, parsed, normalized, quarantined, reviewed and released layers remain separate. Source disappearance is “not observed,” not closure. Schema drift, missing identifiers, CAPTCHA/authentication, suspicious count changes and ambiguous identity matches fail closed into review/quarantine.

FSSAI premises and MCA registered offices may expose personal or mixed residential/business locations; suppress precise addresses and coordinates while privacy status is unresolved. Government origin is not project approval, factual review, current operation or completeness. Publication remains blocked until terms, privacy eligibility, project review, release approval and authorized maintainer availability are separately recorded.

## Blockers and recommended effort

The main blockers are the absence of a documented public FoSCoS bulk contract, MCA access/rate-limit semantics, the fragmented CPCB/SPCB landscape, and unclear reuse/coordinate rules. A first adapter tranche should take approximately 3–5 engineering days after authorized contracts are pinned; environmental/state expansion is a separate 5–10 day effort. No adapter is built in this reconnaissance.
