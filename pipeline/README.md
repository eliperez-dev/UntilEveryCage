# Until Every Cage data pipeline

Acquisition, retention, geocoding, and release work follow [docs/ETHICS.md](../docs/ETHICS.md). Append-only history is the ordinary rule, with controlled privacy/removal exceptions. Government origin and successful validation do not certify truth or grant publication permission. Outstanding protections are tracked in the [policy checklist](../docs/governance/policy-implementation-todo.md); this README is not evidence that they are implemented.

This directory is the local-development home for V2 ingestion code. Acquired and generated data lives under the repository-level `data/` directory. The current application data remains unchanged while the pipeline is being established.

New contributors should start with [pipeline/ONBOARDING.md](ONBOARDING.md),
which provides the safe fixture-first test path and explains the boundary
between private staging, release validation, and public publication.

## First operation

Run the manifest generator from the repository root:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File pipeline/scripts/maintenance/build-legacy-manifest.ps1
```

It writes `data/manifests/legacy-files.csv` with one row per legacy input,
including byte size, SHA-256 checksum, relative path, and generated-at time.
It also writes the metadata-only `data/manifests/legacy-status.json` ledger,
which records artifact/integrity state, unknown lineage/currentness, and
whether a checked-in artifact has entered the V2 database. The current ledger
is intentionally conservative: checked-in V1-era artifacts are
`metadata_only_not_migrated`, not V2 database rows. The generated timestamp
records when this inventory was made; it is not an assertion about when the
source data was current.

## Controlled Denmark acquisition

The canonical Denmark launcher is
`pipeline/sources/denmark/run-denmark-pipeline.py`. It archives an artifact
only; it never imports, validates for publication, promotes a release, or
alters application data. Network retrieval is intentionally opt-in and
requires an operator-authored terms review JSON with `reviewer`, `reference`,
`reviewed_at`, `decision: "approved"`, and `notes`.

```powershell
python pipeline/scripts/stages/acquire-denmark-smiley.py --fetch --terms-review <operator-approved-terms-review.json>
```

Raw XML and its deterministic `acquisition-metadata.json` are written under
ignored `data/raw/dk.smiley/<run-id>/`. For offline development, use
`--local-file path/to/synthetic.xml`; it needs no terms review and records that
distinction. Existing staging runs can continue to take an already archived
local XML path. Database import and release promotion remain separate
commands. The historical `pipeline/run-denmark-pipeline.py` wrapper remains
available for one release as a deprecated compatibility path.

## Status vocabulary

- `legacy`: checked-in historical data preserved for migration.
- `source_candidate`: the upstream source still needs live verification.
- `derived`: generated from another local file and not an independent upstream source.
- `unknown`: provenance not established yet.

The first adapter should be built only after one `source_candidate` has been downloaded and inspected as a current artifact.

The development geocoder is configured in `config/geocoding-dev.json`. DAWA is temporary and must be reevaluated before production.

The required interpreter is pinned in `.python-version`, and third-party packages are pinned exactly in `requirements.txt`.

Database migrations are applied in filename order by `scripts/maintenance/apply-migrations.py`. The runner records each migration's SHA-256 in `uec.schema_migrations`, refuses a changed migration after application, and applies each new migration transactionally. `002_geocode_job_events.sql` upgrades an existing local database with append-only geocoding jobs and events without resetting the database. A clean database is the certified deployment baseline; existing databases must be assessed before adopting the ledger.

`003_read_only_map_projection.sql` adds `uec.map_facilities_current`, a derived view that exposes only default-visible observations with accepted coordinates. It does not update source records or observations.

It also adds `uec.map_facilities_release`, which includes release identity and status so public callers can require a validated or promoted release explicitly.

Validate a candidate release without changing it:

```powershell
python pipeline/scripts/stages/validate-release.py dk-2026-09-13-candidate --expected-records 58776
```

Add `--mark-validated` only after reviewing the passing report. Promotion remains a separate explicit operation.

For a readable review artifact, add `--html-output data/reports/denmark-release-review.html`. The public application should query `uec.map_facilities_public`, which only returns the explicitly promoted release.

Migration `005_coarse_location_display.sql` adds the city-reference table and `uec.map_facilities_display`. City-level fallbacks are used only when a maintained city reference exists; missing references remain unmapped rather than guessed.

Promote only after validation and final maintainer review:

```powershell
python pipeline/scripts/stages/promote-release.py <validated-release-id>
```

Script organization and execution conventions are documented in `scripts/README.md`.

## Single-command staging run

The orchestrator runs the auditable stages in order and leaves database import as an explicit separate action:

```powershell
python pipeline/sources/denmark/run-denmark-pipeline.py data/raw/denmark-smiley/<run>/Smileydata.xml
```

Add `--geocode-limit 100` to run a bounded DAWA development sample. Every run gets numbered stage directories and a `pipeline-manifest.json` containing output sizes and SHA-256 checksums.

## Restricted run comparison

The shared `common/delta.py` comparison is private and aggregate-only: it retains
both run manifests and fingerprints, classifies added/changed/not-observed/suppressed
counts, blocks schema changes, and never interprets source absence as closure. Failed
or partial comparisons retain the prior eligible release reference and expose no
public surface. Terms, privacy/safety, suppression, review, project approval, and
publication remain separate gates.

## Private-alpha source operations

The shared operational layer in `common/source_operations.py` adds the
schedule/freshness inventory in `source_operations.json`, content-addressed raw
artifact deduplication, append-only run history, row-free review packets and
release diffs, bounded acquisition retry classification, and local failure
notification hooks. See [the source operations contract](../docs/architecture/source-operations.md).

Every operational record preserves the prior eligible release reference and
keeps `release_promoted` false. A changed artifact, unchanged rerun, failed
attempt, or review-required result is recorded as a new event; no run overwrites
earlier evidence. The health index is private operational evidence only.

## Small reviewed demonstration release

The bounded real-data demonstration lane is documented in
[`docs/reviewed-demonstration-release.md`](../docs/reviewed-demonstration-release.md).
Use `prepare-demonstration-release.py` to copy at most 25 already-ready,
opaque-ID-selected observations from a private candidate into a new candidate,
then use `record-demonstration-review.py` for an explicit release-scoped
maintainer review. Neither command promotes or publishes. The current Denmark
source remains blocked until terms, coverage, privacy, precision, and project
approval are actually reviewed; do not create a review document that claims
those decisions without an authorized maintainer's evidence.
