# Developer entrypoint

Production-shaped deploy, rollback, backup, restore, incident, and
fresh-machine procedures are in
[`deployment/production-operations.md`](deployment/production-operations.md).
They describe controls and verification steps; they do not claim that hosting,
staffing, retention, or provider behavior has been audited.

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

`python scripts/dev.py --json doctor` (and any command with the global `--json` flag) emits one machine-readable JSON object. Child-command output is captured so it cannot corrupt JSON output. Diagnostics report only whether environment variables are set; values and database credentials are never printed. `up` may apply migrations and seed/promote the synthetic local fixture through the existing `local-v2.ps1` workflow. It does not publish project data.

## First checkout

Install the pinned root dependencies before running the root JavaScript suite:

```powershell
npm ci
python scripts/dev.py --json doctor
```

The doctor reports missing dependencies with a corrective command and distinguishes an expected `uec-local-v2` database from an unknown process occupying port 5433. Missing `UEC_RUNTIME_MODE` and `UEC_DATABASE_URL` are informational when documented local defaults apply. For the Svelte preview, install its separate dependencies with `npm --prefix frontend ci`.

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

The fixture preview is the default, does not need a database, and is the correct first environment for UI work. `npm run test:e2e:fixture` starts its own local preview. Do not add `?mode=local-v2` until `python scripts/dev.py --json doctor` reports a healthy environment, then use `up`, `probe`, and `npm run test:e2e:local` as documented in the frontend README. `status` distinguishes a running Axum process from a database-only local environment, and `probe` reports a concise next step when the backend is unavailable. Port conflicts and an unavailable Docker engine are environment problems, not a reason to stop an unknown process or silently fall back to fixtures.

## Troubleshooting persistent local V2 state

`local-v2.ps1 start` uses the named `uec-local-v2` Compose project and keeps its
volume across normal stops. Migration application records checksums and
refuses to run when an already-applied migration differs from the checkout.
That failure is intentional: never edit an old migration or bypass the check.

If the error names `migration checksum changed after application`, first run
`python scripts/dev.py --json status` and confirm which checkout owns the
database. If the volume contains work you need, stop and preserve it, then
restore the matching checkout or migrate it through an explicit maintainer-
reviewed procedure. If it is only the disposable synthetic local fixture, an
operator may intentionally remove just that named project and volume, after
confirming the target:

```powershell
docker compose -p uec-local-v2 -f docker-compose.pipeline.yml down -v --remove-orphans
python scripts/dev.py up
```

This reset is destructive to the local synthetic database and is not part of
ordinary `down`; do not run it against production or an unknown Compose
project. The migration ledger exists to prevent accidental history changes.
