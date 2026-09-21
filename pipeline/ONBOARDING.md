# Pipeline contributor onboarding

This is the shortest safe local path for a new pipeline contributor. Run every
command from the repository root. It uses synthetic fixtures and temporary
directories; it does not acquire data, import a release, or publish anything.

## 1. Read the boundaries

Read [the governing ethics policy](../docs/ETHICS.md), then [the source
adapter contract](contracts/README.md) and [the source registry](source_registry.json).
The registry describes source evidence and blockers; it is not an acquisition
permission or publication approval.

## 2. Run the contract tests

```powershell
python -m unittest pipeline.sources.denmark.test_adapter pipeline.common.test_orchestrator pipeline.common.test_review_packet
```

The Denmark tests are the reference vertical slice. They exercise preserved
input integrity, parsing, normalization, quarantine, private manifests, QA,
health, candidate handoff, and rerun determinism. The shared orchestrator tests
cover registered-input compatibility and suppression behavior.

Run the complete Python suite before submitting pipeline changes:

```powershell
python -m unittest discover -s pipeline -p 'test*.py'
```

The one-command private demo runs the graph-candidate and review-packet
contracts without acquiring, importing, or publishing anything:

```powershell
python scripts/dev.py demo
python scripts/dev.py preflight
python scripts/dev.py diagnostics data/reports/real-corpus-report.json
python scripts/dev.py review-export data/staging/<source>/<run-id>
```

`review-export` is a row-free operator packet. It is not approval. Source
adapters remain the canonical acquire -> parse/normalize -> quarantine ->
candidate handoff path; candidate database import is restricted to the
disposable loopback database. Rebuild candidates by rerunning the source-owned
adapter with a new private run directory; never edit or promote a candidate in
`static_data`. Missing evidence, source drift, ambiguous identities, and
quarantined rows remain blockers and are reported in the packet/health files.

## 3. Inspect private operational evidence

For an existing private run, build a row-free report from its manifest root:

```powershell
python pipeline/scripts/diagnostics/real_corpus_report.py `
  --manifest-root data/manifests `
  --output data/reports/real-corpus-report.json
```

Unknown row counts remain unknown; they are never converted to zero. The
report is an inventory aid, not a source health claim, release validation, or
publication decision. Keep raw and derived run directories under ignored
`data/raw`, `data/staging`, or `data/restricted`.

## 4. Follow one source lifecycle

For Denmark, use the source-owned launcher as the canonical path:

```powershell
python pipeline/sources/denmark/run-denmark-pipeline.py --help
python pipeline/sources/denmark/run-denmark-pipeline.py path/to/private/Smileydata.xml --output-dir data/staging/denmark-smiley/<run-id>
```

Acquisition requires an operator-approved terms review and is intentionally
opt-in. Candidate import, geocoding, release validation, and promotion are
separate commands and separate gates. The older
`pipeline/run-denmark-pipeline.py` path remains a deprecated compatibility
launcher for one release; new source-specific documentation should link to the
source-owned path.

## Known onboarding friction

- The repository root README describes the Rust application, while this guide
  describes the private V2 pipeline; contributors must choose the pipeline
  path before running `cargo run`.
- Both historical and source-owned Denmark launchers exist. The source-owned
  launcher is canonical; the historical path is deprecated and retained for
  one release for compatibility.
- Full local V2 API startup requires Docker/Postgres and a Rust build. It is
  not required for adapter contract tests and must use only the disposable
  local configuration in `pipeline/scripts/maintenance/local-v2.ps1`.
- Real corpus reports can only claim what local manifests record. Missing raw
  bytes, row counts, or V2 runs are reported as unavailable, not inferred.
