# Current-source reacquisition and private V2 rehearsal

The checked-in [row-free manifest](../data/manifests/current-reacquisition-2026-09-16.json)
records the 2026-09-16 current-source run. Raw artifacts and normalized rows
remain ignored local research inputs under `data/raw/` and
`data/staging/reacquisition/`; no public release was created or promoted.

## Reproduce a refresh

Run from the repository root with the pinned Python environment and an
operator-authorized terms file. The terms file used for this run is the ignored
`data/restricted/reacquisition-terms-review.json`. Replace run IDs with a new
unique UTC ID; never overwrite an existing raw observation.

```powershell
python pipeline/sources/denmark/stages/acquire-denmark-smiley.py --fetch --terms-review data/restricted/reacquisition-terms-review.json --output-root data/raw --run-id <dk-run>
python pipeline/sources/denmark/run-denmark-pipeline.py data/raw/dk.smiley/<dk-run>/Smileydata.xml --output-dir data/staging/reacquisition/dk.smiley/<run>

python -m pipeline.sources.italy.acquire --fetch --terms-review data/restricted/reacquisition-terms-review.json --output-root data/raw --run-id <it-run>
python -m pipeline.sources.italy.refresh --raw data/raw/it.853-2004/<it-run>/source.csv --run-dir data/staging/reacquisition/it.853-2004/<run>

python -c "from pipeline.sources.france.acquire import fetch_section; fetch_section(section='I', output_root='data/raw', terms_review_path='data/restricted/reacquisition-terms-review.json', run_id='<fr-i-run>')"
python -m pipeline.sources.france.refresh --section I --raw data/raw/fr.dgal.section-i/<fr-i-run>/source.txt --run-dir data/staging/reacquisition/fr.dgal.section-i/<run>
python -c "from pipeline.sources.france.acquire import fetch_section; fetch_section(section='II', output_root='data/raw', terms_review_path='data/restricted/reacquisition-terms-review.json', run_id='<fr-ii-run>')"
python -m pipeline.sources.france.refresh --section II --raw data/raw/fr.dgal.section-ii/<fr-ii-run>/source.txt --run-dir data/staging/reacquisition/fr.dgal.section-ii/<run>

python -m pipeline.sources.uk.fsa_approved.refresh --fetch --terms-review data/restricted/reacquisition-terms-review.json --run-dir data/staging/reacquisition/fsa_approved_establishments/<run> --mode handoff
python -m pipeline.sources.uk.fss_approved.refresh --fetch --terms-review data/restricted/reacquisition-terms-review.json --run-dir data/staging/reacquisition/fss_approved_establishments/<run> --mode handoff
python -m pipeline.sources.canada.refresh --source ontario --fetch --terms-review data/restricted/reacquisition-terms-review.json --run-dir data/staging/reacquisition/ca.ontario.meat-plants/<run> --output-root data/raw --run-id <on-run>
```

Each lifecycle writes a source manifest, normalized and quarantined JSONL,
private health evidence, and a candidate handoff. Verify the raw artifact hash
and byte size against its manifest before restoring or rerunning. A source
disappearance is recorded as not observed, never as closure.

CFIA is captured privately as an XLS workbook. The adapter accepts the legacy
BIFF workbook as well as XLSX and HTML-table exports mislabeled as XLS,
preserves source-native cell text and workbook provenance, and fails closed on
malformed workbooks or schema drift. The current 874 rows parse deterministically
but remain quarantined because their function-code values have not yet been
mapped to a reviewed project category. Therefore no CFIA rows enter the
candidate release. Candidate handoffs remain private and human-gated; no public
release is created.

## Full-corpus V2 rehearsal

The eight requested source profiles can be rechecked without exposing their
rows by running the aggregate-only validator below. It reads the ignored raw
artifacts and candidate handoffs named by the checked-in manifest, verifies raw
and normalized hashes, and checks `input = normalized + quarantined` for every
source. Its output contains counts and hashes only:

```powershell
python pipeline/scripts/maintenance/rehearse_current_reacquisition.py `
  --manifest data/manifests/current-reacquisition-2026-09-16.json `
  --root . `
  --output data/reports/current-reacquisition-rehearsal.json
