# V2 frontend development

The production client is Svelte 5/TypeScript with MapLibre, served by Rust/Axum.
[Current UI instructions](../docs/frontend/README.md) own layout and copy;
[development](../docs/development.md) owns the local API/data setup.

## Routes and data modes

- `/` and `#/`: outreach landing; Open the map leads to the separate map route.
- `#/map`: map and selected facility detail.
- `#/database`: search and paginated records; links open full pages.
- `#/records/:id`: full facility page; old location routes remain aliases.
- `#/database/api`: downloads, paginated API and self-hosted Swagger.
- `#/contribute`: facility/evidence/correction/duplicate/privacy and bug intake.
- `#/about` and `#/faq`: manifesto/counter and concise help.
- `#/contribution-status`: submission tracking.

Public-release mode uses eligible published projections. Private real-preview
mode is a separately configured loopback workflow; tokens stay server-side in
the Vite proxy. A fixture/local-artifact run is not public or fresh-source E2E.
Do not silently substitute synthetic records when real-data acceptance is required.

Set `UEC_COMMUNITY_API_ORIGIN` in the Vite server environment to route
`/api/community` and `/api/private/community` to a separate contribution service while `VITE_API_ORIGIN`
serves the remaining API. The override applies to dev and preview, stays
server-side, and leaves existing routing unchanged when unset.

The canonical OpenAPI/schema files are served under `reference/` and bundled
with the self-hosted Swagger notices. Do not maintain copied specs in `public/`.
Swagger executes same-origin public GET operations, not private/intake writes.
The API supports full-release CSV, explicit bounded exports and cursor JSON.

## Frontend checks

From `frontend/`, install dependencies only when needed. For a small change,
run its focused tests and applicable type/lint checks. The commands below are
available gates, not a requirement to repeat every suite after every edit:

```powershell
npm ci
npm run check
npm test
npm run lint
npm run boundary
npm run build
```

## Real-preview map performance harness

`npm run test:performance` measures the real MapLibre path through the normal
same-origin Vite proxy. It is deliberately skipped unless `UEC_REAL_PREVIEW_URL`
points at a populated loopback preview; it does not create a token, add one to a
URL, or call the private API separately from the browser application.

The harness reports these end-to-end timings as a Playwright JSON attachment:

- first MVT map readiness;
- warm pan and zoom settle (including cached tile rendering);
- satellite style swap settle;
- global search response/UI availability;
- facility dossier selection; and
- rendered city/coarse reference selection.

Run it against the local preview, for example:

```powershell
$env:UEC_REAL_PREVIEW_URL = 'http://127.0.0.1:34195/'
npm run test:performance
```

It is report-only by default because timings vary by populated source set,
machine, browser, and basemap provider. To turn it into a regression gate, opt
in explicitly and supply only the budgets relevant to the environment:

```powershell
$env:UEC_PERF_ENFORCE = '1'
$env:UEC_PERF_BUDGET_INITIAL_MVT_MS = '8000'
$env:UEC_PERF_BUDGET_WARM_PAN_MS = '1200'
$env:UEC_PERF_BUDGET_WARM_ZOOM_MS = '1600'
$env:UEC_PERF_BUDGET_BASEMAP_MS = '5000'
$env:UEC_PERF_BUDGET_SEARCH_MS = '1500'
$env:UEC_PERF_BUDGET_DETAIL_MS = '1500'
$env:UEC_PERF_BUDGET_REFERENCE_MS = '1500'
npm run test:performance
```

The values above are starting budgets, not universal expectations. Capture a
baseline from the target machine first, then set budgets with intentional
headroom. The harness needs a populated local preview; deterministic unit tests
continue to cover parsing, layer contracts, and motion decisions without a
database or browser map worker.

For the populated browser route check, set `UEC_REAL_PREVIEW_URL` to the local
preview and run `npx playwright test tests/e2e/real-preview-record-route.spec.ts`.
It verifies both map and database entry points to a stable record URL.
