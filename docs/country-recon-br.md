# Brazil source reconnaissance

Status: reconnaissance and private artifact/schema validation only. No adapter, candidate import, release, publication, or public API exposure was created. Raw files and row-level samples are retained only under the ignored local path `data/raw/brazil/`.

Last checked: 2026-09-16 UTC, against `docs/ETHICS.md` version 1.0 (last reviewed 2026-09-12), on baseline `87fde1136f09be22e6d65ef1e741298544746a1f`. This report is source-status evidence, not a publication approval or healthy-pipeline claim.

## Decision summary

| Source family | Current finding | Integration decision |
| --- | --- | --- |
| MAPA SIF registered establishments | Official CKAN CSV is live and retrievable. The capture has 24,174 rows but only 3,147 distinct `NR_SIF`; 1,025 SIF numbers repeat, so rows are not facility counts. It contains CNPJ, names, SIF, registration dates, situation, full address, contacts, area/category/class, and occurrence text, but no coordinates. | Conditional go for restricted acquisition and schema validation. Keep establishment identity separate from export/product observations; privacy, terms, and release gates remain blocked. |
| MAPA SIF export-authorized establishments | Official CKAN CSV is live and retrievable. The capture has 37,508 country/product rows and 2,912 distinct SIF numbers across 55 countries. | Conditional go for a separate capability-observation feed. Never use row count as facility count or infer current operation from export presence alone. |
| MAPA SIF establishment report | Official CKAN route and current data dictionary are documented. The dictionary describes area, category, class, SIF, legal name, address, municipality, and UF; it is a supplemental classification report, not a replacement for the registered-establishment file. | Keep separate until a current CSV snapshot and relation semantics are verified. |
| e-SISBI public | MAPA documents public access to service, establishment, and product registrations. The live client exposes JSON routes for establishments, products, capacities, and a GIS address route. A bounded GET returned HTTP 200; the establishment count route returned 10,541, while the list returned 10 records by default. | Conditional go for bounded private capture. Confirm pagination, route parameters, code lists, effective-date/status semantics, address linkage, and update cadence with an authorized operator before recurring retrieval. |
| Trase Brazil facilities | Current 2026 dataset page says it covers 2025 and compiles federal, state, and municipal inspection registries. The private GeoJSON capture has 18,090 feature rows from `SIF database`, `SISBI`, and `SIE database`, with 15,119 source-local facility IDs and 13 repeated `unique_id` groups. It is a high-quality secondary compilation, not MAPA-origin data. | Use as a separately labeled corroboration/coverage benchmark. Do not silently merge it into MAPA or treat its geocodes, status, categories, or constructed IDs as government source facts. |

## Official routes and observed schemas

### MAPA / SIF

