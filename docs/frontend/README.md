# Current V2 frontend instructions

**Owner:** project maintainer. This is the single current frontend specification.
The [product roadmap](../PRODUCT-READINESS.md) owns scope/readiness; this guide
owns approved behavior and copy. Do not rebuild from deleted wireframes or old
Git versions. The V1 contract is a migration reference, not V2 design authority.

## Implementation and references

The public map follows:

```text
frontend/src/app/App.svelte
  -> design-lab/DesignLab.svelte (public-release)
    -> design-lab/variants/field/Field.svelte
      -> design-lab/components/MapSurface.svelte
```

The folder name does not make it preview-only. Database and full record pages
are `app/PublicDatabase.svelte` and `app/PublicRecord.svelte`. Trace active imports.
Technical setup/tests: [frontend/README.md](../../frontend/README.md).
Wire contracts: [API index](../api/README.md), not duplicate frontend DTO docs.
[V1 behavior inventory](v1-behavioral-contract.md) and its JSON retain tested
migration requirements. The [capability matrix](capability-matrix.json) and
[UI-state matrix](ui-state-matrix.json) are legacy design/test references:
where their prose differs, this guide owns current UI instructions and current
API schemas own supported fields. They are not additional roadmaps.

## Layout and navigation

- Compact, serious, data-driven interface. No unsolicited redesign, oversized
  cards, decorative labels, glow, filler or large empty spaces.
- The shared header and map use the approved landing-inspired typography and
  restrained surfaces: neutral near-black (`#141414`) in Dark and warm cream
  (`#f2f0e8`) in Light. Keep category pins, clusters and map imagery independent
  of interface theme. Preserve all existing controls and workflow behavior.
- One centered navigation group: `Map Data | Contribute About`.
  Brand/logo left, More tools right; all four destinations remain usable on mobile.
  No old hover-subpage navigation, disabled account placeholder or extra header strip.
- Release selection/history and diagnostics belong in More tools, not a separate
  header Release button. Display dataset dates; retain immutable IDs internally.
  Application semver comes from the backend Rust crate, not a frontend constant.
- The default `/` and `#/` route is the separate outreach landing page. Preserve
  the approved `HIDDEN IN / PLAIN SIGHT.` layout, short copy, documentary pig/cow
  imagery, cream map-preview section and direct `Open the map` links to `#/map`.
  Use the same shared four-link header, theme control and More tools as the other pages;
  landing does not mark a navigation destination active.
  Its still-image motion has pause/resume and a static reduced-motion fallback.
  `See the scale` scrolls to the integrated outreach story without replacing the
  hash route or release context. Four conversational chapters appear in natural
  scroll order: introduce one human glyph and one animal dot; compare worldwide
  human all-cause mortality with a single U.S. chicken slaughter line; show the
  land-animal funnel; then add the separately dated fish funnel. There is no
  population tab required to discover either funnel. The chicken example uses
  140 birds per minute, with grey human outcomes and red chicken outcomes at
  labelled lines; it does not describe every plant's measured throughput.
  Land-animal slaughter (2024), estimated finfish capture/slaughter (2019) and
  the human mortality benchmark (January 2025) retain their distinct scopes and
  dates. They are not a single contemporary total, release totals or counts
  attributed to mapped facilities. Each human/chicken glyph and animal dot
  represents one individual. Each visible animation uses active time: pause,
  hidden tabs and offscreen sections do not accumulate animation time. Reduced
  motion shows a static equivalent. Funnel remains the default, with an optional
  snaking batch grid in each throughput chapter.
  Sources, conversion assumptions and ranges are available in the collapsed
  methodology. Population and conditional drip/pool comparisons illustrate
  counts; the water analogy does not describe resource use.
  This locally implemented story uses a private-validated statistics edition;
  publication approval remains governed by the
  [aggregate statistics specification](../statistics/aggregate-statistics-spec.md).
  Keep `Open the map` primary and `Find locations near me` secondary. Only that
  explicit nearby click requests device permission. A one-time in-memory command
  opens the map and searches within 50 miles; reloads and links never replay it.
  The discovery section shows current release totals, mapped records and public
  source counts from validated public aggregates, with activity links into map
  results. Distinguish unavailable totals from zero; do not add animal-death or
  other unsupported estimates to this section.
  Check the manifest before requesting live aggregates. Publish records,
  mapped locations and sources after their release/restriction identity check;
  countries finish separately. Recheck identity after the country queries and
  discard the summary on a mismatch. Do not reuse unchecked totals from storage.
  One aggregate-only localStorage entry (at most 2 KiB, 24-hour lifetime) may
  reuse complete checked totals after a fresh no-store manifest confirms the
  same official profile, release, manifest hash and restriction generation.
  Never display it offline or before validation. Identity changes, unavailable
  releases, errors and invalid entries clear it; blocked storage falls back to
  live aggregates. Cache hits skip the heavier facet/country queries.
  Countries mapped is the union of countries in source-reported, approximate and
  exact precision partitions. Each release/ruleset-bound country facet must sum
  to that precision's complete count; truncated, duplicate, invalid or failed
  partitions make this stat unavailable without removing other totals. Never
  count unmapped-only countries or fetch the full map or records for these stats.
  The map stays lazy until opened. Cold loading preserves header link gestures;
  late module completion cannot replace a different destination. Map search replaces the separate Database page;
  old public Database links open map results. FAQ content lives within About;
  old FAQ links retain their section and map context. API and downloads remain
  available from Data; map search has no CSV shortcut.
  Existing informational/download routes remain compatible aliases.
