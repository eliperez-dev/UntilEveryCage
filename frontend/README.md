# V2 frontend preview and local integration

Svelte 5/TypeScript preview. Start with the [developer entrypoint](../docs/development.md); this file defines the frontend-specific commands and the fixture/local boundary.

## Start in fixture mode

From `frontend/`, use the lockfile-based install and then run the checks below:

```powershell
npm ci
npm run check
npm test
npm run lint
npm run boundary
npm run build
npm run dev
```

Open the URL Vite prints, normally `http://127.0.0.1:5173/v2-preview/#/`. This is **fixture mode**: the default and only safe onboarding path. It makes no live API, tile, analytics, or geocoding request. `npm run test:e2e:fixture` starts its own fixture preview and runs the Chromium/Firefox/WebKit-configured suite unless a project is selected explicitly.

The existing root `npm test` is the legacy static/Jest suite. It is deliberately separate from the commands above; run it from the repository root when changing root `static/` assets or compatibility modules.

The ethics link intentionally targets the existing `/ethics.html` page.

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

## Local V2 integration: explicit and optional

Fixture mode does not require Docker, PostgreSQL, backend data, or a token. Only use local mode when checking the V2 client against the **synthetic local release**.

From the repository root, first check prerequisites and port ownership:

```powershell
python scripts/dev.py --json doctor
```

`doctor` must report ports 8000 and 5433 as free and Docker Compose as available. A port in use means another local service owns it; inspect it before stopping anything. If Docker Desktop's engine is unavailable or access is denied, start/authorize Docker Desktop and rerun `doctor`. The helper's `status` output can report an unmanaged Axum process, but it cannot make an unavailable Docker engine healthy.

When `doctor` is clean, the supported seeded workflow is:

```powershell
python scripts/dev.py up
python scripts/dev.py probe
npm --prefix frontend run dev
```

Open `http://127.0.0.1:5173/v2-preview/?mode=local-v2#/`. The helper starts a named local Postgres stack on 5433, applies migrations, seeds/promotes only the synthetic contract release, and starts Axum on 8000. It preserves its database volume on `down`; it does not publish data. Do not substitute an arbitrary `cargo run` instance for this workflow, because it may not have the expected synthetic release, database configuration, or CORS origin.

Run `npm run test:e2e:local` from `frontend/` only while that helper-owned stack is healthy. The command is cross-platform and sets `LOCAL_V2_E2E=1` itself. Finish with `python scripts/dev.py down` when you own the stack. Do not stop a service merely because `doctor` found its port occupied.

In development/preview, Vite proxies `/api` to `http://127.0.0.1:8000`; the proxy is development-only and production builds do not enable a backend connection. The `LocalLocationRepository` targets `/api/v2/locations?profile=...` only when the explicit `?mode=local-v2` route is used; fixture mode remains the default and there is no V1 fallback.

The opt-in local view loads one API page at a time. Search, country/region/category/source/profile/precision/lifecycle filters are evaluated by the server against the selected promoted release; cursor pages remain explicit and are never merged across release IDs. Bounded bbox and radius parameters are available to map clients. Record context is limited to fields in the current V2 wire response and does not imply that review events, evidence hashes, or scoped approvals are available.

The private scale/story prototype begins with a neutral individual-animal representation and uses only bounded synthetic values. It labels model arithmetic separately from measured facility evidence; no biography, live counter, global animal total, or sourced aggregate is embedded in the production build. Candidate sourced scale figures remain outside this UI until maintainer publication approval.

The underlying `pipeline/scripts/maintenance/local-v2.ps1` accepts `start`, `status`, `probe`, and `stop`, but use the `scripts/dev.py` wrapper first so the prerequisite and port diagnostics are part of the onboarding trail. The helper is local-only and does not alter V1, production, or unrelated data.

Private candidate preview is a separate development-only shell. Its API is `/api/dev/preview/candidates?limit=100`, never `/api/v2/*`; it requires loopback, explicit development opt-in, and an operator token in `X-UEC-Dev-Preview-Token`. The token must stay in memory/session-only state or a local proxy, never a URL, committed source, log, or production bundle. Candidate rows must remain visibly marked `PRIVATE TEST DATA — NOT REVIEWED OR PUBLISHED`, with source/date/coverage/uncertainty context on every list, detail, map, and export surface. No real candidate rows or credentials belong in this repository.
