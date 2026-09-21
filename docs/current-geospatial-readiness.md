# Current-corpus geospatial readiness

`pipeline/scripts/diagnostics/current_geospatial_readiness.py` audits private
candidate handoffs listed by a row-free current-corpus manifest. It is an
offline diagnostic: it does not call a geocoder, modify the database, create a
release, or make a publication decision.

Run it from the repository root after a private candidate acquisition:

```powershell
python pipeline/scripts/diagnostics/current_geospatial_readiness.py `
  --manifest data/manifests/current-reacquisition-2026-09-16.json `
  --root . `
  --output data/reports/current-geospatial-readiness.json `
  --as-of 2026-09-16T00:00:00Z
```

The manifest is the source inventory. Each listed source is reported as either
an available normalized handoff or `unavailable_private_handoff`; missing
private artifacts are never silently counted as zero rows. The report contains
only source IDs, declared counts, file hashes/bytes, and aggregate metrics.
It excludes source identifiers, names, addresses, coordinates, geocoder
queries/responses, and row samples.

The report has two complementary views:

- `display_states` are mutually exclusive: `exact`, `city`, `unmapped`, or
  `restricted`. A restricted record is never made safe merely by having a
  coordinate.
- `evidence_states` overlap intentionally. A row may have a source coordinate
  and an accepted geocoder result, so both facts are counted rather than one
  overwriting the other. Source coordinates held in restricted source values
  are counted as evidence without copying those values into the report; a
  source-value-present row whose numeric point is not exposed is counted as
  `source_coordinate_pending_review`. Invalid coordinates are never repaired.

Each source also reports `suppressed_rows` explicitly. This is the count of
whole-record restriction signals in the private handoff; a coordinate withheld
for privacy is kept in the coordinate-review queue and is not automatically
treated as a whole-record suppression.

The privacy and coordinate review queues are conservative indicators for human
review. They are not residential classifications, factual approval, or
publication eligibility. An accepted geocode is evidence about location only;
it does not grant project approval or release permission. City values produce
coarse display readiness only when no exact point is eligible; no city point is
invented by this diagnostic.

## Current evidence and limits

The checked-in current-reacquisition manifest lists eight private source
profiles, with seven normalized profiles and one raw-only CFIA workbook. The
normalized row counts are provenance declarations from the private rehearsal;
the actual normalized handoffs remain ignored local research inputs. Running
the audit without those local handoffs therefore reports the sources as
unavailable rather than claiming coordinate coverage. A run with local
handoffs is required to produce current-corpus coordinate percentages.

The current geocoding registry contains one engine: Denmark's DAWA adapter.
Its development configuration is one request per second with result caching,
30-second request timeout, append-only attempts, retryable transport failures,
and explicit review for multiple matches. It is approved for development only
and must be reevaluated before production. No production cost or provider
retention claim is made by the project; providers and terms must be assessed
per country before enabling a new engine.

The API contract independently proves the same boundary: exact records may
carry coordinates, city records may carry only a coarse reference point, an
unmapped record carries null coordinates, and a restricted record is absent
from list, detail, and export surfaces. These are tested in the seeded API E2E
suite; the diagnostic does not replace those database-backed tests.