- A horizontal map toolbar sits 24px from the desktop map's left edge and 16px
  below its top. It joins Search map with one Street/Satellite switch, 2D/3D,
  Your location, Search this area and Search settings. Settings choose visible
  map bounds or a radius, with a 5–250-mile radius control. Changing settings
  reruns an active search at its original radius center or current map bounds.
  The style switch shows the current style
  and exposes the next style in its tooltip. Search input stays in place as
  results, detail and filters open flush below the entire toolbar width.
  Resizing the panel changes both joined widths; bounds keep the controls usable
  at narrow desktop and zoomed layouts. On mobile, tools stay centered near the map top while
  search uses the bottom sheet. Keep 44px touch targets and native gestures.
  The 3D view uses a 60-degree pitch; 2D looks straight down and resets bearing
  to north, preserving geographic focus and zoom. More tools contains
  release selection, clustering, icon size, optimized dots and diagnostics;
  map style and camera controls are not duplicated in that menu.
- Resize applicable panels by dragging edges, not plus/minus width buttons.
  Do not change panel layout without the maintainer's specific approval.
- The map stage fills the space below the header, including when navigation
  wraps. On desktop Search opens its anchored resizable workspace at one-third
  width, with a 448px minimum for the joined toolbar and a viewport-safe maximum;
  the map remains full-size underneath it. Opening, closing or resizing the
  overlay preserves the map canvas, camera and marker positions. Search,
  filters, results and facility detail share that overlay.
  Back to results restores the list and its scroll position. Mobile uses a
  bottom search sheet with collapsed, middle and expanded positions. The
  collapsed sheet is only a 56px Search map pull handle plus the safe area;
  tapping, keyboard steps or dragging that handle opens it. Normal result
  scrolling never drags the sheet. The sheet overlays the unchanged map canvas;
  its handle stays reachable even when expanded. Toolbar and attribution sit
  above the mobile sheet; the toolbar can hide when a short viewport leaves
  no usable map strip. The middle and expanded height settings
  are bounded, temporary controls under Layout & density in the debug menu.
  Every search action opens results. Preserve an already expanded mobile sheet;
  reopening a collapsed sheet starts at middle. Short scoped-search viewports
  compact summary actions and row padding while retaining the middle height.
  One outer results scroller owns records and pagination; record rows never
  shrink into a zero-height nested scroller.
  Mobile detail uses the same three sheet positions and replaces all search,
  filters, totals and download chrome, including while loading or reporting a
  detail error. A new selection preserves an expanded sheet; from collapsed
  or middle it opens at middle. Cold selected deep links start at middle.
  Its handle remains visible and draggable. Collapsing retains the
  selected record, and expanding retains its detail. Back restores the previous
  results position and list context. Show on map
  collapses the sheet while retaining the selection; View facility details
  returns to that record. Unmapped records have no Show on map action.
  Below Search, keep Filters with its
  sliders icon and the result count on one compact row. Keep detail dense and
  readable, with a white `Open facility page` action with black text at the bottom.
  Keep checkbox multi-selection, totals/pagination, evidence and relationship
  controls. Public category filters use short translated labels and existing
  semantic color swatches in two columns. Country and Source use multi-select
  disclosures that show their current selections. Location preserves explicit
  precision choices; Mapped expands to supported mapped precision values,
  with an indeterminate state for partial selection. Filters fill the available
  workspace, with a scrolling options region and fixed Clear filters / Show
  results footer. Opening filters on mobile expands the sheet; closing them
  restores its previous results height.

## Map

- Individual pins show a compact, subtly rounded escaped-text name/category label on fine-pointer
  hover. Labels use the validated release-pinned public detail projection, with
  cancellation and a bounded short-lived in-memory cache. Verified loaded records
  and cached names render synchronously; an unseen name starts its detail request
  immediately, without a hover timer. Release,
  restrictions, filter and active-state changes invalidate labels; clusters and
  aggregate references never expose a facility tooltip. Hover does not move the
  camera or obstruct pin selection. The category uses muted text without a
  colored swatch; the pin already communicates category color.
  PNG highlights follow the actual pin's alpha mask and rendered size, with a
  stronger static white glow. Optimized dots use a centered ring. Do not pulse
  clusters or rebuild map data to show the hover cue.