```

The command always writes an aggregate report, but exits nonzero if a private
artifact, handoff, checksum, candidate state, or reconciliation count is
missing or changed. It enumerates every unavailable or invalid source instead
of stopping at the first one; unavailable inputs are never counted as zero.
CFIA is parsed through the legacy BIFF adapter, but all 874 current rows remain
explicitly quarantined because their function-code values still need reviewed
project-category mapping. The checked-in report must remain aggregate-only; do
not substitute a normalized JSONL path for its output path or add row payloads
to the manifest.

For the complete disposable candidate/API rehearsal, use the separate
operator command below. `--root` may point at an authorized ignored staging
checkout; it is read-only from this command. The command imports every
available normalized handoff into one candidate release, reruns every import,
checks list/detail/facets/cursor pagination, verifies the bounded CSV guard,
and records an append-only suppression check. Its output is row-free and must
be written outside the repository or to an ignored report path:

```powershell
python pipeline/scripts/maintenance/rehearse_current_candidate.py `
  --manifest data/manifests/current-reacquisition-2026-09-16.json `
  --root C:\New\ Projects\UntilEveryCage-current-reacquisition `
  --output $env:TEMP\uec-current-candidate-rehearsal.json
```

The candidate release is loopback-only, `test_only`, unapproved, and never
promoted. A successful run must report 108,475 normalized rows imported on
the first pass and zero new rows on the rerun. CFIA is represented by its 874
quarantined input rows and is not silently counted as zero. A zero-normalized
source remains included when every input row is explicitly quarantined.

To run the complete disposable candidate rehearsal, including all seven
normalized handoffs, one idempotent rerun, list/detail/facets/cursor checks, the
bounded export guard, and an append-only suppression check, use:

```powershell
python pipeline/scripts/maintenance/rehearse_current_candidate.py `
  --manifest data/manifests/current-reacquisition-2026-09-16.json `
  --root . `
  --output data/reports/current-candidate-rehearsal.json
```

The runner resolves each raw artifact by its recorded hash and byte size and
fails closed if the authorized ignored artifact is unavailable or ambiguous.
It writes only row-free evidence. The candidate release is test-only and
loopback-authenticated; it is never a publication approval or public release.
The checked-in aggregate result is [the candidate rehearsal manifest](../data/manifests/current-candidate-rehearsal-2026-09-16.json);
the detailed runner report remains ignored because it is regenerated from
authorized private artifacts.

The previous bounded rehearsal used a disposable `docker-compose.e2e.yml`
project (`uec-reacq-20260916`, DB port `55440`) with all 34 migrations. The
current lane supersedes that partial rehearsal by importing the seven
normalized handoffs into one disposable candidate release; the CFIA profile is
accounted for but contributes zero candidate rows while its 874 rows remain
quarantined.

The row-free runner report records the current loopback API results. The full
CSV endpoint must return its explicit `export_too_large` guard above 1,000
rows. The public V2 route must return zero rows because no promoted release
exists. One append-only `public_access_revoked` event must remove the selected
facility from test-release detail and list responses. Re-running every source
import must produce zero new rows.

The disposable Compose project and API process should be stopped and removed
after inspection:

```powershell
docker compose -p uec-reacq-20260916 -f docker-compose.e2e.yml down -v --remove-orphans
```

This rehearsal is evidence of private normalization, quarantine, candidate
handoff/import, test-only preview/export, suppression, and rerun behavior. It
is not project approval, currentness certification, or publication permission.

## Current workspace availability check

The `eli/front-end-overhaul` integration checkout intentionally contains only
the row-free manifest. The authorized private staging root used for the final
rehearsal was the separate ignored checkout
`C:\New Projects\UntilEveryCage-current-reacquisition`; it was inspected
read-only and no raw or normalized rows were copied into the integration
checkout. The aggregate validator completed successfully there for seven
normalized profiles and one CFIA raw-only profile.

The verified reconciliation is 115,182 input rows = 108,475 normalized rows
+ 6,707 quarantined rows. The current-corpus geospatial audit found 40,115
source-coordinate-valid rows, 1,710 source-coordinate-pending-review rows,
68,273 city-display rows, 87 unmapped rows, and 103,676 rows still requiring
privacy/coordinate review. It produced aggregate evidence only. No source
was approved, promoted, or published; the public API row count remains zero.

The candidate/API rehearsal is run separately with
`rehearse_current_candidate.py` because it requires Docker and a disposable
database. Its report should record the exact per-source import counts, a zero
row delta on the idempotent rerun, successful test-only API surfaces, a
bounded full-export rejection above 1,000 rows, and suppression reducing
visible candidate rows by one. CFIA remains the explicit unresolved adapter
blocker: its current official response is an XLS workbook and has no reviewed
normalized handoff.
