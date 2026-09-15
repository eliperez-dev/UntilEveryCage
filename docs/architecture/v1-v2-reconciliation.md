# V1-to-V2 reconciliation

`pipeline/reconciliation/crosswalk.py` produces a row-free comparison of a
legacy V1 snapshot and one private V2 adapter run. It is a review instrument,
not an identity resolver and not a release gate by itself.

## Matching rules

- A source-specific stable key must be supplied for both inputs.
- Matching is exact after trimming whitespace. Names, addresses, coordinates,
  geocoder output, and fuzzy similarity are never used as identity evidence.
- A repeated key on either side is `ambiguous`; it is excluded from matches and
  requires a separately recorded identity decision.
- A V1 key absent from V2 is `not_observed_in_v2`, never “closed”, deleted, or
  suppressed. Source disappearance is only an observation boundary.
- Quarantined rows remain counted in the report but are not treated as accepted
  V2 observations.

The report contains aggregate counts and field-presence/category summaries only.
It must not be written to Git when generated from real local data. Raw rows,
addresses, coordinates, names, and geocoder responses stay in ignored private
staging.

## Example

```powershell
python pipeline/scripts/diagnostics/crosswalk-report.py `
  static_data/dk/locations.csv `
  data/staging/dk/run/normalized/records.jsonl `
  --v1-key establishment_id `
  --v2-key source_record_key `
  --country DK `
  --source-id dk.smiley `
  --output data/reports/dk-v1-v2-crosswalk.json
```

This command is intentionally explicit about the two source keys. It should be
run only after the V2 run has produced a private normalized artifact and its
manifest has been reviewed. It does not create facility links, releases, API
records, or publication approval.

## Remaining country work

Denmark, the UK, and Italy still need source-specific key mappings and private
current snapshots before a substantive comparison can be claimed. For Italy,
the 853/2004 and 1069/2009 populations remain separate. For the UK, England /
Wales, Scotland, and Northern Ireland remain separate until coverage and
identity semantics are evidenced. Legacy rows with unknown provenance or
unresolved keys remain explicitly unmatched rather than being repaired by
heuristic matching.

## Legacy-country inventory

Before a private V2 artifact exists, use the row-free inventory command:

```powershell
python pipeline/scripts/diagnostics/inventory-v1-countries.py `
  --output data/reports/v1-country-inventory.json
```

It counts rows, missing and duplicate legacy keys, and coordinate-pair
presence for the V1 country directories represented by the checkout. It
explicitly reports `blocked_no_private_v2_artifact`; it does not pretend that
every legacy row is unmatched against a current source, and it does not infer
currentness, closure, or identity. Generated reports belong in ignored local
data when run against real snapshots.
