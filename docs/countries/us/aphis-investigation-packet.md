# Private APHIS investigation packet

This packet is a private, bounded evidence product over the existing APHIS
source-local adapter and Wave 2 identity candidate ledger. It is intended for
an investigator who needs to answer which captured annual-report and
inspection observations attach to a registration, which periods were covered,
and why a link or document remains unresolved.

The builder is `pipeline.sources.us.accountability.aphis_evidence`. It accepts
an explicit manifest and named artifact root; it never scans for files or
performs upstream acquisition. Each manifest-named artifact must carry a
SHA-256 and byte size. A missing artifact, invalid hash, or size mismatch is a
visible `failed` input. A replay keeps the source retrieval timestamp from its
manifest and is not a fresh source observation.

When acquisition lanes hand off normalized observations separately, use the
explicit `run_from_handoffs` boundary with one handoff directory for each of
`registrations`, `annual_reports`, and `inspections`. Each directory must
contain the existing `us-aphis-observation-handoff-v1` `manifest.json` and
`records.jsonl`; the consumer verifies the handoff checksum, row count, source
identity, and blocked/private state before building the same packet and
identity graph. The handoff's source-artifact checksum remains row provenance,
but is not treated as independently verified raw bytes unless a retained raw
artifact is separately replayed through `verify_retained_artifacts`.

Example private run after an authorized handoff:

```powershell
python -m pipeline.sources.us.accountability.aphis_evidence `
  --manifest C:\restricted\aphis\input-manifest.json `
  --artifact-root C:\restricted\aphis\artifacts `
  --run-dir C:\restricted\aphis\runs\investigation-<run-id>
```

The packet writes `private/` JSONL files for authorized review and a separate
`row-free-summary.json`. The row-free report contains counts, periods,
artifact verification outcomes, link exclusion reasons, coverage boundaries,
and unknowns. It never contains names, addresses, raw rows, document URLs, or
signed URLs. The companion editorial note records what the evidence makes
visible, why it matters to activists, what it cannot establish, and useful
next research questions.

Each timeline item has one of these states:

* `observed`: an accepted source-local record with its source key, period and
  profile provenance;
* `not_observed`: an expected row or period was outside the captured input;
* `quarantined`: duplicate, suppressed, conflicting, or otherwise unresolved
  evidence remains visible for review;
* `failed`: an input artifact or processing step could not be verified; and
* `document_not_captured`: a source record explicitly references a document
  key whose retained document is unavailable.

Annual report years are represented as `start`, `end`, and
`precision: "year"`. The builder does not turn a year into a claimed event
date. Inspection dates retain day precision when supplied. Document links
require an explicit source document key; a URL alone is never copied into a
packet.

Links are copied from the existing source-native candidate ledger. Exact APHIS
certificate/customer identifier matches retain matched identifier types and
review state. Conflicts and duplicate evidence remain quarantined. Names and
addresses are not identity evidence, and no candidate establishes ownership,
current operation, approval, wrongdoing, or a complete animal-use total.

For a real capture spanning multiple export pages, graph edges retain the
source-record-specific artifact hash for each side of a link. Profile-level
aggregate hashes remain accounting metadata only and cannot stand in for the
bytes containing an individual observation. This is what allows a replay to
distinguish an exact evidence path from a missing or unverifiable artifact.

All output remains private, `not_eligible`, and `release_state: not-created`.
Raw and parsed inputs remain outside Git under the retention and removal rules
in `docs/ETHICS.md`. A synthetic test pass demonstrates engineering behavior
only; the real retained-input rehearsal requires a permitted artifact handoff
and a second deterministic replay with aggregate count reconciliation.
