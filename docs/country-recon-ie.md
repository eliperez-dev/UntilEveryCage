# Ireland source reconnaissance

Status: reconnaissance complete, private metadata only, no adapter, no release. Checked 2026-09-16. The machine-readable [field crosswalk](countries/ireland/v1-field-crosswalk.json) and [artifact manifest](../data/manifests/ireland-source-artifacts.json) are the implementation handoff. No raw bulk data, addresses, coordinates, company rows, or named enforcement rows are committed.

## Decision summary

Ireland is a strong but split source landscape. FSAI is the directory/coordinating layer; DAFM, HSE, and SFPA own different approval populations. EPA LEAP, planning, CRO, statistics, funding, and enforcement/welfare material are useful accountability or context layers, not additional facility masters. The recommended decision is to proceed only with a bounded, operator-authorized capture phase, preserving each authority and entity class separately.

| Source family | Current evidence | Integration decision |
|---|---|---|
| FSAI | Approved-premises page says products of animal origin requiring Regulation (EC) 853/2004 approval must appear in up-to-date competent-authority lists, and links DAFM, HSE, and SFPA | Coordinator only; do not add a fourth facility population |
| DAFM | Current publication page last updated 2026-09-15 and exposes three XLSX families: main establishments, former-LA establishments, and milk/dairy establishments | Three source identities; workbook headers/counts still unverified |
| HSE | Rendered low-throughput directory last refreshed 2026-09-16; 72 distinct `Approval_Number` nodes observed | Facility parent plus repeated activity/species children; no address release |
| SFPA | Approved establishments updated 2026-09-15 with 184 table entries; freezer vessels 50; factory vessels 1 | Establishment, freezer-vessel, and factory-vessel entity classes stay separate |
| EPA / planning / CRO | LEAP exposes licence/compliance events, MyPlan exposes ten years of applications with weekly uploads, CRO catalog describes daily company data | Accountability and identity edges only; explicit reviewed joins |
| Statistics / funding / enforcement / welfare | CSO/DAFM aggregate measures; DAFM seafood funding context; FSAI orders; DAFM control responsibilities | Context/event layers; never facility counts or proof of current operation |

## Official routes and schemas

