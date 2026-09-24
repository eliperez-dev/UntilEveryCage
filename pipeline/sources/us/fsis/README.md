# FSIS MPI private refresh

This source package feeds the private preview from the USDA FSIS Meat, Poultry
and Egg Product Inspection (MPI) Directory. The scheduled operator command is
non-interactive and refreshes the database the map reads:

```text
python scripts/real_preview.py refresh --source us.fsis
```

Run it in an environment with Python pipeline requirements, Firefox, and
Selenium installed. It downloads the current published directory-by-number
CSV and supplemental demographics CSV, validates both, runs exact-ID
reconciliation and quarantine, normalizes observations, and imports the exact
handoff to the isolated loopback preview database. The frontend has no
operational refresh control. State inspection programs, APHIS observations,
and non-FSIS populations remain outside this source.

## Capture boundary

The authorized Firefox method uses a fresh temporary profile and only follows
the exact public export links present on the official FSIS directory page. It
records the linked edition label, URL, retrieval time, hash, byte size, browser
and Selenium versions, and navigation outcome. It never imports a user
profile, credentials, cookies, or hidden endpoints. Missing official links,
HTML, login pages, 403 responses, incomplete downloads, malformed CSV, and
schema drift fail closed. Each of the two required exports must succeed; there
is no retained-artifact fallback.

For an operator-assisted capture:

```text
python -m pipeline.sources.us.fsis.refresh \
  --directory <private-directory.csv> \
  --demographics <private-demographics.csv> \
  --run-dir <private-run> --mode dry-run
```

For the scheduled command, install the pinned Python requirements and system
Firefox in the operator runtime:

```text
python -m pip install -r pipeline/requirements.txt
```

The automated preview runner selects the browser method and project-scoped
private-preview authorization for FSIS. Operators should schedule the single
command above. The lower-level module remains available for isolated diagnosis:

```text
python -m pipeline.sources.us.fsis.refresh \
  --fetch --acquisition-method firefox \
  --source-url https://www.fsis.usda.gov/sites/default/files/media_file/documents/MPI_Directory_by_Establishment_Name.csv \
  --acquisition-authorization <private-acquisition-authorization.json> \
  --run-dir <private-run> --mode dry-run
```

The project authorization record permits private preview acquisition only; it
does not establish redistribution rights or authorize public release. Each
browser attempt is bounded to two fresh sessions, retains validated CSV bytes
and row-free provenance, and removes incomplete or invalid download bodies
after writing a failure record. A browser navigation timeout is accepted only
when the complete file passes the byte and source-role CSV checks.

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
