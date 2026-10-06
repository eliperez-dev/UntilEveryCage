# V2 frontend preview

The Svelte 5/TypeScript production build remains a structural shell. A local,
development-only real-preview mode connects MapLibre, the research index, and
record evidence to the same-origin private API. It does not publish the data or
fall back to synthetic records if the private service fails.

## Routes

- `#/map` — map; real MapLibre field when the local real-preview mode is enabled
- `#/database` — paginated research index in local real-preview mode
- `#/records/:id` — stable, directly addressable record evidence page in local real-preview mode
- `#/contribute` — Add a facility by default; labeled task links switch contribution type
- `#/about` — Overview; the About menu also links Sources & methodology
- `#/about/help` — written guides and a controlled contribution walkthrough
- `#/about/api` — public API documentation, Swagger explorer and bounded download links

The hash routes work under the `/v2-preview/` base path without server-side
route rewrites. Old `#/locations/:id` links remain compatible. Unknown paths
show a not-found state. The browser uses the Vite same-origin proxy; it never
receives the private-preview token.

The Help tutorial contains blank UI only, has native playback controls and no
autoplay, and has equivalent written steps. Refresh it when the contribution
flow changes. Do not record real preview rows, filled submissions, receipts or
operator screens.

With a pilot-enabled loopback preview running, regenerate the blank walkthrough
from `frontend/`:

```powershell
node scripts/capture-contribution-tutorial.mjs http://127.0.0.1:4173/v2-preview/
```

The recorder blocks API/private/external requests, submits nothing, and writes
the reusable WebM under `public/tutorials/`. Review playback before committing it.

The API page loads pinned, self-hosted Swagger assets only when opened. Vite
serves the canonical `docs/api/public-openapi.json` and shared location schema
together under `reference/`; builds emit the same files and Swagger license
notices into `dist/reference/` for the existing staging command. Do not maintain
copied specifications in `public/`. API execution is same-origin GET-only, with
no online validator, remote spec configuration or credentials. Published-release
eligibility still applies; private preview data are not an export source.
CSV rejects datasets over 1,000 records; larger exports use paginated JSON.
From the repository root, check API specification drift with
`python -B -m unittest pipeline.tests.test_public_openapi_contract pipeline.tests.test_v2_contract_convergence`.

## Frontend checks

From `frontend/`, install the lockfile dependencies and run:

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

The legacy public application remains at the repository root under `static/`
and `src/`. Local-preview APIs are not connected to the production shell.