The FSAI [approved food premises directory](https://www.fsai.ie/enforcement-and-legislation/official-controls/mancp/approved-food-premises) explains the competent-authority split. FSAI’s [approval guidance](https://www.fsai.ie/business-advice/starting-a-food-business/approval-of-a-new-business) identifies slaughterhouses, meat processors, egg/dairy businesses, and fish processors as typical approval cases. Its [establishments subject to approval](https://www.fsai.ie/enforcement-and-legislation/legislation/food-legislation/meat-fresh-meat/establishments-subject-to-approval) page distinguishes approval under 853/2004 from registration under 852/2004.

DAFM’s [approved establishments publication](https://www.gov.ie/en/department-of-agriculture-food-and-the-marine/publications/dafm-approved-establishments/) says the Hygiene Package took effect 1 January 2006, was transposed by S.I. 432/2009 and revised by S.I. 22/2020, and that DAFM inspects existing and new meat establishments. The page links:

- [main workbook](https://assets.gov.ie/static/documents/09fe3ad4/AllApprovedPlants_2026_5.xlsx), incorporating fish, egg, and dairy;
- [former local-authority workbook](https://assets.gov.ie/static/documents/09fe3ad4/AllApprovedPlants_2026_Formerly_LA_Plants_1.xlsx); and
- [milk/dairy workbook](https://assets.gov.ie/static/documents/09fe3ad4/1._Milk_Dairy_Establishments_Registered_and_or_Approved_11th_August_2026.xlsx).

The links are verified, but the workbooks were not downloaded in this run. No count, header, status code, effective date, or overlap is inferred from a filename or page title.

The [HSE/FSAI directory](https://oapi.fsai.ie/HSEApprovedEstablishments.aspx) explicitly renders `Approval_Number`, `Premises Trading Name`, `Address`, `County`, `Primary Business Type`, `Activity`, and `Species`. Its 72 approval-number count excludes the many repeated activity/species rows. The source therefore requires a parent approval record and a child activity observation, with `Not Stated` and `Unknown` preserved as source values.

SFPA’s [approved-establishments table](https://www.sfpa.ie/What-We-Do/Seafood-Safety/Registration-Approval-of-Businesses/List-of-Approved-Establishments/Approved-Establishments) renders `Approval Number`, `Establishment Name`, `Address`, `County`, `Categories`, `Activity Codes`, and `Certificate Number`; it defines `AH`, `DC`, `FFPP`, `PC`, `PP`, and `CS`. It displayed 184 entries and an update date of 15 September 2026. The [freezer-vessel](https://www.sfpa.ie/What-We-Do/Seafood-Safety/Registration-Approval-of-Businesses/List-of-Approved-Establishments/Approved-Freezer-Vessels) table displayed 50 entries, while the [factory-vessel](https://www.sfpa.ie/What-We-Do/Seafood-Safety/Registration-Approval-of-Businesses/List-of-Approved-Establishments/Approved-Factory-Vessels) table displayed 1. SFPA approval strings sometimes show both an EC form and a non-EC form; preserve that raw value and normalize only in a reviewed transform.

## Identity, counts, and overlap

The safe key is `(source_id, source-local approval/registration number, entity_class)`. DAFM’s three workbook families must not be unioned until overlap is measured. HSE approvals, SFPA establishments, and SFPA vessels must not be deduplicated by name or address. Approval, activity, category, species, certificate, and status are observations attached to a parent identity, not separate facilities.

The report’s observed values are deliberately not a national total:

- HSE: 72 distinct approval-number nodes in the rendered page;
- SFPA: 184 approved-establishment table entries, 50 freezer-vessel entries, and 1 factory-vessel entry;
- DAFM: count unavailable until a bounded workbook capture and schema fingerprint;
- FSAI: no independent rows; it is a coordinator;
- EPA, NPAD, CRO, enforcement, and funding: no facility count claimed;
- CSO and DAFM beef-kill: aggregate statistics only.

The first implementation must produce both `source_row_count` and `distinct_parent_count`, plus `repeated_child_count`, `quarantined_count`, and an overlap report. A cross-source link needs an explicit evidence packet: source IDs, raw identifiers, reviewed name/address evidence kept privately, match method, reviewer, confidence, and unresolved alternatives. A shared trading name, registered office, certificate, county, or approximate location is not enough.

## Accountability graph and map usefulness

The graph potential is high: competent authority → approval; approval → activity/species/category; SFPA approval → certificate; facility/vessel → EPA licence or compliance event; facility/company → CRO identity; site → planning application; sector/time → CSO or DAFM aggregate; facility/event → reviewed enforcement or welfare observation. Keep graph edges typed and dated. Absence of a public event is not evidence of no event.

Map usefulness is medium for fixed premises because HSE, DAFM, and SFPA expose address fields, but no source coordinates were verified. It is low for vessels as fixed points. EPA and MyPlan geometry is an accountability/development clue, not a substitute for source address review; MyPlan itself warns that portal points/polygons are approximate and unsuitable for site-specific decisions. Geocoding is disabled until source terms, privacy eligibility, residential/mixed-use risk, and publication approval are separately passed. A successful geocode would not authorize publication.

## Environmental, planning, corporate, statistics, funding, and controls

The EPA [licence search](https://www.epa.ie/our-services/licensing/licencesearch/) and [LEAP guidance](https://www.epa.ie/our-services/compliance--enforcement/whats-happening/leap-online/) cover licence/site profiles, inspections, returns, incidents, complaints, non-compliances, and compliance investigations. EPA’s [API documentation](https://data-stg.epa.ie/api-list/leap-open-data/) describes separate endpoint families and identifier-based retrieval. The [LEAP terms](https://www.epa.ie/publications/compliance--enforcement/licensees/performance/LEAP-Online-Terms-%26-Conditions-23-May-2023.pdf) and personal-data controls are a hard gate against bulk copying.

The [MyPlan national planning map](https://www.myplan.ie/national-planning-application-map-viewer/) and [help page](https://www.myplan.ie/help/) say applications are sourced from 31 local authorities and uploaded weekly. Planning records evidence applications, development history, and decisions; they do not prove that an approved food establishment operates. Applicant/personal data and approximate geometry stay restricted.

The CRO [company open-data catalog](https://opendata.cro.ie/dataset/companies) describes daily machine-readable company records and CC BY 4.0. Use company number as an identity edge only. A [CORE search](https://cro.ie/services-and-help/using-services/) or registered office is not operating-premises evidence, and officer data should not enter the released model.

The [CSO livestock slaughterings releases](https://www.cso.ie/en/statistics/agriculture/livestockslaughterings/) provide monthly aggregate context; CSO background notes say monthly data come from DAFM and include DAFM and local-authority approved plants. The [DAFM national beef-kill catalog](https://opendata.agriculture.gov.ie/dataset/national-beef-kill-figures) is described as weekly but the observed resource metadata is historical through 2024 with a 1 August 2024 update. Neither is a current facility census.

Funding is context only. DAFM’s [Seafood Processing Capital Investment Scheme](https://www.gov.ie/en/department-of-agriculture-food-and-the-marine/press-releases/minister-dooley-announces-opening-of-the-seafood-processing-capital-investment-scheme/) describes 2025 support under the Ireland Seafood Development Programme and EMFAF. It must not be joined to establishments by name alone. DAFM’s [control statement](https://www.gov.ie/en/department-of-agriculture-food-and-the-marine/press-releases/statement-on-garda-investigation-into-alleged-offences-of-deception/) describes permanent official-veterinary/technical presence and checks including identification, hygiene, animal welfare/transport, remedies, and animal-by-product disposal. FSAI’s [enforcement notices](https://www.fsai.ie/news-and-alerts/latest-news/fourteen-enforcement-orders-served-on-food-bus-%281%29) and the [FSAI 2024 annual report](https://www.fsai.ie/getmedia/14f8726b-1f98-4d44-90d9-dcdf96d49cef/FSAI-Annual-Report-2024-ENG-Final-Accessible_1.pdf?ext=.pdf) are event/aggregate context. No current row-level facility-linked welfare feed was verified.

## Access, provenance, privacy, and blockers

The checked-in manifest records exact official URLs, retrieval time, capture state, byte-size/hash nullability, and browser accessibility-snapshot hashes. A snapshot hash is not presented as a source-byte hash. Direct PowerShell HTTP was blocked by the execution proxy, and browser-rendered workbook links did not yield a retained file. This is an access blocker, not evidence that the sources lack data.

Primary blockers are:

1. authorized bounded capture of the three DAFM workbooks and headers;
2. export/pagination and cadence contracts for HSE and SFPA;
3. workbook/table status and effective-date semantics;
4. rights and attribution confirmation, especially SFPA copyright and EPA LEAP terms;
5. privacy review for addresses, mixed residential premises, registered offices, vessels, applicants, officers, and enforcement subjects;
6. source overlap and company/licence/planning identity review; and
7. human release approval. No public map, API, promotion, or deployment is authorized by this reconnaissance.

## Staged pipeline plan and difficulty

1. Operator-authorized capture: retain each source artifact privately with URL, retrieval/effective dates, content type, bytes, SHA-256, and terms record.
2. Parse: preserve raw values and source-local IDs; record schema fingerprints and pagination completeness.
3. Normalize: create parent facility/vessel records and one-to-many activity/category/species observations; never overwrite source values.
4. Validate: check identifiers, row lengths, status/effective dates, duplicate approvals, missingness, and source-specific counts.
5. Reconcile: emit candidate overlaps only; require reviewed evidence for cross-source links to EPA, planning, or CRO.
6. Enrich privately: apply coarse geography only after privacy/terms review; keep precise coordinates quarantined.
7. Review and release gate: inspect QA, provenance, privacy, rights, accountability semantics, and publication eligibility before any disposable candidate import or release.

Implementation difficulty is medium-high. The approval topology is understandable, but three competent authorities, three DAFM workbook families, repeated child rows, mobile vessels, approximate planning geometry, and identity/privacy constraints make a production adapter materially harder than a single national CSV. Adapter implementation is intentionally not started until bounded artifacts are lawfully captured.

## Recommended next country

Germany is the recommended next country after Ireland. The repository already has a typed BVL route and partial adapter/refresh scaffolding, so its remaining work is bounded export capture, terms confirmation, duplicate-approval validation, and privacy review. That is a lower incremental implementation cost than starting Ireland’s multi-authority adapter family. This recommendation is operational, not a claim that Germany is more complete or more publishable.
