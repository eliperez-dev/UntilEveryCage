# Private source-health contract

`source_health.build_health_snapshot` and
`pipeline/scripts/diagnostics/build-source-health.py` combine one private run's
`manifest.json`, `qa.json`, and `run-status.json`, with optional importer
evidence, into a deterministic `SourceHealthSnapshot` v1.

The snapshot is aggregate metadata only. It records provenance, freshness,
effective-date uncertainty, row counts, drift alarms, quarantines,
`not-observed` deltas, and private importer/idempotency counts. It contains no
source values, raw fields, addresses, coordinates, or record rows.

Health states are deliberately conservative: `not-run`, `blocked`, `failed`,
`degraded`, and `private-validated`. `private-validated` means only that the
supplied private evidence passed this contract; it is not a claim of current,
complete, accurate, approved, or publishable data. Every snapshot has
`public_exposure: false` and `publication_eligibility: blocked`.

Build a snapshot with a fixed timestamp when reproducibility matters:

```powershell
python pipeline/scripts/diagnostics/build-source-health.py `
  --run-dir data/restricted/example/run `
  --output data/reports/source-health/example.json `
  --as-of-utc 2026-09-15T00:00:00Z
```

Missing or inconsistent evidence, a promoted release, a public import flag, or
privacy-bearing fields fail closed and leave no output snapshot. This command
does not acquire data, alter `docs/source-status.json`, promote a release, or
make a public health claim.
