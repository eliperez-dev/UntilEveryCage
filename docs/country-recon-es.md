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

## Recommendation

HOLD. Spain has a credible official discovery route, but current acquisition, export/schema fingerprint, file-specific rights, effective-date semantics, coverage boundaries, and privacy handling are unresolved. A later adapter can proceed only after one permitted current artifact is privately staged and reviewed; no pipeline implementation is authorized by this reconnaissance.
