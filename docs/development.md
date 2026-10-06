# Developer entrypoint

## Approved v0 development baseline

**Maintainer decision, 2026-10-06:** `v0 — Early Access` is the approved
real-data baseline. It contains 63,601 curated searchable records from 13
sources, including 48,756 map locations and 54,256 names. It is approved
release data, not an externally deployed website. V1 is required before
website launch. V0 must remain available as a historical release, subject
to current corrections and privacy restrictions.

The tracked aggregate-only contract is
`pipeline/contracts/development-baseline.json`. It binds the exact internal
release ID and immutable manifest checksum to these counts. The public dataset
version is `v0`; schema/product contract versions are separate identifiers.

Run the read-only verification with the local database URL supplied privately
through `UEC_DATABASE_URL`:

```powershell
python scripts/dev.py baseline
```

Verified local setup (2026-10-06), in the existing PostgreSQL container at
`127.0.0.1:55433`:

- Frozen reference: `uec_v0_review_r3`, read-only by default; never a test target.
- Writable development copy: `uec_v0_dev`, restored from the verified archive.
- Private backup: `D:/UntilEveryCage-backups/database/v0-early-access-20261006/`.
  The archive checksum and restore receipt are in `backup-verification.json`.

Point the development API's privately supplied database URL at `uec_v0_dev`
and its official release projection. Do not point the public-data UI at the
larger private research projection: withheld records remain in the private
backup for provenance, but are not part of approved v0 output. Database
credentials are not stored in the tracked baseline contract. A rollback-only
write probe passed on the copy; the reference's verified counts were unchanged.

For later restores, replay the latest restriction ledger using the production
operations runbook; an old snapshot does not override newer restrictions.

Use a verified disposable v0 copy for normal development, migration trials
and mutating tests. Never run a reset, seed, truncate, schema experiment or
destructive test against the frozen reference database. A clone starts with
the exact approved snapshot; subsequent source refreshes create future-release
work and do not change v0. Preserve the verified snapshot on D: and use the
existing PostgreSQL backup/restore procedure, rather than another Docker stack.

All new data-backed integration and feature acceptance tests must run against
v0 copies. Keep synthetic unit and adversarial fixtures where needed to test
cases the real dataset does not contain, but do not count fixture-only success
as real-data readiness. If the real baseline is unavailable, report that test
as blocked; do not silently switch datasets. Public CI can continue its
sanitized fixture tests until a secure real-baseline input is configured; a
local verified v0 acceptance run is required in addition. Never upload private
source artifacts, excluded rows, database credentials, or a full research
snapshot to public CI or Git.

The older fixture/legacy workflows below remain diagnostic tools, not the
default data-backed product development environment.

### Integrated public-data frontend

The ordinary `/v2-preview/#/map` and `#/database` routes use the approved
official release, including in development. Set `VITE_API_ORIGIN` to your
local API origin; do not add private-preview credentials for this workflow.
The map fetches the release-scoped `/api/v2/map/feed` point projection once
per release identity and clusters it locally. Search and record pages fetch
their data separately. CSV downloads explicitly contain at most 1,000 rows
and report whether the export is truncated; JSON remains paginated.

After migrations, run the real-data acceptance against an API serving a
verified v0 copy:

```powershell
$env:UEC_API_ORIGIN = 'http://127.0.0.1:<api-port>'
python -m unittest pipeline.tests.e2e.public_v0_integration_acceptance -v
```

The acceptance checks real release identity, counts, map precision, record
lookup and export bounds. Mutating contribution checks belong on a disposable
copy; submissions do not change the approved release or its map.

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

### Local community contribution pilot

This feature is disabled by default and refuses production enablement or a
non-loopback bind. It is a local workflow, not a public submission launch.
Use an allocated checkout and a separate disposable, migrated PostgreSQL/PostGIS
database; preserve existing source databases and developer services. Run
`python scripts/dev.py --json doctor` before starting services.

For your separately chosen API port, set `UEC_RUNTIME_MODE=development`,
`UEC_BIND_HOST=127.0.0.1`, `PORT`, `UEC_DATABASE_URL` and
`UEC_COMMUNITY_ENABLED=true`. Supply a distinct randomly generated
`UEC_COMMUNITY_OPERATOR_TOKEN` (32–512 bytes) through process configuration;
never commit, log or reuse a preview credential. Explicitly choose positive
`UEC_COMMUNITY_RETENTION_DAYS` (maximum 365),
`UEC_COMMUNITY_CONTACT_RETENTION_DAYS`, `UEC_COMMUNITY_RECEIPT_DAYS`
(both no longer than payload retention), `UEC_COMMUNITY_DAILY_INTAKE_CAP`
(maximum 1,000) and `UEC_COMMUNITY_PENDING_CAP` (maximum 10,000).
These bounds are implementation limits, not approved operational defaults.

