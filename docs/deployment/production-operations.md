# Production operations runbook

Status: production operations procedure. Current verified Render deployment
state and remaining acceptance work live in [product readiness](../PRODUCT-READINESS.md).
This procedure is not evidence that the service is hosted, that a reviewer is
staffed, or that
any retention period, response SLA, backup destination, or provider control has
been verified.

The service is allowed to bind in production only after the independent
restriction-ledger replay state and trusted release-manifest digest pass the
startup gate. A failed gate, failed readiness check, stale release projection,
or unsafe proxy configuration leaves the service stopped. A development
process may start without a database so that static UI work remains possible,
but `/health/ready` and database-backed APIs remain unavailable; this is an
intentional degraded state, not a publication fallback.

## Configuration preflight

Set secrets through the deployment platform's secret store or an equivalent
private mechanism. Do not put them in the repository, image, command history,
URLs, browser bundles, diagnostics, or logs.

| Variable | Production requirement | Failure behavior |
| --- | --- | --- |
| `UEC_RUNTIME_MODE` | `production` | Startup exits before bind. |
| `UEC_DATABASE_URL` | Non-empty `postgres://` or `postgresql://` URL without whitespace. | Startup exits before bind. |
| `UEC_COMMUNITY_ENABLED` | `true` only after the restricted community role, retention decision, staffed private queue, and maintenance caller are ready; otherwise unset or `false`. | Enabled intake without its restricted URL exits before bind. |
| `UEC_COMMUNITY_DATABASE_URL` | Non-empty `postgres://` or `postgresql://` URL without whitespace for the restricted community runtime role; it must not be the public serving-role credential. | Enabled intake exits before bind. |
| `UEC_COMMUNITY_OPERATOR_TOKEN` | Independent 32–512 byte secret for the private queue, disposition, and maintenance endpoints. | Enabled intake exits before bind. |
| `UEC_COMMUNITY_RETENTION_DAYS`, `UEC_COMMUNITY_CONTACT_RETENTION_DAYS`, `UEC_COMMUNITY_RECEIPT_DAYS` | Positive, approved bounded retention values; contact and receipt values cannot exceed claim retention. | Enabled intake exits before bind. |
| `UEC_COMMUNITY_DAILY_INTAKE_CAP`, `UEC_COMMUNITY_PENDING_CAP` | Positive approved abuse/backlog caps (at most 1,000 daily and 10,000 pending). | Enabled intake exits before bind. |
| `UEC_COMMUNITY_PUBLIC_ENABLED` | `false`/unset unless separately approving the already-screened linkage-read surface; it never publishes new intake content. | Invalid enabled/disabled combination exits before bind. |
| `PORT` | Non-zero TCP port; defaults to `8000`. | Startup exits before bind. |
| `UEC_BIND_HOST` | Valid IP address; defaults to `0.0.0.0` in production. | Startup exits before bind. |
| `UEC_CORS_ORIGINS` | One or more exact bare `http(s)` origins, comma-separated; no wildcard. | Startup exits before bind. |
| `UEC_TRUST_PROXY` | Explicit `true` or `false`. | Startup exits before bind. |
| `UEC_TRUSTED_PROXY_CIDRS` | Required and limited to the reverse-proxy networks when proxy trust is `true`; absent otherwise. | Startup exits before bind. |
| `UEC_RESTRICTION_LEDGER_PATH` | Separate current private ledger. | Startup exits before bind. |
| `UEC_RESTORED_RESTRICTION_SNAPSHOT_PATH` | Separate post-replay row-free snapshot. | Startup exits before bind. |
| `UEC_RELEASE_MANIFEST_PATH` | Trusted manifest for the release being served. | Startup exits before bind. |
| `UEC_RELEASE_MANIFEST_SHA256` | 64 lowercase hexadecimal trusted digest. | Startup exits before bind. |

The legacy singular `UEC_CORS_ORIGIN` is accepted only for compatibility and
must not conflict with `UEC_CORS_ORIGINS`. Candidate/test-release settings are
development-only and must never be set in production.

