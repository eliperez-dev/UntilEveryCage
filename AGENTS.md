# Repository operating guide

## Required reading order

Before repository work, read in order: `AGENTS.md` (this file) → [docs/ETHICS.md](docs/ETHICS.md)
→ [docs/VISION.md](docs/VISION.md) → [docs/README.md](docs/README.md) →
task-specific documents routed by the hub. The ethics policy governs data,
privacy, evidence, and publication decisions. The vision is not a readiness
claim; [docs/PRODUCT-READINESS.md](docs/PRODUCT-READINESS.md) owns current
product completion and [docs/source-status.md](docs/source-status.md) owns
source status.

## Project map and local work

The public application is Rust/Axum in `src/` with a vanilla JavaScript client
in `static/`. The V2 pipeline is in `pipeline/`; private inputs and generated
artifacts live in ignored/local `data/`. Start at [docs/README.md](docs/README.md)
for architecture, frontend, source, operations, and governance navigation.

Use `python scripts/dev.py --help` for the V2 developer entrypoint and
`python scripts/dev.py --json doctor` before starting local services. Root
`npm test` runs the legacy/static Jest suite after `npm ci`; the Svelte preview
has separate dependencies under `frontend/`. For the standard database-backed
pipeline gate, use `pwsh -NoProfile -ExecutionPolicy Bypass -File
pipeline/tests/run-standard.ps1`.

## Approved real-data development baseline

Use **v0 — Early Access** for all future data-backed development and new
integration/feature acceptance tests. Its aggregate identity and expected
counts live in `pipeline/contracts/development-baseline.json`; follow
[the v0 baseline workflow](docs/development.md#approved-v0-development-baseline).
Run `python scripts/dev.py baseline` before claiming real-data readiness.
The frozen reference database is not a writable test target: use a verified
disposable copy for migrations and mutating tests. Do not silently substitute
synthetic or legacy V1 data when v0 is unavailable. Retain synthetic unit and
negative-case tests, but they do not replace the required v0 acceptance run.
Never commit real rows or include them in test output. Keep current privacy
restrictions effective in historical releases and restored copies.

Preserve existing and untracked work. Do not commit private source rows,
addresses, coordinates, credentials, or geocoder responses. Keep changes scoped
and report verification and evidence limits. Documentation additions and
retention follow [the writing policy](docs/README.md#where-durable-facts-live).
