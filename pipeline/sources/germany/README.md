# Germany BVL BLtU private staging

The live refresh follows the public BLtU session flow to select and preserve its
general-list CSV export, then stages it privately. It uses bounded HTTPS requests,
session cookies, a 30-second request timeout, a 16 MiB default artifact cap, and
the pinned 50-column schema contract. Effective date stays unknown unless BVL
supplies one. Run it with:

```text
python -m pipeline.sources.germany.refresh --fetch --run-dir <private/run> --output-root <private/raw>
```

Live mode requires `pipeline/sources/germany/terms-review.json`. That record
authorizes private acquisition under the project task scope only; it does not
resolve BVL reuse rights or allow publication.

Preserved artifacts may still be replayed with `--raw <private/bltu-export.csv>`.

The typed adapter preserves repeated activity columns and source evidence,
quarantines schema and mapping anomalies, emits shared health evidence, and
cannot create a release. Address/coordinate review, BVL reuse terms, and human
publication approval remain blocked.

## Private location enrichment and taxonomy

Acquisition and enrichment remain separate. Retained BLtU business addresses
can use the existing worker profile `geoapify-de-bltu`; queries contain address,
postcode/locality and country, not business names. Current scripts deliberately
target the disposable `uec_launch_sources_test_20261025` database only. Keep its
connection URL and `GEOAPIFY_API_KEY` in process memory, never command arguments.

```text
python pipeline/scripts/stages/activate-de-bltu-geoapify.py --limit 24
python pipeline/scripts/stages/geocode-worker.py --provider geoapify --private-source-profile geoapify-de-bltu --limit 24 --max-attempts 2 --retries 1 --daily-budget 3000
python -m pipeline.sources.germany.reproject_taxonomy --apply
```

The activator creates durable jobs/targets without provider calls. Later finite
batches support `--offset`; the worker shares the existing daily reservation
ledger with other sources. Its initial queued event has attempt number 1, so
`--max-attempts 1` will select no jobs in this profile. A larger command-line
budget does not raise an already-created ledger limit: an authorized operator
must reconcile that existing daily limit without resetting used reservations.

Taxonomy assignments preserve each native code and the official EU Annex V
legend reference, including separate codes that map to one display category.
Original observations are not rewritten. See the [source inventory](../../../docs/source-status.json)
for measured coverage, unresolved matches and remaining release work; a bounded
geocoding run does not mean the full German source is mapped.

## Older adapter foundation

`pipeline/germany/` is the earlier restricted local-artifact foundation, not
another live acquisition path. Its synthetic tests run with
`python -m unittest -v test_adapter.py` from that directory. Its narrow prototype
mapping accepts CP/GME as processing and SH as slaughter; unknown codes retain
their values in quarantine. The BLtU positional profile preserves repeated
headers, irregular row lengths and distinct current/legacy approval IDs.
Schema/config/mapping hashes and diagnostics do not establish public readiness.
Use this source-owned page for implementation instructions and
[the Germany assessment](../../../docs/germany-source-assessment.md) for research.