For the existing loopback development pilot only, an enabled community service
may omit `UEC_COMMUNITY_DATABASE_URL` and reuse `UEC_DATABASE_URL`; this keeps
the disposable pilot harness compatible. Production never uses that fallback:
it requires the separate URL and performs `current_user` checks at startup to
reject a community URL authenticated as the serving role.

### Restricted community runtime role

The serving role configured by `UEC_DATABASE_URL` remains read-only and has no
access to contributor intake/contact tables. Create a separate
`uec_community_runtime` role (or equivalently restricted role) before setting
`UEC_COMMUNITY_ENABLED=true`. Grant it only `USAGE` on schema `uec`, then:

```sql
GRANT SELECT, INSERT, UPDATE ON uec.community_submissions TO uec_community_runtime;
GRANT SELECT, INSERT, DELETE ON uec.community_submission_contacts TO uec_community_runtime;
GRANT SELECT, INSERT ON uec.community_submission_events TO uec_community_runtime;
GRANT SELECT ON uec.map_facilities_public_discovery_read_model,
  uec.releases, uec.public_discovery_read_models, uec.release_manifests
  TO uec_community_runtime;
```

Do not grant this role `CREATE`, migration/schema ownership, sequence access,
or access to source records, observations, raw artifacts, geocoder tables,
curated release writes, or unrelated tables. It needs the four read-model
relations only to verify that an operator-linked community claim already
belongs to a currently promoted, privacy-passed community release. It never
creates a source record, release member, graph edge, or map pin.

Use independent secret-store values for the community database URL and
operator token. The operator token authenticates the private maintainer queue;
it is not a contributor credential and must never be in URLs, logs, browser
storage, or the serving database credential. Schedule authenticated
`POST /api/private/community/maintenance` using the operator's restricted
secret mechanism and record only its aggregate result. The application does
not install a scheduler. Each accepted intake transaction opportunistically
applies the same expiry policy, but idle data is not deleted merely because
time passes; a periodic maintenance caller remains required before claiming
unattended retention enforcement. Record that limitation with the approved
retention and private-review process.

For a rollback to a binary that does not support production intake, first set
`UEC_COMMUNITY_ENABLED=false`, then deploy that binary with the matching release
controls. Keep the intake tables and restricted controls intact; disabling the
service is not permission to delete submissions. Re-enable intake only after
the supporting binary and its separate-role checks pass again.

## Deploy a release

1. Build the exact revision with locked dependencies (`cargo build --release
   --locked`) and retain the image/revision identifier in the private change
   record. Do not substitute a working tree or an unreviewed candidate.
2. Run the private environment gate from a clean checkout. Supply the current
   ledger, post-restore snapshot, trusted release manifest, and trusted
   manifest digest. The gate validates migration inventory and metadata but
   does not approve publication or copy sensitive rows.
3. Apply migrations using the deployment's migration procedure. Stop on any
   checksum or migration error; preserve the previous validated release and
   follow `docs/development.md` before considering a disposable local volume
   reset. Never edit migration history to bypass a checksum mismatch.
4. Build or select the named release projection through the existing release
   validation and approval workflow. Keep source origin, review, privacy,
   project approval, and publication state separate. Automated acquisition or
   a successful source check is not publication authorization.
5. Replay the current independent restriction ledger against the target
   database and write a fresh snapshot. Verify that the snapshot revision,
   digest, and opaque reference set match the ledger. Do this after any restore
   or release rebuild as well as during first deployment.
6. Start the service with the production variables. Confirm a
   `server_starting` event with no secret-bearing fields, then poll
   `/health/live` and `/health/ready`. Only route traffic after readiness is
   HTTP 200 and reports a migrated schema.
7. Perform bounded smoke checks through the public origin: the selected
   manifest endpoint, the default curated profile, and one known-safe detail
   path. Confirm current suppression is effective and that community claims do
   not appear in default results. Do not save response bodies containing real
   records in incident tickets or CI logs.
8. Record the revision, release ID/profile, manifest digest, migration
   inventory digest, ledger revision/digest, readiness result, and operator
   decision in the restricted change record. These identifiers are operational
   metadata; they do not establish factual accuracy or legal compliance.