Run `cargo run --locked --bin uec-api`. For a separate Vite instance, set
`VITE_COMMUNITY_PILOT=true` and `VITE_API_ORIGIN` to that loopback API origin,
then `npm --prefix frontend run dev -- --host 127.0.0.1 --port <unused-port>`.
Open `/v2-preview/#/contribute` for Add a facility. Visible task links switch
the unified form to evidence, correction, duplicate, privacy/removal or bug report.
Canonical type links use `#/contribute?type=facility`, `evidence`, `correction`,
`duplicate`, `privacy_removal` or `bug`. Existing `#/contribute/…` links
preselect the appropriate type. The shared
styled header is Map, Database | Contribute, About. Contribute is a direct
link; Database's text-only menu offers Browse records, Downloads and API
documentation. About offers Overview, Sources & methodology, FAQ and Help.
`#/about/manifesto` remains an alias for Overview. Overview and Contribute
provide the open-source code contribution link on GitHub.
Country names and source links are optional on facility intake; a name is
required. Evidence needs a record reference and either a link or explanation.
Contact email is optional for private follow-up and is stored separately from
the claim. No automated email is sent; entering email is not an account,
receipt recovery method or subscription. It expires under the configured
contact retention period (the current disposable user test uses one day), so
this pilot is not a durable list for future notifications. Future delivery
needs approved retention/purpose, sender verification, a restricted contact
workflow and delivery controls before enabling it.
Receipt lookup uses the **Submission ID** and **Private receipt** returned
after sending. Save both with the explicit copy controls; neither is stored
in a link or browser storage. A **Record ID** identifies an existing facility
and is used to target evidence/corrections; it cannot replace a Submission ID.
Bug reports compose email or open GitHub; the user sends the report.
Other local routes are `#/contribution-status`,
`#/contribution-review` and `#/community`. Supply the operator credential
in the private review form; it remains in memory. Privacy-request actions
operate on the submission; target-record suppression follows the governance
runbook. Accounts, uploads and email delivery are absent.

For a separately authorized combined local preview, keep `/api/community/*`
on the isolated intake service. Vite's server-only
`UEC_REAL_PREVIEW_API_ORIGIN` can route `/dev/real-preview/*` to a different
authenticated loopback service against the retained database;
`UEC_COMBINED_PREVIEW=true` preserves the `/v2-preview/` base. The existing
`UEC_DEV_PREVIEW_TOKEN` and `VITE_LOCAL_DATA_MODE=real-preview` gate still apply.
Keep credentials in process memory and make retained-database sessions read-only.
This does not import data, apply migrations, make a public release or enable
private downloads. Verify authenticated aggregate responses and independent
intake health; a synthetic browser test does not prove this connection.

`UEC_COMMUNITY_PUBLIC_ENABLED=true` separately enables safe linkage reads.
It does not release submitted pins. An authenticated `link_community` API
disposition requires an already eligible community **source-record** UUID and
its release ID. Public claim metadata links to existing released facility
detail; no intake narrative or selected coordinate is exposed.

Call authenticated `POST /api/private/community/maintenance` to expire raw
claims/contact and revoke expired receipt hashes, retaining tombstones and
payload-free events. Arrange and verify an idle maintenance schedule before
any ongoing pilot; none is installed here. Do not enable public operations
without triage and retention approval, role separation and proven removal
restore/replay. See the [owning proposal](governance/user-submitted-data.md).

For the synthetic database/API proof, apply migrations to an **empty disposable**
loopback database, build `cargo build --locked --bin uec-api`, and set
`UEC_COMMUNITY_TEST_DATABASE_URL` plus `UEC_COMMUNITY_TEST_BINARY` to the local
binary. Run `python -m unittest pipeline.tests.e2e.test_community_intake -q`.
The proof refuses a nonempty source/intake database, starts and stops its own
loopback API, and seeds synthetic community releases without provider calls.
It exercises live restrictions, receipt isolation/revocation, payload expiry,
immutable audits and concurrent admission caps. It intentionally leaves its
fixtures in the disposable database; destroy only your owned test database.

For the synthetic browser proof, start your separate Vite instance with
`VITE_COMMUNITY_PILOT=true`, then run from `frontend`:

```powershell
$env:VITE_COMMUNITY_PILOT = 'true'
$env:UEC_REAL_PREVIEW_URL = 'http://127.0.0.1:<your-vite-port>/v2-preview/'
npx playwright test tests/e2e/community-pilot.spec.ts --workers=1
```

This proof mocks only synthetic API responses and blocks external map tiles.
It checks pin interaction, coordinate fallback, receipt secrecy, private queue
context and community warnings. It does not certify live basemap availability
or publication of a newly submitted point. CI runs the same dedicated proof
with explicit pilot enablement; the ordinary frontend remains disabled.

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

The fixture preview is available for isolated UI/unit checks without a database. Use the approved v0 copy for data-backed UI development. `npm run test:e2e:fixture` starts its own local preview and proves fixture behavior only. Do not add `?mode=local-v2` until `python scripts/dev.py --json doctor` reports a healthy environment, then use `up`, `probe`, and `npm run test:e2e:local` as documented in the frontend README. `status` distinguishes a running Axum process from a database-only local environment, and `probe` reports a concise next step when the backend is unavailable. Port conflicts and an unavailable Docker engine are environment problems, not a reason to stop an unknown process or silently fall back to fixtures.

### Local real-preview for map testing

Synthetic fixtures remain available for diagnostics. For a prepared disposable candidate
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

The superseded local rehearsal used a bounded 50,750-row legacy V1
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
