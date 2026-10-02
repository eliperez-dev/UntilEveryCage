# Spain source reconnaissance

Status: reconnaissance only; no adapter, release, publication, or row-level fixture. Current V2 source baseline marks `es.locations` as partial/blocked until a permitted current artifact and rights review exist.

## Assessment

The strongest competent-authority route identified is AESAN's Registro General Sanitario de Empresas Alimentarias y Alimentos (RGSEAA), especially its subset of Spanish establishments authorised to produce and market products of animal origin under EU rules. Official entry points are [RGSEAA](https://aesan.gob.es/registro-sanitario/empresas-alimentarias), [Spanish establishments authorised in the EU](https://www.aesan.gob.es/registro-sanitario/empresas-espa-olas-ue), and the linked [EU authorised-establishments list](https://food.ec.europa.eu/food-safety/food-hygiene/establishments_en).

AESAN describes RGSEAA as an administrative register covering food operators and establishments in production, transformation, preparation, packing, storage, distribution, transport, and import. It is broader than animal agriculture and includes retail, restaurants, and other sectors; a later adapter must filter by authorised activity/category and keep the source identity separate from any geocoding or legacy transformation. The RGSEAA number is an administrative identifier, not proof of current operational status or public-release permission.

MAPA also exposes sector-specific public searches, including [SILUM animal-feed establishments](https://servicio.mapa.gob.es/es/ganaderia/temas/alimentacion-animal/acceso-publico/registro_general_establecimientos) and [SANDACH establishments](https://servicio.mapa.gob.es/sandachcorebuspub/). These are complements, not substitutes for a food-establishment master: their sector boundaries, current export/schema, and terms require separate verification.

## Access, terms, and privacy

The official pages are publicly reachable in web search, but a bounded direct fetch from this environment was refused by the target host; no artifact was retained and no access control was bypassed. No file-specific licence or redistribution grant was established. Treat official origin as provenance only. Establishment names, postal addresses, operator identifiers, and possible sole-trader/farm information require minimisation, privacy screening, and human publication approval. Do not infer facility completeness from RGSEAA, SILUM, SANDACH, or the EU list.

## Acquisition recipe (private, repeatable)

1. From an approved runner, retrieve only the official AESAN page and its explicitly linked current authorised-establishments export or query route; record final URL, UTC retrieval, HTTP status, content type, byte count, SHA-256, supplied publication/effective date, and terms text.
2. Store the raw response only in access-controlled ignored private storage. Never place row-level values in Git, logs, screenshots, fixtures, or handoff messages.
3. Fingerprint format/encoding, headers, delimiter or JSON schema, identifier fields, activity/category vocabulary, status/date fields, and geographic scope. Quarantine if the route is interactive/session-bound or schema changes.
4. Validate animal-facility coverage separately from feed, SANDACH, retail, restaurant, and general food sectors. Keep any legacy CSV as comparison-only until source identity and transformation history are proven.
5. Apply privacy/terms review, coarse-location policy, suppression controls, and maintainer publication approval before any adapter or release work.

## Implemented regional E2E lane: Catalonia feed/SANDACH register

The official Generalitat dataset [Registre d'establiments del sector de l'alimentació animal i de l'àmbit dels SANDACH](https://analisi.transparenciacatalunya.cat/d/m48e-zdz9) is a current machine-readable regional source. Its official Socrata metadata and export use dataset ID `m48e-zdz9`; the observed export has a pinned 13-column schema and was updated 2026-07-03. Catalog metadata describes quarterly updates and Catalonia coverage. Scope is limited to Catalonia feed-sector operators and specified SANDACH categories; this is not a national Spain register and does not replace or merge with 853/2004.

Official Generalitat open-data reuse guidance allows reuse subject to attribution of the source/department and update date, preservation of content and meaning, and no implied endorsement; dataset-specific terms prevail. A source-specific review authorizes acquisition and private preview only, records remaining privacy/third-party-rights uncertainty, and does not authorize release. The live adapter fetches current metadata and export, fingerprints schema and byte digests, quarantines required-field failures, excludes establishment/company names and personal contacts, and preserves the official facility address, postal/locality fields, and exact municipality code in a private allow-listed location-evidence projection. The source supplies no coordinates, and external geocoding is disabled. Public release remains closed.

Latest verified execution (2026-10-01): 12,341 source rows; 12,117 accepted into the minimized handoff; and 224 quarantined for missing required identity/scope fields. The disposable preview import reported 4,367 grouped candidates, zero source coordinates or map-visible records, and zero public rows. A separate `uec-taxonomy-v1` dry run and SQL verification retained source-native activity/sector values and wrote 4,367 Unclassified assignment sets pending reviewed codebooks; it does not reconcile the legacy all-Spain CSV or claim national coverage. Establishment/company names and personal contacts remain outside normalized handoff; the facility address is carried only in the private location-evidence projection. Review exact personal-data and any dataset-specific rights before any publication decision. See the [row-free run manifest](../data/manifests/catalonia-preview-e2e-20261001.json).

Location-evidence contract verification (2026-10-02) reprocessed that retained snapshot in a disposable database. The private handoff carried address/postal/locality/code evidence without names or contacts. Exact ICGC municipality-code matching resolved 2,370 candidates to coarse capital-locality display points; 1,997 unmatched codes remained unmapped. No external geocoder was called, no per-record human review was used in this private development run, and the result created no public projection or release. See the [row-free location-evidence manifest](../data/manifests/catalonia-location-evidence-e2e-20261002.json).

## Remaining Spain-wide work

National AESAN RGSEAA, MAPA SILUM/SANDACH, and regional registers have distinct sector scopes and terms. They require independent verification and source IDs; none may be silently unioned. `Old CSVs/spain-data.csv` remains a reconciliation-only V1 baseline, not an acquisition source.
