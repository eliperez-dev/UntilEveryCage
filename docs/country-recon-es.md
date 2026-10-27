# Spain source reconnaissance

Status: the national AESAN RGSEAA bulk-workbook route and a separate Catalonia feed/SANDACH route are implemented as private candidate sources. The national route's shared private acquisition, importer replay, and API/map checks are recorded in the [canonical source inventory](source-status.json); those checks are not publication approval. National AESAN coverage and Catalonia-only coverage remain separate. No rows, addresses, native identifiers, or raw artifacts are committed.

## Assessment

The strongest competent-authority route identified is AESAN's Registro General Sanitario de Empresas Alimentarias y Alimentos (RGSEAA), especially its subset of Spanish establishments authorised to produce and market products of animal origin under EU rules. Official entry points are [RGSEAA](https://aesan.gob.es/registro-sanitario/empresas-alimentarias), [Spanish establishments authorised in the EU](https://www.aesan.gob.es/registro-sanitario/empresas-espa-olas-ue), and the linked [EU authorised-establishments list](https://food.ec.europa.eu/food-safety/food-hygiene/establishments_en).

AESAN describes RGSEAA as an administrative register covering food operators and establishments in production, transformation, preparation, packing, storage, distribution, transport, and import. It is broader than animal agriculture and includes retail, restaurants, and other sectors; the national candidate adapter filters by authorised activity/category and keeps source identity separate from any geocoding or legacy transformation. The RGSEAA number is an administrative identifier, not proof of current operational status or public-release permission.

