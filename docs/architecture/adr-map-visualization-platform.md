# ADR: map and visualization platform

Status: proposed for maintainer review. Date: 2026-09-16. This is a technology decision for future V2 platform work, not authorization to publish data, enable a live map, acquire third-party services, or imply that present safeguards are deployed.

## Decision

Keep the existing Svelte 5 application's **flat 2D investigative map** as the primary experience. Replace the future production Leaflet implementation with a `MapLibre GL JS` adapter that consumes release-scoped vector tiles and is loaded only when the visitor opens the map. Use `deck.gl` as a lazy GPU overlay inside the same adapter for aggregation, density, relationship arcs, and temporal rendering. Store basemap and project vector tiles in `PMTiles` archives and serve them from project-controlled object storage/CDN; begin with a deliberately plain, self-hosted/open-data basemap. Use PostGIS for private/release generation and a tile service or generated PMTiles for public viewport queries.

Treat a 3D globe as a separate, optional **exploration view** after the 2D map, access-control, accessibility, and performance gates have passed. Start it with MapLibre's globe projection where a globe adds orientation value. Evaluate CesiumJS only when the product has a reviewed 3D Tiles, terrain, or genuinely three-dimensional data requirement. Do not make globe mode the default, and never use 3D terrain/buildings to make a sensitive point easier to identify.

This preserves the product's primary job: inspect place-based evidence with clear uncertainty. A globe is good at global orientation and broad patterns; it is a worse default for filtering, comparing rows, keyboard operation, coarse-location explanation, and careful evidence reading. The story lane likewise says a facility row is not an animal and a map pin is not an animal count; visual scale, map points, and relationship lines must remain distinct claims.

## Why this fits the project

The current Svelte preview has a local blank Leaflet map, fixture-first repository boundary, explicit publication states, and no tile provider. It is a sound Phase 2 safety boundary, but it cannot scale from the browser's loaded page to a 100k–500k worldwide collection. Phase 4 already calls for viewport loading, clustering, cursor traversal, and mobile benchmarks. The accountability-graph foundation keeps facilities, organizations, source identifiers, relationships, claims, source evidence, review state, privacy status, and publication state separate. The visualization layer must preserve those distinctions instead of converting them into a single confidence color or an unqualified network graph.

ETHICS.md requires restrictions to apply to maps, APIs, downloads, embeds, previews, caches, historical releases, reimports, and restores. It also requires exact/city/unmapped uncertainty, explicit community context, no targeting of workers/residents, no inferred closure, and no invented coordinates. Consequently, the public map is a **derived release artifact** rather than a direct renderer for evidence tables or graph tables.

## Decision matrix

Scores are project fit, not generic library quality: 5 is strongest. “No live decision” means the capability should remain absent until its data, privacy, and operational gate exists.

| Candidate | 2D vector performance | 3D/globe | Aggregation / arcs / time | Open licensing / self-hosting | Svelte fit | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| MapLibre GL JS | 5 | 3 | 3 | 5 | 5 | Primary map renderer and globe experiment |
| deck.gl | 5 | 3 | 5 | 5 | 4 | Optional GPU overlay, not application map owner |
| PMTiles + Protomaps-compatible tooling | 5 | — | — | 5 | 5 | Primary portable tile artifact and static/offline delivery option |
| CesiumJS | 3 | 5 | 4 | 4 | 3 | Deferred 3D specialist option |
| OpenLayers | 4 | 1 | 3 | 5 | 4 | Fallback if WebGL/vector-style requirements conflict with MapLibre |
| Current Leaflet | 2 | 1 | 1 | 5 | 5 | Keep only for current fixture boundary; do not scale it to production |
| Mapbox GL JS/services | 5 | 3 | 4 | 2 | 4 | Optional paid comparator, not default |
| Google Maps Platform | 4 | 3 | 2 | 1 | 4 | Do not use for primary map/geocoding |

MapLibre GL JS is TypeScript/WebGL and renders browser vector tiles; it has a globe-capable style/projection model and published guidance for vector tiling and clustering large datasets. deck.gl is an MIT-licensed WebGL2 visualization framework with layers suited to hex bins, heatmaps, arcs, paths, tiled vectors, and animation. MapLibre is BSD-3-Clause, deck.gl is MIT, CesiumJS is Apache-2.0, and OpenLayers is BSD-2-Clause; each dependency still requires a pinned version, license inventory, and attribution review. PMTiles is an archive format, not a map renderer; it makes a tile set a versionable, immutable release object.

## Architecture

