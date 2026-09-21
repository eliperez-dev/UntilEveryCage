# United States state meat and poultry inspection source reconnaissance

Scope/date: documentation-first reconnaissance of the 29 state Meat and Poultry
Inspection (MPI) programs identified by USDA FSIS, observed 2026-09-18 UTC.
This is private source research, not a current facility capture, publication
approval, or claim that a state list is complete. No row-level facility data,
raw downloads, personal contacts, addresses, coordinates, or sensitive source
artifacts are retained in this repository.

## Executive findings

The federal FSIS [State Inspection Programs](https://www.fsis.usda.gov/inspection/state-inspection-programs)
page says 29 states operate their own MPI programs and that state-inspected
product is limited to intrastate commerce unless a state also participates in
the [Cooperative Interstate Shipment (CIS) program](https://www.fsis.usda.gov/inspection/state-inspection-programs/cooperative-interstate-shipping-program).
The current FSIS CIS establishment page names ten participating states:
Indiana, Iowa, Maine, Missouri, Montana, North Dakota, Ohio, South Dakota,
Vermont, and Wisconsin. CIS is an establishment-level subset, not a second
statewide directory; FSIS lists separate state spreadsheets for each of the ten
states and says no state currently has a supplemental CIS export agreement.

The 29-state inventory is:

* **Meat and poultry:** Alabama, Arizona, Delaware, Illinois, Indiana, Iowa,
  Kansas, Louisiana, Maine, Minnesota, Mississippi, Missouri, Montana, North
  Carolina, North Dakota, Ohio, Oklahoma, South Carolina, Texas, Utah,
  Vermont, Virginia, West Virginia, Wisconsin, and Wyoming.
* **Meat only:** Arkansas, Georgia, Oregon, and South Dakota. South Dakota's
  official page explicitly says poultry inspection remains under USDA FSIS.

FSIS estimates about 1,450 establishments are inspected under state MPI
programs, but this is an all-state aggregate and not a release-ready row count.
State pages often publish a wider licensed universe containing custom-exempt,
retail, distributor, warehouse, wild-game, or poultry-exempt operations. Those
must not be silently counted as inspected slaughter or inspected processing
facilities.

## Reusable acquisition families

| Family | Examples | What is observable | Contract and difficulty |
| --- | --- | --- | --- |
| **Structured HTML roster** | Iowa, North Dakota, Minnesota custom-exempt, Wisconsin service directory | Search/filter tables with names, city/county, phone, classes, license or plant numbers; some expose CSV/XLSX links | Medium. Capture the exact list URL, displayed filters, page count, last-updated text, and export link. Do not assume table pagination is a complete snapshot until verified. |
| **Downloadable roster** | Georgia, Maine, Montana, North Carolina, South Carolina, South Dakota, Texas | PDF, XLSX, or PDF-backed map/list, often with establishment number, class and activity columns | Medium to high. Preserve the file and its revision date privately; PDF tables require schema and OCR/layout validation. A roster revision is an observation, not a closure event. |
| **Interactive map or map-backed page** | Louisiana, North Carolina, Utah, Minnesota | Map/search UI or embedded map with separate state/federal/custom filters | High. Browser-assisted capture may be required; record selected filters, result counts, map layer names, access date, and any download control. Coordinates are source/map output and are not automatically publication-eligible. |
| **Contact/licensing route** | Alabama, Arizona, Arkansas, Delaware, Illinois, Missouri, Oregon, Vermont, Virginia, Wyoming | Official program and application pages; current statewide roster is absent, hidden, or contact-mediated in bounded search | High/manual. Do not invent an API or infer that a licensing application is a facility list. Request an authorized current export or operator-assisted list and record terms and scope. |
| **CIS overlay** | Ten FSIS CIS states | FSIS publishes state-specific XLSX files of current selected establishments | Medium, but separate. Treat CIS workbook rows as an interstate-eligibility observation linked to the state source by exact state/plant identifiers; do not replace or merge the underlying state roster. |

The preferred implementation is one source-local adapter with a source-specific
profile and a common provenance envelope, not 29 bespoke scripts. Profiles
should cover `state_official`, `cis`, `custom_exempt`, `retail_or_handler`, and
`inactive_or_expired` where a source explicitly provides them. A missing row or
changed list must produce `not_observed` or a versioned observation, never an
inferred closure.

## State-by-state inventory

“List route” below means the authoritative state page or document found during
the bounded search. “No public roster located” is an access/reconnaissance
result, not evidence that the state has no list. Scale figures are only quoted
where an official source supplied one; otherwise they are intentionally
`unknown`. Address quality describes the observed publication shape, not the
truth or currentness of an address. No official state source in this scan
provided a documented coordinate provider/precision contract.

| State | FSIS scope | Official state route / delivery | Native identifiers and categories | Scale, cadence, address/coordinate quality, automation |
| --- | --- | --- | --- | --- |
| Alabama | Meat & poultry | [Meat Inspection](https://agi.alabama.gov/animalindustries/meat-inspection/) has program scope and an “Establishments” section, but no current public roster was located in bounded search; official contact is the acquisition route. | State licensing/establishment number is expected but not documented in the public page. The page explicitly distinguishes state, federal, and custom-exempt duties. | 40 program staff reported; plant count unknown. Cadence unknown. Manual/contact-only, high difficulty. Do not use Alabama retail-food or general establishment searches as an MPI roster. |
| Arizona | Meat & poultry | [Animal Services Inspections](https://agriculture.az.gov/node/14) and [department directory](https://agriculture.az.gov/arizona-department-agriculture-directory); current public state roster not located. An old third-party-hosted roster is not treated as current evidence. | Establishment/license number semantics need confirmation from the state. | Scale/cadence unknown. Contact-mediated, high difficulty. Address/coordinates not documented. |
| Arkansas | Meat only | [Arkansas state MPI announcement/rules](https://www.agriculture.arkansas.gov/wp-content/uploads/2022/10/10.4.22-State-Meat-Inspection-Program-Press-Release.pdf) and [processing requirements](https://www.agriculture.arkansas.gov/wp-content/uploads/2022/10/AR-Processing-Plant-Reqs.pdf); no current public roster located. | Meat program only; official rules distinguish inspected establishments from custom establishments and require “Not For Sale” marking for custom product. | Scale/cadence unknown. Contact/manual, high difficulty. No public coordinate contract. |
| Delaware | Meat & poultry | [Meat and Poultry Inspection](https://agriculture.delaware.gov/food-products-inspection/meat-poultry-inspection/) and [Food Products Inspection](https://agriculture.delaware.gov/food-products-inspection/); annual license application is public, but no current statewide establishment roster was located. | Annual establishment license; official establishment, handlers, storage, transport and rendering scopes are broader than slaughter/processing. | Scale/cadence unknown. Contact/licensing route, high difficulty. Address is application/licensing evidence, not necessarily operating-site evidence. |
| Georgia | Meat only | [Meat Inspection](https://agr.georgia.gov/meat-inspection) links a [January 2026 Directory of Licensed Meat Plants](https://www.agr.georgia.gov/sites/default/files/documents/meat-inspections/directory-of-licensed-meat-plants.pdf). | Directory contains establishment numbers, names/addresses, phones, counties/districts, S&P/processing classes, species, Talmadge-Aiken, state-inspected and custom-exempt categories. | Current document revision observed as January 2026; cadence appears edition-based, not formally documented. PDF/address-only; no coordinates. Medium difficulty. Meat-only; do not model poultry state coverage from this directory. |
| Illinois | Meat & poultry | [Illinois Meat & Poultry Inspection](https://agr.illinois.gov/animals/meat-inspection.html) and [license pages](https://agr.illinois.gov/animals/meat-inspection/meat-poultry-license.html); public page reports program scope and licensing but no current official-inspected roster was located. A separate [poultry/rabbit exemption list](https://agr.illinois.gov/animals/meat-inspection/meat-poultry-license/poultry-and-rabbit-exemption-list.html) is not an official inspected-plant list. | AGR location/license fields; Type 1 state slaughter/processing and Type 2 custom-only are explicitly distinct. Annual broker/warehouse licenses and poultry/rabbit exemptions are separate. | Official page says over 150 slaughter/processing establishments, over 700 brokers and more than 60 refrigerated warehouses; date not clear on the page. Contact/manual, high difficulty. Address fields exist in applications; no coordinate contract. |
| Indiana | Meat & poultry | [BOAH Meat & Poultry Inspection](https://www.in.gov/boah/meat-and-poultry-inspection/) links the [state/custom facility list](https://secure.in.gov/boah/meat-and-poultry-inspection/types-of-meat-and-poultry-inspection) and a roster PDF such as [2021 MPI establishments](https://www.in.gov/boah/files/2021-MPI-Establishments.pdf). | State establishment number, name, address, city, ZIP, phone; state-inspected, custom-exempt, CIS and federal populations are explained separately. | Official 2024 meeting material reports 83 official, 55 custom-exempt and 3 limited-permit-retail facilities (141 total); year-specific. PDF/HTML, address-only, no coordinates. Medium difficulty. Indiana is a CIS state; use FSIS CIS XLSX as an overlay. |
| Iowa | Meat & poultry | [IDALS licensing list](https://data.iowaagriculture.gov/licensing_lists/meatpoultry/) is a filterable HTML roster with pagination; [bureau page](https://iowaagriculture.gov/meat-poultry-inspection-bureau) documents scope. | Plant name, city, county, phone, plant class and CIS flag. Classes distinguish federal, state official slaughter/processing, custom, poultry exemptions and retail-related classes. | Page displayed 276 rows and explains class semantics; current page does not provide a stable last-updated field in the observed content. No street address or coordinates in the table. Medium difficulty; exact class vocabulary is reusable. Iowa is CIS. |
| Kansas | Meat & poultry | [KDA Meat & Poultry Inspection](https://www.agriculture.ks.gov/divisions-programs/meat-poultry-inspection) exposes separate links for inspected, custom, USDA, map, wholesalers and other licenses. | Separate inspected/custom lists; exact official establishment numbers and export formats require link-by-link inspection. Program explicitly distinguishes custom-exempt, retail-exempt, inspected slaughter and inspected processing. | Scale not stated on the page. HTML/PDF/map family, medium-high difficulty until list links and revision cadence are pinned. Address/coordinates not documented. |
| Louisiana | Meat & poultry | [LDAF meat and poultry](https://www.ldaf.la.gov/food/selling/meat-poultry) provides an interactive map and an `MPI Directory Aug 2026`/list-of-plants route; [wholesale inspection](https://www.ldaf.la.gov/food/selling/meat-poultry/wholesale-inspection-information) defines inspected scope. | Map/list type includes LDAF-inspected, wholesale inspected and custom-exempt distinctions; establishment numbers are assigned during application. | Edition label observed as August 2026; no official count captured. Map plus linked directory, address/possibly map geometry but no precision/provider contract. High difficulty; filter state must be recorded. |
| Maine | Meat & poultry | [Red Meat and Poultry Inspection](https://www.maine.gov/dacf/qar/inspection_programs/red_meat_poultry_inspection.shtml) links a [State and USDA inspected establishments PDF](https://www.maine.gov/dacf/qar/inspection_programs/documents/mmpi/State%20and%20USDA%20Inspected%20Establishments%202025.pdf), a facility map and a separate custom directory. | Establishment/license information is mixed across state/USDA PDF; custom-exempt is explicitly separate. Exact state establishment-number semantics require schema review. | PDF revision observed as 2025; cadence is document-based. Address/map route, no coordinate contract. Medium-high difficulty. Maine is CIS. |
| Minnesota | Meat & poultry | [MDA starting-a-business page](https://www.mda.state.mn.us/es/node/1436) links the current State “Equal To” list and map; [custom-exempt list](https://www.mda.state.mn.us/es/node/1516) is a separate public HTML roster updated weekly. | Equal-To/state and custom-exempt permits/licenses; custom list includes establishment, address, city, ZIP and phone, with active-license/custom-permit scope. | Custom roster explicitly says weekly updates and occasional (1–4/year) inspection; official Equal-To scale not captured. HTML/map, address-only for custom list, no coordinates. Medium-high difficulty; category split is essential. |
| Mississippi | Meat & poultry | [MDAC Meat Inspection page](https://agnet.mdac.ms.gov/website/Meat_Single?id=12) provides a facility directory-style page and links a [Meat Establishments Map](https://www.mdac.ms.gov/bureaus-departments/regulatory-services/meat-inspection/poultry-faq/); route is web/UI, not a verified bulk export. | Directory records distinguish federal/state inspection, category, custom-exempt status and species; establishment number/ID semantics not confirmed. | Scale/cadence unknown. HTML/map with address and phone; no coordinate contract. High difficulty; row classification must not be inferred from “state inspection” text alone. |
| Missouri | Meat & poultry | [Missouri MPIP](https://agriculture.mo.gov/animals/health/inspections/) is the official program page; no current public statewide facility roster was located in bounded search. | MPIP-inspected official establishments, USDA establishments and custom-exempt facilities are distinct; plant/establishment number semantics need an authorized roster. | An official 2020/21 grant release reported 27 new MDA-inspected and 62 existing USDA/MDA-inspected establishments plus 43 existing custom-exempt facilities; historical/context only. Contact/manual, high difficulty. |
| Montana | Meat & poultry | [Meat & Poultry Inspection Section](https://liv.mt.gov/Meat-Milk-Inspection/Meat-and-Poultry-Inspection/) links [state-inspected establishments](https://liv.mt.gov/_docs/MI/Webpage-State-Plant-List-for-Public-2025.pdf) and a separate custom-exempt list. | State establishment number, name, location, license type, Department of Livestock license number, license status and establishment type. | State roster search result says last update January 8, 2026; custom list has its own dated snapshot. Address is city/location only in observed roster; no coordinates. Medium difficulty. Montana is CIS. |
| North Carolina | Meat & poultry | [Plant Directory](https://www.ncagr.gov/divisions/meat-poultry-inspection/plantdirectory) publishes PDF directories and a map for state, custom, Talmadge-Aiken, all and farmer-service plants; [program information](https://www.ncagr.gov/meat-poultry-inspection/info) gives scale. | Plant number, name/location and coded plant type; directory explicitly separates state, custom, TA, federal and farmer-service files. | NCDA says 186 red-meat slaughter/processing and poultry-processing facilities; date not clear in page. PDF/map, likely address/county; no coordinate contract. Medium-high difficulty. |
| North Dakota | Meat & poultry | [North Dakota meat processors](https://www.ndda.nd.gov/divisions/grain-livestock/meat-inspection/north-dakota-meat-processors) publishes HTML sections for selected/CIS, federal slaughter and custom/exempt processors; [application](https://www.ndda.nd.gov/sites/www/files/documents/files/52498MeatApp_0.pdf) documents fields. | Establishment number, license/exemption number, official/custom/poultry-exemption/retail-exempt types; HTML includes company, address, city, state, ZIP. | Cadence not stated. HTML roster includes street/mailing addresses, but no coordinates. Medium difficulty; separate selected/CIS and custom sections. North Dakota is CIS. |
| Ohio | Meat & poultry | [Ohio Meat Inspection Web Portal](https://www.apps.agri.ohio.gov/MeatInspectionWebPortal/About) is the official portal; [2024–25 annual report](https://dam.assets.ohio.gov/image/upload/v1772547739/agri.ohio.gov/Communications/Annual%20Report/FINAL_August_1_2025_ODA_2024-2025_Annual_Report.pdf) supplies current aggregate scale. | Portal/roster identifier and license fields require direct capture; annual report distinguishes full inspection, CIS and custom-exempt. | Official annual report reports 272 licensed establishments: 144 full inspection, 47 CIS, 81 custom-exempt. Portal/UI, address/coordinates not documented. High difficulty until export/API terms are confirmed. Ohio is CIS. |
| Oklahoma | Meat & poultry | [ODAFF Food Safety](https://ag.ok.gov/divisions/food-safety/) publishes current `2026 Meat Processing`, `2026 State Plant`, and `2026 Custom Plant` lists. | List-specific establishment/license identifiers; program page distinguishes inspected harvesters/processors, state plants and custom plants. Official marks include establishment number. | Current 2026 editions are observed, but row counts and exact file formats were not captured. Downloadable list family, likely address-only; no coordinate contract. Medium difficulty. |
| Oregon | Meat only | [State Meat Inspection Program](https://www.oregon.gov/oda/food-safety/pages/state-meat-inspection-program.aspx) documents a program effective July 2022; no current public roster located. Poultry and rabbits are explicitly out of scope. | State-assigned establishment number is distinct from license number and appears on the Oregon inspection legend. | Scale/cadence unknown. Contact/manual, high difficulty. Red-meat-only; do not add poultry rows. Address/coordinates not documented. |
| South Carolina | Meat & poultry | [Clemson SC Meat-Poultry Inspection](https://www.clemson.edu/public/lph/scmpid/) publishes an [Establishment Directory](https://www.clemson.edu/public/lph/scmpid/) with separate state meat, cross-utilization federal, state poultry, custom-exempt, rendering and handler PDFs plus an Excel accessibility file. | SCMPID establishment/permit/grant fields; separate state meat, poultry, custom-exempt, rendering and handler categories. | Public directory is PDF/XLSX, with annual permit renewal noted by SCMPID. Address quality depends on each PDF; no coordinate contract. Medium difficulty. |
| South Dakota | Meat only | [SDAIB Meat Inspection](https://aib.sd.gov/meat-inspection.html) links [inspected establishments](https://aib.sd.gov/List%20of%20inspected%20establishments.pdf) and a separate custom-exempt list. | Establishment name, town, class; class codes S/P and CIS are explained. State page explicitly says poultry is under USDA FSIS. | Roster revised November 2025; no exact count asserted here. Town-only in inspected PDF, no coordinates. Medium difficulty. Meat-only and CIS. |
| Texas | Meat & poultry | [DSHS inspections and exemptions](https://www.dshs.texas.gov/meat-safety/inspections-exemptions-meat-safety) publishes a linked current “Establishments by Grant Type” document; grant types include full, voluntary, custom and poultry/rabbit exemptions. | Grant/license type, establishment location and state/federal/voluntary/custom distinctions; poultry/rabbit low-volume registration is separate. | Statewide count not captured. Regional DSHS page reports 9 inspected and 11 custom-exempt facilities for Public Health Region 1 only; do not generalize statewide. PDF, address-only, no coordinates. Medium-high difficulty. |
| Utah | Meat & poultry | [Utah Meat and Poultry Inspection](https://ag.utah.gov/animal-industry/meat-and-poultry-inspection-program/) exposes separate federal, state and custom processing/slaughter map sections; [2023 annual report](https://ag.utah.gov/wp-content/uploads/2023-Annual-Report-Final.1-1-compressed.pdf) supplies scale. | Establishment number/license fields appear in the state inspection application; separate federal, state, custom and farm-custom categories. | 2023 report: 4 state harvest, 9 state harvest/process, 8 state process-only, 2 Talmadge-Aiken harvest, 4 Talmadge-Aiken harvest/process, 11 Talmadge-Aiken process-only, 57 custom-exempt and 37 farm-custom permittees (38 official; 94 total in those categories). Map/UI, coordinate contract unknown. High difficulty. |
| Vermont | Meat & poultry | [Vermont Meat & Poultry Inspection](https://agriculture.vermont.gov/food-safety/vermont-meat-poultry-inspection) provides a [Meat Handlers Facilities Search](https://agriculture.vermont.gov/food-safety/vermont-meat-poultry-inspection) link and separate commercial/custom/exemption resources; no stable bulk roster was located. | Meat-handler license classes include commercial slaughterhouse, packing plant, poultry slaughterhouse, custom, distributor, broker, warehouse and renderer; state inspection is separate from handlers. | Scale/cadence unknown; page documents recurring capacity surveys, not a canonical roster. UI/contact route, high difficulty. Address/coordinates not documented. Vermont is CIS. |
| Virginia | Meat & poultry | [VDACS Meat & Poultry Services](https://www.vdacs.virginia.gov/animals-meat-and-poultry.shtml) says the directory of Virginia inspected and custom-permitted facilities is available by contacting the office; no public roster was located. | State establishment/license identifiers not public on the page; inspected and custom-permitted facilities are explicitly separate. | Scale/cadence unknown. Contact-only, highest difficulty among reviewed routes. No public coordinate or redistribution contract. |
| West Virginia | Meat & poultry | [WVDA Meat and Poultry Inspection](https://agriculture.wv.gov/divisions/meat-poultry-inspection/) links a [licensed commercial establishments list](https://agriculture.wv.gov/commercial-list/) and [commercial map/services](https://agriculture.wv.gov/commercial-map-services/). | Establishment number prefixes S, P and SP; list includes county, street/mailing address, circuit, manager/phone and service flags for red meat, poultry, retail, distributor, custom, etc. | List observed as of July 22, 2025; map/list family, address-rich but no coordinate provider contract. Medium difficulty. Validate private-contact exposure before any staging. |
| Wisconsin | Meat & poultry | [DATCP meat processing](https://datcp.wi.gov/Pages/MeatProcessinginWisconsin.aspx) links the [Inspected and Custom Service Directory](https://mydatcp.wi.gov/documents/dfrs/Meat%20Establishment%20Inspected%20and%20Custom%20Service%20Directory.pdf) and the service page exposes PDF, Excel and CSV outputs. | License, plant number, service type, DBA, business location/mailing address, county, phone/email and license activities. Official and custom-exempt are separate; federal rows may appear in the same directory. | Official page reports as of 2026-08-27: 217 state official (61 slaughter, 156 non-slaughter, 45 CIS), 71 custom-exempt, 233 federal, 521 total. PDF/XLSX/CSV, address-rich and no coordinate contract. Low-medium difficulty, but filter federal/state/custom before use. Wisconsin is CIS. |
| Wyoming | Meat & poultry | [Wyoming State Meat Program](https://agriculture.wy.gov/meat-poultry) documents state-inspected, custom-exempt and wild-game categories; no current public roster was located in bounded search. | State license/inspection category; WDA says state-inspected products are intrastate, custom is separate, and wild game is separate. | Scale/cadence unknown. Contact/manual, high difficulty. No public coordinate or redistribution contract. |

## Semantics and safety boundaries

### Slaughter and processing

State official rosters may describe a plant as slaughter, processing, or both;
some use state-specific classes such as Iowa `1ACB`, `1ASO`, `1B`, `OP1A`, or
South Dakota `S/P`. Preserve the source class and source text. A processing-only
row is not a slaughter facility, and a state inspection program does not imply
that every licensed processor has on-site slaughter.

### Custom-exempt

Custom-exempt operations are not inspected product facilities. State sources
consistently describe custom product as for the animal owner/household and
marked “Not For Sale”; inspection is periodic or risk-based rather than
continuous. Custom rows may be useful as a separately labeled processing
capacity evidence layer, but must never be counted as state-inspected slaughter
or processing or treated as eligible for retail/wholesale sale.

### Retail, handlers, brokers, warehouses and exemptions

Retail meat markets, brokers, warehouses, meat-handler licenses, poultry/rabbit
exemptions, farm slaughter registrations, wild-game processors and rendering
plants occur in several state routes. They are legally and operationally
different populations. Keep them in source-specific profiles and do not turn a
license or retail inspection into an inspected slaughter/processing facility.

### Inactive, expired and absent rows

Some state lists include explicit active/inactive or license-status fields;
others are undated PDFs or contact-only routes. Store a source-provided status
and observation date when present. An expired or inactive license is a dated
regulatory observation, not proof that a site closed. A row absent from a later
roster is `not_observed` until the state confirms closure or the source defines
its lifecycle semantics.

### Addresses and coordinates

Observed public rosters range from town-only (South Dakota), city/county-only
(Iowa), city/location (Montana), full street address (North Dakota, West
Virginia, Wisconsin), and map/UI outputs (Louisiana, North Carolina, Utah).
None of the observed state sources documented a coordinate provider, query,
precision, or review state. Do not geocode these rows automatically. A mailing
address, registered office, or map point is not proof of an operating facility
and does not override the repository privacy rules for mixed residential/private
locations.

## Terms, redistribution and access mechanics

The sources reviewed are government pages or official state program pages, but
government origin does not itself grant redistribution rights. Before any
acquisition or release, record the final URL, retrieval UTC, visible revision or
effective date, content type, byte size, SHA-256, source terms/attribution,
filter/query context, and adapter/configuration version. Preserve raw artifacts
only in restricted staging where permitted. Treat public HTML/PDF/XLSX/CSV
availability as an access observation, not a license conclusion.

The default legal/product boundary is intrastate: FSIS says state-inspected
products cannot move interstate unless the establishment is selected under CIS.
The CIS list is therefore an eligibility overlay, not a blanket authorization
for all facilities in a participating state. CIS sources say selected plants
must meet additional conditions, including no more than 25 employees and a
federal review/inspection contract. No state in FSIS's current page has a
supplemental agreement for CIS export to foreign countries.

## Recommended next implementation slice

1. Add a row-free `us.state-mpi` source entry and a private source-local
   acquisition contract with profiles for `state_official`, `cis`,
   `custom_exempt`, and `retail_or_handler`.
2. Start with structured/dated routes: Wisconsin CSV/XLSX, Iowa HTML, North
   Carolina PDFs, Georgia PDF, South Carolina XLSX/PDF, South Dakota PDF,
   Montana PDF, and the ten FSIS CIS workbooks. Use synthetic fixtures for
   schema and classification tests; do not commit real rows.
3. Add contact-assisted capture contracts for states without a public roster.
   The operator must provide the authorized list/export and terms context; no
   hidden endpoint or scraping assumption should be introduced.
4. Validate state-native identifiers and category vocabularies before any
   cross-state comparison. Never merge a state establishment to FSIS by name,
   address, phone or coordinates; only exact source-native IDs or an explicit
   reviewed link event may create a cross-source relationship.

## Primary source index

* [FSIS State Inspection Programs](https://www.fsis.usda.gov/inspection/state-inspection-programs)
* [FSIS States With and Without Inspection Programs](https://www.fsis.usda.gov/inspection/state-inspection-programs/states-and-without-inspection-programs)
* [FSIS Cooperative Interstate Shipment program](https://www.fsis.usda.gov/inspection/state-inspection-programs/cooperative-interstate-shipping-program)
* [FSIS CIS Establishments](https://www.fsis.usda.gov/inspection/state-inspection-programs/cooperative-interstate-shipping-program/cooperative-interstate)
* [FSIS Directive 5740.1](https://www.fsis.usda.gov/policy/fsis-directives/5740.1)

State-specific official routes are linked in the inventory above. The FSIS
central list is the authority for the 29-state/10-CIS inventory used here;
state pages are the authority for each state's roster mechanics and local
classification vocabulary. Where those sources disagree on a count or “number
of states” (for example, a Wisconsin explanatory page saying 30 while FSIS
lists 29), preserve the disagreement and recheck both pages before capture.
