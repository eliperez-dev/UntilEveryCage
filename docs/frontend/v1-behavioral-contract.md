# V1 behavioral contract

This document freezes the user-critical behavior observed in the public
vanilla-JavaScript application at the 2026-09-20 checkpoint. The normative
machine-readable record is [v1-behavioral-contract.json](v1-behavioral-contract.json);
the Jest contract test requires every JSON requirement ID to be named here.
This is a migration and test contract, not a data-completeness, factual-truth,
privacy-clearance, or V2 launch claim.

## Disposition vocabulary

* **preserve_user_critical** means retain the interaction until an equivalent
  replacement is implemented and verified.
* **v2_privacy_review_replacement** means V2 intentionally changes exposed
  behavior to enforce release-scoped privacy, review, precision, provenance,
  and honest coverage context. Government origin is not approval or completeness.
* **deferred_to_eli_v2_frontend_overhaul** means this lane records the
  requirement but does not redesign the frontend, write CSS, or implement V2
  API/frontend behavior. Eli owns the later responsive, accessible,
  performance-tested, production V2 experience.

## Preserved user-critical behavior

### Search and geographic filters

`V1-SEARCH-001` preserves case-insensitive, debounced facility-name search
across USDA establishment names, APHIS lab account names, and inspection
account names. The suggestion dropdown contains USDA and lab matches. See
`FilterManager.filterUsdaLocations`, `FilterManager.filterLabs`,
`FilterManager.filterInspections`, and `SearchManager.updateSearchResults`.

`V1-SEARCH-002` preserves OR matching for USDA DBA, animals slaughtered,
animals processed, and mapped facility-type text; labs also match animal-use
text and laboratory terms; inspection rows match license-type terms. `cow` and
`cows` normalize to `cattle` for USDA animal text. An empty query closes and
clears the suggestion dropdown.

`V1-GEO-001` preserves the data-derived country selector (All, US, DE, ES, FR,
CA, MX, DK, NZ, UK where evidence is present). Selecting a country filters all
categories and resets its region selector; All hides the region selector.
`V1-GEO-002` preserves state/province semantics for US, Germany, Spain, Canada,
Mexico, and the UK, and city-as-region semantics for Denmark. France currently
does not narrow by selected state, and missing France/Denmark region data is
shown as a disabled explanatory option. That quirk is recorded rather than
silently “fixed.”

### Types, map, and detail discovery

`V1-TYPE-001` preserves the six checked-by-default toggles: slaughterhouses,
processing plants, labs, breeders, dealers, and exhibitors. Type mapping is
category-aware, and APHIS inspection rows use Class A/B/C license types.
Turning one toggle off removes that category from markers, counts, and export
rows only.

`V1-DISCOVERY-001` records the actual V1 surface: it is map-first, with Leaflet
markers and a search suggestion dropdown; a suggestion focuses a marker and
opens its popup, and the popup is the detail view. V1 has no complete result
list. `V1-MAP-001` preserves category colors/icons (slaughter red, processing
gray, lab violet, breeder yellow, dealer orange, exhibitor green), unified
marker clustering at the selected-result threshold, and marker-to-detail
reachability. `V1-MAP-002` records a known initialization mismatch: the HTML
slider displays 1,750 while `FilterManager` starts at 2,800 until slider input.
The mismatch is evidence to reconcile, not a reason to change V1 silently.

### Restorable state, reset, and export

`V1-URL-001` preserves URL state for `lat`, `lng`, `zoom`, `country`, `state`,
`search`, and active `layers`; load restores those values. `V1-URL-002`
preserves Share View copying the current URL and its temporary “Link Copied!”
feedback. Shared state must not add device geolocation or private data.

`V1-RESET-001` preserves Reset Filters: country/state become All, the state
selector hides, search clears, all six category toggles are checked, options are
repopulated, and filters/map are reapplied. Reset does not currently reset the
cluster threshold, icon scale, or browser URL history by itself.

`V1-EXPORT-001` preserves CSV export of the currently filtered, loaded category
arrays and selected inspection types, with identity/location/activity headers
and CSV escaping. The result is the visible selection, not an implicit request
for additional pages. `V1-COVERAGE-001` is the explicit safety boundary:
V1's “complete” filename is only an unconstrained UI state, and V2's cursor
metadata labels partial pages/visible results. Neither is a claim of global
source completeness, current operation, or animal totals. Missing observations
are not closure.

### Detail actions, language, and APHIS reports

`V1-ACTION-001` preserves source links, Google directions where V1 has usable
coordinates, and copyable address, ID/certificate, phone, and DBA fields in
popups. The V2 replacement is precision-aware: city-precision V2 rows omit
directions and show status/precision context. Source origin, privacy eligibility,
review, project approval, and publication are separate facts.

`V1-I18N-001` preserves the language selector and checked-in de, en, es, and fr
locale resources. Popup/category/animal labels go through the translation
manager, and an open popup refreshes after a language change without changing
selection.

`V1-APHIS-001` preserves explicit lazy report loading: opening a popup does not
fetch reports; a certificate-number button requests only that certificate and
report type, displays loading/no-results/error states, and hides after a
successful non-empty response. `V1-APHIS-002` preserves the annual-report
exceptions-only checkbox as a filter over already-loaded rows, with no second
request and an explicit empty state.

## Intentional V2 privacy/review replacements

`V2-PRIVACY-001` and `V2-PRIVACY-002` govern behavior that cannot be carried
forward merely because V1 displayed it. A public V2 row must remain a
release/profile-scoped projection with independently named source origin,
factual review status and reviewer role, privacy-screening status, project
approval, publication profile, precision, lifecycle, and provenance. V2's
public UI currently allows only the official profile. Restricted, unscreened,
or suppressed material is excluded from map, detail, search, export, history,
and cache paths. Government-sourced does not mean project-approved, and
project-published does not certify truth.

Exact location actions are conditional. City or coarse precision may show a
region and limitation but must not provide a routing link; exact directions
require eligible coordinates and an approved public projection. A registered
office, geocoder match, or facility address is not permission to expose a
private person or targetable location. These constraints follow
[ETHICS.md](../ETHICS.md), including its source/claim separation and
suppression requirements.

## Deferred to Eli's V2 frontend overhaul

`V2-DEFER-001` assigns Eli the first-class semantic list and map/list/detail
parity. V1's suggestion dropdown is not a substitute for a full accessible
result list. The future list must carry the same filters, provenance,
uncertainty, suppression, and visible-export scope as the map.

`V2-DEFER-002` assigns Eli responsive 320px/200% zoom, screen-reader,
keyboard, reduced-motion, cross-browser, visual, and scale/performance review.
No CSS or visual redesign is part of this lane. `V2-DEFER-003` assigns Eli's
later frontend/API integration the server-backed search, facets, pagination,
viewport loading, and export work; those changes need their own API contracts
and must retain the visible-results versus complete-coverage distinction.

## Verification

`static/modules/__tests__/v1BehavioralContract.test.js` checks that this prose
and the JSON agree on requirement IDs and dispositions, that referenced source
files exist, and that the frozen controls and safety wording are actually
present in the current V1 implementation. It intentionally does not redesign
the UI, change CSS, or implement an API.