The [MAPA SIF page](https://www.gov.br/agricultura/pt-br/assuntos/inspecao/produtos-animal/sif) links the public SIF establishment, export, establishment-report, and statistical routes. The [MAPA open-data catalog](https://dados.agricultura.gov.br/dataset/servico-de-inspecao-federal-sif) identifies the responsible unit as DIPOA/SDA, reports monthly update frequency, UTF-8 encoding, a last-update timestamp of 2 September 2026 03:26 BRT, and displays a Creative Commons Attribution link. That catalog-level indication is recorded as source evidence, not a blanket conclusion about every field, downstream use, personal-data handling, or project publication permission.

The current identity-relevant CSV resources were:

- [Estabelecimentos Registrados no SIF](https://dados.agricultura.gov.br/dataset/062166e3-b515-4274-8e7d-68aadd64b820/resource/97277e92-264a-4dc0-9aea-f87b8ea93798/download/sigsifestabelecimentosregistradosnosif.csv)
- [Estabelecimentos Nacionais Habilitados](https://dados.agricultura.gov.br/dataset/062166e3-b515-4274-8e7d-68aadd64b820/resource/fcb7f87d-0092-4a52-a44b-b3550747b4c2/download/sigsifestabelecimentosnacionais.csv)
- [Relatório de Estabelecimentos](https://dados.agricultura.gov.br/dataset/062166e3-b515-4274-8e7d-68aadd64b820/resource/7d02af92-e3cf-4ae4-af8a-0dad334ffdfa/download/sigsifrelatorioestabelecimentos.csv)

The [registered-establishment dictionary](https://dados.agricultura.gov.br/dataset/062166e3-b515-4274-8e7d-68aadd64b820/resource/c01a51a6-033e-4470-8c31-63998c0eaa38/download/estabelecimentosregistradosnosif.pdf) names the observed fields: CNPJ, legal/trade name, SIF, reservation/registration dates, process number, situation, address, neighborhood, CEP, municipality, UF, telephone, email, product name, category/class, occurrence date, and occurrence description. The observed file is semicolon-delimited UTF-8 and preserves source values as strings. Its `SITUACAO` was `A` for all 24,174 captured rows; that is an observation of this snapshot, not a claim that every SIF facility is active outside it.

The [export-authorized dictionary](https://dados.agricultura.gov.br/dataset/062166e3-b515-4274-8e7d-68aadd64b820/resource/36ba4d24-d828-4f58-a01c-dd8f1dede1e1/download/listasdeestab.nacionaishabilitados.pdf) names country, area, establishment, SIF, UF, municipality, product, validity date, habilitation-occurrence date, and suspension date. It is naturally one-to-many by SIF, country, and product. It should be modeled as dated authorization evidence, not joined into a single establishment row by lossy aggregation.

The catalog and live download behavior observed from this environment was HTTP 200 for GET. The two CSV responses had `Content-Type: text/csv`, ETags, and `Last-Modified: 2 Sep 2026` headers. The raw downloads are ignored and their hashes/sizes are listed below.

### e-SISBI / SISBI-POA

MAPA's [e-SISBI documentation](https://www.gov.br/agricultura/pt-br/assuntos/defesa-agropecuaria/suasa/manuais-e-tutoriais-do-e-sisbi/e-sisbi) says the public access function exposes information about inspection services, establishments, and products registered in services that are integrated or not integrated into SISBI-POA. The [SISBI-POA page](https://www.gov.br/agricultura/pt-br/assuntos/defesa-agropecuaria/suasa/sisbi-1) explicitly distinguishes an active service `Situação SISBI` from establishment and product status, so those states must not be collapsed.

The public application [SGSI establishment route](https://sistemasweb.agricultura.gov.br/sgsi/app/estabelecimentos) is a JavaScript client. Its public bundle exposed these service bases and route families:

| Service | Observed route | Role |
| --- | --- | --- |
| SISBI API | `https://sistemasweb.agricultura.gov.br/sisbi_api/estabelecimentos-sisbi` | Establishment records; separate `/count` route returned `10541`. |
| SISBI API | `https://sistemasweb.agricultura.gov.br/sisbi_api/produtos-sisbi` | Product registrations; `/count` route exists in the client route map. |
| SISBI API | `https://sistemasweb.agricultura.gov.br/sisbi_api/estabs-capacidades` | Capacity/species/category records. |
| SISBI API | `https://sistemasweb.agricultura.gov.br/sisbi_api/servicos-inspecao` | Inspection-service records and status/scope context. |
| GIS API | `https://sistemasweb.agricultura.gov.br/gis_api/gis/genderecos/{idEndereco}` | Coordinate lookup by address identifier. |

Bounded GETs returned `application/json; charset=UTF-8` and HTTP 200. The establishment, capacity, and product list routes returned 10-item arrays by default in this observation; the route did not return a documented page object. Repeated GET responses advertised `Cache-Control: no-store, must-revalidate, no-cache, max-age=0` and no ETag/content length. HEAD requests to the three SISBI list routes returned HTTP 403 while GET succeeded, so acquisition must test the actual method used by the public client. The GIS route returned HTTP 200 with a 106-byte JSON object containing `idEndereco`, `dsTipo`, `nrLongitude`, and `nrLatitude`; the establishment payload carries `idEndereco` but not a complete flat address.

Observed establishment keys include `idEstabSisbi`, `nrProcesso`, `nrRegistro`, `csEstabelecimento`, `csSituacaoEstabelecimento`, `situacaoExclusao`, `dtRegistro`, `idEndereco`, `sgUf`, `nmMunicipio`, `nome`, `tipoEstabelecimento`, and nested `servicoInspecao` and `pessoa`. The nested legal-person object exposes `nrCnpj`, `nmRazaoSocial`, and `nmFantasia`; the service object exposes service ID, UFs, name, status/suspension fields, and address references. Capacity records link `estabSisbiClassificacao` to an establishment and expose category, area, species, capacity type, and `qtCapacidade`. Product records expose product registration/name, commerce and SISBI codes, establishment, standardized product references, active/suspension fields, seal, and scope status.

The public route proves current access and shape, not a stable API contract. Before a recurring adapter, obtain an operator-confirmed pagination/query contract, current code lists, status/effective-date meaning, and source terms. Do not assume that an `idEstabSisbi`, `nrRegistro`, status code, or GIS point is lifetime-stable or publication-eligible without that validation.

MAPA's [service description for SISBI-POA](https://www.gov.br/agricultura/pt-br/assuntos/defesa-agropecuaria/suasa/perguntas-e-respostas-decreto-12-408-2025-e-o-sisbi/perguntas-e-respostas-sisbi) distinguishes SIM, SIE, SIF, and SISBI-POA: SISBI-POA is a standardisation/equivalence system, not a fourth inspection level. The [Planalto text of Decree 9.013/2017](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2017/decreto/d9013.htm) places interstate/international establishments under SIF, while establishments under state, district, or municipal services may execute interstate inspection when their service equivalence is recognized. The [current MAPA service page](https://www.gov.br/pt-br/servicos/solicitar-adesao-de-servico-de-inspecao-estadual-municipal-e-consorcio-publicos-municipais-ao-sisbi-poa) confirms that states, municipalities, and municipal consortia can seek equivalence. Model inspection level and SISBI equivalence as separate dimensions.

### Trase as secondary evidence

The current [Trase Brazil facilities page](https://trase.earth/open-data/datasets/brazil-facilities) is labeled 2026, covers 2025, reports a 1 January 2026 update, and describes a compilation from federal, state, and municipal inspection registries. Its published GeoJSON schema includes company, inspection number, IBGE municipality code, inspection level, state, status, municipality, longitude/latitude, commodity, source, export countries, facility types, capacity units/value/text, facility ID, and unique ID.

The [Trase methodology](https://resources.trase.earth/data/facilities-data/Brazil_slaughterhouses_facilities_methods_2025_07.pdf) says its SISBI inputs included establishments, products, capacities, addresses, and geolocation; its SIF inputs included registered facilities and export-approved facilities. It states that SISBI records were joined by `ID_SISBI`, SIF records by `NR_SIF`, addresses were geocoded using the SISBI GIS API or Google Maps fallback, and the cleaned source families were transformed to a common schema and concatenated. It also states that Trase constructs an ID as `<inspection_level>_<cnpj>_<inspection_number>_1` and does not guarantee lifetime uniqueness after ownership/CNPJ changes.

The captured Trase file had 18,090 features; source values were `SISBI` (10,661), `SIF database` (3,398), and `SIE database` (4,031). Inspection-level values were `SIF` (3,398), `SIE` (9,445), `SIM` (2,778), and `CONSORCIO` (2,454). There were 15,119 distinct `facility_id` values, 18,077 distinct `unique_id` values, and 13 repeated `unique_id` groups. This confirms one-to-many commodity/activity rows and the need for source-local deduplication rules. It does not establish that Trase's source snapshots, cleaning, geocodes, status, or classifications are identical to today's MAPA state.

The Trase page says charts, graphics, maps, and other representations on its platform may be used under CC BY 4.0, while commercial data use should be discussed with Trase. That wording is not treated as blanket permission to redistribute the downloaded raw dataset or its personal/precise location fields. Any project reuse needs a terms/privacy review and explicit attribution/citation.

## Identity, scope, and double-counting strategy

Use source-scoped observation keys first and cross-source identity links second:

1. SIF establishment identity: `sif:<normalized NR_SIF>`, with CNPJ, names, dates, address, and category retained as source attributes. SIF export rows are `sif-export:<SIF>:<country>:<product>:<effective/suspension observation>` and are never collapsed into the establishment master.
2. SISBI establishment identity: `sisbi:<idEstabSisbi>` when present. Keep `idServicoInspecao`, `nrRegistro`, CNPJ, and `idEndereco` as separate supporting keys. Products and capacities are child observations keyed to the SISBI establishment; they must not multiply the displayed facility count.
3. Trase identity: `trase:<unique_id>` or an artifact-row key. Treat its `facility_id`, CNPJ, inspection level, and inspection number as secondary evidence. A link to SIF or SISBI is an explicit reconciliation event only when the source identifier matches exactly or a human-reviewed match is recorded; name, CNPJ, address, or coordinates alone must not silently merge records.
4. Inspection level is not the same as SISBI status. Keep `SIF`, `SIE`, `SIM`, and `CONSORCIO` as authority-level values; keep SISBI equivalence/service/establishment/product states separately. A SISBI establishment can be under a state, municipal, or consortium service.
5. Count facilities by a declared unit: source-local establishment IDs for source coverage, and reviewed cross-source entities for a reconciled view. Never sum SIF rows, export-country rows, product rows, capacity rows, Trase commodity rows, or overlapping SIF/SISBI views as if each were a facility.

No closure should be inferred from disappearance, a suspension field should not be interpreted without its date/semantics, and a source status should remain raw alongside any normalized interpretation.

## Privacy and geocoding

The SIF capture contains CNPJ, company names, complete addresses, CEP, telephone numbers, emails, and occurrence text. e-SISBI responses expose CNPJ/legal-person fields, names, address IDs and potentially address objects; the GIS service returns precise latitude/longitude. Some official facility addresses may be mixed residential/business sites or may identify individuals. Under `docs/ETHICS.md`, retain these fields privately for validation, screen residential/private and harmful locations, and do not publish private contacts or precise coordinates by default. A registered office or geocoder match is not proof of an operating site.

Coordinates are a separate enrichment/evidence field. Preserve source provider (`MAPA GIS`, source-supplied, or later geocoder), query/input, retrieval timestamp, precision, result, and review state. Trase's Google-geocoded points are Trase-derived evidence and must not be presented as MAPA coordinates. Do not geocode before a terms/privacy decision; a successful geocode does not grant publication permission. Public projections should prefer municipality or reviewed coarse geometry when precise publication is not justified.

## Artifact provenance and schema inventory

All artifacts below are local and ignored; none is a repository fixture. Retrieval times are UTC. CSV byte sizes are the captured file sizes; API list responses did not provide a content-length header. The `HEAD 403` observation applies to SISBI list routes, while the recorded sample artifacts were captured with GET.

| Artifact | URL / route | Retrieved | HTTP / content type | Bytes | SHA-256 | Response metadata |
| --- | --- | --- | ---: | ---: | --- | --- |
| SIF registered CSV | [MAPA resource](https://dados.agricultura.gov.br/dataset/062166e3-b515-4274-8e7d-68aadd64b820/resource/97277e92-264a-4dc0-9aea-f87b8ea93798/download/sigsifestabelecimentosregistradosnosif.csv) | 2026-09-16T06:27:27.9394921Z | 200 / `text/csv` | 11,374,764 | `6a9b944ac34f9872b00b32338d5b5f4969c724167d6e2006ec2f71b372538c5a` | ETag `"1788328931.62-11374764"`; Last-Modified 2026-09-02T06:02:11Z |
| SIF export-authorized CSV | [MAPA resource](https://dados.agricultura.gov.br/dataset/062166e3-b515-4274-8e7d-68aadd64b820/resource/fcb7f87d-0092-4a52-a44b-b3550747b4c2/download/sigsifestabelecimentosnacionais.csv) | 2026-09-16T06:27:31.7523210Z | 200 / `text/csv` | 4,864,067 | `7b0540b3f9df244d562495eba07e3be20245219caaebd5d701beba0de636d113` | ETag `"1788328873.14-4864067"`; Last-Modified 2026-09-02T06:01:13Z |
| SISBI establishment sample | [public route](https://sistemasweb.agricultura.gov.br/sisbi_api/estabelecimentos-sisbi) | 2026-09-16T06:34:53.2156653Z | 200 / `application/json; charset=UTF-8` | 25,371 | `33479012c36503b991c8d25f888e2c332bfa91927a8e2adb588e38d4a12902b9` | GET list returned 10 items; no ETag/content length; repeated response `Cache-Control: no-store, must-revalidate, no-cache, max-age=0`; HEAD 403 |
| SISBI capacity sample | [public route](https://sistemasweb.agricultura.gov.br/sisbi_api/estabs-capacidades) | 2026-09-16T06:34:54.3079161Z | 200 / `application/json; charset=UTF-8` | 13,079 | `38f5023812736a691383857e4fcd0c99956ad7ff9606ec9c3097cb2eeab90b40` | GET list returned 10 items; same no-store headers; HEAD 403 observed on list route |
| SISBI product sample | [public route](https://sistemasweb.agricultura.gov.br/sisbi_api/produtos-sisbi) | 2026-09-16T06:34:55.1203410Z | 200 / `application/json; charset=UTF-8` | 35,890 | `2b67d0d56dad29eb68da19c8399edc82c9074a99c7fd15ad7c26c04eda04ea5f` | GET list returned 10 items; same no-store headers; HEAD 403 observed on list route |
| SISBI GIS sample | [public route](https://sistemasweb.agricultura.gov.br/gis_api/gis/genderecos/4836007) | 2026-09-16T06:34:55.9739665Z | 200 / `application/json; charset=UTF-8` | 106 | `72f80b8ac3c9a199cc6ea548bd82e447aca8332f5d1cdfaee659dc3c2912fcb7` | Content-Length 106; no ETag/Last-Modified |
| Trase GeoJSON | [current dataset file](https://resources.trase.earth/data/facilities-data/2026-05-07-br_beef_logistics_map_v6.geo.json) | 2026-09-16T06:28:09.2156309Z | 200 / `application/octet-stream` | 15,888,949 | `11eb5131e0a9379c0bbbff731425726d76db74d8ac21b0356773293c75be32c5` | ETag `"f6e87a7ec515b47c44aa04c533b507cc-2"`; Last-Modified 2026-08-10T14:38:31Z |
| Trase methodology PDF | [methodology](https://resources.trase.earth/data/facilities-data/Brazil_slaughterhouses_facilities_methods_2025_07.pdf) | 2026-09-16T06:27:34.1428599Z | 200 / `application/pdf` | 520,686 | `b506873b2688f218b567d310002a91d1f98d49388982edb73975bb26ecbaa2e9` | Public PDF; methodology says source access dates 2025-03-12/14 |

The hashes above are the captured bytes; they can be regenerated from the ignored files. The machine-readable crosswalk repeats them for automated checks.

## Staged implementation plan

1. **Restricted acquisition contract.** Add a Brazil source-local configuration using the shared bounded acquisition/provenance primitives. Capture URL, retrieval time, HTTP method/status, content type, ETag/Last-Modified when supplied, byte size, SHA-256, catalog/effective date, and schema fingerprint. Keep raw, parsed, normalized, quarantined, and reviewed layers distinct.
2. **Separate adapters.** Implement SIF registered, SIF export authorization, e-SISBI establishments, e-SISBI products, e-SISBI capacities, and GIS lookup as separate evidence families. Preserve all source columns and code values; classify only through reviewed codebooks. Add synthetic tests for repeated activities, missing identifiers, status changes, multilingual text, malformed rows, and mixed residential/business addresses.
3. **Operator-assisted e-SISBI validation.** Confirm pagination/query parameters, whether count endpoints are consistent with list filters, code-list meanings, effective dates, update cadence, address selection, and terms. The current browser route is enough for private reconnaissance but not a stable recurring-ingestion contract.
4. **Identity/reconciliation.** Use SIF number and `idEstabSisbi` as source-local keys. Store cross-source matches as explicit reviewed links with evidence and confidence; never merge by CNPJ/name/address alone. Keep Trase as a labeled secondary source and compare coverage by exact identifiers and aggregate counts only.
5. **Geocoding/privacy review.** Prefer source-provided MAPA GIS points after privacy screening. Any fallback geocoding must record provider/query/time/precision/review state and third-party disclosure. Suppress precise residential/private or unresolved points and propagate restrictions through caches, exports, previews, and reimports.
6. **Count and release gates.** Report counts separately by source, inspection level, authority, active/status interpretation, and facility-vs-activity unit. Run schema drift, sharp-change, duplicate, state-coordinate, and disappearance checks. Publication remains blocked until terms, privacy, project review, release approval, and authorized-maintainer availability are all documented.

## Open questions requiring assistance

- Obtain an operator-confirmed e-SISBI extraction contract and current codebooks; public JavaScript route names are not an API stability promise.
- Confirm MAPA dataset-specific reuse/attribution and personal-data handling beyond the catalog's displayed CC link.
- Confirm whether SIF registration number reuse, SISBI internal ID lifecycle, ownership changes, and service/establishment status codes have documented historical semantics.
- Decide, with human review, what high-level facility fields and coordinate precision are appropriate for publication under the ethics policy.
- Confirm Trase's raw-data reuse terms for this project's non-commercial/commercial use and retain Trase attribution/citation separately from MAPA attribution.
