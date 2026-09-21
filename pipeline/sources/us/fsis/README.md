# FSIS MPI private refresh

This source package is a private, test-only acquisition and transformation
boundary for the USDA FSIS Meat, Poultry and Egg Product Inspection (MPI)
Directory. It does not create a public release. State inspection programs,
APHIS observations, and non-FSIS populations remain outside this source.

## Capture boundary

The official page currently exposes a directory export by establishment name,
a directory export by establishment number, and a supplemental establishment-
demographic CSV. Direct HTTP links may return HTTP 403 while a normal Firefox
download succeeds on the same source route. The refresh command has an
explicit `--acquisition-method` choice: `http` uses the bounded HTTP primitive;
`firefox` uses a fresh temporary Firefox profile and Selenium download settings.
The browser method records the exact URL, retrieval time, hash, byte size,
browser/runtime version, navigation method, and whether a navigation timeout
occurred after a complete validated file appeared. It never imports a user
profile, credentials, cookies, or hidden endpoints. HTML, login pages, 403
responses, unsupported content types, malformed CSV, incomplete downloads, and
schema drift fail closed.

For an operator-assisted capture:

```text
python -m pipeline.sources.us.fsis.refresh \
  --directory <private-directory.csv> \
  --demographics <private-demographics.csv> \
  --run-dir <private-run> --mode dry-run
```

For an owner-authorized normal-browser capture, install the optional Selenium
package in the operator runtime and install system Firefox; these are not
project runtime dependencies:

```text
python -m pip install selenium
```

Then choose the browser method explicitly:

```text
python -m pipeline.sources.us.fsis.refresh \
  --fetch --acquisition-method firefox \
  --source-url https://www.fsis.usda.gov/sites/default/files/media_file/documents/MPI_Directory_by_Establishment_Name.csv \
  --acquisition-authorization <private-acquisition-authorization.json> \
  --run-dir <private-run> --mode dry-run
```

The authorization record must state `status=authorized`, an owner basis,
source scope, private/no-public restrictions, and `terms_status=unknown` or
`pending_review`. It records acquisition permission separately; it is not a
redistribution or licensing approval. Supply `--terms-review` only when a
separate approved terms record exists; otherwise the browser metadata records
terms as unknown and publication remains blocked. Each browser attempt is bounded to two fresh sessions by default, retains only
validated CSV bytes and row-free metadata, and removes incomplete/invalid
download bodies after preserving the failure record. A browser navigation
timeout is accepted only after the completed file passes the byte bound and
the source-role CSV validator. The demographic route is acquired in the same
run; missing demographics remain an explicit directory-only profile.

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