- Search this area captures fixed bounds and draws a native geographic perimeter.
  Panning, rotation and style changes retain those bounds. There is no separate
  Searching this area indicator. With any box, radius or device-derived scope
  active, the existing toolbar area action becomes a black X on white, labeled
  Clear map area. Clearing removes only spatial scope and boundary, preserving
  query, other filters, selection, workspace position and private-camera marker.
  A removable This map area chip shares the Filters/count row, and the same
  checked applied filter appears inside Filters for every spatial mode.
  Radius scopes remain distinct. Queries and spatial scopes are not persisted.
  Scoped results start with `In this area` (or `Near you` for the device radius),
  the complete matching mapped total and explicit radius where applicable.
  Six clickable primary-category bars, source count and location precision live
  in an Activity breakdown disclosure, collapsed initially so records are visible.
  Each record counts once by its display category. Clicking a category narrows
  both map and list; clicking the sole selected category again clears it.
  The summary has no Explore full map action. Removing the spatial filter does
  not restore or expose the device camera. Loading or failed matching
  never retains a previous ready summary.
  Your location searches a 50-mile radius by default and opens results after permission.
  It preserves the current query and filters. Device coordinates, radius and
  camera remain in memory and do not enter browser URLs, history, diagnostics or storage.
- Facility icons default to 80% size. More tools and the existing debug slider
  share renderer settings for clustering, icon size and optimized dots; changes
  retain camera, filters and selection and are not persisted.
- Use MapLibre, the existing V1 PNG pin family and V2 taxonomy mappings.
  Do not substitute the six legacy type names for the V2 classification model.
  Processing uses subdued graphite (`#515B60`), Animal keeping uses ochre yellow
  (`#D5B84A`), and Unclassified retains pale grey (`#B8B8B8`). Apply the same
  category mapping to PNG pins, optimized dots, native renderers, filters,
  results and facility panels. Preserve all other category colors, category
  meanings and precision cues.
- Default cluster radius is 50 px and the camera-zoom cutoff is 9.0. Preserve
  explicit debug overrides. Automatic clustering also stops below 3,000 matching
  mapped facilities. Panning does not
  toggle clustering or rebuild the index. Clusters group geographically, not into a
  visible square grid. Exact and approximate records participate in clustering;
  do not make areas disappear between zoom levels or clear valid markers while
  replacement data/index work settles.
- A single approximate record uses the regular category pin, an accessible
  approximation cue and no cluster-style `1`. Do not flash fallback dots.
  On selection/inspection, show a red geographic area 500 metres across
  (250-metre radius), not a fixed-pixel circle or invented confidence interval.
  Use supported source extent where available. No permanent approximation legend.
- The Street/Satellite switch and adjacent 2D/3D toggle live in the map toolbar,
  with accessible camera-gesture help. Do not duplicate them in More tools.
  Keep the map navigation toolbar in the map column, above mobile sheets
  and attribution; no separate gesture banner or default white MapLibre controls.
- Native terrain is lazy, true-scale and has a usable flat fallback.
  Initial 2D does not request elevation. The first 3D activation waits for
  elevation before tilting; returning to 2D keeps healthy loaded terrain and
  changes the viewing angle, preserving geographic focus. Terrain failures
  clear elevation and leave a usable flat map.
  Keep provider attribution; changing style/camera must not rebuild facility data.
- Clicking a real pin, PNG, cluster or search result must work on cold load.
  Pin selection, detail opening and camera focus must work with Search map
  collapsed as well as expanded, using the same existing selection behavior.
  Closing detail with X, Escape or Back leaves the focused camera in place.
  Preserve allowlisted camera, style, selection and release context on navigation.
  Public URLs omit fixture parameters such as `scenario=default`.
- Unmapped records stay searchable without invented map points. Do not turn an
  approximate location into exact directions or a street-address claim.

## Search and Database

- Search the released database, not only the visible viewport or loaded page.
  Use only fields supported by the actual public endpoint; all-record-family
  search is a future contract, not an implied feature.
- Country, source and activity/category filters use the same scope as results.
  Provide Clear filters, query totals distinct from loaded-page counts, and
  usable loading/error states without a map-covering loading popup.
- Debounce/cancel stale requests; preserve input and pagination semantics.
  OR within a filter dimension, AND between dimensions.
- Public map pins follow the complete query/filter match set, not the loaded
  results page. The release-pinned `/api/v2/map/matches` read-only route shares
  list predicates and returns mapped facility IDs with manifest/restriction
  identity. Pending or failed matching requests never show unfiltered pins;
  failed requests offer Retry. Unmapped matches remain in the results.
- Search supports removable filter chips, keyboard facet suggestions, country
  phrases such as `slaughterhouses in Spain`, a fixed Search this area snapshot,
  and city navigation with an explicit nearby-radius search. A city centre is
  never presented as a facility location. Panning does not silently change an
  area search. Free text and spatial scopes stay out of public URLs/history.
  Saved searches are removed. Do not load or write old saved-search storage,
  and do not create automatic search history. Filters wrap into multiple
  columns when space allows, with full readable source labels.
  Filters extend to the available viewport bottom and scroll within that space.
  Applying Search this area, nearby searches, query changes and settings reruns all open
  results while retaining an expanded mobile sheet. Scope and category changes
  preserve unrelated query and filter dimensions.
