# Background geocoder sprint lane ledger

This ledger prevents completed work from being mistaken for active work or
being omitted from consolidation. It records implementation state only; no
entry grants publication approval or authorizes live provider calls.

## Ready for consolidation or recovery

| Lane | Evidence | State | Required consolidation action |
| --- | --- | --- | --- |
| Private operator review console | `b74c1a36` | committed, not in `eli/front-end-overhaul` | review and cherry-pick; rerun frontend, Python, Rust, and browser checks |
| Country geocoding reconnaissance | `7dc7fd0a` | committed, not in `eli/front-end-overhaul` | review and cherry-pick provider profiles/schema; resolve overlap with hosted-provider implementation |
| Geoapify adapter | integration worktree changes | implemented locally, focused tests pass, uncommitted | combine with adversarial adapter changes and commit |
| Geocoder adversarial tests | agent worktree at `2f796b1` | tests and narrow DAWA fixes complete; commit blocked by worktree Git metadata permissions | recover patch, review, commit, and run database E2E |

## In flight

| Lane | Scope | Exit requirement |
| --- | --- | --- |
| Durable worker | concurrency-safe leasing, stale recovery, retry and daily budget, suppression race protection | committed changes plus focused and database-backed tests |
| Geocoder operator tooling | aggregate status/ETA, safe logs, secret configuration, local/container background operation | committed changes plus privacy tests and operator documentation |

## Consolidation gate

1. Every lane is represented by a reviewed commit or explicitly rejected.
2. No API key, address, query, provider payload, or private identifier appears
   in repository fixtures, diagnostics, or logs.
3. No live geocoder call occurs in tests or consolidation.
4. Suppression is checked before and after provider work, stale leases recover,
   concurrent workers do not duplicate requests, and quota exhaustion pauses
   safely.
5. A successful geocode cannot create privacy approval, publication approval,
   release membership, or graph certainty.
6. Focused geocoder tests, database E2E, standard gate, frontend tests, and the
   Docker E2E suite pass on the consolidated branch.
7. The branch is clean before a checkpoint push and human CI review.