## Normal stop and graceful drain

Remove the instance from the load balancer, wait for in-flight requests to
finish according to the deployment platform's bounded drain period, and send
SIGTERM (Ctrl-C is supported for local operation). The Axum server emits
`server_stopping` and completes a graceful shutdown before emitting
`server_stopped`. If the process does not exit within the platform's limit,
capture only safe process diagnostics and use the platform's documented force
stop; investigate incomplete requests before re-enabling the instance.

Do not treat a stopped process as a rollback. A rollback still requires the
startup gate, current suppression replay, readiness, and smoke checks.

## Rollback

Use rollback when the new binary, schema, projection, configuration, or
external dependency causes an unsafe or materially broken public surface.

1. Remove the instance from traffic. For privacy or targeting exposure, also
   restrict the affected public capability immediately and notify the
   responsible maintainer; do not wait for a normal release cycle.
2. Preserve the safe operational record: revision, release/profile, manifest
   digest, ledger revision, timestamps, health status, and aggregate error
   metrics. Do not copy addresses, coordinates, source text, requester data,
   or response payloads into it.
3. If the database schema is backward-compatible, deploy the last validated
   image and its matching trusted manifest. If a database restore is required,
   restore into an isolated database first and follow the restore procedure
   below. Do not overwrite the only copy of a current database.
4. Replay the current restriction ledger, create a new matching snapshot, and
   run the startup gate. An old backup or old snapshot is not sufficient.
5. Start the prior release, wait for readiness, verify suppression across map,
   API, export, historical, cache, and reimport paths as applicable, then
   restore traffic gradually.
6. Record the unresolved cause and any incomplete propagation. A rollback
   does not recall independent third-party copies; request downstream
   corrections where appropriate.

## Backup

Backups are private recovery material, not public evidence or release
artifacts. Before scheduling a real backup, the maintainer must document the
provider, access controls, encryption, retention/deletion behavior, restore
owner, and legal/preservation review. This repository does not assert those
controls exist.

For each backup event, record only safe metadata in the operational record:
backup identifier, database/schema revision, creation time, byte size, checksum,
encryption/key reference, storage location reference, and verification result.
Keep the database backup, independent restriction ledger, current ledger
digest, release manifest, and manifest digest linked by identifiers. The
ledger must remain separately access-controlled; do not assume a database
backup contains the current suppression control plane.

Use a disposable synthetic database for rehearsal. A representative shape is:

```powershell
pg_dump --format=custom --no-owner --file=<private-backup>/uec-<backup-id>.dump <private-database-url>
Get-FileHash <private-backup>/uec-<backup-id>.dump -Algorithm SHA256
python pipeline/scripts/maintenance/replay-restriction-ledger.py `
  --database-url <private-restored-database-url> `
  --ledger <private-ledger>/current-ledger.json `
  --snapshot-output <restore-workspace>/restriction-snapshot.json