- Browse-record links open the full facility page directly. Do not restore
  the intermediate database preview panel.
- API offers full-release CSV, explicitly bounded exports, paginated JSON and
  the self-hosted Swagger explorer. Do not silently crawl the whole database
  in the browser to render a map or open a facility.

## Facility details and connections

- Search result cards show category, locality, precision and source without a
  redundant Recorded activities summary. Detailed facility classification stays
  available in the facility panel and full record.
- A verified source-codebook slaughter range appears directly below the
  classification summary when available, including for a processing-classified
  record with slaughter evidence. Preserve exclusive upper and unbounded lower
  values and the exact `last 360 days` period. Link the HTTPS source codebook;
  never extrapolate absent ranges or convert them to annual point estimates.
  Do not repeat the promoted range inside Source facts. Processing monthly
  volume remains in Source facts.

- Full page order: facility name and chain-icon Copy facility link action;
  category and classification overview; Location facts; single-record map;
  remaining facts. The map panel uses the same overview before Location,
  with Open facility page at the bottom of the map detail.
  No separate copy-record-ID button or repeated Record Evidence heading.
- Public source-reported and exact facility points also offer `Open in maps`
  in Location. It sends only the public destination to the external map, never
  the visitor's origin. Approximate, city, coarse, mailing-locality and unmapped
  records have no external-map action. Existing Show on map remains available
  according to its normal mapped-location behavior.
- Copy actions show a brief checkmark only after the clipboard write succeeds,
  with a localized live-region status. Failure shows an X and accessible status;
  neither state shifts the facility heading or share button.
- Map detail has an `Open facility page` link, selected-release context and
  close control. It shares the mobile map sheet with scrollable content.
  Detailed classification follows Location immediately before Source facts,
  collapsed by default. Connections start collapsed when none exist and expand
  when connections are available; loading and errors remain accessible.
- Full mapped records have `Open in Map`, centering/selecting that facility
  in the same release. Unmapped records have no location map/action.
- Single-record previews use the existing providers/pins: source/exact
  satellite zoom 15; approximate street zoom 9. Do not fetch the global point
  projection for these previews or invent an address from a locality.
- Show the category pin and short text label in search rows and expanded detail.
  Keep explanatory prose in facility details rather than repeating it in result cards.
  The panel and full record share a source-referenced catalogue of 41 concise
  definitions, including six broad fallbacks and specific activities and APHIS
  classes. Use one or two sentences, selecting specific definitions only from
  recognised structured keys, source-native classes or affirmative facts.
  Category-level process descriptions must not assert a facility's particular
  slaughter method. Preserve exact source classification and all supporting
  activities in labeled detail. APHIS registration classes take precedence
  over generic fallback taxonomy in summaries; do not turn registration into
  an assertion about operations at the displayed location. Class T describes
  animal carriers, not laboratory-only transport. Legacy G/V explanations require
  their full source-native designation. A valid exact-matched research report
  may add its fiscal year and total across reported species, never a death count.
  Definitions and source links remain available in collapsed Classification details.
  Format underscores and
  technical activity labels; retain original values in data. Show all
  affirmative species/activities and supported slaughter/product estimates.
  Use `animals`, not `head`, in presentation.
- Group available address/locality, coordinates, source method/provider and
  recorded confidence in Location. Label native points
  `Source-provided coordinates`; do not invent confidence or validation.
- Hide unknown lifecycle and internal taxonomy/crosswalk versions from UI.
  Do not hide useful original classifications or source evidence.
- Exact and inferred connections remain public and filterable at all available
  confidence bands. Use `Exact source`, `Inferred`, and `Source` for the
  source-assertion method. Keep real evidence/signals accessible, not repeated
  general disclaimer paragraphs. No human-confirmed connection state.
- A loaded record with no connections shows `None`, without Relationship or
  Confidence controls. Keep controls when filters caused an otherwise nonempty
  list to have no matches. Loading, errors and empty results remain distinct.
- Use only public graph routes and supported entity mappings. An organization
  summary does not gain a fabricated facility page. A canvas limit or API page
  bound is not a graph storage cap.
- APHIS controls appear only for relevant APHIS records, fetch on request and
  retain error/retry states. The release-scoped lookup combines released
  evidence references with additional official historical document links for
  that same source identifier. Keep those origins structured and distinct.
  Successful empty searches are not errors; source pages are not report files.
  Verified sample history includes pre-2025 annual and inspection PDFs, not a
  claim that every facility has a complete archive.

## Contribution behavior

