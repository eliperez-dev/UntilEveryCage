# Italy source reconnaissance (V2)

Status: reconnaissance only. No adapter, release, publication, row-level fixture, or downloaded artifact was created. No row-level real data, personal names, addresses, contacts, coordinates, or private artifacts are retained here.

Checked 2026-09-13. This document is source-status evidence, not publication approval or a healthy-pipeline claim.

## Executive finding

The strongest candidate is the Italian Ministry of Health open-data catalog rather than the session-bound `ConsultazioneStabilimentiServlet` interface. The catalog describes daily CSV data, with JSON/XML alternatives, for establishments approved under Regulation (EC) 853/2004, plus a separate 1069/2009 animal-by-products dataset. The servlet and general Ministry landing page presented a JavaScript/cookie security challenge during the read-only check; no bypass or undocumented API inference was attempted.

## Sources and evidence

- Maintainer page: <https://www.salute.gov.it/consultazioneStabilimenti/ConsultazioneStabilimentiServlet?ACTION=gestioneSingolaCategoria&idNormativa=2&idCategoria=1>
- Ministry landing page: <https://www.salute.gov.it/new/it/tema/sistema-di-controllo-della-sicurezza-alimentare/elenchi-stabilimenti/>
- 853/2004 catalog: <https://www.dati.salute.gov.it/it/dataset/stabilimenti-italiani-gli-alimenti-di-origine-animale/>
- 1069/2009 catalog: <https://www.dati.salute.gov.it/it/dataset/stabilimenti-italiani-i-sottoprodotti-di-origine-animale/>
- 853 schema dictionary: <https://www.dati.salute.gov.it/dati/documenti/ID_8_Dataset_Stabilimenti_Italiani_per_gli_alimenti_di_origine_animale_v2.0.pdf>
- 1069 schema dictionary: <https://www.dati.salute.gov.it/dati/documenti/ID_9_Dataset_Stabilimenti_italiani_per_sottoprodotti_di_origine_animale_v2.0.pdf>

The catalog reported 853 data last updated 2026-09-12 and daily frequency; the 1069 catalog reported last updated 2026-09-11 and daily frequency. Category pages may have independent amendment dates. The catalog identifies the Ministry of Health/DGSAN Office 2 and Italian Open Data Licence v2.0. It warns that some coordinates came from OpenStreetMap contributors; this is source metadata, not permission to publish precise points.

## Meaning and schema

The 853/2004 sections are regulatory product/activity sections, not animal species or a simple facility type. Observed concepts include approval number, name, VAT/tax identifiers, town/region, category, associated activities, species, remarks, recognition number, activity/status fields, codes, products, export countries, coordinates, geolocation status, and last-update date. The separate 1069/2009 dataset covers animal by-products with its own recognition number, plant/activity/product codes, coordinates, status, and an optional 853 recognition link.

Keep the datasets separate and preserve original source values. Treat activity/status and coordinates as evidence requiring interpretation and review, not proof of current animal use, safety, completeness, or permission to expose a precise location.

## Acquisition and access

No real-row artifact was acquired or retained. Catalog-linked download routes were documented, but direct retrieval was refused by the environment and the Ministry interface displayed a JS/cookie challenge. This is an acquisition blocker, not evidence that downloads are unavailable. No official API, bulk endpoint, rate limit, or authentication contract was verified; servlet query parameters must not be treated as an API. Prefer catalog-linked downloads or an authorized export, recording HTTP metadata, UTC retrieval, SHA-256, byte size, update date, and adapter/config version. Keep raw artifacts outside Git.

## Historical boundary

The repository’s historical Italy CSV and scraper are legacy/unverified inputs, not evidence of a supported API or current source. Historical transformations, name truncation, province mapping, and third-party geocoding must not be reused as source truth. Legacy rows remain visibly historical.

## Per-source readiness

| Source | Discovered | Acquisition | Adapter / validation | Terms / privacy / publication | Blocker / next action |
|---|---|---|---|---|---|
| Ministry 853/2004 food establishments | Official catalog and regulatory sections verified | Not acquired; direct fetch refused/challenged | Feasible via catalog formats; not implemented/tested | Italian Open Data Licence v2.0; coordinate provenance partly OSM; ETHICS privacy/approval gates apply | Authorized maintainer acquires bounded catalog sample with provenance/hash/size, then synthetic adapter test |
| Ministry 1069/2009 by-products | Separate official catalog/dictionary verified | Not acquired | Separate schema/scope; not implemented | Same licence and privacy/approval gates | Decide whether scope belongs in project, then acquire/validate separately |
| Servlet HTML interface | Official interface identified | Not acquired; JS/cookie challenge | Historical HTML parser is brittle; no API claim | No export/terms contract verified; do not scrape through challenge | Prefer catalog downloads or request authorized export/documented endpoint |

## Integration recommendation

Build a deterministic catalog-download adapter with an explicit dataset variant and format. Validate encoding, delimiter/header, recognition identifiers, status vocabulary, category/activity codes, dates, coordinate ranges, duplicate identifiers, and count changes. Quarantine schema drift and malformed rows. Geocoding, if approved later, must be a separate derived event with provider/query/time/precision/review fields.

Do not publish names, addresses, tax identifiers, or precise coordinates merely because the Ministry publishes them. Apply residential/private-location screening, source-origin labels, project approval, and publication profile independently. Government-sourced does not mean current, complete, project-approved, or safe to expose.

## Limitations

This reconnaissance did not acquire current rows, verify download responses by HTTP, establish rate limits/authentication, or certify completeness/current accuracy. It makes no healthy-pipeline claim.
