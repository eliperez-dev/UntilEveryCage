# Canada source reconnaissance

Status: sanitized metadata handoff; no facility rows, names, addresses, coordinates, or downloaded artifacts are retained here. Last checked 2026-09-14 UTC. This is not publication approval or a healthy-pipeline claim.

## Comparison

| Source | Role | Access / coverage | Difficulty |
|---|---|---|---|
| CFIA federally registered/export-eligible meat lists | Slaughter and processing evidence | Official HTML with CSV/XML on some lists; federal/export subsets, not complete domestic coverage | Medium-high |
| Provincial meat-plant datasets | Provincial abattoir/meat-plant coverage | Province-specific open data; Ontario verified | Medium |
| AAFC / Statistics Canada | Livestock, slaughter, farm and production aggregates | Open-data/statistical tables; context only, not facility points | Low for context; unsuitable as facility registry |

## CFIA

Official guidance: <https://inspection.canada.ca/en/food-safety-industry/food-guidance-commodity/meat-products-and-food-animals>. CFIA distinguishes federally licensed and provincially registered establishments, so a federal list is not complete Canadian coverage.

Verified export-list route: <https://inspection.canada.ca/en/importing-food-plants-animals/food-imports/food-specific-requirements/approved-countries/redirectforeignmeatlist>. It exposes CSV/XML, establishment number, country/program filters, activities, and version information, but primarily lists foreign establishments eligible to export to Canada. Country-specific export lists, such as <https://inspection.canada.ca/en/exporting-food-plants-animals/food-exports/requirements-library/mexico-meat-and-poultry/annex-1>, contain Canadian establishment information but are export-eligibility subsets, not necessarily the domestic federal registry.

Establishment numbers are candidate identifiers; semantics across lists require confirmation. Currency is list-specific. Auth, rate limits, redistribution terms, and complete federal coverage remain unresolved. Names, business addresses, phones, and precise locations require privacy screening.

## Provincial meat plants

Verified Ontario dataset: <https://open.canada.ca/data/en/dataset/a763088c-018d-48b7-bf47-3027a8c725b8>. It covers provincially licensed meat plants, including abattoirs and processing plants, with plant identifiers, contact fields, coordinates, and animal classes. It is Ontario-only, not national. Other provinces require separate source, terms, identifier, cadence, and adapter review. Confirm current licence/attribution and apply coordinate/contact privacy review before use.

## Agriculture and Statistics Canada

AAFC livestock/slaughter context: <https://agriculture.canada.ca/en/sector/animal-industry/red-meat-and-livestock-market-3>. Additional farm/statistical context includes <https://agriculture.canada.ca/en/sector/animal-industry/canadian-dairy-information-centre/statistics-market-information/farm-statistics> and the Statistics Canada Business Register overview at <https://www.statcan.gc.ca/en/survey/business/1105>. These support aggregate context and validation, not named farms or facility points; preserve suppression, quality, licence, and privacy notes.

## Readiness block

| Source | Verification | Acquisition | Adapter / validation | Terms/privacy/publication | Blocker / next action |
|---|---|---|---|---|---|
| CFIA | Official guidance/export routes verified; complete federal route unresolved | Not performed; no account/rows | Not implemented/tested | Government-sourced only; distinguish export eligibility/domestic registration; minimize fields | Locate current federal list and privately capture URL/date/size/hash |
| Ontario | Open Government Portal dataset/resource structure verified | Not performed | Not implemented/tested | Confirm current licence/attribution and coordinate privacy | Acquire metadata/bounded schema check; assess other provinces separately |
| AAFC/Statistics Canada | Official aggregate sources verified | Not performed | Not implemented/tested | Aggregate role only; table-specific licences/suppression notes required | Select aggregate tables and keep separate from facility totals |

## Unresolved gaps

Verify the complete CFIA federal registry, verify provinces individually, confirm licences/attribution/rate limits/update cadence/stable identifiers, and make project approval, privacy eligibility, and publication-profile decisions separately from government source origin.