Contribute opens Add a facility. Three main tasks are Add a facility, Update a
record and Report a problem; Update groups correction, evidence and duplicate.
Keep Privacy/removal directly accessible and Track submission near the page
heading. On mobile and narrow tablets, use a compact labeled task chooser in place
of the desktop task cards, with Privacy/removal included. Put the current form
directly below it, retain the update subtype links, and keep inputs at 16px.
Mobile forms use the normal page scroll; submit and receipt actions remain fully
readable without nested frames or fixed overlays. Preserve older task URLs and
target/return-map context. Bug reports
save into the system and return confirmation/tracking, never an email draft.
Use short task-specific forms, with optional location/classification details
behind a disclosure. Preserve the existing structured fields, category pins,
precision choices and location picker. Existing-record actions preselect their
target; allow bounded public facility search or a pasted record link/ID.
An unavailable public record must not prevent a valid privacy request.

Keep unfinished drafts in page memory across task switches, never browser
storage, query strings or logs. Successful submission replaces the form with
its actual receipt, private tracking link and a copy action with accurate
success/failure feedback. A submission reference alone does not grant access.
Tracking shows only returned states and facts: privacy screening is not factual
approval, and removing intake does not establish removal of its public target.
Do not show simulated decisions, unsupported reply/email controls or an E2EE
claim. New messaging and notification features require the actual backend
capability and verified transport before appearing in the public flow.
Beside Copy tracking link, show: `Save this link. You cannot access your submission again without it.`

Use one Track submission link, with its capability in the fragment and status
credentials sent in a POST body. Accounts, uploads, automated email and receipt
recovery are not implemented. Public community browsing is offered only for an
eligible published community release; intake never automatically changes the
curated map, graph or counts. The [contribution contract](../governance/user-submitted-data.md)
and [production runbook](../deployment/production-operations.md) own operational details.
Maintainers access `#/contribution-review` with the contribution service's
operator token. In split-service local previews, public intake/status and
private review requests must use the same contribution service; the normal
public data API remains separate.

### Local encrypted inbox

The encrypted intake and two-way reviewer inbox are an opt-in development
experiment. `VITE_SECURE_INBOX_EXPERIMENT=true` requires Vite development mode;
production builds exclude the SDK and encrypted API client. Pin the full public
reviewer fingerprint independently through `VITE_SECURE_REVIEWER_FINGERPRINT`.
`UEC_SECURE_COMMUNITY_API_ORIGIN` can proxy only the secure endpoints to a
loopback HTTP API, ahead of the normal contribution/data proxies. This option
is local to the Vite process. The backend capability must also be enabled and
match the configured key; failure does not fall back to plaintext intake.

The local Contribute flow encrypts the structured draft and signs it with a
per-case contributor key. OpenPGP.js 6.3.2 encrypts each message for the contributor
and reviewer. Only ciphertext, public keys and relay metadata reach the service.
Both public keys are parsed and their full fingerprints checked locally. Signed
message context binds the protocol, case, message, author, classification and
both fingerprints. Decryption is buffered and bounded; all messages must pass
signature/context checks before the view receives submission text.

`#/secure-inbox` supports verified messages, encrypted replies and processing
status. `#/secure-review` supports metadata queue access, local reviewer-key
unlock, verified messages, encrypted replies and explicit status/removal actions.
Operator tokens, private keys, drafts and decrypted text stay in memory. Inbox
access secrets travel in POST bodies and private URL fragments, never query
parameters sent to the server. Removing an inbox revokes intake access; it does
not remove its public map target or publish a decision into the dataset.

The receipt downloads a local encrypted `.asc` recovery file and supplies a
separate random recovery key. Both are needed to reopen on another device.
The file contains the contributor private key, case access and observed-history
checkpoint under SDK password encryption and a self-signature. It is never
uploaded by the interface. The reviewer key uses the same local encrypted-file
pattern. Browser storage does not retain keys or recovery secrets. API retries
reuse the exact prepared identifiers and ciphertext.

Identical authenticated history rereads are allowed. Acknowledged outgoing
replies are pinned before refreshing. Missing previously observed or acknowledged
messages, reordered history or a conflicting message ID fail verification and
clear displayed text. This checkpoint does not prove freshness across an older
recovery backup or authenticate relay status/timestamps. There are no attachment,
automatic publication or email-alert controls. This local implementation is not
a production E2EE guarantee; activation and operational requirements belong to
the contribution contract and production runbook linked above.

Focused checks are `secureInbox.test.ts`, `secureCommunityRepository.test.ts`
and the secure cases in `communityProxy.test.ts`. The real relay and browser
journeys are opt-in through `UEC_SECURE_RELAY_INTEGRATION=true` and
`UEC_SECURE_RELAY_BROWSER=true`, using an owned disposable database and synthetic
submissions. Local fixture material belongs only in ignored `target/` paths.

## Exact copy and informational pages

Use supplied wording verbatim. No em dashes in authored visitor copy, internal
candidate/projection jargon, repeated category summaries, unsolicited warning
blocks or polite filler. Preserve source-native evidence, provider attribution
and required public unreviewed-community context.

