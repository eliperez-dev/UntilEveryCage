# Reviewed demonstration release lane

This lane is the controlled path for a small real-data demonstration. It is
not a shortcut around the governing [ethics policy](ETHICS.md), source terms,
privacy screening, or maintainer approval. Raw XML, normalized rows, review
documents, and coordinates remain in restricted ignored storage. Checked-in
documents and receipts must stay row-free.

The current Denmark source is still blocked for publication. Its source review
packet records open terms/currentness, coverage/effective-date, category,
privacy, and release-review questions. No second source is included because no
additional source currently has all of rights, provenance, privacy, and
precision gates demonstrated.

## Workflow

1. Acquire and stage Denmark privately using the source-owned pipeline. Keep
   raw artifacts and normalized handoffs outside Git. A failed or partial run
   must not change an existing release.
2. Write a row-free selection document containing the candidate release ID,
   source ID, raw-artifact SHA-256, an explanation of the bounded selection,
   and at most 25 opaque `source_record_id` UUIDs. Do not put names, addresses,
   coordinates, source text, or requester evidence in this document.
3. Prepare a new non-test candidate. Preparation copies only selected,
   already-classified, coordinate-approved, accepted, visible observations. It
   does not approve or publish:

   ```powershell
   python pipeline/scripts/stages/prepare-demonstration-release.py `
     --selection data/restricted/demo/selection.json `
     --release-id dk-demo-2026-09-17 `
     --profile official `
     --receipt data/reports/dk-demo-prepared.json `
     --database-url $env:UEC_DATABASE_URL
   ```

4. After an authorized project maintainer has separately reviewed source terms,
   rights, provenance, classification, privacy/location exposure, and the
   bounded selection, write a review document. `rights_status` must be
   explicitly `cleared`; the command does not decide whether the reviewer is
   authorized and does not provide legal advice.
5. Record the release-scoped review decisions. This appends immutable
   publication-review events and updates only the candidate control summary:

   ```powershell
   python pipeline/scripts/stages/record-demonstration-review.py `
     --review data/restricted/demo/review.json `
     --receipt data/reports/dk-demo-reviewed.json `
     --database-url $env:UEC_DATABASE_URL
   ```

   The review must cover exactly every member in the prepared release. A
   pending, failed, rejected, or denied decision cannot approve the demo.
6. Run release validation and stop on any finding. Then promote explicitly,
   writing the immutable manifest to a new file. Promotion remains separate
   from review and validation:

   ```powershell
   python pipeline/scripts/stages/validate-release.py dk-demo-2026-09-17 `
     --expected-records 5 --mark-validated `
     --output data/reports/dk-demo-validation.json
   python pipeline/scripts/stages/promote-release.py dk-demo-2026-09-17 `
     --manifest data/reports/dk-demo-manifest.json `
     --no-distributed-artifacts
   python pipeline/scripts/maintenance/build_public_discovery_read_model.py `
     dk-demo-2026-09-17 --database-url $env:UEC_DATABASE_URL
   ```

7. Verify the public API and packaged export by release/profile and retain only
   aggregate, row-free evidence. The manifest records source coverage,
   retrieval, review/publication state, limitations, and the release it
   supersedes. A later promotion records the previous promoted release in
   `supersedes`; it does not mutate earlier evidence.
8. Exercise suppression with an opaque source-record reference. Verify list,
   detail, facets, CSV, historical views, reimport, renewed geocoding, release
   reconstruction, and restore replay. The suppression runbook remains the
   authority for privacy/removal cases. A closed case still requires an
   explicit lifted event before publication can return.

## Review document shape

The following is a template, not an approval and not a claim that the current
Denmark source is cleared:

```json
{
  "review_version": "uec-demo-review-v1",
  "release_id": "dk-demo-2026-09-17",
  "source_id": "dk.smiley",
  "source_artifact_sha256": "<64 lowercase hex characters>",
  "rights_status": "cleared",
  "rights_reference": "<restricted terms review reference>",
  "reviewer_role": "<actual authorized project reviewer role>",
  "reviewed_at": "<UTC timestamp>",
  "decisions": [
    {
      "source_record_id": "<opaque UUID>",
      "factual_review_status": "reviewed",
      "privacy_screening_status": "passed",
      "maintainer_approval": "approved",
      "publication_eligible": true,
      "note": "<scoped, non-sensitive review note>"
    }
  ]
}
```

Do not substitute `government-sourced`, a successful download, a geocoder
match, or an attribution string for project approval. Until an authorized
review actually records the required decision, the current Denmark rehearsal
remains private candidate/test-only and no public release should be created.
