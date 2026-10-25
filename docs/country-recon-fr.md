# France source reconnaissance

Status: source reconnaissance plus strict live private E2E evidence for the two separate DGAL scopes and a filtered Géorisques ICPE source. No release, publication, or row-level fixture is created in Git; real artifacts remain restricted and ignored. The canonical source inventory and current counts are maintained in [`source-status.json`](source-status.json).

Reconnaissance checked 2026-09-14 UTC under `docs/ETHICS.md`, policy version 1.0, last reviewed 2026-09-12. A later bounded strict live private E2E was verified 2026-09-24. This document is source-status evidence, not publication approval or a recurring-health claim.

## Current bounded E2E evidence — 2026-09-24

Section I produced 1,449 observations and 1,449 private candidates; Section II
produced 1,069 observations and 1,068 private candidates. The scopes remain
separate and their counts are not unique-facility totals. This one-time run
does not establish complete coverage or approve publication. Terms, source
category/identity review, address privacy, geospatial review, factual review,
and release approval remain open. The public projection contains zero rows.

## Readiness

| Source | Discovered / verified | Acquisition | Adapter / validation | Terms / privacy | Blocker / next action |
|---|---|---|---|---|---|
| DGAL approved CE lists | Official Ministry page and Section I/II TXT routes verified | HTTP 200 bounded retrieval with recorded artifact provenance | Shared private lifecycle, source-local handoff, category/quarantine QA, row-free review packet, and graph-candidate rehearsal | Etalab attribution appears on Ministry page; confirm file-specific terms; screen names, addresses, and precise geocodes | Human terms, privacy, category, duplicate, and release review |
| Alim’confiance | Official DGAL Opendatasoft dataset/API/CSV routes verified | Bounded API query HTTP 200; bytes discarded | Not started | Licence Ouverte 2.0 in data.gouv metadata; screen address/coordinate and farm/person fields | Define qualifying activity/agreement labels; do not ingest all food establishments |
| INSEE SIRENE | Official open-data page, bulk route, and API terms verified | Not attempted; API account/subscription and multi-GB bulk | Not started | Licence Ouverte 2.0; diffusion-partielle and personal-data rules are material | Authorized access, partitioned import, NAF mapping, and privacy rules |
| HVE directory | Official Ministry dataset/current CSV verified | HTTP 200 bounded retrieval; bytes discarded | Not started | Licence Ouverte 2.0; voluntary opt-in, head-office address, possible individual farm names | Treat only as labeled HVE subset, never exhaustive farm source |
| Agence Bio professionals API | Official API route, terms/rate limit, and CGU verified | Bounded lookup HTTP 200; response discarded | Not started | Published CGU; manager/address fields require minimization/screening | Confirm nested schema and certificate-link handling; organic subset only |
| Géorisques ICPE | Official download/WMS/WFS/API entry points and V1 OpenAPI pagination/schema verified | Full filtered capture completed: 126 sequential pages, 12,552 returned rows; counts reconciled | 12,503 private candidates imported idempotently; authenticated API walk verified; 49 source rows quarantined for missing native names; source-declared CRS transformed and aggregate-checked in memory | CGU accepted for private acquisition/processing only; Licence Ouverte 2.0 attribution/update-date implementation/review, privacy and release remain separate | 12,458 candidates have a valid private map point; 45 remain unmapped (25 missing projected XY, 20 outside configured extents). Generic certificate compatibility remains with parent |

## Ranked source notes

### DGAL approved CE establishment lists

Official index: <https://agriculture.gouv.fr/liste-des-etablissements-agrees-ce-conformement-au-reglement-ce-ndeg8532004-lists-ue-approved>.

