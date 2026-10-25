# Offline geospatial diagnostics

`pipeline/scripts/diagnostics/current_geospatial_readiness.py` reads authorized
candidate handoffs listed by a supplied aggregate manifest. It does not call
a geocoder, modify a database or publish a release.

```powershell
python pipeline/scripts/diagnostics/current_geospatial_readiness.py --help
```

Supply `--manifest`, `--root`, `--output` and `--as-of` explicitly.
The historical `data/manifests/current-reacquisition-2026-09-16.json` is one
possible retained input, not the current source inventory.
Unavailable private handoffs are reported as unavailable, not zero.

The report separates mutually exclusive display states (exact, city, unmapped,
restricted) from overlapping evidence states (source coordinates, accepted
geocoder results, unresolved source evidence). It never overwrites one with
the other. A source coordinate retained in private values but not exposed is
counted separately from an eligible displayed point. Invalid coordinates are
not silently repaired. Whole-record restrictions and held coordinate fields
are distinct counts; risk indicators are not residential classifications.

Reports contain source IDs, counts, hashes and aggregate metrics, not names,
addresses, coordinates, native identifiers or geocoder queries/responses.
Valid ranges/decimal precision do not prove real-world positional accuracy.

The related `pipeline/scripts/diagnostics/geospatial_readiness_audit.py`
supports separate legacy V1 and private V2 funnels. Use its `--help` and
explicit input/output scope; never combine V1 rows with fresh V2 counts.
A geocoding result is separate evidence, not publication approval.

For the current queue, providers, usage and eligibility use
[the worker guide](geocoding-worker.md) and
[async enrichment contract](async-location-enrichment-contract.md).
For current source coverage use [source-status.json](source-status.json).
This diagnostic reference is not a provider registry or another status ledger.
