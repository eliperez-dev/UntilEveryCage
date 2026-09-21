# Disposable candidate import

`pipeline/scripts/maintenance/import-candidate.py` is a private development
handoff from a validated adapter staging run into PostgreSQL. It is not a
release or publication command.

Run it only against a disposable local database with an explicit acknowledgement:

```powershell
python pipeline/scripts/maintenance/import-candidate.py `
  --manifest data/staging/<source>/<run>/manifest.json `
  --normalized data/staging/<source>/<run>/normalized/records.jsonl `
  --raw data/staging/<source>/<run>/raw/source-artifact.bin `
  --release-id candidate-<source>-<run> `
  --database-url postgresql://uec:...@127.0.0.1:5433/uec `
  --disposable-db
```

The command refuses a missing acknowledgement, non-loopback host, default
PostgreSQL port, non-UEC database name, non-candidate release ID, mismatched
normalized/raw hash/count, or a manifest that is already released. In addition,
the connected server must contain the exact `uec.disposable_import_guard` marker
installed by `docker-compose.e2e.yml`, matching both `current_database()` and
`current_user`; the CLI flag alone never authorizes writes. `--reset` is
also refused because evidence and release membership are append-only. To
rebuild, stop the local stack and recreate its disposable volume using the
existing local maintenance recipe, after checking retention obligations.

The transaction records artifact and acquisition provenance, source records,
facilities, candidate observations, candidate release membership, and an
append-only pending publication review event. Every imported observation starts
with `default_visible=false`, `classification_review_status=review_required`,
`coordinate_review_status=review_required`, `privacy_screening_status=pending`,
`maintainer_approval=pending`, and `publication_eligible=false`. The importer
never creates geocode approval, privacy clearance, validation, promotion, or
public visibility. Rerunning the same staging run is idempotent for source
records and release membership.

Raw artifacts are retained outside Git and only their metadata is stored in the
database. `source_values` are private evidence and are never selected by the
public API or development preview. Docker-backed E2E remains a CI requirement;
local Windows runs must report the Docker Desktop access-denied condition rather
than claiming an end-to-end pass.
