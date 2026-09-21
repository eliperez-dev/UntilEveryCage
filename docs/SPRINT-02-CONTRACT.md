# Sprint 02 — real evidence activation

Status: authorized and active, 2026-09-19. Owner approved all eight lanes before dispatch.

## Goal and baseline

Deliver a reproducible private data release covering current US laboratory and slaughterhouse evidence plus France and Italy, with useful evidence links, explicit coverage limits, and independently verified provenance. This is private candidate delivery, not public publication or factual approval.

Base: `eli/front-end-overhaul`, `5570b6ab42e74dc5227e08c2cd7c1ac7f08aab96`. The saved project root is legacy master; all task code belongs in isolated V2 worktrees starting from the named branch. Final integration/push target: `origin/eli/front-end-overhaul`.

The project manager coordinates scope, interfaces, architecture, and acceptance. Luna tasks implement, integrate, and independently review. No major frontend work, new general framework, automatic ownership inference, or country substitution.

## Authority and operating rules

Live public-source acquisition, private processing, necessary implementation fixes, testing, and normal integration/push are authorized. Follow AGENTS.md and docs/ETHICS.md; ethics governs conflicts. Do not ask again for ordinary downloads or private pipeline runs. Actual paid access, access-control bypass, exceptional destructive retention changes, and publication are outside this sprint. A blocked endpoint requires investigation of permitted alternatives, not an immediate permission question or silent synthetic substitution.

Use separate tasks and worktrees. Never overwrite another task's edits, existing user data, or applied migrations. No force pushes. Raw records, identifiers, private URLs and payloads must not enter Git, public logs, or task reports. Reports are row-free. Prior manifests claiming captures do not prove file availability.

## Shared interfaces and storage

Each acquisition lane owns a separate directory under `C:/New Projects/UntilEveryCage/.private/sprint02-20260919/`: `aphis-core`, `aphis-inspections`, `fsis`, `france`, `italy`. Integration initializes and verifies Git exclusion before retained writes; each lane must independently check exclusion before writing raw bytes. No Docker build context may include this shared private root. Existing authorized evidence is preserved; new retrievals get new run directories.

Preserve original response/export bytes, authoritative source URL, actual retrieval timestamp, content hash, byte size, source publication/effective date when known, acquisition method/parameters, code revision, parsing configuration, and completeness limits using existing contracts. Separate raw, parsed, normalized, quarantine, candidate, and review outputs. Downloaded attachments require explicit association and integrity metadata; do not fetch arbitrary links or expose signed URLs.

Each lane records a private handoff manifest with exact local artifact paths and verification commands. A row-free tracked report names the handoff location, source IDs, hashes/counts where safe, source dates, eligibility/rights unknowns, attempted/captured/failed partitions, and commands. Acquisition is distinct from redistribution clearance. Never fabricate owner approvals to make real candidates pass publication gates.

## Eight lanes