- About uses the supplied V1 manifesto. Counter is on the right on desktop,
  stacked on mobile. Exact title: `Animals Killed Since You Opened This Page`.
  No subtitle; all 18 animal groups form one vertical list at every width.
  Update from elapsed time around 30 times per second, isolated from map rendering;
  respect reduced motion and hidden tabs.
- Rates/source notes remain in the model. Do not restore counter Source and
  method or About Sources and methods sections, or relocate them as replacement copy.
- The closing `Until Every Cage is Empty` heading is followed by the existing logo.
- Footer opens `An independent, open-source, ad-free project.` No feedback invitation.
  Credit `Counter Adapted from ADAPTT.`, linking ADAPTT to
  `https://www.adaptt.org/`. Retain project/support/code links and distinct
  software/data licences; do not restore obsolete country/version claims.
- About's questions section explains the data path, contributions and support. Its current
  data-path paragraph is: "Government datasets are collected, cleaned and
  standardized, with links back to their sources. Address lookups add
  coordinates, and matching connects related records. Dated releases supply
  the map, search and downloads through a Rust API."
- Keep one questions section on About, without a duplicate Common questions
  block or tutorial video in Help.

## Boundaries and acceptance

Release/profile eligibility and current restrictions apply to UI, APIs, caches,
history and exports. Never expose private routes/tokens/raw evidence in the
public bundle. Keep community submissions separate from curated records.
Device location is optional and is not persisted by default.
Request it only after Your location or Find locations near me is clicked. Keep its live camera in memory;
links and browser history retain the prior public camera, including subsequent
zoom/pan and navigation actions.

Debug controls operate in memory with Reset defaults. Show current renderer,
release identity, aggregate list/map matching state, meaningful timings and
layout dimensions; hide inactive renderer controls and label unavailable
metrics. Clustering supports Auto/On/Off. Layout width, result spacing/type and
pin scale tune the actual current UI. Diagnostic copying uses an explicit
allowlist of aggregate/version/timing/settings data, excluding raw queries,
facility IDs/names, coordinates, request URLs, tokens and payloads.

Maintain keyboard access, visible focus, reduced motion, screen-reader labels
and usable narrow/zoomed layouts. Test the actual public built route and real
approved data where available; synthetic unit/negative tests supplement, not
replace, real-data acceptance.

English, Spanish, French, German, Dutch and Danish are available from the
language button between the theme control and Tools. The popover shows native
language names, closes with Escape or an outside click, and returns keyboard
focus to its button. Opening it closes Tools and vice versa. English is the
default; missing translations fall back to English. Additional catalogs load on
demand, keeping the current language until loading succeeds. Reloading restores
a saved language without overwriting its preference during loading.
Language switching preserves map camera,
release, filters and selection. Public About and methodology, filter labels and
normalized options, Data/download copy, records and contribution flows use the
shared dictionaries. Country display names and formatted dates/numbers use the
selected locale. Source names, identifiers, unknown source facts and user content
retain their original language. Generated Swagger references and operator/debug
strings may remain English. Extend the existing dictionary rather than
creating another localization path or rewriting approved English copy.

The square theme button immediately left of the language button shows a moon in Dark and a
sun in Light, indicating the current mode; clicking switches modes. Theme
selection does not also appear in Tools. Dark is the default; explicit language
and theme choices persist as nonsensitive browser preferences. Initialize the theme
before rendering, tolerate unavailable storage, and keep maps, category pins
and cluster colors independent of interface theme. Verify translated controls
at narrow widths in both themes. The persistent map-projection cache retains
one release/profile/manifest/restriction identity, replacing older copies after
successful validation. A separate IndexedDB slot retains the built public
cluster hierarchy across browser reloads, up to 64 MiB by default. Its hash
includes release/profile/manifest/restriction identity, complete matched point
content, clustering options and pinned engine/codec versions. Restoring
reattaches validated KD trees to a native empty shell without reclustering.
Snapshots reference point properties in the validated current input and pack
projected coordinates and KD/numeric data as binary buffers, avoiding a second
copy of the full facility object graph. The complete input-content hash must
match before these references can be restored. Incompatible inputs retain the
JSON/lossless-gzip fallback within the same 64 MiB budget; decoding is bounded
before parsing and native-tree validation. Compatible existing gzip snapshots
remain reusable; the encoding upgrade does not force a rebuild. Debug diagnostics include the stored size
and a bounded failure reason. Restoring still incurs storage,
parsing and validation work; skipping the build does not guarantee lower total
startup time on every dataset or device.
Large validated public point collections cross the native worker boundary as
a JSON-string envelope, avoiding recursive serialization of the full object
graph. The original main-thread source data and native queries remain intact.
This adapter is guarded against the pinned engine version and source-parameter
method; unsupported values and private/device views use native transport.
Storage failure, corrupt data or an incompatible snapshot falls back to a new
build. The cold build displays “First time loading. This may take a while…”;
cached reloads restore the existing hierarchy with one concise restoring label,
without repeating numbered startup steps. Projection-cache status and byte
metrics come from public feed metadata. Projection byte measurements are saved
with newly cached feeds; older entries may show an unmeasured value rather than
serializing the entire feed again just for a diagnostic. Cache Storage failures use validated
network data rather than preventing the map from loading. Private preview and
device-derived search views do not persist indexes, raw queries or camera data.
Public in-app navigation keeps one hidden, inert map and its built worker index in memory.
Returning rechecks the selected release's manifest and restriction identity
before revealing it; changed identities replace the projection, and failed
validation clears the retained data and offers Retry. Private preview maps
are not retained. Changed matching membership or clustering options rebuild
clusters so counts and membership match the search. Do not reopen
map-engine selection or redesign approved visual behavior.