```text
private evidence / graph observations / restrictions
                    │  release validation + human authority
                    ▼
       promoted public display projection (per profile/release)
                    │
          tile/export build ──► manifest, hashes, attribution, policy revision
                    │                         │
       PostGIS/tiles service              immutable PMTiles archive
                    │                         │
                    └──► Map repository ◄─────┘
                              │
     Svelte map adapter: MapLibre base + optional deck.gl overlays
                              │
          accessible list/detail/provenance and non-map equivalent
```

The browser receives only a public projection whose tile attributes are a minimal allowlist. A point feature needs, at most: stable public facility ID, display geometry, `display_precision`, category, profile, public source-origin/review/approval labels, release ID/ruleset, and a token for a detail fetch. It must not contain street address, source payload, source-record ID, geocoding query, reviewer identity, restriction reason, internal relationship IDs, or raw graph evidence. A map click resolves through the same profile- and release-scoped public detail route as the list; it never fetches private data or uses the browser tile cache as an evidence store.

### Geometry and visual semantics

| State | Map behavior | Required text/list equivalent |
| --- | --- | --- |
| Exact public point | Eligible marker only after privacy/release projection; no address inferred from it | “Exact display point,” source/retrieval context, and limitations |
| City precision | Distinct coarse marker/symbol and clustering membership only at city level | “Approximate city location — not the facility site” |
| Unmapped | No marker, no cluster contribution, no guessed point | Eligible record remains discoverable as “No publishable map location” |
| Restricted/unscreened/rejected | Absent from tiles, map, aggregates, exports, caches, and direct detail | Ambiguous unavailable state; never confirm why a record is absent |
| Community unreviewed | Separate selected profile and persistent canonical warning in controls, map legend, list, details, exports | Warning before access and on every result; never merge into curated totals |
| `not_seen_recently` | Existing eligible geometry may remain with lifecycle styling | “Not observed recently,” never “closed” |

Do not encode credibility only with hue. Show source origin, factual review, privacy eligibility, project approval, publication profile, precision, lifecycle, release, and provenance as separately named controls or panels. A relationship arc represents a source-backed, time-bounded assertion, with its observation date, relation type, uncertainty/review state, and source context. It is never a force-directed “ownership truth” visualization. Contradictions and unknowns need an accessible table; contested, sensitive, or non-public edges produce no public arc.

### Rendering modes

1. **Low zoom:** server-built country/region aggregates or H3/hex bins with explicit unit, period, profile, method, release, and uncertainty. They are counts of eligible records, never animal totals or proof of activity. Avoid client aggregation over arbitrary partial pages.
2. **Mid zoom:** vector-tile cluster circles or deck.gl `HexagonLayer`/`ScreenGridLayer`; the legend must say whether a symbol is a cluster, bin, or facility. Each aggregate excludes unmapped/restricted rows and carries the same profile separation.
3. **High zoom:** individual public exact points and intentionally coarse city points, with a bounded visible feature count. A list remains primary for keyboard/screen-reader use.
4. **Time:** a scrubber only when observations or claims have a defined time basis. Default to static release view. Never animate source disappearance into a closure claim; retain prior data only while it remains eligible under current restrictions.
5. **Network/overlay:** deferred graph layer for reviewed, public relationships and separately governed environmental/permit layers. Polygon/raster/vector overlays require their own source terms, effective date, resolution, attribution, publication approval, and suppression assessment. Do not spatially join an environmental/permit layer to claim a facility caused an effect without a reviewed causal methodology.

## Data delivery and costs

### Primary: generated PMTiles plus controlled object storage

For low/moderate traffic, generate a small number of profile- and release-specific PMTiles artifacts (for example, curated official, secondary, and community only when eligible) and host them as immutable objects. A generated archive is auditable, supports static preview/offline use, gives a stable checksum/manifest target, and does not require a permanently exposed tile database. Tile URLs and archives must be removed or denied as part of suppression propagation; immutable caching is safe only after a release/public-revision design gives revocation a bounded response path.

Use a service worker **only after** a suppression/cache audit. The current V1 worker is not a safe V2 cache policy. No static artifact, browser cache, CDN cache, preview, or offline bundle may retain a later-restricted payload. Offline packaging is a future explicitly authorized release artifact with a manifest and recall/restriction procedure, not a default browser feature.

Cloudflare R2 is a cost comparator, not a selected vendor: its current published Standard tier has 10 GB-month and 10 million Class B reads free, then $0.015/GB-month storage and $0.36/million reads, with no R2 internet-egress charge. Thus a 1–5 GB low-traffic tile archive is commonly within the free storage tier; even 50 GB stored is roughly $0.60/month before request charges. At a moderate 20 million tile/archive reads beyond the free tier, the listed R2 read rate implies about $3.60/month, excluding domain, Workers, logging, WAF, build, and application/database costs. These are arithmetic examples from the published rate, not a quote or performance prediction. Recheck pricing and provider logging before procurement. AWS CloudFront is a viable alternative, but its current pricing varies by data transfer, request region, and features, making R2's simple no-egress model more predictable for this narrow artifact workload.

