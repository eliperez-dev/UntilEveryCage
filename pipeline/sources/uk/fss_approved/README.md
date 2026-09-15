# FSS Scotland approved establishments

This source-first adapter accepts a preserved CSV artifact or a bounded,
explicitly authorized fetch from the FSS open-data URL. Acquisition uses the
shared private acquisition primitive: raw bytes and acquisition metadata remain
under ignored private storage, with requested/final URLs, redirect chain,
response headers, retrieval/effective dates, hashes, byte size, code/config
versions, coverage, privacy/rights caveats, and the operator terms record.
The adapter never promotes, publishes, exports, or geocodes. It preserves source cells and approval IDs as strings,
including leading zeroes, while representing absent coordinates as `null`.

Rows with duplicate or missing approval IDs, missing/unknown activities,
unknown statuses, malformed cells, remarks, or privacy-risk address tokens are
quarantined. Header and row-shape drift fails closed. Every run records a
checksum, byte size, source metadata, adapter/schema versions, activity
categories, counts, and the explicit private-candidate/non-release state.

The source-owned refresh command runs the shared lifecycle and emits row-free
QA and `source-health.json`. `--mode handoff` additionally emits the shared
candidate-handoff contract; it does not approve or publish a release.

Before acquisition, a maintainer must verify the current FSS artifact URL,
schema, publication/effective date, licence and attribution terms in an
approved environment. England/Wales FSA and Northern Ireland sources require
separate evidence and adapters. Privacy/suppression review, human factual
review, project approval, release authorization, and any legal/terms decision
remain gates; no real artifact or facility record belongs in this repository.

Private refresh example:

```text
python -m pipeline.sources.uk.fss_approved.refresh \
  --fetch --terms-review <operator-approved-terms-review.json> \
  --run-dir <ignored-private-run-dir> --mode dry-run
```
