# APHIS accountability-graph proof (Wave 2)

Status: private/test-only implementation evidence. This is not a release,
project approval, or claim that the captured subset is complete.

## What the proof demonstrates

The Wave 2 runner consumes operator-saved APHIS Public Search Tool CSV pages
from a private directory and keeps the three profiles separate:

* registrations are the source-local registration observation;
* annual reports are dated FY2025 animal-use observations; and
* inspections are dated inspection observations.

Registration-to-annual-report and registration-to-inspection links are emitted
only when the source records share an exact APHIS certificate number and/or
customer number. Every link retains source record keys, profile provenance,
matched identifier types, confidence, review state, and the blocked publication
state. The graph does not create a canonical facility, ownership, operation,
or approval assertion.

The runner is:

```powershell
python -m pipeline.sources.us.accountability.aphis_wave2 `
  --input-root C:\path\to\private\aphis-exports `
  --run-dir data\raw\us\aphis-accountability-wave2-<run-id>
```

It reads only `ExportData*.csv` files, validates each page with the existing
APHIS adapter, records a per-page SHA-256/size/schema/count manifest, and
writes parsed rows, graph candidates, and quarantine rows under ignored
private staging. The checked-in result is only the row-free aggregate
manifest: [`us-aphis-wave2-accountability-2026-09-18.json`](../../../data/manifests/us-aphis-wave2-accountability-2026-09-18.json).

## Current private capture

The proof used the authorized browser-saved pages from 2026-09-18:

| Profile | Validated pages | Input rows | Accepted | Adapter quarantine | Distinct observation keys |
| --- | ---: | ---: | ---: | ---: | ---: |
| FY2025 annual reports | 10 | 995 | 995 | 0 | 995 |
| Registrations | 78 | 4,763 | 4,763 | 0 | 2,811 |
| Research-facility inspections | 21 | 2,100 | 1,917 | 183 | 1,917 |

The inspection view displayed 15,726 rows, but only 2,100 rows were acquired
in this bounded proof. The remaining view rows are `not_observed` by this run;
they are not closure, non-use, or evidence that no other observations exist.
Four additional local export attempts failed adapter validation and remain
outside the accepted page set. They are recorded as failures in the private
run and are not treated as zero-row observations.

The registration pages include separate pagination/state evidence. 1,952
source observation keys repeat across those pages. The raw/parsed rows remain
private; the graph projection excludes all rows in repeated-key groups instead
of silently merging them. This conservative boundary leaves 859 registration
rows in the graph projection and records the excluded rows as a quarantine
reason.

## Graph and query result

The projection contains 3,771 source-local entities and 955 exact-ID review
candidates. All 955 candidates use both certificate and customer identifiers
in this capture, with confidence `1.0`, `review_state=review_required`, and
`assertion_status=candidate`. The value `1.0` describes exact agreement on
the source identifiers; it is not a factual-truth or project-approval score.

The runner emits two bounded, row-free example queries: one for a
registration-to-annual-report relationship and one for a
registration-to-inspection relationship. Query results expose only hashed
identifier fingerprints and candidate IDs in the committed aggregate
manifest; the private graph retains the source-native values for review. The
projection has 3,999 quarantined relationship/projection items, including
3,904 repeated-key pagination rows and 95 conflicting-identifier cases.

## Safety and uncertainty controls

The proof and its tests demonstrate that:

* weak name/address similarity does not become an asserted relationship;
* exact name/address agreement without compatible official identifiers is at
  most a review candidate, and conflicting official identifiers quarantine it;
* suppressed source rows do not enter accepted candidates;
* all graph candidates remain `private`, `not_eligible`, `release_state=not-created`,
  and all public surfaces remain disabled; and
* writing the same graph twice produces the same idempotency key and bytes.

Observed duplicate/ambiguous keys and identifier conflicts stay in private
quarantine. A missing APHIS observation is not closure. APHIS source origin
does not establish current operation, ownership, factual accuracy, project
approval, or publication permission. Names, addresses, and coordinates are
not included in the committed aggregate result and geocoding is disabled.

Raw, parsed, normalized, and quarantine payloads must remain outside Git under
the retention and removal rules in `docs/ETHICS.md`. The proof does not create
a database release or alter any public API, map, export, cache, or history.
