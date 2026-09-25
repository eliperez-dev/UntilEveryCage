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
launchpad              owned Postgres + API + Svelte development stack (one command)
launchpad-stop         stop only launchpad-owned processes; preserve its database
launchpad-status/probe launchpad lifecycle and contract probes
launchpad-reset        explicitly remove only the launchpad database volume
logs                   recent Compose logs
test [--full]          JavaScript tests (full runs the configured suite)
pipeline [pytest args] Python pipeline tests
contracts              database and adapter contract tests
review-packet RUN_DIR  deterministic, row-free private review packet
```

### Run CFIA strict live private E2E

For the bounded CFIA source lane, run one command from the repository root:

```powershell
python scripts/real_preview.py strict-live-private-e2e --source ca.cfia.federal-meat
```

It starts a uniquely named disposable loopback Postgres/PostGIS preview,
performs one authorized CFIA public download with the tracked source terms
record, runs provenance/schema/function-code validation and quarantine,
atomically imports the private candidate handoff, verifies read-only search,
detail, and viewport behavior, writes a row-free certificate, and removes the
disposable database volume. Raw workbook and row-bearing private lifecycle
artifacts remain under ignored local staging; do not commit them. CFIA has no
source coordinates, so candidates are searchable/listable but remain off the
map. The official result page and workbook counts differ, and the listing is
stale-dated; this run proves bounded processing of the acquired artifact only,
not source completeness, current facility status, privacy clearance, or
publication eligibility. No public rows are created.

### Certify one strict private real-preview run

`python scripts/certify_real_preview.py --source <source-id> --ledger <path-to-source-preview-ledger.json>`
verifies one already completed source run. It does not acquire data. The source
must be explicitly enabled for private production E2E, and the command requires
the exact run ledger, its loopback Postgres database, and the running loopback
preview API. Supply the database URL through `UEC_DATABASE_URL` and keep a
32-character-or-longer preview token in `UEC_DEV_PREVIEW_TOKEN` in the current
process environment; neither value is printed or written by the command. The
API address defaults to `http://127.0.0.1:38001` and can be changed with
`--api-url` only to another loopback HTTP address.

The row-free JSON certificate binds acquisition and runner IDs to provenance
hashes, quarantine and candidate counts, database rows, zero public projections,
coordinate validity, and the served private API's run/count/list/detail/map
readiness. A failure exits nonzero without producing a certificate. Live source
acquisition remains a separate explicit operator action through
`scripts/real_preview.py refresh --source <source-id>`; certification itself
never fetches or imports source data. A passing result is a point-in-time,
source/run-scoped private-preview check. It does not establish source
completeness, factual accuracy, privacy clearance, publication approval, release
eligibility, or recurring runtime health.

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

### Local real-preview for map testing

Synthetic fixtures remain the default. For a prepared disposable candidate
release that needs real-location rendering tests, use the guarded local
real-preview route only after following
[the preview protocol](deployment/dev-preview.md#local-real-preview-protocol).
The launchpad never imports or discovers data: it only forwards an explicit,
complete allowlist to the loopback API. Set these values in the current shell
(never in a `.env` file or command line) and start the owned stack:

```powershell
$env:UEC_LOCAL_REAL_PREVIEW = 'true'
$env:UEC_DEV_PREVIEW = 'true'
$env:UEC_DEV_PREVIEW_TOKEN = '<memory-only-token>'
$env:UEC_TEST_RELEASE_ID = '<prepared-candidate-release-id>'
$env:UEC_TEST_RELEASE_TOKEN = '<memory-only-token>'
python scripts/dev.py launchpad
```

All four preview values are required when the flag is true; otherwise the
launchpad fails closed. It always binds the API and Vite to `127.0.0.1` and
passes the tokens only to the API child. The Vite child does not inherit them;
the frontend must retain any user-entered token only in memory and send it as
the required request header. Do not use a tunnel, browser persistence,
analytics, CSV export, screenshots with sensitive rows, or a remote host.
`launchpad-stop` and clearing these variables ends the local session; it does
not make a candidate published or alter the empty public projection.

The currently approved local rehearsal is a bounded 50,750-row legacy V1
snapshot (48,703 mapped; 2,047 unmapped), explicitly labeled
legacy/development-only/not-V2-reviewed and never promotable. Keep map reads
viewport-bounded; do not mount all rows as DOM markers or serialize the corpus
into a frontend artifact.

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

## One-command frontend launchpad

After both dependency sets are installed, the complete loopback development
stack can be started with:

```powershell
python scripts/dev.py launchpad
```

The command validates Docker, Compose, Python, Cargo, Node, npm, PowerShell,
the frontend dependencies, and the API/frontend ports before starting
anything. It owns a distinct Compose project (`uec-v2-launchpad`) and a
distinct `target/launchpad` process/state directory. It starts the local
Postgres/PostGIS service, applies the checked-in migrations, starts the Rust
API on `http://127.0.0.1:8000`, and starts Vite on
`http://127.0.0.1:4173/v2-preview/`. The launchpad emits only URLs, aggregate
data mode, release id, and a row-free summary; it never prints credentials,
private paths, or rows.

The default mode is the checked-in sanitized contract fixture. Private data is
never discovered automatically. To select a prepared private development
dataset, set both variables explicitly before starting:

```powershell
$env:UEC_DEV_DATASET_MODE = 'private'
$env:UEC_DEV_DATASET_MANIFEST = 'D:\approved\uec\development-manifest.json'
python scripts/dev.py launchpad
```

The manifest is an aggregate-only control document owned by the development
dataset workflow. It must declare `mode: "private"`, `ready: true`, a safe
`release_id`, and may include integer counts under `row_free_summary`.
Malformed or missing private configuration fails closed before any service is
started. The launchpad does not scan directories, acquire data, or import raw
records.

The local real-preview protocol is independent of this dataset selection: it
does not change the synthetic default, the row-free private-artifact mode, or
`public_projection.json`.

Use `python scripts/dev.py launchpad-probe` to check API liveness/readiness and
the Vite preview. Use `python scripts/dev.py launchpad-stop` for an ordinary
stop; the database volume is preserved. There is no implicit reset command.
Only the launchpad's explicitly named Compose project and verified Vite
process lease are eligible for cleanup, so an unrelated container or process
is not stopped.

If the disposable fallback database must be recreated, use the explicit
destructive command `python scripts/dev.py launchpad-reset`. It targets only
the `uec-v2-launchpad` Compose project and its volume, then requires a fresh
`launchpad` start.