MAPA also exposes sector-specific public searches, including [SILUM animal-feed establishments](https://servicio.mapa.gob.es/es/ganaderia/temas/alimentacion-animal/acceso-publico/registro_general_establecimientos) and [SANDACH establishments](https://servicio.mapa.gob.es/sandachcorebuspub/). These are complements, not substitutes for a food-establishment master: their sector boundaries, current export/schema, and terms require separate verification.

## Access, terms, and privacy

AESAN's [legal notice](https://www.aesan.gob.es/aviso-legal) permits reuse unless a contrary notice applies, with source/update-date attribution and preservation of meaning. Its [open-data page](https://www.aesan.gob.es/datos-abiertos) lists RGSEAA. The adapter retains `Razon_Social`, industrial addresses and native sector classifications in private evidence. Candidate business-label retention passed fresh shared-runner import and replay checks. Dated-release inclusion remains separate from private acquisition and enrichment.

## Implemented national AESAN RGSEAA lane

The national source is AESAN's published [Listado completo](https://www.aesan.gob.es/registro-sanitario/empresas-alimentarias) XLSX (`260901_Industrias_RGSEAA.xlsx`) linked from the RGSEAA page, discovered as a bulk workbook rather than an API. It is not the V1 Spain CSV and is not a union with Catalonia or other registers. The workbook declares an update date of 2026-09-01; the captured response returned HTTP 200 with the publisher's `Last-Modified` value of 2026-09-08 13:41:47 GMT. The ignored private capture and acquisition metadata retain final URL, retrieval timestamp, response headers, bytes, SHA-256, terms evidence, and source date. The pinned one-sheet schema is `N_RGSEAA`, `Razon_Social`, `Domicilio_industrial`, `Provincia`, `CCAA`, `Clave`, and `Clave_Descripcion`; drift fails closed.

The [AESAN RGSEAA guide](https://www.aesan.gob.es/dam/jcr:fad0c267-172d-42a3-b758-24a537da3b3e/Gu%C3%ADa_RGSEAA.pdf) describes a post-primary-production food register, not a complete animal-agriculture census or proof of current operations. Handoff is limited to exact source keys 10 (meat), 12 (fishery products), 14 (eggs), and 15 (dairy). These are sector keys, not proof that a particular facility slaughters or performs another specific activity. The source's native keys and descriptions remain source-linked evidence; no project activity category is inferred.

The [source inventory](source-status.json) owns current counts, digests and API/map acceptance. AESAN supplies no coordinates. Separate enrichment uses the ordinary public finder's province/sector Excel export, exact registration/province joins and the official [IGN NGMEP 2026 archive](https://centrodedescargas.cnig.es/CentroDescargas/detalleArchivo?sec=9000004). A municipality/province match supplies an approximate municipality point. Name matching accepts the canonical IGN name, its exact slash-separated components, and trailing-article reorderings derived from those names. Province matching remains exact; matches to different municipality codes remain ambiguous. The evidence records any name-format rule used. Existing provider address points are not replaced by municipality references. Unsupported province labels, conflicting registration matches and unknown municipality names stay unresolved; no fuzzy coordinates are generated.

The separate worker is `python -m pipeline.sources.spain_rgseaa.cohort_acquisition <current-handoff-records.jsonl> <events.jsonl> --strategy bulk`. Set `UEC_REAL_PREVIEW_RUNS_ROOT` to its permitted external artifact root; it paces public form/export requests, checkpoints completed source keys and retains bounded raw exports with hashes. Build the reusable IGN index with `write_ign_reference_index` in `municipality_reference.py` from the normally downloaded official archive, retaining its actual retrieval time and attribution. Apply it with `python pipeline/scripts/stages/activate-spain-aesan-ign-reference.py <events.jsonl> <reference-index.json>`. These private helpers currently guard the assigned disposable database `uec_launch_sources_test_20261025`; do not point them at a frozen or serving database. Acquisition, enrichment and publication remain separate tasks.

No legacy V1 rows were reused or reconciled. The legacy CSV remains comparison-only until provenance and transformation history are independently established.

## Acquisition recipe (private, repeatable)

1. From an approved runner, retrieve only the official AESAN page and its explicitly linked current authorised-establishments export or query route; record final URL, UTC retrieval, HTTP status, content type, byte count, SHA-256, supplied publication/effective date, and terms text.
2. Store the raw response only in access-controlled ignored private storage. Never place row-level values in Git, logs, screenshots, fixtures, or handoff messages.
3. Fingerprint format/encoding, headers, delimiter or JSON schema, identifier fields, activity/category vocabulary, status/date fields, and geographic scope. Quarantine if the route is interactive/session-bound or schema changes.
4. Validate animal-facility coverage separately from feed, SANDACH, retail, restaurant, and general food sectors. Keep any legacy CSV as comparison-only until source identity and transformation history are proven.
5. Apply privacy/terms review, coarse-location policy, suppression controls, and maintainer publication approval before any adapter or release work.

## Implemented regional E2E lane: Catalonia feed/SANDACH register

This is a separate Catalonia-only source, not part of the national AESAN RGSEAA
candidate cohort; its counts and readiness are tracked separately in the source
inventory.

The official Generalitat dataset [Registre d'establiments del sector de l'alimentació animal i de l'àmbit dels SANDACH](https://analisi.transparenciacatalunya.cat/d/m48e-zdz9) is a current machine-readable regional source. Its official Socrata metadata and export use dataset ID `m48e-zdz9`; the observed export has a pinned 13-column schema and was updated 2026-07-03. Catalog metadata describes quarterly updates and Catalonia coverage. Scope is limited to Catalonia feed-sector operators and specified SANDACH categories; this is not a national Spain register and does not replace or merge with 853/2004.

Official Generalitat open-data reuse guidance allows reuse subject to attribution of the source/department and update date, preservation of content and meaning, and no implied endorsement; dataset-specific terms prevail. A source-specific review authorizes acquisition and private preview only, records remaining privacy/third-party-rights uncertainty, and does not authorize release. The live adapter fetches current metadata and export, fingerprints schema and byte digests, quarantines required-field failures, excludes establishment/company names and personal contacts, and preserves the official facility address, postal/locality fields, and exact municipality code in a private allow-listed location-evidence projection. The source supplies no coordinates, and external geocoding is disabled. Public release remains closed.

Historical verified execution (2026-10-01): the retained Catalonia snapshot was imported into a disposable preview database, with a separate `uec-taxonomy-v1` dry run and SQL verification. That work does not reconcile the legacy all-Spain CSV or claim national AESAN coverage. The [canonical source inventory](source-status.json) owns the latest Catalonia run and its aggregates. See the [row-free 2026-10-01 run manifest](../data/manifests/catalonia-preview-e2e-20261001.json).

Location-evidence contract verification (2026-10-02) reprocessed that retained snapshot in a disposable database. The private handoff carried address/postal/locality/code evidence without names or contacts. Exact ICGC municipality-code matching resolved 2,370 candidates to coarse capital-locality display points; 1,997 unmatched codes remained unmapped. No external geocoder was called, no per-record human review was used in this private development run, and the result created no public projection or release. See the [row-free location-evidence manifest](../data/manifests/catalonia-location-evidence-e2e-20261002.json).

## Remaining Spain-wide work

MAPA SILUM/SANDACH and other regional registers have distinct sector scopes and terms. They require independent verification and source IDs; none may be silently unioned with AESAN or Catalonia. `Old CSVs/spain-data.csv` remains a reconciliation-only V1 baseline, not an acquisition source.