```

The commands above contain placeholders and must not be pasted with real
credentials into shared shells. Backup success is not restore success: run a
portless synthetic restore rehearsal and verify that the public projections
remain suppressed after reimport/rebuild.

## Restore

1. Stop public traffic and restore into a new isolated database or disposable
   clone. Keep the known-good public instance available until the restored
   target passes all gates.
2. Verify the backup checksum and provenance metadata. Apply the exact
   migration inventory expected by the image; stop on checksum mismatch.
3. Replay the latest independent restriction ledger into the restored
   database. Write a fresh row-free snapshot and validate revision, digest,
   and reference-set equality. Never use an old snapshot as proof of current
   suppression.
4. Run `private-environment-gate.py` with the restored snapshot and trusted
   manifest. A missing, malformed, duplicate, stale, or ambiguous reference
   fails closed.
5. Start the service with the matching image and verify live, ready, manifest,
   curated default, opt-in community separation, exports, caches, and any
   historical views. Confirm that current removal decisions survive the
   restore. Do not publish a replacement guessed location.
6. Cut traffic over only after an authorized maintainer records the result.
   Retain or delete restricted restore material according to the documented
   privacy/removal and preservation decision; do not make indefinite retention
   the default.

The executable synthetic drill is
`pipeline/tests/e2e/backup-restore.ps1`. It is a test-only recovery rehearsal,
not a production backup service or a claim that real data has been restored.

## Incident response

### Any availability or integrity incident

Take the affected instance out of traffic, capture bounded safe diagnostics,
and preserve the last known-good release. Check `/health/ready`, migration
state, manifest digest, restriction-ledger replay state, and aggregate
metrics. Do not fix a checksum mismatch by editing migration history or
silently falling back to a test release. If the cause is unresolved, keep the
affected publication stopped while eligible existing content remains only if
current restrictions still hold.

### Privacy, targeting, or suppression concern

Treat a credible exposure as urgent suppression. Restrict the affected map,
API, export, preview, cache, historical, and reimport paths first, then assign
the responsible maintainer and a restricted case ID. Do not put the exposed
address, coordinate, worker/resident detail, requester identity, or private
evidence in a public issue, commit, log, or chat transcript. Rebuild affected
projections and verify suppression before reopening. Follow the removal and
correction process in `docs/ETHICS.md`; assess preservation obligations before
exceptional deletion and seek qualified legal advice for legal demands.

### Source or release integrity concern

Quarantine the candidate/release, preserve original source artifacts only as
permitted, and compare source/retrieval metadata, transformation/configuration
versions, manifest checksums, and validation reports. Do not infer closure from
source disappearance. No acquisition result or automated diagnostic grants
publication approval.

## Fresh-machine setup

1. Clone a clean checkout and read `docs/ETHICS.md`,
   `docs/ETHICS-SUMMARY.md`, and `docs/development.md`.
2. Install the pinned toolchain prerequisites: Rust/Cargo, Python 3, Node/npm,
   and Docker only if using the local V2 database. On Windows, install
   PowerShell as required by the local scripts.
3. Run `python scripts/dev.py --json doctor`. Treat unknown port occupants,
   missing dependencies, and unavailable Docker as environment failures; do
   not stop unknown processes.
4. Run `cargo build --locked` and `npm ci`. Run the focused Rust, pipeline,
   and static tests before changing configuration.
5. For local UI work, use the fixture preview. For local database work, use
   `python scripts/dev.py up`, then `python scripts/dev.py probe` and the
   documented local E2E checks. Local fixtures are disposable and never
   publication evidence.
6. For a production-shaped dry run, supply synthetic private ledger,
   snapshot, and manifest files to the private gate. Keep all real source
   artifacts and credentials outside the checkout.

## Diagnostics contract

`/health/live` is a process liveness check. `/health/ready` is the traffic gate
and fails when the database is absent, unreachable, or missing required
relations/columns. `/health/diagnostics` is an aggregate operational view. It
may report runtime mode, configured/not-configured state, control-gate status,
response classes, rate-limit counts, and bounded latency totals/maxima.

Diagnostics intentionally excludes URLs, paths, query strings, request
payloads, response bodies, IPs, forwarded headers, facility IDs, source rows,
restriction references, and secrets. Metrics live only for the process
lifetime and are not visitor analytics. Do not attach them to a log sink that
adds the excluded fields or invents a retention period. Current logs also emit
an allowlisted route class and bounded status/latency event; this does not
prove that a hosting provider, proxy, CDN, or error service retains nothing.

There is no configured backup reviewer, legal service, publication guarantee,
response SLA, anonymity guarantee, or production capacity claim in this
runbook. Those remain explicit deployment decisions and policy obligations.

## Selected public-serving package rehearsal (local only)

`pipeline/scripts/maintenance/prepare-release-serving-package.py` prepares a
selected-column package for one already-approved public release. It is a local
restore rehearsal, not a publication command, backup format, or authorization
to copy a private database to a host. The source database is read-only; use an
empty isolated target only. The helper refuses a package whose manifest or any
individual binary `COPY` payload has a different SHA-256 or byte count before
opening the target connection. It also copies the source migration ledger
first and checks its canonical inventory digest before any other package data.

The target schema must be derived from the same verified migrated source, in
the following order: create `postgis` in `public` and `pgcrypto`; restore the
schema's pre-data archive; create `pg_trgm` in `uec`; run the selected-column
package restore; then restore the filtered post-data archive. Record SHA-256
for both schema archives with the package using repeated `--schema-artifact
NAME=SHA256` arguments. The serving derivative excludes exactly these two
private acquisition-preview callbacks from post-data restoration:

- `uec.geocode_results.aaa_aphis_mailing_locality_geoapify_display`
- `uec.geocode_results.geocode_results_geoapify_preview_display`

They depend on the private `real_preview` acquisition/geocoder schema and are
not public eligibility, restriction, review, or cache-generation gates. Do
not omit any other constraint, index, trigger, or function without a separate
review. The package manifest records both exclusions and schema-archive hashes.

For a rehearsal, export and restore with environment-held connection strings
only; do not put a credential in shell history, a command argument, or a log:

```text
prepare-release-serving-package.py export --source-database-url-env UEC_SOURCE_URL \
  --release-id <approved-release> --migration-inventory-sha256 <ledger-sha256> \
  --schema-artifact pre_data=<sha256> --schema-artifact post_data=<sha256> --output <empty-package-dir>
