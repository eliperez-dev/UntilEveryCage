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

The catalog reported 853 data last updated 2026-09-13 and daily frequency; the 1069 catalog reported last updated 2026-09-11 and daily frequency. Private retrieval was 2026-09-14T05:44:54.7132759Z UTC. The 853 artifact is 49,927,230 bytes (SHA-256 `af1ec6eb7b530fef8dd420cdd08215b36d1b29cb202cf355b87a95fc938d6fea`) with 47,370 data rows; the separate 1069 artifact is 7,708,707 bytes (SHA-256 `4071c10f00f59070f75435988c7b22858bbd24abdc456613d448ff873bd9a2ce`) with 9,935 data rows. Raw files and sanitized metadata remain under ignored `data/raw/italy/` and are not release inputs.

The catalog identifies the Ministry of Health/DGSAN Office 2 and Italian Open Data Licence v2.0. It warns that some coordinates came from OpenStreetMap contributors; this is source metadata, not permission to publish precise points.

## Dictionary investigation (read-only)

The Ministry's [853 data dictionary v2.0](https://www.dati.salute.gov.it/dati/documenti/ID_8_Dataset_Stabilimenti_Italiani_per_gli_alimenti_di_origine_animale_v2.0.pdf) was accessible on 2026-09-14. It defines `num_identificativo_produzione_commercializzazione` as the EU recognition number, `codice_comune` as a six-character ISTAT municipality code, `classificazione_stabilimento` and `codice_impiatto_attivita` as classification/activity fields, and product/export fields as coded descriptions. It also defines supplied `longitudine`/`latitudine`, `stato_localizzazione` (`1` geolocalized, `2` not geolocalized), fiscal/VAT identifiers, `stato_attivita` (`Autorizzata`, `Revocata`, `Sospesa`), and `data_ultimo_aggiornamento` applying to establishment master data or an individual activity.

The dictionary does not settle cross-snapshot identity for repeated activities, coded multi-value normalization, address privacy eligibility, or permission to expose precise coordinates. These remain explicit adapter/review decisions; headers alone are insufficient.

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
| Ministry 853/2004 food establishments | Official catalog and regulatory sections verified | Private current CSV acquired; provenance recorded | Private candidate adapter and shared-contract handoff implemented; bounded real QA quarantines ambiguous duplicates | Italian Open Data Licence v2.0; coordinate provenance partly OSM; ETHICS privacy/approval gates apply | Validate broader snapshots and resolve identity, coded values, and privacy treatment before publication |
| Ministry 1069/2009 by-products | Separate official catalog/dictionary verified | Private current CSV acquired; provenance recorded | Kept separate; no adapter | Same licence and privacy/approval gates | Decide whether scope belongs in project, then validate separately |
| Servlet HTML interface | Official interface identified | Not acquired; JS/cookie challenge | Historical HTML parser is brittle; no API claim | No export/terms contract verified; do not scrape through challenge | Prefer catalog downloads or request authorized export/documented endpoint |

## Integration recommendation

Build a deterministic catalog-download adapter with an explicit dataset variant and format. Validate encoding, delimiter/header, recognition identifiers, status vocabulary, category/activity codes, dates, coordinate ranges, duplicate identifiers, and count changes. Quarantine schema drift and malformed rows. Geocoding, if approved later, must be a separate derived event with provider/query/time/precision/review fields.

Private aggregate QA of the 853 snapshot found 41,844 distinct recognition/activity pairs; 4,529 pairs repeat, covering 10,055 rows. Multiplicity was 3,666 pairs occurring twice, 739 three times, 114 four times, and 10 five times. The adapter therefore retains source-row identity and quarantines repeated pair collisions rather than merging them; this is not evidence of duplicate facilities or an operating-status conclusion.

Do not publish names, addresses, tax identifiers, or precise coordinates merely because the Ministry publishes them. Apply residential/private-location screening, source-origin labels, project approval, and publication profile independently. Government-sourced does not mean current, complete, project-approved, or safe to expose.

## Limitations

This reconnaissance and private candidate adapter do not certify completeness/current accuracy, rate limits/authentication, or publication eligibility. Both artifacts remain private; no public release or healthy-pipeline claim is made. Repeated-activity identity and safe publication treatment of addresses, identifiers, and OSM-derived coordinates remain to be reviewed.
