# Denmark source entry points

Denmark-specific commands are exposed from this directory so country logic has
a stable home as more sources are added. The historical commands under
`pipeline/scripts/stages/` and `pipeline/run-denmark-pipeline.py` remain valid
compatibility paths and retain their argument behavior.

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
adapter emits a private candidate with `release_state: not-created`; no health,
approval, geocoding, or publication conclusion follows from a successful run.
