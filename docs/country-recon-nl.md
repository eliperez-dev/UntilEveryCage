# Netherlands source reconnaissance

Status: private research and integration planning only. As of 2026-09-16. No release, deployment, public map, or publication approval is implied.

## Decision

The Netherlands is a strong next-country implementation candidate, with a current official NVWA approval source that is machine-readable once its SOAP contract is implemented, useful current welfare/enforcement publications, and stable CBS/Eurostat aggregate context. Integration difficulty is medium-high rather than low: the approval source is a SOAP viewer with repeated observation rows, the country has separate NVWA and COKZ competent-authority register families, RVO data is access-controlled, KVK is identity evidence rather than a facility master, and there is no verified national open permit/facility export.

Recommendation: implement a private NVWA adapter first, then add dated evidence layers for NVWA enforcement and COKZ. Keep CBS/Eurostat, DSO/PDOK, KOOP, KVK and RVO as explicitly separate sources. Keep publication blocked until source terms, privacy, identity links, schema drift, and review gates are complete.

The strongest subsequent reconnaissance candidate is Ireland. The official FSAI approved-premises page explicitly routes users to DAFM, HSE and SFPA establishment lists and states that approved establishments receive unique approval numbers; this is a promising multi-authority source shape for a dedicated lane, but it has not been acquired or integration-tested here. See the [FSAI approved food premises page](https://www.fsai.ie/enforcement-and-legislation/official-controls/mancp/approved-food-premises) and [FSAI approval guidance](https://www.fsai.ie/business-advice/starting-a-food-business/approval-of-a-new-business).

## V1 and legacy boundary

No verified Netherlands V1 facility file was found under `static_data`, `Old CSVs`, or `dirty-datasets`. The Netherlands crosswalk therefore records zero legacy rows and zero legacy columns, with no attempted reconciliation. This is an explicit “no legacy snapshot” result, not evidence that no Dutch facilities exist.

The repository’s older V1 facility shape cannot safely be used as the target model. The new source package must preserve approval observations, activities, products, species and lifecycle values before any candidate facility view is produced.

## Primary source inventory

| Source | Authority / class | Access and current evidence | Identity and scope | Integration decision |
|---|---|---|---|---|
| [NVWA approved establishments](https://www.nvwa.nl/onderwerpen/dier/slachthuis-uitsnijderij/overzicht-erkende-slachthuizen-en-uitsnijderijen) | Dutch official | Public viewer; control XML and SOAP endpoint captured privately | `erkenningsnummer` plus one-to-many approval/activity observations; slaughter, cutting, game, meat and other food categories | First adapter; deduplicate only within source and retain every observation |
| [NVWA animal welfare](https://www.nvwa.nl/over-de-nvwa/publicaties/jaarbeeld-2025/dierenwelzijn) and [animal-experiment results](https://www.nvwa.nl/onderwerpen/dier/dierproeven-voor-onderzoek/inspectieresultaten/2025) | Dutch official | Current 2025 HTML publications captured privately | Dated aggregate and institution/inspection evidence, not a facility master | Separate inspection/enforcement evidence tables |
| [NVWA red-meat compliance tables](https://www.nvwa.nl/documenten/eten-drinken-roken/vlees-en-vleesproducten/naleefmonitor/tabellenboek-roodvlees-slachthuizen-met-permanent-toezicht-juli-december-2024) | Dutch official | 24-page PDF published 2025-04-22; effective period Jul-Dec 2024 | Individual slaughterhouse compliance tables; publication says facility NAW came from KVK | Keep period and publication date; reviewed identity link only |
| [COKZ](https://cokz.nl/) registers | Dutch official delegated regulator | Current HTML register captured; register pages expose update dates and tables | `Approval No.` and address/name fields; dairy, farm dairy, eggs and egg products | Separate source family; do not union with NVWA by name/address alone |
| [RVO I&R](https://www.rvo.nl/form/bestanden-webservices) | Dutch official, restricted | WSDL/XSD and service documentation; no data acquired | UBN/location/animal records; authorized users only for restricted data | Blocked pending purpose-specific authorization |
| [KVK open dataset/API](https://developers.kvk.nl/nl/documentation/open-dataset-basis-bedrijfsgegevens-api) | Dutch official identity source | API route and CC BY 4.0 open dataset documented; no calls made | `kvkNummer`, branch identifiers where authorized, activity/SBI and status fields | Link evidence only; no facility inference or UBO use |
| [CBS slaughter 7123slac](https://opendata.cbs.nl/ODataApi/OData/7123slac) | Dutch official statistics | Public OData; current data captured | 6,162 aggregate rows; monthly species/count/weight | Claims/context only; never facility rows |
| [CBS livestock 84952NED](https://opendata.cbs.nl/ODataApi/OData/84952NED) | Dutch official statistics | Public OData; current data captured | 1,003 aggregate rows; twice-yearly agricultural-business scope | Claims/context only; preserve provisional status |
| [Eurostat slaughter API](https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/apro_mt_pann?geo=NL&lang=en) | EU official mirror | Current NL JSON captured; last-updated metadata retained | Multidimensional aggregate, no facility IDs | Harmonized context only; never add to CBS/NVWA counts |
| [PDOK/DSO Omgevingswet](https://api.pdok.nl/omgevingswet/omgevingsdocumenten/ogc/v2?f=html&lang=nl) | Dutch official planning/geometry | Public OGC API; 10 collections observed; production metadata updated 2026-09-15 | RD geometry/document identifiers; legal content comes from DSO services | Planning evidence layer, not a facility master |
| [KOOP official publications](https://data.overheid.nl/dataset/officiele-bekendmakingen) / [SRU](https://zoek.officielebekendmakingen.nl/sru/Search) | Dutch official publications | Daily publication surface; bounded test query returned diagnostics because `keyword` is unsupported | Publication/document IDs, authority, dates, text and links; local coverage varies | Implement collection-specific CQL; no national completeness claim |
| [TRACES approved establishments](https://food.ec.europa.eu/food-safety/biological-safety/food-hygiene/approved-eu-food-establishments_en) | EU official mirror/standard | National links and TRACES context verified; no separate NL artifact acquired | EU establishment approval/activity layer | Keep as mirror provenance, never a second facility population |

Secondary compilations were not used as facility authority. No third-party geocoded directory, commercial company list, or constructed facility compilation is part of this package.

## NVWA approval route and bounded results

The NVWA list page describes approved establishments under Regulation (EC) 853/2004. The control file publishes list codes and the Berichtenboek SOAP endpoint. The current viewer’s request shape is a POST with `Content-Type: text/xml`, a list code, language, and pagination (`cvgOffset`, `cvgLimit`, observed limit 10,000). The response parser exposes `erkenningsnummer`, `handelsnaam`, `adres`, `postcode`, `plaats`, `categorie`, `activiteit`, `producttype`, `diersoortEn`, `regelgeving`, `erkenningssoort`, `specificatiecode`, `aanvangsdatum`, `opheffingsdatum`, remarks and related fields.

The current client groups observations by `erkenningsnummer`. That grouping must not be mistaken for a flat facility export: activity/product/species/specification observations repeat source identities. The bounded responses were parsed privately as follows.

| List code | NVWA label / scope | XML observations | Advertised/unique recognition numbers | Repeated observations |
|---|---|---:|---:|---:|
| `overig_303` | Domestic ungulate slaughter | 118 | 115 | 3 groups |
| `overig_304` | Domestic ungulate cutting | 470 | 470 | 0 |
| `overig_305` | Poultry/rabbit slaughter | 25 | 23 | 2 groups |
| `overig_306` | Poultry/rabbit cutting | 425 | 356 | 69 |
| `overig_307` | Farmed-game slaughter | 16 | 14 | 1 group |
| `overig_308` | Farmed-game cutting | 102 | 102 | 0 |
| `overig_309` | Wild-game processing | 17 | 10 | 3 groups |
| `overig_310` | Wild-game cutting | 86 | 86 | 0 |

These numbers are source-response diagnostics, not a national facility total. The same recognition number can be present across list families, and an observation can represent a product/activity/species authorization rather than a distinct site. Counts must therefore be reported as “observations” or “unique recognition numbers within list,” never summed as facilities.

No geocoding was performed. No closure was inferred from missing or null `opheffingsdatum`; lifecycle semantics require source review. Preserve all nulls and source status values.

## Welfare, inspection and enforcement evidence

The NVWA 2025 welfare yearbook reports 4,418 welfare inspections, 3,136 unique companies and 943 companies receiving a measure; it also reports 137 animal-experiment inspections in 2025, plus the published severity and response breakdown. The 2025 animal-experiment result page identifies 52 institutions/companies, 137 inspections plus 4 audits, and 69 license holders. These are dated publication claims and should not be converted into facility rows without a source-local identity.

The [Zo Doende annual overview](https://www.nvwa.nl/onderwerpen/dier/dierproeven-voor-onderzoek/jaaroverzicht-dierproeven-en-proefdieren-zo-doende) provides 2023 aggregate animal-experiment context (413,746 experiments). It is not a current facility list. The red-meat compliance PDF covers July-December 2024 and was published in April 2025; it includes individual slaughterhouse tables, inspections, official warnings and boeterapporten, but is only one part of NVWA enforcement. Keep its effective period distinct from the 2025 yearbook.

## Statistics and publication state

CBS table 7123slac is monthly, modified 2026-08-21, and currently covers January 1990 through June 2026. It has `Slachtdieren`, `Perioden`, `AantalSlachtingen_1` and `GeslachtGewicht_2`; status markers include provisional and unknown/unreliable/secret values. CBS table 84952NED is twice-yearly, modified 2026-08-26, covers April 2018 through April 2026, and is limited to agricultural businesses above the table’s size threshold. Neither table has named facilities or coordinates.

Eurostat’s `apro_mt_pann` API is a harmonized multidimensional aggregate mirror. The captured response reports dimensions including frequency, meat item, meat, unit, geo and time and a last-updated property observed on 2026-09-03. Eurostat and CBS must remain separate statistical provenance layers, not additive facility or throughput sources.

## Environment, permits and planning

PDOK’s Omgevingswet OGC API exposes production current/full collections, RD geometry and document/geometry identifiers; the service metadata states daily update behavior, no authentication/cost, and CC0 1.0 for that geometry surface. The DSO developer register documents omgevingsdocument, geometry, publication and permit-related APIs, with some APIs requiring an API key. The geometry is only meaningful with DSO document context and legal interpretation.

KOOP/Overheid.nl provides official publications and local permits/announcements through collection-specific SRU routes. The bounded test request used an unsupported generic `keyword` field and produced a diagnostic response with zero rows. The next run must select the correct collection (for example local permits) and use documented CQL. Local/provincial publication feeds are scoped official evidence, not proof of a complete national animal-facility permit register.

## Identity, privacy and overlap

KVK’s documented open dataset includes business identity, activity and status fields and is described under CC BY 4.0; subscribed search/base/branch APIs require an API key. KVK warns that business names, numbers and addresses can become personal data for sole proprietorships or mixed addresses, and protected/private fields and UBO data are restricted. Use KVK as an identity-link evidence source keyed to a source-local recognition/approval/establishment identifier. Do not infer that a KVK record is an animal facility, and do not publish protected fields.

RVO I&R is a service/documentation surface, not an open facility dump. UBN, holder, stall/manager, location and animal information must be treated as restricted until authorization and purpose are documented. COKZ is a distinct official delegated regulator and its HTML registers expose a current farm-dairy table with 357 data rows in the private capture; this is not evidence for all dairy/egg coverage or a reason to merge COKZ and NVWA.

The overlap policy is:

- NVWA: deduplicate recognition numbers only for within-list facility-candidate diagnostics; preserve one-to-many observations.
- COKZ, RVO, KVK and TRACES: preserve source-local identifiers and add only explicit reviewed link records.
- CBS and Eurostat: aggregate claims only; preserve flags, scope and effective period.
- NVWA inspection/enforcement, DSO/KOOP permits and planning: dated evidence observations; absence is not closure, compliance or non-compliance proof.
- Addresses and geometry: retain source precision and review privacy before any map or release; do not automatic-geocode for public output.

## Private artifact and provenance record

The complete manifest is [data/manifests/nl-source-artifacts.json](../data/manifests/nl-source-artifacts.json). Bulk/raw captures remain ignored under `data/raw/` and are not committed.

| Artifact group | Private paths | Size/rows | Provenance and schema |
|---|---|---|---|
| NVWA control and eight approval responses | `data/raw/nl-nvwa/2026-09-16/` | 378,439-byte control; responses 14,199–376,998 bytes; observations as table above | SHA-256, URLs, timestamps and response headers in manifest; XML control/SOAP schemas |
| NVWA current welfare/animal experiments | `data/raw/nl/nvwa-welfare-2025.html`, `nvwa-dierproeven-2025.html` | 254,984 and 223,281 bytes | 200 HTML captures; dated 2025 publication schema |
| NVWA enforcement reports | `data/raw/nl/nvwa-slaughter-enforcement-2024.pdf`, `nvwa-zo-doende-2023.pdf` | 412,995 and 836,656 bytes | 200 PDF captures; 24 pages for red-meat table; effective periods preserved |
| COKZ farm-dairy register | `data/raw/nl/cokz-dairy-register.html` | 107,964 bytes; 357 data rows | 200 HTML; last-modified 2026-09-16; six bilingual columns |
| CBS OData | `data/raw/nl/cbs-slaughter-*`, `cbs-livestock-*` | 6,162 and 1,003 data rows | JSON metadata, properties, categories, periods and data captured; response headers in manifest |
| Eurostat | `data/raw/nl/eurostat-slaughter-nl.json` | 56,379 bytes | 200 JSON; multidimensional aggregate |
| PDOK/DSO | `data/raw/nl/pdok-omgevingswet-root.json`, `*-collections.json` | 3,306 and 24,014 bytes; 10 collections | 200 JSON; public cache headers and production update metadata |
| KOOP/SRU | `data/raw/nl/overheid-sru-slachthuis.xml` | 563 bytes; 0 rows | Diagnostic only: unsupported `keyword`; retained to document access behavior |

The manifest records retrieval timestamps, URLs, HTTP observations, byte sizes, SHA-256 checksums, response schemas and bounded row/collection counts. No facility names, addresses, coordinates, or row-level business data are reproduced in this report.

## Integration difficulty and staged plan

Difficulty: medium-high.

1. Build a private NVWA acquisition/parser contract from the control XML; fingerprint namespaces and fields, paginate explicitly, retain raw observations, and test counts against the eight captured responses.
2. Add a normalized source-local approval-observation table keyed by recognition number plus list code and observation dimensions. Generate facility candidates only as a derived, reviewable view.
3. Add NVWA inspection/enforcement evidence as dated observations, preserving publication/effective periods and avoiding name-only joins.
4. Add COKZ as a separate register adapter; add KVK only through explicit identity-link review. Keep RVO blocked unless authorization is supplied.
5. Add CBS/Eurostat claim adapters and validation for provisional/unknown/secret flags; keep them outside facility counts.
6. Add PDOK/DSO and KOOP document evidence with collection-specific queries and legal/document review; do not promise national permit completeness.
7. Run source-specific privacy, terms, coverage, duplicate, lifecycle and release review. Only then prepare a release candidate; the current package remains private.

## Open blockers

- NVWA SOAP schema, pagination, code-list completeness, lifecycle/status semantics and terms need a repeatable adapter contract.
- Recognition numbers are strong source-local keys but cross-authority links are not established.
- COKZ has multiple register families with register-specific dates and no verified uniform API/export contract.
- RVO I&R requires authorization; restricted location/holder/animal data cannot be scraped or exposed.
- KVK API choice, query limits, attribution and personal-data handling need a per-run review record.
- The detailed red-meat enforcement source is effective Jul-Dec 2024, not current 2025 enforcement.
- KOOP’s initial SRU query was rejected because of unsupported field syntax; local permit coverage is heterogeneous.
- No national open permit/facility master or source-approved geocoding policy was verified.
- No Netherlands V1 file exists for reconciliation, and no publication approval exists.