Verified files: [Section I domestic ungulate TXT](https://fichiers-publics.agriculture.gouv.fr/dgal/ListesOfficielles/SSA1_VIAN_ONG_DOM.txt) and [Section II poultry/lagomorph TXT](https://fichiers-publics.agriculture.gouv.fr/dgal/ListesOfficielles/SSA1_VIAN_COL_LAGO.txt). The observed header contains department number, approval number, SIRET, legal/trade name, address, postal code, commune, category, associated activities, and species. `SH` was observed as a slaughterhouse category code and `CP` as a cutting/processing category; freeze the codebook and preserve source values.

These are approved food-establishment lists, not general farm registers. Daily replacement, undocumented abbreviations, encoding/quoting variation, and absent source checksums require deterministic snapshots, schema quarantine, and retrieval provenance. Addresses may involve individuals, agricultural entities, schools, or mixed sites; geocoding must remain a separate enrichment with provider/query/time/precision/review and privacy screening.

### Alim’confiance

Official dataset: <https://www.data.gouv.fr/datasets/resultats-des-controles-officiels-sanitaires-dispositif-dinformation-alimconfiance>. Verified routes include metadata at <https://dgal.opendatasoft.com/api/explore/v2.1/catalog/datasets/export_alimconfiance>, records at <https://dgal.opendatasoft.com/api/explore/v2.1/catalog/datasets/export_alimconfiance/records?limit=...>, and CSV at <https://dgal.opendatasoft.com/explore/dataset/export_alimconfiance/download/?format=csv&timezone=Europe/Berlin&use_labels_for_header=true>.

The dataset covers abattoirs, retail, restaurants, farm sales, catering, and other food businesses. Filter using activity/agreement fields; do not classify every record as a facility in scope. Observed metadata reported a 2026-09-12 update, weekly frequency, and 72,594 records at the checked processing timestamp. This is a live query surface, not an immutable release; snapshot query parameters, retrieval time, response hash, and processing date. SIRETs, addresses, coordinates, farm/person fields, and geospatial fields require minimization and privacy screening.

### INSEE SIRENE

Official dataset: <https://www.data.gouv.fr/datasets/base-sirene-des-entreprises-et-de-leurs-etablissements-siren-siret>; API service: <https://www.data.gouv.fr/dataservices/api-sirene-open-data>.

SIRENE provides broad establishment discovery and crosswalk identifiers, not a facility-specific register. NAF codes are declared administrative activity, not proof of animals, slaughter, or current operation. API access requires account/subscription; the advertised limit is 30 requests/minute. The current stock bulk route is multi-gigabyte, and a versioned 2026-09-01 redirect was observed but not downloaded. Preserve SIRET/SIREN, active/closed dates, diffusion status, and source variables; treat partial-diffusion (`P`) as a hard privacy input and plan for the NAF transition.

The advertised API base was `https://portail-api.insee.fr/catalog/api/2ba0e549-5587-3ef1-9082-99cd865de66f?aq=ALL`; the observed stock-establishment resource redirected to a versioned September 2026 ZIP. These routes support acquisition planning only; access and current schema were not tested here.

### HVE directory

Official dataset: <https://www.data.gouv.fr/datasets/annuaire-des-exploitations-certifiees-haute-valeur-environnementale>. Verified [July 2026 CSV](https://static.data.gouv.fr/resources/annuaire-des-exploitations-certifiees-haute-valeur-environnementale/20260903-130258/annuaire-des-exploitations-hve-juillet-2026.csv). It is a voluntary, non-exhaustive directory. Head-office SIRET/address is not automatically an operating livestock site; use only as a labeled HVE subset and screen possible individual farm names/addresses.

### Agence Bio professionals API

Official records/terms: <https://www.data.gouv.fr/dataservices/api-professionnels-bio>, [CGU](https://api.gouv.fr/resources/CGU%20API%20Professionnels%20du%20bio.pdf). Verified route: <https://opendata.agencebio.org/api/gouv/operateurs/>. It covers organic operators, including farms, processors, distributors, and importers, with active/stopped certification information. The service description advertises 50 calls/second/IP and no availability SLA; treat this as published service information, not a performance guarantee. Preserve nested source values; minimize `manager`, addresses, and social/contact fields. Use only as a labeled organic subset, not a complete farm inventory.

### Géorisques ICPE

Official pages: <https://www.georisques.gouv.fr/donnees/bases-de-donnees/installations-industrielles>, <https://www.georisques.gouv.fr/acceder-la-carte-interactive-aux-bases-de-donnees-et-lapi>, <https://www.georisques.gouv.fr/services>, and [API V1 OpenAPI](https://www.georisques.gouv.fr/api/v3/api-docs/georisques-api-v1). ICPE classifications and rubrics are regulatory evidence, not proof of current animal use, capacity used, or complete farm coverage. V1 `GET /api/v1/installations_classees` documents the `nomenclature`, `page`, and `page_size` parameters and a paginated `{results,page,total_pages,data}` response; the public V1 route answered without a token. The source adapter uses an exact allowlist for animal-holding/agriculture, aquaculture, animal-food and slaughter rubrics and does not use the unfiltered national export.

A bounded live check on 2026-10-20 requested nomenclature 2101, two records per page. Pages 1 and 2 each returned HTTP 200 with two records; both reported 62 matches and 31 pages, and the returned source identifiers did not overlap. This verifies observed paging behavior for that rubric only, not a provider guarantee or a complete snapshot. The source-owned adapter now checks each declared page, stable totals, row-count reconciliation, response hashes, and duplicate AIOT identifiers before producing a private candidate handoff. Its explicit allowlist is maintained in source config and based on the official [21xx animal-agriculture](https://aida.ineris.fr/thematiques/21xx-activites-agricoles-animaux), [22xx agro-food](https://aida.ineris.fr/thematiques/22xx-agroalimentaire), [3641 abattoir](https://aida.ineris.fr/reglementation/3641-exploitation-dabattoirs), and [3660 intensive livestock](https://aida.ineris.fr/reglementation/3660-elevage-intensif) references. Ambiguous mixed/vegetable processing and animal-waste rubrics are excluded. Native facility names, SIRET/AIOT, source activity status, allowlisted rubric details, animal capacity indicators, address and source longitude/latitude are preserved for restricted review; inspection narratives/document links, unrelated rubrics and unknown fields are excluded from the handoff. Coordinates are not geocoded, and overseas France extents are classified separately from metropolitan France.

On 2026-10-21 the configured allowlist was acquired as a complete private snapshot (12,552 returned rows across 126 pages at page size 100; 20 coordinate-bearing candidates were classified outside configured French extents). The adapter produced 12,503 candidate observations and quarantined 49 rows missing a native establishment name. This snapshot contained 12,503 distinct AIOT identifiers among those candidates; AIOT is a source-scoped grouping key, not a project-wide facility identity. The adapter does not collapse distinct observations solely because they share an AIOT; it preserves their observation multiplicity and quarantines an exact repeated source observation. No candidate from this run lacked an AIOT identifier. Detailed counts are in the [canonical source inventory](source-status.json); the ignored acquisition snapshot manifest, source lifecycle manifest, and candidate-handoff manifests retain the private retrieval and checksum evidence under `data/staging/france-graph-20261021/refresh-6c87874b9fbd62f1/`.

The same retained run completed the shared private import and an idempotent replay. Authenticated private API acceptance covered the paginated source-filtered list (12,503 candidates over 63 API pages; native/display names present for all), detail, private facets, map feed, and world viewport. At that time all candidates remained outside default map scope and no public rows were created. Raw API longitude/latitude is not used as a map location: the API schema does not declare its datum. The source separately supplies AIOT projected X/Y and `systemeCoordonneesAIOT`; the adapter now transforms only that source-declared pair to EPSG:4326 through pyproj, with `always_xy=True`, `only_best=True`, and `allow_ballpark=False`, preserving X/Y/EPSG and the API pair as private evidence. An aggregate-only in-memory run over all 12,552 retained observations confirmed non-ballpark operations with reported 1 m accuracy for every observed CRS: 12,346 rows EPSG:2154, 10 EPSG:2972, 87 EPSG:2975, 1 EPSG:4471, and 34 EPSG:4559; all 12,478 transformable pairs agreed with the API lon/lat within 100 m. These are private validation counts, not new DB acceptance. Among the 12,503 normalized candidates, 12,458 source-declared points fall within configured French extents and are eligible for private map scope; 25 have no projected XY pair and 20 transform outside those extents, so remain unmapped. API longitude/latitude comparison is a non-authoritative quality signal only. Publication, privacy, factual, and release gates are unchanged. No geocoding is used.

The legacy generic certificate was not passed. Its v0-clone assumptions compare global rather than source-filtered counts and equate numeric/coarse coordinates with map visibility, which conflicts with this source's explicit unmapped CRS policy and the clone's existing multi-source contents. Direct source-filtered API checks and independent import/replay evidence are the acceptance evidence for this run; certificate compatibility remains open.

The [Géorisques CGU](https://www.georisques.gouv.fr/cgu) explicitly make service use subject to prior acceptance and state that public data is provided under Licence Ouverte 2.0, with attribution and last-update date obligations. The project maintainer approved CGU acceptance for private acquisition and processing only; see the [recorded acceptance](../pipeline/sources/france/georisques_icpe/terms-review.json). The full filtered capture, private import, authenticated API walk, and idempotent replay are verified as described above. The terms decision does not clear attribution implementation/review, external redistribution, privacy, factual, CRS, map, or release gates. No API account/token was created.

A fresh bounded acquisition-only retry on 2026-10-25 used the ordinary filtered API route, at most two attempts per page, and a two-second retry delay. Pages 1–101 were captured into restricted local staging; page 102 failed twice with DNS resolution error 11001. The runner stopped without a complete snapshot manifest or candidate handoff. This partial attempt does not replace the retained 12,548-observation snapshot or establish fresh shared-run health. No database import was attempted. Its partial private artifacts are under `D:\UntilEveryCage-private\captures\fr-georisques-launch-20261025\`.

## Sources not suitable as V1 facility rows

Agreste agricultural census tables are useful for commune-level aggregate context but lack facility identifiers and point locations. BDNI/animal-identification systems are restricted administrative systems rather than public facility downloads. Alim’confiance includes restaurants and retail as well as relevant activities; dataset presence alone is not enough to classify a record as animal agriculture or slaughtering.

## Historical bounded retrieval provenance (2026-09; responses discarded)

This table records the earlier September 2026 bounded reconnaissance requests only; their response bytes were discarded. It does not describe the later retained private Géorisques snapshot above. No row-level values from either effort are tracked in Git, fixtures, logs, or releases; the current raw source pages remain in ignored restricted staging.

| Artifact/query | UTC retrieval | HTTP | Bytes | SHA-256 |
|---|---|---:|---:|---|
| DGAL Section I TXT | 2026-09-14T04:35:06.9602154Z | 200 | 204,211 | `b1171561865ab664ddf18adeeed7b6993224cc2275277fdaa6e4d411dd062649` |
| DGAL Section II TXT | 2026-09-14T04:35:09.6616214Z | 200 | 136,506 | `50af4ba9e7227d876cb89c369dfc8d7c3fb329039cbb82b4985748ec09595643` |
| HVE July 2026 CSV | 2026-09-14T04:35:11.6594779Z | 200 | 2,831,601 | `0498f6804b43ae76f95166258371fe4c31a25e24cff8ee17301d44403cec41cd` |
| Alim’confiance bounded API query | 2026-09-14T04:35:36.5998785Z | 200 | 364 | `cb861a4bb49c6f27b4fc8a630d491f4d865526e634f9c51912b1fa4e3d7727da` |
| Alim’confiance metadata | 2026-09-14T04:36:15.7272614Z | 200 | 19,305 | `b028a4f6fe456a190436fcd03dcadac7c8f54e75c70e17f6cc2a39c51ad43312` |
| Alim’confiance aggregate category query | 2026-09-14T04:36:49.5329067Z | 200 | 320 | `f045dba990abdf588ac2db65f758cfdb1a393c2e5d4f166ab8d4b60ded1f2488` |
| Agence Bio bounded lookup | 2026-09-14T04:35:37.3045285Z | 200 | 24 | `ff530172cf6b5992874e8bfada4002be95aed7f635bd09dee8fed513bbfc1edb` |

## Recommended sequence

1. Start with DGAL Section I/II TXT as a direct slaughterhouse layer, preserving approval number, SIRET, category, activity, species, and raw values.
2. Use Alim’confiance as a separately labeled inspection/corroboration layer and selected producer-farm records.
3. Add HVE and Agence Bio only as labeled voluntary/certification subsets.
4. Use SIRENE as a cross-source backbone only after authorized access and diffusion/privacy handling.
5. Treat Géorisques as a later regulatory complement after schema/licence/token/rubric review.
6. Obtain authorized project approval before any release; acquisition success and government origin are not publication authorization.

## Private candidate implementation status (2026-09-17)

Section I and Section II now run through the shared typed lifecycle and
candidate-handoff contract. Source values remain restricted; normalized rows
keep approval, SIRET, category, activity, species, section, and explicit
uncertainty states. Category codes are tokenized rather than substring-matched;
unknown categories and duplicate source observations stay quarantined. Address
and coordinate fields remain suppressed, geocoding is disabled, and the
non-public graph handoff contains only source-supported claims with
`review_required`, source-scoped identity, and `publication_status: not_eligible`.

Refresh accepts `--previous-normalized`; the shared delta reports additions,
changes, and `not-observed` rows without inferring closure. Review packets are
aggregate-only and retain the prior-run linkage. France sections remain
separate sources and no candidate is owner-approved or public.

The current checked-in evidence is aggregate only. The 2026-09-16 private
reacquisition manifest records 1,448 Section I rows and 1,068 Section II rows,
with zero quarantines in that snapshot; those counts are not a release decision
and the underlying artifacts are not present in Git. Remaining maintainer
decisions are file-specific rights/attribution, address/privacy disposition,
category codebook confirmation, duplicate identity handling, and any
release-specific project approval.