prepare-release-serving-package.py restore --target-database-url-env UEC_TARGET_URL \
  --package <package-dir> --apply-api-grants
```

After post-data restoration, run `ANALYZE` in the isolated serving database to
refresh planner statistics, then verify all restored constraints and public gate
triggers are enabled, the release's manifest/read-model/public-detail aggregate
hashes match the source, and the runtime role can read only the explicit public
handler relations. Run the real-V0 API acceptance against the isolated target:
manifest, list/detail, map (including conditional ETag), CSV, history, graph
(`200` with the truthful empty V0 graph), and negative private-route checks.
Reapply the current restriction ledger before any serving decision; never use
the package as permission to ignore a later suppression.

## Render preparation (not a deployment instruction)

This is the bounded hosting shape approved for later operator use: one paid
Render Docker web service running this binary and the approved Svelte build on
the same origin, plus one paid Render Postgres database with PostGIS. It does
not authorize creating a Render account, database, service, custom domain,
backup job, disk, scheduled job, or external storage bucket. Acquisition,
source refresh, raw evidence, geocoding queries/responses, and private preview
remain outside the public host. Do not add Redis, a worker, Kubernetes, or a
second public framework to this deployment.

The repository Dockerfile has three locked-input stages: `npm ci` against
`frontend/package-lock.json`, `cargo build --release --locked` against
`Cargo.lock`, and a minimal runtime containing only `uec-api` and the public
Svelte `dist/` output. The operator must record the immutable pushed-image
digest with the exact repository revision before a deploy; exact image tags do
not replace recording that digest. Render builds Docker images with BuildKit;
do not declare or consume a build argument for any secret.

Render web-service settings to enter after an authorized account exists:

| Setting | Required value / decision |
| --- | --- |
| Service type | Docker web service; use the repository Dockerfile and its `CMD`. |
| Health check | `/health/ready` (not liveness): Render accepts HTTP 2xx/3xx, and this endpoint refuses traffic until the database schema is present. |
| Port | Leave `PORT` supplied by Render; the application binds `0.0.0.0` in production. |
| Region | Oregon, selected by the maintainer for both the web service and database. |
| Public origin / CORS | Set `UEC_CORS_ORIGINS` to the final exact `https://` public origin(s), no wildcard and no path. Same-origin browser API use needs no extra origin. |
| Proxy trust | Start with `UEC_TRUST_PROXY=false` and omit `UEC_TRUSTED_PROXY_CIDRS`. Enable it only after Render supplies a stable, verified proxy CIDR boundary that is recorded in the restricted change record; never use a wildcard or guessed range. |
| Filesystem | Treat it as ephemeral. Do not attach a persistent disk for release artifacts or the ledger; it is not an independent backup. |
| Auto-deploy / previews | Keep disabled until an authorized maintainer accepts the explicit release procedure. No preview environment receives production controls or data. |

