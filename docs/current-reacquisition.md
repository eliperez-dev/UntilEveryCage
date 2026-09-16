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

CFIA was captured privately but is not normalized: the current response is an
XLS workbook, while `ca-meat-v1` intentionally accepts delimited text only.
Keep that artifact raw-only until a reviewed workbook adapter and schema
contract exist.

## Full-corpus V2 rehearsal

The completed rehearsal used a disposable `docker-compose.e2e.yml` project
(`uec-reacq-20260916`, DB port `55440`) with all 34 migrations. It imported the
Denmark and Italy candidate handoffs into
`candidate-current-reacquisition-20260916` for 100,613 normalized rows using
`pipeline/scripts/maintenance/import-candidate.py` and loopback-only
test-release configuration.

The loopback API was exercised on `127.0.0.1:18000`: candidate preview,
test-release locations, facets, paginated location retrieval, and a bounded
sample CSV export returned successfully. The full CSV endpoint correctly
returned its explicit `export_too_large` guard above 1,000 rows. The public V2
route returned zero rows because no promoted release existed. One append-only
`public_access_revoked` event reduced private candidate visibility from 100,613
to 100,612. Re-running both candidate imports produced zero new rows.

The disposable Compose project and API process should be stopped and removed
after inspection:

```powershell
docker compose -p uec-reacq-20260916 -f docker-compose.e2e.yml down -v --remove-orphans
```

This rehearsal is evidence of private normalization, quarantine, candidate
handoff/import, test-only preview/export, suppression, and rerun behavior. It
is not project approval, currentness certification, or publication permission.
