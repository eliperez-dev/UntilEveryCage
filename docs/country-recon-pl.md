# Poland source reconnaissance

Status: private research and integration planning only. Checked 2026-09-16. No release, deployment, public map, publication approval, or claim of national completeness is implied.

## Decision

Poland is a strong implementation candidate for the animal-products lane. The Chief Veterinary Inspectorate (GIW) exposes a national approved-establishment register with a stable-looking veterinary identifier (`WNI`), section filters, species/category/activity fields, and an XLS export route. The rendered current view is unusually useful for a source-local facility candidate layer, but it is not a clean one-row-per-facility data product: the same WNI can occur across sections and the displayed activity/species/product values are observations attached to that source identity.

Integration difficulty is medium-high. The food register is accessible in HTML but its XLS export could not be captured in this environment; registered-food and animal-by-product lists are separate families; inspection statistics are report-shaped; environmental permits are regional; the EIA database states that access from outside Poland is blocked; and KRS/REGON are organization-identity services rather than facility masters. Keep all publication blocked until terms, privacy, schema drift, identity links, and review gates are complete.

The strongest next-country recommendation is Ireland. The [Food Safety Authority of Ireland approved-premises page](https://www.fsai.ie/enforcement-and-legislation/official-controls/mancp/approved-food-premises) coordinates DAFM, HSE, and SFPA lists, while the [HSE approved-establishments view](https://oapi.fsai.ie/HSEApprovedEstablishments.aspx) currently exposes a refreshed structured view with approval number, trading name, address, business type, activity, and species. That is a good multi-authority adapter rehearsal after Poland, not a claim that Ireland is complete or publication-ready.

## Primary source inventory

| Source | Authority / class | Access and current evidence | Identity and scope | Integration decision |
|---|---|---|---|---|
| [GIW approved establishments](https://www.wetgiw.gov.pl/handel-eksport-import/listy-zakladow) and [GIW register UI](https://zywnosc.wetgiw.gov.pl/spi/zatw/index.php?sekcja=2&lng=0) | Polish official, Chief Veterinary Inspectorate | Rendered HTML with filters and an XLS route; current views observed 2026-09-16; direct source bytes were not retained because shell HTTP was refused and the browser export timed out | `WNI`, name, address, category, species, linked activity, notes; Sections 0–XVI and combined meat view | First adapter target. Preserve source observations; count facilities only after source-local WNI handling |
| [GIW registered establishments](https://www.wetgiw.gov.pl/nadzor-weterynaryjny/wykaz-zakladow-rejestrowanych) | Polish official | Index observed with 14 list families and separate links; list-specific schemas not acquired | Registered food-sector activities including game collection, transport, egg farms, own-use slaughter, marginal/local/limited and retail | Separate adapters/list families; never union registration rows with 853/2004 approvals |
| [GIW animal by-products](https://www.wetgiw.gov.pl/handel-eksport-import/niespozywcze-produkty-pochodzenia-zwierzecego) | Polish official / Inspekcja Weterynaryjna | GIW page and linked [ABP register](https://pasze.wetgiw.gov.pl/uppz1/demo/index.php?l=en) observed; export contract unresolved | Regulation (EC) 1069/2009 / 142/2011 ABP establishments and operators | Separate ABP evidence layer; no addition to food-facility totals |
| [GIW RRW statistical reporting](https://www.wetgiw.gov.pl/publikacje/rrw-sprawozdawczosc-statystyczna/printpage) | Polish official | Current publication/index route observed | RRW-3: welfare, controls and enforcement; RRW-5: animal-origin product establishments; RRW-6: official animal/meat examination | Dated reports/events and aggregates, not a facility master |
| [GUS slaughter 2025](https://stat.gov.pl/obszary-tematyczne/rolnictwo-lesnictwo/produkcja-zwierzeca-zwierzeta-gospodarskie/uboje-zwierzat-gospodarskich-w-ubojniach-i-rzezniach-w-2025-r-,16,1.html) | Polish official, Statistics Poland | Current publication dated 2026-03-02; XLSX attachment; monthly collection | Aggregate slaughter counts and live/slaughter weight from R-09U; reporting obligation covers all slaughterhouses conducting livestock slaughter | Statistics/context only; no named facilities or map points |
| [GIOŚ integrated permits index](https://www.gov.pl/web/gios/instalacje-wymagajace-uzyskania-pozwolenia-zintegrowanego) | Polish official, GIOŚ plus 16 WIOŚ | Central page lists 16 regional registers; regional formats and cadence vary | IPPC installations and permits under Polish/EU IED rules | Environmental permit overlay; regional acquisition required |
| [GDOŚ EIA database](https://www.gov.pl/web/gdos/bazy-danych-o-ocenach-oddzialywania-na-srodowisko) | Polish official | Public BIP database/search described; page explicitly states access from outside Poland is blocked | EIA proceedings/documents, decisions, authorities and project dates | Strong accountability evidence if access is available from Poland; no facility master |
| [Geoportal Urban Register announcement](https://www.geoportal.gov.pl/aktualnosci/nowe-uslugi-w-geoportalu-rejestr-urbanistyczny/) | Polish official, GUGiK/MRIT and local governments | Public WMS/register route; announcement says regular updates and transition by end of September 2026 | General plans, local plans, landscape resolutions, voivodeship plans, landscape audits | Planning/zoning context around reviewed sites, never proof of operation |
| [ARiMR processing support](https://www.gov.pl/web/arimr/startuje-wsparcie-dla-przetworcow) and [PS WPR](https://www.gov.pl/web/rolnictwo/plan-strategiczny-dla-wspolnej-polityki-rolnej-na-lata-2023-27) | Polish official | Current 2026 call page observed; 1–30 September 2026 application window | Funding calls, beneficiaries and projects; not operating authorizations | Separate funding edges; do not infer activity, compliance or throughput |
| [KRS open API](https://prs.ms.gov.pl/krs/openApi) | Polish official, Ministry of Justice | API announced; schema/auth/rate behavior not exercised | Legal entities, KRS number, status and registered information subject to RODO | Exact legal-entity crosswalk only; no operating-site inference |
| [REGON BIR1 API](https://api.stat.gov.pl/Home/RegonApi?lang=en) | Polish official, GUS | Documentation observed; registration/user key required; limits documented | Lookup by REGON, NIP or KRS | Identity evidence only; retain restricted fields and query provenance |
| [EU approved-food establishments](https://food.ec.europa.eu/food-safety/biological-safety/food-hygiene/approved-eu-food-establishments_en) and [TRACES](https://food.ec.europa.eu/horizontal-topics/traces/modules_en) | EU official mirror | Public publication/search surface; Poland national authority remains GIW | EU approval mirror and establishment/activity identifiers if exported | Lineage/cross-check only; never double-count GIW |

No secondary facility compilation, commercial directory, or third-party geocoded list was used.

## GIW route, schema and counts

The source index lists separate GIW views for Section 0 (general scope), Sections I–XVI of Regulation (EC) 853/2004, a combined meat view (I, II, III, IV, V, VI, XII, XIII), and a separate adapted-measures view. The rendered table exposes `LP`, `WNI`, `Nazwa`, `Adres`, `kat.`, `gatunki`, `powiązana działalność`, `uwagi`, and an Article 44 field. Section I exposes category codes `SH` (slaughterhouse) and `CP` (cutting plant), species codes including bovine, goat, sheep, porcine and equine, and filter dimensions for province, WNI, name, Article 44 and TSE exceptions.

| GIW rendered view | Current displayed rows | Interpretation |
|---|---:|---|
| Section 0 | 279 | General activity scope; not a slaughterhouse-only count |
| Section I: domestic ungulates | 1,050 | Approval-register rows keyed by WNI; slaughter/cutting categories and species observations |
| Section II: poultry and lagomorphs | 559 | Approval-register rows keyed by WNI; poultry/rabbit activity/species observations |
| Section III: farmed game | 20 | Approval-register rows |
| Section IV: wild game | 45 | Approval-register rows |
| Section V: minced meat/raw preparations/MSM | 687 | Product/activity approval rows |
| Section VI: meat products | 899 | Product/activity approval rows |
| Section VII: live bivalve molluscs | 0 | No rows in the current rendered view; absence is not a closure conclusion |
| Section VIII: fishery products | 265 | Approval-register rows |
| Section IX: raw milk/dairy | 678 | Approval-register rows |
| Section X: eggs/egg products | 407 | Approval-register rows |
| Section XI: frog legs/snails | 8 | Approval-register rows |
| Section XII: animal fats/greaves | 263 | Product/activity approval rows |
| Section XIII: processed stomachs/bladders/intestines | 219 | Product/activity approval rows |
| Section XIV: gelatin | 10 | Approval-register rows |
| Section XV: collagen | 15 | Approval-register rows |
| Section XVI: highly refined products | 3 | Approval-register rows |
| Combined meat view | 1,686 | Best bounded meat candidate view observed; still source-view rows, not a release count |
| Adapted 853/2004 measures | 49 | Separate legal/measure scope; do not merge into combined meat total |

The section counts sum to 5,407 for Sections 0–XVI only, but that arithmetic is intentionally not a facility total. Sections overlap by WNI and by activity/product/species. The combined meat view is the preferred diagnostic for meat candidates because it is a single source view, but it still requires export-level uniqueness checks and lifecycle review. No address, coordinate, or contact payload was retained in this run.

## Inspection, welfare and enforcement

GIW’s RRW index states that RRW-3 includes animal welfare, controls, nonconformities and administrative/criminal proceedings; RRW-5 covers activities and sanitary condition of animal-origin product establishments; RRW-6 covers official pre- and post-mortem examination and causes of meat being deemed unfit. These reports are valuable accountability evidence, but their row grain is report/table/year or control observation, not automatically `WNI`. Keep the original report and effective year, and distinguish inspection, nonconformity, allegation, administrative action, criminal proceeding and outcome.

The GIW [animal-origin food page](https://www.wetgiw.gov.pl/nadzor-weterynaryjny/zywnosc-pochodzenia-zwierzecego/printpage) and [registered-establishment page](https://www.wetgiw.gov.pl/nadzor-weterynaryjny/wykaz-zakladow-rejestrowanych) establish the broader official-control surface. A source disappearance or missing current row remains `not_observed`; it is never closure, compliance or non-compliance proof.

## Slaughter statistics and funding

GUS’s 2025 slaughter publication says the R-09U results cover all slaughterhouses and abattoirs conducting livestock slaughter in Poland, present total and ritual slaughter in head-counts and live/slaughter weight, and are collected monthly. GUS is therefore a valuable national aggregate context layer but cannot be joined to a named GIW site by total, species, or period. Preserve revision/status information in any later capture.

ARiMR’s current processing-support notice states that applications for investment in processing and placing agricultural products on the market were accepted from 1–30 September 2026 through PUE. The PS WPR page provides the program context. Funding can support an accountability graph edge (`funded_project` → beneficiary/project) when a lawful project dataset is acquired, but it does not prove an operating facility, current approval, throughput, welfare performance, or wrongdoing.

## Environment, permits and planning

GIOŚ states that WIOŚ maintain the registers of installations subject to integrated permits and publishes 16 regional links. This is a real official environmental source family, but not a single national facility export; formats, identifiers and update cadence must be captured per voivodeship. Treat permit holder, installation, permit document, emission condition, monitoring and enforcement as separate observations and preserve historical holders.

GDOŚ describes the EIA database as a statutory system containing strategic EIA, project EIA/re-assessment and Natura 2000 proceedings, sourced from the authorities conducting those proceedings. It also states that access from outside Poland is blocked. This is a concrete acquisition blocker for the current environment, not evidence that the database is empty or incomplete.

The Geoportal announcement says the Urban Register provides plans and spatial data for general municipal plans, local plans, landscape resolutions, voivodeship plans and landscape audits, updated regularly by local-government units. Use this for zoning and planning context around a reviewed facility point. Geometry-only joins are insufficient: preserve the planning act, legal status, publication/effective date and municipality.

## Identity, privacy and overlap policy

- GIW `WNI` is the primary source-local key. Preserve one-to-many observations by section, category, activity, product, species and note. Deduplicate only exact WNI within a declared source view, and never sum section rows into facilities.
- GIW registered-food and ABP identities stay in separate namespaces. A shared name/address is only a review signal.
- RRW, GUS, ARiMR, EIA, IPPC and planning rows are evidence events/claims/overlays, not facility rows.
- KRS `KRS` and GUS `REGON`/`NIP` are exact organization identifiers. A successful identity lookup does not show that the organization operates a GIW site, owns it, controls it, or is a beneficial owner.
- Addresses and coordinates require privacy and precision review. A registered office, sole-trader address, geocoder match, or mixed residential/business site is not automatically an operating facility. No geocoding was performed.
- Keep source origin, project review, project approval and publication as separate fields. All current entries are government-sourced or EU-mirror-sourced evidence, not project-approved or project-published records.

### Map value

The GIW WNI layer can support a reviewed, source-qualified map of approved establishment candidates, with category/species/activity facets and coarse or suppressed location states. The environmental and planning layers can show permit, EIA and zoning context without pretending those documents identify a facility. GUS and RRW can provide aggregate regional/time context, not points. Missing or changed observations must render as dated source states rather than inferred closures.

### Accountability-graph value

Poland has a useful graph shape: `WNI` approval observations connect to activity/species/product claims; RRW adds inspection and outcome events; GIOŚ/WIOŚ adds permit and monitoring edges; GDOŚ adds EIA proceedings; Geoportal adds planning acts; ARiMR adds funding-project relationships; KRS/REGON add exact legal-entity evidence; and TRACES adds an EU mirror lineage edge. Each edge must carry source ID, source-local identifier, observation/effective date, evidence URL, review outcome and publication scope. A graph makes those different claims visible without collapsing them into a single “official facility” fact.

## Legacy boundary and crosswalk

No Poland V1 file was found under `static_data`, `Old CSVs`, or `dirty-datasets`. The machine-readable crosswalk at [`docs/countries/pl/source-crosswalk.json`](countries/pl/source-crosswalk.json) records `rows_found=0` and the checked paths. This is an explicit no-legacy-snapshot result, not evidence that Poland has no facilities. No fuzzy name/address/coordinate matching was attempted.

## Private artifact and provenance record

The tracked manifest is [`data/manifests/pl-source-artifacts.json`](../data/manifests/pl-source-artifacts.json). The only private artifact created is the metadata-only run note at `data/raw/poland/20260916T000000Z/metadata.json`; it contains route observations, displayed counts, schema notes and privacy assertions, not source row payloads. It is ignored as a raw-path artifact except for its explicitly tracked `metadata.json` file. The manifest records its byte size and SHA-256 and records null bytes/hashes for source pages whose bodies were not captured.

The shell network refusal and browser XLS timeout are blockers that must remain visible in any rerun report. Do not replace missing source hashes with hashes of rendered notes. The GIW displayed counts above are web observations, not byte-verified exports.

## Difficulty, staged pipeline and blockers

Difficulty: medium-high.

1. Acquire one bounded GIW XLS export or a complete paginated HTML capture from an authorized Polish execution context; record headers, redirects, retrieval time, bytes, SHA-256, schema fingerprint and any supplied update/effective date.
2. Build a GIW adapter keyed by `(source_id, WNI, section/view, observation dimensions)`; retain raw source values and generate a separate reviewable facility-candidate projection.
3. Add registered-food and ABP adapters as separate source families, beginning with one list and one ABP category; test missing IDs, repeated observations and status/date semantics.
4. Add RRW inspection/welfare/enforcement observations and GUS aggregates with explicit effective periods, report/table keys and no facility-count joins.
5. Add one regional WIOŚ IPPC register, then GDOŚ EIA from an in-Poland/authorized context; preserve regional coverage limits.
6. Add Urban Register/Geoportal planning evidence and exact KRS/REGON links only when an upstream WNI row supplies a reviewed organization key; never query identity sources as a facility discovery mechanism.
7. Run privacy/terms/schema/coverage/duplicate/lifecycle review, then a private candidate handoff. Publication remains blocked pending authorized human review.

Open blockers:

- GIW XLS body, headers, byte hash, export terms and update metadata were not captured in this environment.
- GIW WNI lifecycle/status semantics and cross-section repeat rules need an export-level contract.
- Registered-food and ABP list families have unresolved per-list schemas, cadence and terms.
- RRW reports need current artifact acquisition and careful report-grain modeling.
- GIOŚ/WIOŚ IPPC coverage is regional and heterogeneous; GDOŚ EIA access is geographically blocked from outside Poland.
- KRS/REGON API registration, rate/terms and RODO filtering need a purpose-specific review.
- No national source-approved geocoding or public precision policy was verified.
- No Poland V1 file exists for reconciliation and no publication approval exists.

All artifacts, status changes and code are scoped to this isolated branch. No source rows, addresses, coordinates, publication, deployment, promotion or public exposure were performed.
