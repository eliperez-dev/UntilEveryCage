# Denmark source entry points

Denmark-specific commands are exposed from this directory so country logic has
a stable home as more sources are added. The source-owned runner below is the
canonical entrypoint. The historical `pipeline/run-denmark-pipeline.py`
launcher remains valid for one release as a deprecated compatibility path and
retains its argument behavior.

The current launchers intentionally delegate to the established implementations
to avoid duplicating acquisition, parsing, normalization, classification, and
validation logic. New source-specific behavior should be added here first;
generic release, geocoding, restriction, and maintenance commands remain in
their shared locations.

Example:

```powershell
python pipeline/sources/denmark/run-denmark-pipeline.py --help
```

## Current-source evidence (private staging)

The current bulk XML endpoint is the Fødevarestyrelsen publication linked from
the official [Find Smiley data page](https://www.findsmiley.dk/om-smiley/statistik-og-data/hent-smileydata).
That page says the export covers data available on findsmiley.dk, is reusable
under public-data terms, requires Fødevarestyrelsen attribution, prohibits use
of its logo, and requires displayed smileys to remain current and follow the
design rules. The page does not supply a dataset effective date; the adapter
records supplied HTTP publication metadata separately from retrieval time.

Coverage is the publisher's Find Smiley dataset (primarily food-service/detail
inspection records); the publisher's statistics page explicitly excludes
wholesale businesses. This is source coverage, not a claim that the project
dataset is complete or that records are current. A reviewed acquisition may be
retained in ignored private storage for research and validation only. The
adapter emits a private candidate with `release_state: not-created`. The
source-owned runner additionally emits row-free QA and private health evidence
when acquisition provenance is complete; `private-validated` is only an
evidence-contract result, not a currentness, approval, geocoding, or
publication conclusion.

## Full private refresh evidence

The retained full artifact was retrieved from the endpoint above at
`2026-09-14T05:41:12Z` (59,852,153 bytes; SHA-256 recorded in ignored local
acquisition metadata). Its deterministic handoff contained 58,792 normalized
rows. In a uniquely named disposable PostGIS database, the batched importer
created 58,792 source records and release members; all 58,792 remained pending
privacy review and 0 were default-visible. A rerun left those counts unchanged.
The database volume was removed after the check. The guarded API was not run
against the full candidate; the existing synthetic DK-shaped E2E covers public
exclusion and preview gates. No release or publication approval follows.
