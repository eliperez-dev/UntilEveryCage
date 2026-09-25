# Private geocoding worker

The worker drains already queued `uec.geocode_jobs` rows for one provider. It is
an operator tool for bounded private runs; it does not publish a release and it
does not make provider terms, privacy, or human review decisions.

## Durable lifecycle

Each job claim commits a `started` event and a random lease token before any
provider work. The provider call happens outside a database transaction. Every
attempt, including retries, first commits a row in
`uec.geocode_request_reservations` and increments the shared
`uec.geocode_provider_budgets` counter for the UTC provider day. The reservation
is therefore conservative if a process dies after sending a request. A result
transaction rechecks the restriction table and the latest lease token before
writing the result and terminal event. An expired worker can finish its network
call, but its stale result is discarded when another worker has taken the lease.

Previous result rows are append-only and remain available when a worker is
interrupted. A restarted worker can reclaim a `started` event after
`--lease-timeout`; an external request is not claimed to be exactly once.

If the shared provider interval is occupied, the worker does not spin or spend
one of the provider retry slots. It appends a retryable `failed` event with a
`provider_rate_limited` reason and a future `next_attempt_at`, then moves on.
Daily allowance exhaustion is recorded the same way with a next-day retry time.
The latest event is therefore always an inspectable deferred outcome rather
than an unbounded `started` lease.

## Bounded private run

Apply migrations in the disposable database, enqueue jobs through the existing
enqueue stage, then run a finite image/container with explicit values. The
worker logs provider and aggregate status only; it must not log a query,
source-record ID, address, provider response, or credential.

```text
UEC_DATABASE_URL=postgresql://... \
docker compose -f docker-compose.pipeline.yml run --rm \
  -e UEC_DATABASE_URL \
  worker --provider dawa --limit 100 --daily-budget 100 \
  --retries 3 --lease-timeout 900 --provider-interval 1
```

The worker image is built from `Dockerfile.worker` and installs only the pinned
`pipeline/worker-requirements.txt`. The shared Compose service and build-context
exclusions are owned by the integration lane; keep synthetic queues and fake
providers in disposable test projects. Never point this command at retained
production-like volumes during testing.

## Recovery checks

For an operator rehearsal, pause a synthetic provider and query
`geocode_job_events` from a second database connection: the `started` row must
be visible before the call returns. Kill the worker and confirm earlier result
rows and their events remain. Start a second worker with a short lease timeout,
then confirm its terminal event has a different lease token and a late first
worker cannot append a result. Run two workers against one remaining daily
reservation and inspect the reservation ledger: at most one provider call is
allowed. Retryable outcomes create one reservation per retry.

Rows in the reservation ledger and worker events are private operational
evidence. Reports and logs should contain aggregate counts and status only.

## Real-preview separation

`python scripts/real_preview.py refresh --source ID` ends after acquisition,
classification, and private candidate import. It does not call a geocoder or
wait for enrichment. Source adapters may provide a separate normalized
candidate handoff with `candidate_id`, `snapshot_sha256`, `source_id`,
`source_record_key`, and eligibility (`coarse` or `exact`). A restricted
`normalized_query` is required only when a reviewed source/provider privacy
profile permits external submission. Raw source rows and addresses are not
valid handoff fields. Preview-target provider submission remains fail-closed
until that profile and the shared worker target bridge are implemented.

The shared schema links preview candidates to the existing durable geocode job
machinery; it does not add another lease, retry, or provider budget
implementation. Candidate state is append-only and current state is mutually
exclusive in `real_preview.candidate_enrichment_reconciliation`. Use
`python pipeline/scripts/diagnostics/real-preview-enrichment-status.py` for
aggregate state/reason counts only. It emits no candidate IDs, queries, or
provider evidence.

The importer initializes source-coordinate, local coarse-reference, or
insufficient states. Local reference geometry remains approximate. The schema
provides a place for later provider-derived display evidence with provenance
and `pending_human_review`; it cannot create release or publication membership.
Exact-provider submissions for preview candidates remain disabled until the
relevant source/provider privacy profile is explicitly authorized and the
worker bridge is added.