### Scale-up: dynamic vector tiles

When release artifacts become too large or updates too frequent, introduce a read-only tile service backed by a public PostGIS projection. It must accept only allowlisted profile/release/filter/viewport inputs, enforce restriction state in the query, emit bounded simplified vector tiles, and retain the release/revision in cache keys and headers. Possible implementation paths include PostgreSQL vector-tile functions or a dedicated open-source tile server; choose after a deployment threat model and benchmark, not as part of this ADR. The app API still owns search, detail, and export semantics.

Avoid browser-delivering 100k–500k raw GeoJSON. MapLibre's own guidance recommends vector tiles for larger data and warns that styling/overlap calculations matter. The current user-facing requirement is viewport-based access, not a benchmark contest. Use a 2D map's low-zoom aggregate mode before individual features.

## Privacy, accessibility, and failure behavior

Map tiles expose viewport/tile requests to their host and any third-party provider. Device geolocation is optional and stays off by default. Town/postcode search must work without it; location input is not stored in shared URLs, analytics, or application logs. Do not use browser geocoding for visitor input until a provider inventory, disclosure, retention review, and explicit design are approved. Do not silently transmit a query to Mapbox, Google, or another third-party geocoder. The existing visitor-privacy inventory already identifies V1 tile/directions disclosures as unverified; V2 must not inherit them.

The map itself is progressive enhancement. On no WebGL/WebGL2, a context-loss event, `prefers-reduced-motion`, a low-power/mobile decision, a failed tile request, or a user selecting “list view,” render the same release-scoped list, filters, detail/provenance, and download limits without a map. Do not auto-fallback to V1. Disable globe, animations, extrusions, continuous fly-to, and animated arcs under reduced motion; allow an explicit non-animated retry. Screen readers get semantic filter/list/detail controls and concise aggregate descriptions, not canvas-derived labels. Keyboard users can select a result and request a map focus, but no map interaction is required to inspect evidence.

Use terrain/buildings only if a future source and privacy review approves them. They increase transfer/GPU cost and can make coarse/residential context more identifiable. Do not draw route/directions, “nearby home,” or targetable travel paths. Rate-limit/bound tile and detail requests, protect public endpoints from arbitrary expensive queries, and do not return a special status that distinguishes a restricted facility from an unknown ID.

## Why not the alternatives

**Leaflet:** excellent for the existing fixture map and simple page-scale point sets, but DOM markers and client-side clustering are not the target architecture for 100k–500k global features, GPU bins, vector tiles, globe, and time/arc overlays. Keeping it would create a second later rewrite.

**CesiumJS as the default:** CesiumJS is a strong Apache-2.0 WGS84 globe/3D Tiles engine, but defaulting to globe/3D would overinvest in the least important interaction. Cesium ion's free Community plan is personal/non-commercial; its published commercial pricing begins at $149/month for an individual and hosted/self-hosted ion adds service/licensing/operations complexity. Use it only when reviewed terrain, 3D Tiles, or high-accuracy globe analysis creates an actual user benefit. CesiumJS alone is open source, but Cesium ion content/services are a separate cost and policy choice.

**OpenLayers as the primary:** it is mature, open, and has WebGL point/vector support, making it the credible fallback. It lacks the selected stack's cohesive Mapbox-style vector/globe path and requires more custom visualization composition for the planned GPU layers. Use it if MapLibre's style/projection implementation, browser support, or attribution integration fails acceptance benchmarks.

**Mapbox or Google as primary:** their services are capable, but mapping and geocoding introduce vendor lock-in, account keys, usage billing, and visitor-query disclosure. Mapbox bills map loads and separately bills hosted tileset processing/storage; Google likewise requires a billing/service relationship. They may be evaluated for a specifically approved feature with a published cost cap and privacy review, not adopted by convenience. No need exists to send visitor interests or private candidate data to either service.

**A graph database/force graph:** the accepted graph foundation intentionally uses PostgreSQL and public read-only projections. A graph database or visual force graph would not resolve source-scoped identity, conflicting observations, or publication policy; it would make false relationships visually persuasive. Defer graph visualization until the relationship data meets its own evidentiary and safety gates.

## Staged plan and gates

