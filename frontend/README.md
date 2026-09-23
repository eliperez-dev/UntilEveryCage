# V2 frontend structural shell

The Svelte 5/TypeScript preview currently provides only route structure and basic accessible navigation. It does not load fixture or API data, render a map, or publish record details.

## Routes

- `#/map` — map page shell
- `#/database` — database page shell
- `#/records/:id` — record page shell

The hash routes work under the `/v2-preview/` base path without server-side route rewrites. Old `#/locations/:id` links open the matching record shell for compatibility. Unknown paths show a not-found state.

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

The API clients, domain types, repositories, fixtures, projection and clustering contracts, and historical design documentation remain in the repository for future application work. They are not connected to the current shell. The legacy public application remains at the repository root under `static/` and `src/`.
