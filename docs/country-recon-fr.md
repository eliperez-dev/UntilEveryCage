# France source reconnaissance

Status: source reconnaissance plus a strict live private E2E for the two separate DGAL scopes. No release, publication, or row-level fixture is created in Git; real artifacts remain restricted and ignored. Current source status is maintained in [`source-status.md`](source-status.md).

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
| Géorisques ICPE | Official download/WMS/WFS/API entry points verified | Not attempted; national export dynamic/tokenized | Not started | Mirror licence unspecified; precise coordinates require review | Confirm schema, licence, token/rate rules, and livestock/food rubric coverage |

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

Official pages: <https://www.georisques.gouv.fr/donnees/bases-de-donnees/installations-industrielles>, <https://www.georisques.gouv.fr/acceder-la-carte-interactive-aux-bases-de-donnees-et-lapi>, and <https://www.georisques.gouv.fr/services>. ICPE classifications and rubrics are regulatory evidence, not proof of current animal use, capacity used, or complete farm coverage. The current download schema, licence, token/rate rules, and livestock/food rubric mapping remain unresolved; do not silently substitute the narrower data.gouv mirror.

## Sources not suitable as V1 facility rows

Agreste agricultural census tables are useful for commune-level aggregate context but lack facility identifiers and point locations. BDNI/animal-identification systems are restricted administrative systems rather than public facility downloads. Alim’confiance includes restaurants and retail as well as relevant activities; dataset presence alone is not enough to classify a record as animal agriculture or slaughtering.

## Private retrieval provenance (no raw artifact retained)

All listed requests were bounded and read-only; response bytes were discarded. No row-level values were written to the repository, fixtures, logs, or releases.

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
