# V2 frontend preview

Fixture-only Svelte 5 demonstrator. Run `npm install`, then `npm run dev`. It uses no live API, external assets, analytics, or map tiles. The ethics link intentionally targets the existing `/ethics.html` page.

Phase 2 gate notes: staging is explicit (`npm run stage`) and copies only `frontend/dist` to the resolved ignored `static/v2-preview` destination. The Leaflet adapter is isolated and uses a blank local background; no tile provider is configured. Export previews retain profile, release, limitations, source, and observation context.

Remaining live-use blockers: the backend contract still needs canonical generated DTOs and release/revocation semantics; record-level evidence hashes, geocoder metadata, explicit review events, and scoped project approvals are not present in the current API. Human accessibility review (screen reader, 200% zoom, 320px reflow) and larger-workload performance measurements remain required before product completion. This preview must not be enabled for live publication.
