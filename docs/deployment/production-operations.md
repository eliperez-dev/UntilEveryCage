# Production operations runbook

Status: production-shaped procedure for a future deployment. This document is
not evidence that the service is hosted, that a reviewer is staffed, or that
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
