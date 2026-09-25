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

## Deterministic private golden rehearsal

For a retained local artifact, record the fixed source URL and observation time
before staging, then compare a second run and emit only aggregate evidence:

```powershell
python pipeline/sources/denmark/stages/acquire-denmark-smiley.py `
  --local-file static_data/dk/Smiley_xml.xml `
  --source-url https://pub.fvst.dk/publikationer/Smileydata.xml `
  --retrieved-at-utc 2026-09-14T05:41:12Z `
  --output-root data/raw --run-id denmark-golden-local

python pipeline/sources/denmark/run-denmark-pipeline.py `
  data/raw/dk.smiley/denmark-golden-local/Smileydata.xml `
  --output-dir data/staging/denmark-golden

python pipeline/scripts/maintenance/rehearse_denmark_private.py `
  --run-dir data/staging/denmark-golden `
  --rerun-dir data/staging/denmark-golden-rerun `
  --output data/reports/denmark-private-golden-rehearsal.json
```

The rehearsal quarantines validation findings before geocoding or candidate
handoff, keeps source coordinates distinct from unresolved addresses, verifies
byte-identical rerun artifacts, and checks the separate private-preview
contract. It never creates or promotes a release. Docker-backed API,
suppression, and restoration observations must be supplied by the disposable
E2E environment and remain separate from this row-free staging report.

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

## Strict live private-preview E2E

On 2026-09-25, this scheduler-safe command acquired the linked XML and ran
provenance, parsing, normalization, classification, validation/quarantine,
source-key mapping, transactional private-preview import, idempotent replay,
authenticated list/detail probes, and certification in one bounded run:

```powershell
python scripts/real_preview.py strict-refresh --source dk.smiley
```

Configure dedicated loopback database/API ports, an existing private input
root, and an isolated Docker project through `UEC_REAL_PREVIEW_*` environment
variables. The command restarts only that exact owned project, creates no
release, writes a row-free certificate under
`target/real-preview/runs/<run-id>/certificate.json`, and stops its containers
afterward while retaining the ignored local volume for restricted inspection.
Do not use a shared or production database.

The certified artifact was 59,820,594 bytes (SHA-256
`68a379c4b864336db808ebe90ccc7fdd55f155025530c4474e21b5ca99389702`),
retrieved at `2026-09-25T20:09:49Z`. The publisher supplied
`Last-Modified: 2026-09-25T19:56:00Z` and an ETag. It parsed and classified
58,726 rows with 58,726 unique source keys. Of these, 58,677 passed validation
and mapped one-to-one to candidates; 49 (48 temporary/change-status and 1
unknown category) were quarantined for review. The accepted handoff retained
classification state: 565 were in default map scope and 58,112 were out of
scope. There were no source coordinates; all 58,677 candidates had no usable
facility map point. Authenticated counts/list/detail checks passed, replay was
idempotent, and public rows/projections were zero. The frontend package was not
installed, so no browser rendering check ran; API list/detail passed, while
map-visible and viewport candidate counts were correctly zero.

This demonstrates one private run only. Find Smiley supplies no dataset
effective date; the HTTP `Last-Modified` is not a dataset effective date.
Coverage is Find Smiley only, not a Denmark census. Source terms evidence is
limited to private staging; attribution/current-smiley conditions, address
privacy, category review, recurring health, and public release remain separate
gates.
