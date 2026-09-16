# Developer entrypoint

Use `python scripts/dev.py --help` (or `scripts/dev.ps1 --help` on Windows) to discover the V2 workflow. Commands are thin wrappers around the existing project tools:

```text
doctor                 prerequisites, ports, configuration, and optional DB reachability
up/down/status/probe   local V2 environment
logs                   recent Compose logs
test [--full]          JavaScript tests (full runs the configured suite)
pipeline [pytest args] Python pipeline tests
contracts              database and adapter contract tests
review-packet RUN_DIR  deterministic, row-free private review packet
```

`python scripts/dev.py --json doctor` (and any command with the global `--json` flag) emits a final machine-readable summary. Diagnostics report only whether environment variables are set; values and database credentials are never printed. `up` may apply migrations and seed/promote the synthetic local fixture through the existing `local-v2.ps1` workflow. It does not publish project data.

## Frontend contributor path

The root JavaScript commands exercise the legacy static/Jest application. The Svelte V2 preview has its own pinned dependencies and commands in [`frontend/`](../frontend/README.md):

```powershell
cd frontend
npm ci
npm run check
npm test
npm run lint
npm run boundary
npm run build
npm run dev
```

The fixture preview is the default, does not need a database, and is the correct first environment for UI work. `npm run test:e2e:fixture` starts its own local preview. Do not add `?mode=local-v2` until a clean `python scripts/dev.py --json doctor` reports Docker Compose and ports 8000/5433 available, then use `up`, `probe`, and `npm run test:e2e:local` as documented in the frontend README. Port conflicts and an unavailable Docker engine are environment problems, not a reason to stop an unknown process or change the preview to use fixtures as a live fallback.