Viewed raster tiles use a shared provider-URL-hashed Cache Storage LRU, capped
at 512 entries/32 MiB by default. Reuse honors provider expiry and a seven-day
maximum age cap. If CORS does not expose an absolute freshness deadline, as
with the current Esri response headers, the browser's HTTP cache remains
responsible for reuse; do not invent a renewed TTL or prefetch worldwide tiles.
Private preview/device-camera views bypass this extra persistence, including
late writes. Native decoded-tile retention defaults to 128 tiles per source.
Detailed raster tiles use a 180 ms native fade on flat maps. Debug tunes this
from 0–400 ms and resets to 180 ms. MapLibre disables raster fades with terrain;
the control shows that limitation. Basemap candidates and local overview imagery
remain opaque, and candidate coverage stays until the new base fade completes.

A bundled Natural Earth v5.1.2 1:110m land outline renders beneath raster tiles.
This small public-domain reference asset contains no facility or personal data;
its source URL and original checksum are recorded in `baseMapStyle.ts`.
It remains the final world-outline fallback. A separate self-hosted overview
provides real worldwide roads, boundaries and place labels from Protomaps,
plus NASA Blue Marble satellite imagery, at zooms 0–5. Local per-zoom bundles
total about 16.12 MiB through zoom 5 or 6.41 MiB through zoom 4, excluding the
small manifest files. Labels use local system fonts. These are overview baselines; the existing OSM
and Esri providers continue to supply detailed/current map tiles above them.
Sources, licenses, checksums and reproduction scripts are recorded in
`frontend/public/world-baseline/NOTICE.txt` and the local manifests. Provider,
OpenStreetMap, NASA and Natural Earth attribution remain visible.

World bundles use a separate content-addressed cache with a 30-day lifetime.
Background warming begins after the map is ready and idle: desktop defaults
to zoom 5 within 24 MiB; mobile defaults to zoom 4 within 12 MiB. Data Saver
skips automatic warming. Navigation, deactivation and settings changes cancel
pending warming; private/device-camera views do not initiate it. Demand tile
requests can read small local byte ranges before a whole bundle is ready.
Street overview layers stop at zoom 6. Satellite imagery stays underneath
detail at higher camera zooms while its source remains capped at zoom 5,
providing a coarse image during detailed-tile gaps in both flat and terrain
views. Opening a detailed map uses small demand byte ranges rather than
downloading complete world bundles. Missing storage still permits normal
map loading. Cache settings and diagnostics stay aggregate and coordinate-free.

Debug Cache controls tune index/tile persistence, byte/entry budgets, tile TTL
cap, native RAM retention and the world-outline opacity. Changes are in memory
with Reset defaults and separate Clear built index/Clear viewed tiles actions.
World overview controls separately tune preload, maximum zoom and byte budget,
and clear/reset its cache. The preview-opacity slider affects all overview layers.
The TTL control can shorten provider freshness, never extend it. Metrics
distinguish source updates from actual cache builds/restores and report tile
hits, misses, evictions and HTTP-cache delegation.
Satellite requests delegated to the browser are not application cache hits.
When provider freshness headers are hidden by CORS, an application hit count of
zero can coexist with browser disk-cache reuse. The browser-managed counter
records delegation, not verified cache hits or transferred bytes.

Facility clusters and basemap raster LOD use camera zoom rather than bearing or
distance to individual tiles. Rotation at a fixed center and zoom keeps the
same cluster hierarchy and raster resolution; newly visible tiles may still
load. Terrain retains adaptive LOD. Selection flights settle the camera at the
target's terrain elevation once its DEM is ready, preserving zoom, bearing and
pitch. Manual movement cancels this pending selection adjustment.
Raster handoffs and terrain activation check their own source after native
render updates as well as source events. Each raster handoff stage has a
30-second readiness bound, allowing imagery queued behind elevation work on
slower devices; terrain activation retains its ten-second bound. The existing
map stays visible while replacement imagery loads invisibly; the bundled
baseline changes when the handoff commits. Source metadata alone does not
establish tile readiness. Source errors and cancellation still end the wait
immediately and follow the existing fallback.