1. **APHIS registrations and annual reports.** Acquire the currently exposed research-facility registration population and latest complete annual-report year exposed by APHIS. FY2025 is the expected year, but verify rather than assume; distinguish a complete reporting period from complete submission coverage. Exhaust permitted enumerated pages/partitions for those queries, reconcile provider totals/page counts/deduplication, retain original bytes, and produce source-ID-compatible registration/report observations. Own APHIS acquisition/adapter core paths; coordinate inspection changes through lane 1 if files overlap.
2. **APHIS inspections.** Acquire research-facility inspections with inspection dates in calendar 2025 (`2025-01-01` through `2025-12-31`), retaining actual query semantics and unknown dates separately. This fixed completed-year window supports cross-source analysis without pretending inspection year equals annual-report coverage. Enumerate all exposed permitted pages for the window; identify caps/unavailable partitions explicitly. Retain explicitly referenced documents available through permitted public routes and inventory unavailable documents. Own inspection-specific code/tests; lane 1 owns shared APHIS adapter files.
3. **FSIS modernization.** Acquire current official MPI establishment directory and currently available supplemental demographic files. Reuse existing adapters. Produce private normalized/candidate outputs and a legacy comparison distinguishing source rows, source-native establishments, duplicates, category coverage, additions and not-observed records. No inferred closure.
4. **France activation.** Refresh the existing French slaughterhouse and approved-establishment source profiles already supported by the repository. Freeze their exact registry source IDs in the lane kickoff report before download. Preserve both source scopes, reconcile overlap without automatic merges, build a real private candidate with provenance, quarantine, identity and coordinate coverage.
5. **Italy activation.** Refresh the existing supported Italian establishment source/profile, recording its exact registry ID at kickoff. Produce a reproducible private candidate preserving establishment categories and address/location precision. No new category invention, guessed coordinates, paid geocoding, or public promotion.
6. **Evidence integration.** Consume lane 1–3 handoffs with existing APHIS packet/identity/graph contracts. Deliver real registration-to-report and registration-to-inspection paths with dates, uncertainties, missing documents/coverage, and artifact traceability. Keep FSIS identities separate unless explicit source-native evidence supports a link. Use existing graph projections only when semantics fit. Own packet/accountability integration paths and a private investigator runbook; no frontend redesign or new universal graph importer.
7. **Independent QA.** Independently inspect source-to-output samples stratified by profile/category, valid/quarantined/conflicting/missing-location states and available partitions; verify hashes and replay from retained files in a fresh output directory. Verify deterministic content (excluding documented volatile metadata), reconciliation and privacy boundaries. Review authored changes and send findings back to authors. Do not implement and approve your own fixes. No manifest-only or synthetic real-data acceptance.
8. **Integration/release engineering.** Verify baseline and storage exclusions, maintain source/task handoff ledger, reserve any necessary migration IDs before edits, own shared CI/build/runner files and final integration. Assemble reviewed commits, run appropriate local plus native Linux CI checks, and push normal updates to `eli/front-end-overhaul`. Observe CI for exact SHA, fix failures via owners/review, and produce final evidence report. No public release or deployment.

## Cohesion and execution

Lanes 1–5 start concurrently. Lane 6 prepares existing-contract consumption and begins real replay as soon as first handoffs arrive. QA reviews incremental code and evidence throughout, then performs independent reproduction. Lane 8 integrates continuously without letting unreviewed changes reach the shared target. All tasks report concise checkpoints: actual artifacts/capability delivered, exact tests, blockers, next handoff. Keep network acquisition respectful of source limits. Serialize destructive disposable-DB suites; never use retained/private production-like databases as test fixtures.

Exact source IDs come from the existing registry, not invented new source names. Source/profile/year choices above are frozen; agents may solve technical acquisition problems autonomously but cannot replace a blocked source, change the inspection window, or call a partial capture complete without the project manager recording the limitation and obtaining owner agreement for a material scope change.

## Completion conditions

- Actual retained original artifacts exist and match hashes/byte sizes for every committed source; provider totals, enumerated partitions, accepted rows, duplicates, quarantine, failed/missing captures reconcile. Source limitations are quantified; source observations are never summed as unique facilities without a justified identity rule.
- APHIS current registration/latest complete-year report capture and 2025 inspection capture have reproducible existing-pipeline outputs; real investigator paths trace every displayed observation and link to retained evidence. A packet explains what it establishes and what it does not establish.
- Current FSIS outputs and the legacy comparison are reproducible and dated.
- France and Italy each build a genuine private candidate, with unresolved identity, location, privacy and rights states retained; publication permission is not required or fabricated for a private candidate.
- Independent QA rebuilds all handoffs and verifies stratified evidence, deterministic outputs and privacy/provenance boundaries; no unresolved critical/high defect in changed workflows.
- All reviewed code and safe reports are integrated; required local checks and Linux CI pass for the final implementation revision; origin/eli/front-end-overhaul contains it. Final report identifies exact SHA, artifact handoff locations, commands/results/skips, data coverage and remaining public-launch blockers.

## Escalation and stopping

Continue unaffected lanes when one source is blocked. Investigate official downloads, documented APIs and ordinary browser exports without bypassing controls. Escalate only a concrete unresolved need for owner access, payment, retention/legal judgment, destructive change, publication, or material scope substitution. Report endpoint/operation, attempted permitted alternatives and the specific decision needed, without raw evidence or credentials. Transient failures, difficult parsers, CI failures, missing tools and ordinary implementation choices are work to solve, not permission gates.

The sprint is not complete merely because code/tests pass. Missing real artifacts or unfinished source deliverables keep it incomplete. The project manager records the goal as complete only after requirement-by-requirement evidence audit. User stop/pause requests stop all tasks promptly.
