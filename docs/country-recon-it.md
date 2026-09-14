# Italy source reconnaissance (V2)

Status: reconnaissance only. Two current catalog artifacts were acquired privately for schema/provenance inspection; no adapter, release, publication, or row-level fixture was created. No row-level values are retained in this document.

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

The catalog reported 853 data last updated 2026-09-13 and daily frequency; the 1069 catalog reported last updated 2026-09-11 and daily frequency. Private retrieval was 2026-09-14T05:44:54.7132759Z UTC. The 853 artifact is 49,927,230 bytes (SHA-256 `af1ec6eb7b530fef8dd420cdd08215b36d1b29cb202cf355b87a95fc938d6fea`) with 47,369 data rows; the separate 1069 artifact is 7,708,707 bytes (SHA-256 `4071c10f00f59070f75435988c7b22858bbd24abdc456613d448ff873bd9a2ce`) with 9,935 data rows. Raw files and sanitized metadata remain under ignored `data/raw/italy/` and are not release inputs.

The catalog identifies the Ministry of Health/DGSAN Office 2 and Italian Open Data Licence v2.0. It warns that some coordinates came from OpenStreetMap contributors; this is source metadata, not permission to publish precise points.

## Meaning and schema

The 853/2004 sections are regulatory product/activity sections, not animal species or a simple facility type. Observed concepts include approval number, name, VAT/tax identifiers, town/region, category, associated activities, species, remarks, recognition number, activity/status fields, codes, products, export countries, coordinates, geolocation status, and last-update date. The separate 1069/2009 dataset covers animal by-products with its own recognition number, plant/activity/product codes, coordinates, status, and an optional 853 recognition link.

Keep the datasets separate and preserve original source values. Treat activity/status and coordinates as evidence requiring interpretation and review, not proof of current animal use, safety, completeness, or permission to expose a precise location.

## Acquisition and access

Catalog-linked downloads succeeded through an authorized direct HTTPS route; the session-bound servlet still displayed a JS/cookie challenge and was not scraped. No official API, bulk endpoint, rate limit, or authentication contract was verified; servlet query parameters must not be treated as an API. Raw artifacts remain outside Git. The recorded artifacts establish acquisition integrity only, not permission to publish rows.

## Historical boundary

The repository’s historical Italy CSV and scraper are legacy/unverified inputs, not evidence of a supported API or current source. Historical transformations, name truncation, province mapping, and third-party geocoding must not be reused as source truth. Legacy rows remain visibly historical.

## Per-source readiness

| Source | Discovered | Acquisition | Adapter / validation | Terms / privacy / publication | Blocker / next action |
|---|---|---|---|---|---|
| Ministry 853/2004 food establishments | Official catalog and regulatory sections verified | Private current CSV acquired; provenance recorded | Adapter not implemented; mapping requires dictionary review | Italian Open Data Licence v2.0; coordinate provenance partly OSM; ETHICS privacy/approval gates apply | Review dictionary and implement synthetic-only adapter |
| Ministry 1069/2009 by-products | Separate official catalog/dictionary verified | Private current CSV acquired; provenance recorded | Kept separate; no adapter | Same licence and privacy/approval gates | Decide whether scope belongs in project, then validate separately |
| Servlet HTML interface | Official interface identified | Not acquired; JS/cookie challenge | Historical HTML parser is brittle; no API claim | No export/terms contract verified; do not scrape through challenge | Prefer catalog downloads or request authorized export/documented endpoint |

## Integration recommendation

Build a deterministic catalog-download adapter with an explicit dataset variant and format. Validate encoding, delimiter/header, recognition identifiers, status vocabulary, category/activity codes, dates, coordinate ranges, duplicate identifiers, and count changes. Quarantine schema drift and malformed rows. Geocoding, if approved later, must be a separate derived event with provider/query/time/precision/review fields.

Do not publish names, addresses, tax identifiers, or precise coordinates merely because the Ministry publishes them. Apply residential/private-location screening, source-origin labels, project approval, and publication profile independently. Government-sourced does not mean current, complete, project-approved, or safe to expose.

## Limitations

This reconnaissance does not certify completeness/current accuracy, rate limits/authentication, or publication eligibility. Both artifacts are private candidates only; no release or healthy-pipeline claim is made. No source-local adapter was added because the current dictionary-to-contract mapping and safe publication treatment of addresses, identifiers, and OSM-derived coordinates remain to be reviewed.