Native cluster animation keeps unchanged identities visible in the native
renderer and holds only vanished originals on a bounded, geographically anchored
canvas during a zoom gesture. Permanent feature-state paint expressions mask
only changing identities; gestures do not rewrite layer paint or reload source
tiles. Promote the existing point key to preserve full UUID feature identities.
When zoom-in settles, children travel from their parent cluster to their new
positions. With the default zero idle delay, zoom-out merges advance through
placed scenes while the camera moves, coalescing further changes until the
current short cue finishes. Adopt each newly revealed region's first native
scene immediately, including arrivals during a worker read or another cue.
Advance the tracked viewport after that scene can paint, so its subsequent
cluster changes use the same hold and parent-origin animation as the original
region. Never blanket-hide space before observing its first scene. Keep
unpaired arrivals through intermediate checkpoints and hold vanished marks
even while a different branch animates. Retire them only when their matching
parents replace them; do not discard them with an older worker snapshot.
If only a new region arrives, retain the scene and keep tracking until its
parent hierarchy arrives; remember the new identities to avoid repeated reads.
After an empty lookup, coalesce unrelated arrivals at the same native zoom
rather than querying each partially arrived tile scene. A new parent inside
the observed region retries immediately; it must not wait for another zoom level.
Changed branches inside the held viewport fade in on the same clock,
so the original viewport cannot remain a dense island inside a coarser map.
A custom nonzero idle delay still waits for the camera to stop.
Keep native bottom-to-top stacking on the canvas and retain the
held scene through rapid zoom reversals. The overlay remains until replacement
native paint is ready. Reuse existing pin/cluster artwork and read-only native
hierarchy reads, without bounce or repeated restarts.
Draw every visible wrapped world copy of a masked identity, and align parent and
child longitudes across the short antimeridian path. Reproject held marks while
worker pairing is pending. Resolve lineage once per merge scene or settled
expansion through a worker-only read of the existing index's parent links,
with at most one request in flight. Use a one-use worker message port so tile
message queues cannot delay the animation reply; close it after completion or
timeout. The existing native query channel remains a compatibility fallback. Return
identity pairs only; do not recursively fetch descendants, warm a second cache,
or issue hierarchy requests on every camera frame. Skipping several
zoom levels uses the same lookup. Prepare visibility in a custom layer's
`prerender`, after native symbol placement and before symbols draw. Flush only
the locations source's paint attributes; never repaint the whole scene or run
camera tasks, source selection or symbol placement a second time. Worker
replies and animation timers queue the next native frame. Start each cue when
that frame can paint its mask, rather than when a worker reply arrives.
Clear the canvas only after
the restoring native paint returns, including held scenes whose identities
are temporarily absent from the native query. Source readiness alone is not
confirmation that replacement pixels have painted.
This also applies to each in-flight zoom-out merge checkpoint: a cue can finish
in a canvas RAF between native paints. Retain its final pixels until the next
native paint has drawn the unmasked destination, then resume the held scene.
Reuse projected positions between native camera paints; invalidate them on
each native render, zoom start and cancellation so movement and terrain updates
still reproject correctly.
Cache each fixed pin-and-shadow sprite once, then fade and draw it as one
image. Do not cache facility identities or counts in this artwork cache.
Use CPU-backed canvases for the short overlay and its small artwork so drawing
them does not synchronize additional graphics contexts with the WebGL map.
Initialize the overlay and its label font during map startup.
Chromium browser checks use its full compositor (`channel: chromium`), matching
the normal browser rather than the separate headless shell. Firefox and WebKit
remain part of the configured browser coverage.
Animation timing fixtures keep the real pitched camera over a controlled flat
surface. The camera/terrain journey and the elevation fixtures retain terrain
rendering; animation frame and freeze limits remain explicit.
Freeze checks compare the last painted overlay's camera pose with the current
camera, and include a deliberately stale overlay as a negative control.
If a new zoom starts during a short playing cue, finish that cue without resetting
its progress, then hold its destination identities for the next transition.
The default is 210 ms and at most 1,200 animated marks in total. Debug
controls tune duration from 0–400 ms (0 disables it), the mark cap from
50–2,000, and camera idle delay from 0–500 ms (default 0). A bounded in-memory
lineage lookup stays in the native worker and returns at most the selected
number of identity pairs. Both directions share the 500 ms native-paint
deadline so a busy browser frame does not incorrectly classify a fast reply
as a stalled worker. Allow up to two seconds for source tile readiness after
rapid zoom reversals, retaining the visible scene while input stays live.
Neither wait blocks input. Data, index and style changes cancel stale lookups.
Local pin artwork loads in parallel. Pan and
bearing-only rotation remain native. Reduced motion, views beyond the selected
mark limit, slow lookups and camera/style/data changes may skip or cancel a
transition; Debug exposes the current state or skip reason. Animation never changes source data or
rebuilds the cluster index; native marks retain selection behavior.
