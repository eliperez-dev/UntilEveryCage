# V2 synthetic API load rehearsal

This is a bounded, local, synthetic rehearsal of the V2 API. It is not a
production capacity claim. Each run creates a fresh disposable PostGIS E2E
environment, applies every migration, seeds only deterministic synthetic
records, exercises the API and graph read paths, and destroys the environment.
The report contains aggregate counters and latency percentiles only; raw rows,
coordinates, identifiers, and response bodies are not retained in Git.

## Reproduction

Install the pinned Python dependencies, then run:

```powershell
python pipeline/scripts/benchmarks/run_api_load_rehearsal.py `
  --observations 5000 `
  --concurrency 1,4,8,16 `
  --requests-per-level 10 `
  --timeout-ms 2000 `
  --json-output .tmp/api-load-5000.json

python pipeline/scripts/benchmarks/run_api_load_rehearsal.py `
  --observations 25000 `
  --concurrency 1,4,8,16 `
  --requests-per-level 10 `
  --timeout-ms 2000 `
  --json-output .tmp/api-load-25000.json
```

The runner bounds observations at 25,000, concurrency at 16, and requests per
level at 80. It refuses non-loopback API targets. The 25,000-row bound is an
explicitly finite synthetic safety limit, not a statement about supported
production scale.

## Captured evidence (2026-09-16)

| Synthetic observations | Concurrency | Requests | Successes | Timeouts | 5xx | Throughput (rps) | p50 / p95 / p99 (ms) | Max active / waiting DB sessions |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 5,000 | 1 | 10 | 4 | 6 | 0 | 0.622 | 2013.251 / 2028.338 / 2028.338 | 2 / 1 |
| 5,000 | 4 | 10 | 3 | 7 | 0 | 1.981 | 2001.908 / 2029.853 / 2029.853 | 2 / 0 |
| 5,000 | 8 | 10 | 4 | 6 | 0 | 3.982 | 2013.191 / 2017.044 / 2017.044 | 6 / 1 |
| 5,000 | 16 | 10 | 2 | 8 | 0 | 4.953 | 2009.559 / 2011.767 / 2011.767 | 9 / 1 |
| 25,000 | 1 | 10 | 1 | 9 | 0 | 0.514 | 2016.681 / 2029.881 / 2029.881 | 2 / 1 |
| 25,000 | 4 | 10 | 1 | 9 | 0 | 1.653 | 2012.612 / 2025.954 / 2025.954 | 2 / 1 |
| 25,000 | 8 | 10 | 2 | 8 | 0 | 2.547 | 2007.124 / 2030.413 / 2030.413 | 6 / 2 |
| 25,000 | 16 | 10 | 1 | 9 | 0 | 4.482 | 2004.377 / 2024.087 / 2024.087 | 10 / 3 |

No tested level was clean under the harness definition (zero timeout, server,
or connection errors). The result supports keeping API pool sizing and
production capacity claims blocked until an approved representative load
model is available. It also confirms that the failure mode in this local
rehearsal is timeout pressure rather than HTTP 5xx or connection exhaustion.

The dominant slow path remains the live eligibility/summary work documented in
`v2-public-projection-read-path.md`. The evidence does not justify caching,
relaxing current suppression checks, or claiming production readiness.

## Data and ethics boundary

The fixture uses only synthetic source, facility, observation, graph, and
geocode-shaped records. The API harness reads response bodies to completion
and immediately discards them. JSON outputs belong under `.tmp/`, which is
ignored. Do not copy raw or private rows, coordinates, source paths, or
identifiers into reports, logs, backups, or commits.
