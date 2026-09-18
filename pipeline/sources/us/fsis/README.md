# FSIS MPI private refresh

This source package is a private, test-only acquisition and transformation
boundary for the USDA FSIS Meat, Poultry and Egg Product Inspection (MPI)
Directory. It does not create a public release. State inspection programs,
APHIS observations, and non-FSIS populations remain outside this source.

## Capture boundary

The official page currently exposes a directory export by establishment name,
a directory export by establishment number, and a supplemental establishment-
demographic CSV. Direct links may return HTTP 403. The refresh command never
bypasses that control: use an authorized operator-assisted capture or a
terms-reviewed bounded fetch. HTML, login pages, 403 responses, unsupported
content types, malformed CSV, and schema drift fail closed.

For an operator-assisted capture:

```text
python -m pipeline.sources.us.fsis.refresh \
  --directory <private-directory.csv> \
  --demographics <private-demographics.csv> \
  --run-dir <private-run> --mode dry-run
```

Use `--mode handoff` only after reviewing the private manifest and quarantine.
`--raw` remains a directory-only compatibility alias. `--fetch` requires a
terms-review JSON and fetches the configured directory-by-number and
demographic routes through the shared bounded acquisition primitive.

## Transformation contract

The directory is the facility identity/location spine. Demographic rows are
joined only by exact source-native establishment ID or establishment number;
names, addresses, phones, and coordinates are never identity keys. Duplicate,
ambiguous, and orphan demographic rows are quarantined. An unmatched current
observation is not evidence of closure.

Each accepted private normalized row retains:

- source values separately for the directory and demographics files;
- source-native identity and row numbers;
- source-provided coordinates with provider, precision, and pending review
  state (no geocoding); and
- source activity fields grouped as species slaughtered, processing
  activities, and inspection attributes, without collapsing species,
  inspection systems, exemptions, or volume categories.

The manifest records a hash and byte size for every source file, schema
fingerprints, exact-key reconciliation counts, drift alarms, and the common
`release_state=not-created`, `publication_state=private-candidate` gates.
Private handoff output remains blocked from public API, map, export, cache, and
history surfaces.

## V1 disposition

The field crosswalk in `docs/countries/us/v1-field-crosswalk.json` maps
identity, location, administrative, species/activity, and inspection fields
where a current source field is available. Phone/address/DUNS values remain
source-only pending privacy review. Legacy derived categories are not asserted
as current facts; they are recomputed only from an approved current artifact or
explicitly retired when the current source does not supply the needed inputs.