| Stage | Deliverable | Gate before advancing |
| --- | --- | --- |
| 0: retain | Current blank local Leaflet fixture adapter | Existing fixture safety/boundary tests remain passing; no V2 publication claim |
| 1: interface | Framework-neutral `MapAdapter`, `TileSource`, `AggregateModel`, and accessibility/list contracts; MapLibre spike using synthetic tiles only | Type/boundary tests; no external tile/geocoder requests; no V1 changes |
| 2: 2D release map | MapLibre 2D with self-hosted/open-data basemap, synthetic/publicly eligible vector tiles, exact/city/unmapped semantics, list parity | Manual privacy-provider inventory; keyboard, screen-reader, 320px/200% zoom, reduced-motion, WebGL-fallback, and cross-browser checks |
| 3: scale | Generated PMTiles pipeline and manifest/revocation design; aggregate/cluster modes | Synthetic 100k/500k benchmarks, profile separation, suppression/reimport/restore/cache tests, and operator review |
| 4: overlays | Reviewed source-backed time, relation, environmental, or permit overlays | Overlay-specific provenance/terms/privacy/publication review; causal-language review; mobile budget passes |
| 5: globe | MapLibre globe experiment, behind explicit toggle | Demonstrated orientation benefit over 2D; a11y/list parity; no increased coarse/sensitive disclosure; mobile GPU budget passes |
| 6: Cesium decision | A bounded CesiumJS/3D Tiles proof only if required | Written reviewed 3D data need, source/license/provider review, operational cost approval, and equivalent 2D fallback |

## Benchmark and acceptance plan

Benchmark only synthetic/sanitized public-shaped data. Use three distributions: global uniform, dense urban/city clusters, and a mix of exact/city/unmapped. At 100k and 500k records, measure cold and warm map open, first usable filter/list response, pan/zoom frame time, peak JS heap/GPU memory where observable, tile bytes/requests, selection latency, map context loss/recovery, and battery/thermal observations on representative mobile hardware. Test low zoom aggregation, mid zoom clusters, and high zoom points separately. Do not report a single FPS score as a safety or usability result.

Set provisional acceptance targets before implementation: no raw worldwide collection download; an interactive map first becomes usable within 3 seconds on the defined mid-tier desktop and 5 seconds on the defined mid-tier mobile under a throttled representative connection; map pan stays responsive without long tasks over 200 ms in the tested view; all list/detail/filter functions remain usable with WebGL disabled. Revise targets only with recorded device/network/data assumptions. Bundle budgets should report base application, map renderer, deck overlay, and tiles separately; globe/Cesium must be separate lazy chunks.

Regression tests cover suppression after tile build, cache invalidation/revocation, profile isolation, direct links, city/unmapped absence from exact point layers, aggregate scope/legend correctness, stale requests, map context loss, and a no-WebGL list-only route. Browser tests block unapproved network hosts. Accessibility tests include automated checks plus manual screen-reader, focus, reflow, reduced-motion, touch-target, and mobile orientation review. A performance pass does not replace human review or release authority.

## Primary sources reviewed

- [MapLibre GL JS documentation](https://maplibre.org/maplibre-gl-js/docs/) and [large-data guidance](https://maplibre.org/maplibre-gl-js/docs/guides/large-data/)
- [MapLibre GL JS BSD-3-Clause license](https://github.com/maplibre/maplibre-gl-js/blob/main/LICENSE.txt)
- [deck.gl project and MIT license](https://github.com/visgl/deck.gl) and [performance documentation](https://deck.gl/docs/developer-guide/performance)
- [CesiumJS Apache-2.0 license](https://github.com/CesiumGS/cesium/blob/main/LICENSE.md), [Cesium platform](https://cesium.com/platform/), [ion pricing](https://cesium.com/platform/cesium-ion/pricing/), and [ion self-hosted](https://cesium.com/platform/cesium-ion/cesium-ion-self-hosted/)
- [OpenLayers WebGL points example](https://openlayers.org/en/latest/examples/webgl-points-layer.html) and [WebGL workshop](https://openlayers.org/workshop/en/webgl/points.html)
- [Protomaps basemap license/attribution guidance](https://github.com/protomaps/basemaps)
- [Cloudflare R2 pricing](https://developers.cloudflare.com/r2/pricing/)
- [Mapbox GL JS guide](https://docs.mapbox.com/mapbox-gl-js/guides/), [usage billing explanation](https://docs.mapbox.com/playground/gl-js-usage/), and [geocoding behavior](https://docs.mapbox.com/help/dive-deeper/geocoding/)
- [AWS CloudFront pricing](https://aws.amazon.com/cloudfront/pricing/)

All pricing and service terms are time-sensitive and must be rechecked at procurement or public deployment. This ADR does not endorse the content licenses of any basemap, imagery, terrain, environmental, permit, or geocoding source; each remains a separate source-terms, attribution, privacy, and publication decision.
