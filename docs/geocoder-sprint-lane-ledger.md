# Background geocoder sprint lane ledger

This ledger prevents completed work from being mistaken for active work or
being omitted from consolidation. It records implementation state only; no
entry grants publication approval or authorizes live provider calls.

## Consolidated and focused-tested

| Lane | Evidence | State | Required consolidation action |
| --- | --- | --- | --- |
| Private operator review console | `316d549b`, `88422957`, `898fe019` | consolidated; frontend and focused Python tests pass | include in full consolidation gate |
| Country geocoding reconnaissance | `6367a176` | consolidated; profile/schema tests pass | include in full consolidation gate |
| Geoapify adapter and adversarial provider hardening | `d1ba77d2` | consolidated; 16 adapter/import tests pass | run database E2E and full consolidation gate |
| Durable worker | pending checkpoint commit | transactional claims, stale recovery, budgets, bounded attempts and suppression recheck implemented; seven Docker E2E tests pass | include in full consolidation gate |

## In flight

| Lane | Scope | Exit requirement |
| --- | --- | --- |
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