Required runtime variables are the values in the configuration preflight above,
including `UEC_RUNTIME_MODE=production`, the read-only serving-role Render
Postgres connection string in `UEC_DATABASE_URL`, exact `UEC_CORS_ORIGINS`, and the
explicit proxy setting. If contribution intake is approved, add the independent
restricted community-role URL and community controls above; do not reuse the
serving-role credential. Do not set `UEC_DEV_PREVIEW`,
`UEC_DEV_PREVIEW_TOKEN`, `UEC_TEST_RELEASE_ID`, `UEC_TEST_RELEASE_TOKEN`,
acquisition credentials, or geocoder credentials on the web service.

The first verified cloud database connection uses the external endpoint with
TLS certificate verification. Prefer internal routing once its connection and
TLS behavior have been tested with the production client; do not silently
disable certificate checks or substitute the administrative database account.

Supply these control-plane files as Render secret files, never in the image,
repository, Docker build arguments, or browser bundle. At runtime Render
mounts secret files under `/etc/secrets/`; use exactly these variable/path
pairs:

| Secret-file name | Runtime variable | Purpose |
| --- | --- | --- |
| `uec-current-restriction-ledger.json` | `UEC_RESTRICTION_LEDGER_PATH=/etc/secrets/uec-current-restriction-ledger.json` | Current independent opaque restriction ledger. |
| `uec-restored-restriction-snapshot.json` | `UEC_RESTORED_RESTRICTION_SNAPSHOT_PATH=/etc/secrets/uec-restored-restriction-snapshot.json` | Fresh, row-free post-replay snapshot. |
| `uec-release-manifest.json` | `UEC_RELEASE_MANIFEST_PATH=/etc/secrets/uec-release-manifest.json` | Trusted serving-release manifest. |

Set `UEC_RELEASE_MANIFEST_SHA256` from the separately verified lowercase
SHA-256 digest. The startup gate requires the ledger and snapshot to be
different files and fails closed on mismatch. Render's secret-file limits and
permissions must be checked by the operator before use. The Docker runtime
user is deliberately a member of group ID 1000, which is the documented
Render Docker secret-file access group; if a supplied file is still unreadable,
stop rather than copying it into an image or a world-readable directory.

Create PostGIS with the selected Render Postgres major version and exercise
the repository migrations on an isolated target first. Render supports
`postgis` on supported PostgreSQL versions, but support does not prove this
schema or its extensions can migrate. The serving-package helper carries the
committed least-privilege rehearsal inventory: the API role receives schema
`USAGE` and `SELECT` only on named handler/read-model, restriction/review,
lifecycle, and taxonomy relations; it has no blanket table, sequence,
source-record, raw-artifact, or write privilege. Migrations and release
operations use separate credentials and are not supplied to the web service.
A successful rehearsal checks that inventory, but it is not production
deployment approval.

For recovery, Render paid Postgres PITR is supplementary only (Hobby: three
days; Pro or higher: seven days) and restores to a new database. Do not create
the optional Render backup cron job without separate authorization. The
existing synthetic restore/replay drill remains the required local rehearsal:
restore into an isolated target, replay the current independent ledger, write
a new snapshot, pass the private-environment gate, then run cold and warm
browser checks plus the negative public-route checks. Rollback selects the
previous Render deployment/image only after the same current-ledger replay and
readiness checks; it never reenables a legacy V1 route.

Current primary references: [Render Docker services](https://render.com/docs/docker),
[web-service health checks](https://render.com/docs/health-checks),
[environment variables and secret files](https://render.com/docs/configure-environment-variables),
[Render Postgres extensions](https://render.com/docs/postgresql-extensions),
[Render Postgres recovery](https://render.com/docs/postgresql-backups),
[persistent disks](https://render.com/docs/disks), and
[Render pricing](https://render.com/pricing). These describe platform
capabilities and prices that an operator must recheck at purchase time; they
do not constitute an account configuration or cost approval.
