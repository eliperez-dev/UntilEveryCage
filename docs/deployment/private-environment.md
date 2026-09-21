# Private environment and recovery gate

Status: implemented as a production-shaped, private-only control. It has not
been deployed, and it is not publication approval. The only publication
operator remains the authorized project maintainer; this repository does not
appoint a backup reviewer, assert legal coverage, or claim staffing capacity.

## Control-plane boundary

The current restriction ledger is an independently stored, durable JSON
control-plane artifact. It is not inside a PostgreSQL backup and must be kept
on a separately access-controlled/retained volume or object-store key. The
ledger contains only opaque `source_id`, `source_record_key`, `scope`, and
`action: suppress` references. It must not contain names, addresses,
coordinates, requester details, source text, or a copy of restricted evidence.

A restore snapshot is produced from the restored database after replay. The
service-start gate requires the ledger and snapshot to be different files and
requires matching revision, digest, and reference sets. An old backup therefore
cannot serve until the current ledger has been replayed successfully. Missing,
stale, malformed, duplicated, or ambiguous references fail closed.

Production-shaped startup also requires a trusted release manifest and its
trusted lowercase SHA-256 reference. The manifest is versioned and includes a
declared distributed-artifact inventory. Checksums detect alteration relative
to a trusted reference; they do not prove factual accuracy, privacy
eligibility, or source correctness. Release signing is not claimed.

## Required production configuration

The Rust service validates these before binding its listener:

```text
UEC_RUNTIME_MODE=production
UEC_DATABASE_URL=<private database URL>
UEC_CORS_ORIGINS=https://<verified-public-origin>
UEC_TRUST_PROXY=true|false
UEC_TRUSTED_PROXY_CIDRS=<only the reverse-proxy networks, when trust is true>
UEC_RESTRICTION_LEDGER_PATH=<separate private mount>/current-ledger.json
UEC_RESTORED_RESTRICTION_SNAPSHOT_PATH=<restore workspace>/restriction-snapshot.json
UEC_RELEASE_MANIFEST_PATH=<trusted release mount>/manifest.json
UEC_RELEASE_MANIFEST_SHA256=<64 lowercase hex characters>
```

`UEC_TRUST_PROXY` is explicit in production. If enabled, forwarded addresses
are accepted only from peers inside `UEC_TRUSTED_PROXY_CIDRS`; a forwarded
header from any other peer is ignored and the socket peer remains the rate-limit
key. Wildcard CORS origins, malformed origins, missing proxy boundaries, and
unexpected boolean values are rejected.

The diagnostics endpoint (`/health/diagnostics`) reports only status, counts,
mode, and control names. It does not report URLs, paths, request data,
forwarded addresses, source rows, or restriction references. Readiness remains
separate from liveness and continues to fail when the required schema is not
migrated.

## Recovery rehearsal

Use synthetic fixtures only. The portless drill in
[`pipeline/tests/e2e/backup-restore.ps1`](../../pipeline/tests/e2e/backup-restore.ps1)
performs this order:

1. Apply every migration to an isolated PostGIS container and seed a promoted
   synthetic release.
2. Take a custom-format backup while the record is eligible.
3. Apply a later synthetic suppression and verify public projections exclude
   the record.
4. Roll back to the older backup. The stale snapshot is rejected before a
   service can start.
5. Validate the independent current ledger, replay it with
   [`replay-restriction-ledger.py`](../../pipeline/scripts/maintenance/replay-restriction-ledger.py),
   write a row-free post-replay snapshot, and verify both map projections
   remain suppressed. The private recovery command is:

   ```powershell
   python pipeline/scripts/maintenance/replay-restriction-ledger.py `
     --database-url <private-restored-database-url> `
     --ledger <private-ledger>/current-ledger.json `
     --snapshot-output <restore-workspace>/restriction-snapshot.json
   ```
6. Run the startup/deployment gate only after replay. Any failed migration,
   incomplete replay, manifest mismatch, or unsafe proxy configuration leaves
   the service stopped.

The replay is append-only and idempotent. It is not a substitute for the
ordinary suppression case workflow or for a maintainer's decision to lift a
restriction. A lift must remain an explicit, separately recorded decision.

## Clean-checkout/deployment check

From a clean checkout, the operator/deployment job should run the gate with
the independently mounted ledger, post-restore snapshot, and trusted manifest:

```powershell
$env:UEC_RUNTIME_MODE = "production"
$env:UEC_DATABASE_URL = "postgresql://redacted.invalid/uec"
$env:UEC_CORS_ORIGINS = "https://verified.example"
$env:UEC_TRUST_PROXY = "false"
python pipeline/scripts/maintenance/private-environment-gate.py `
  --repository . `
  --ledger <private-ledger>/current-ledger.json `
  --snapshot <restore-workspace>/restriction-snapshot.json `
  --manifest <release>/manifest.json `
  --manifest-sha256 <trusted-digest> `
  --clean-checkout
```

The example URL and origin are placeholders, not deployment values. The gate
does not fetch data, promote a release, or publish anything. It validates the
migration inventory, runtime configuration, replay state, and manifest, and
prints only safe metadata.

## Verification record

- Hosted CI status at checkpoint `a4f9930`: **user-reported green**. This is a
  record of the supplied report, not an independently inspected job result or
  a claim about this follow-up commit.
- This lane's focused evidence: Rust binary tests, Python private-gate tests,
  and the synthetic portless backup/restore/replay drill when Docker is
  available.
- No deployment, publication, real-data acquisition, or real requester data
  handling is part of this change.
