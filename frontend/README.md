# V2 frontend preview and local integration

Svelte 5/TypeScript frontend preview. Run `npm install`, then `npm run dev`. Fixture mode remains the safe default and uses no live API, external assets, analytics, or map tiles. The ethics link intentionally targets the existing `/ethics.html` page.

The explicit `?mode=local-v2` path uses the V2 API client for the official, secondary, and community profiles, controlled filters, cursor pagination, map/detail navigation, release/provenance context, and the profile-scoped public CSV route. A community profile keeps its persistent screened-but-unreviewed warning; it is not merged into official or secondary counts. Requests are cancellable and generation-checked so stale list/detail responses cannot replace newer state. No V1 fallback is used.

Phase 2 gate notes: staging is explicit (`npm run stage`) and copies only `frontend/dist` to the resolved ignored `static/v2-preview` destination. The Leaflet adapter is isolated and uses a blank local background; no tile provider is configured. Export previews retain profile, release, limitations, source, and observation context.

Remaining live-use blockers: the backend contract still needs canonical generated DTOs and release/revocation semantics; record-level evidence hashes, geocoder metadata, explicit review events, and scoped project approvals are not present in the current API. Human accessibility review (screen reader, 200% zoom, 320px reflow) and larger-workload performance measurements remain required before product completion. This preview must not be enabled for live publication.

Current-wire contract gap checklist (from the platform decision):

- [ ] Canonical machine-readable contract tied to Rust serialization, generated frontend DTOs, and CI drift checks.
- [ ] Record/version and evidence identifiers or hashes linked to source evidence.
- [ ] Source retrieval/publication dates and explicit source-availability semantics on record responses.
- [ ] Geocoder provider, query, timestamp, precision, result, and review-state fields.
- [ ] Independent community/project review events with role, scope, date, and outcome.
- [ ] Release/profile-scoped project approval and publication metadata.
- [ ] Stable release/revocation semantics and cache invalidation signals for concurrent queries.
- [ ] Backend-supported filters, aggregates, export endpoint, and release pinning before live product controls are added.

These are documented gaps, not frontend claims or invented DTO fields. Phase 3 continues to use only the synthetic fixture repository.

Local V2 integration (opt-in only): run the backend with `cargo run` (port 8000), then run the frontend with `npm run dev` (port 5173). In development/preview, Vite proxies `/api` to `http://127.0.0.1:8000`; use `http://127.0.0.1:5173/v2-preview/?mode=local-v2#/` to opt in. The `LocalLocationRepository` still targets `/api/v2/locations?profile=...` only when explicitly invoked; fixture mode remains the default and there is no V1 fallback. The proxy is development-only configuration and production builds do not enable a backend connection.

The opt-in local view loads one API page at a time. When the response includes `next_cursor`, the UI labels its counts, search, and map as partial; text search runs only against loaded records because the current public contract intentionally has no server-side free-text query. Record context is limited to fields in the current V2 wire response and does not imply that review events, evidence hashes, or scoped approvals are available.

The private scale/story prototype begins with a neutral individual-animal representation and uses only bounded synthetic values. It labels model arithmetic separately from measured facility evidence; no biography, live counter, global animal total, or sourced aggregate is embedded in the production build. Candidate sourced scale figures remain outside this UI until maintainer publication approval.

Persistent local two-port workflow (never uses `down -v`): from the repository root run `powershell -ExecutionPolicy Bypass -File pipeline/scripts/maintenance/local-v2.ps1 start`. It starts the named Postgres stack on `5433`, applies migrations, seeds and promotes the synthetic contract release, and starts Axum on `8000`. Run `npm --prefix frontend run dev` in another terminal and open `http://127.0.0.1:5173/v2-preview/?mode=local-v2#/`. Check ownership and health with `... local-v2.ps1 status`; probe list/detail with `... local-v2.ps1 probe`; stop both services with `... local-v2.ps1 stop`. The helper is local-only and does not alter V1, production, or unrelated data.

Private candidate preview is a separate development-only shell. Its API is `/api/dev/preview/candidates?limit=100`, never `/api/v2/*`; it requires loopback, explicit development opt-in, and an operator token in `X-UEC-Dev-Preview-Token`. The token must stay in memory/session-only state or a local proxy, never a URL, committed source, log, or production bundle. Candidate rows must remain visibly marked `PRIVATE TEST DATA — NOT REVIEWED OR PUBLISHED`, with source/date/coverage/uncertainty context on every list, detail, map, and export surface. No real candidate rows or credentials belong in this repository.
