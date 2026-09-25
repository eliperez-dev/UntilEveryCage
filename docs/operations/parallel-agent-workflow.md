# Parallel agent workflow

**Owner:** engineering maintainers. **Status:** Canonical operating contract for
parallel repository work. Read it after the [documentation hub](../README.md).

## Assignment contract

Give each agent one bounded outcome and one exclusive ownership set. An
assignment states: outcome, source ID or subsystem, allowed paths, excluded
shared paths, acceptance evidence, and required checks. For a source task, use
one source ID per assignment; keep independent sources in separate adapters,
descriptors, tests, and country pages. The assigned agent may not widen scope or
change another assignment's files. The coordinator owns shared contracts,
registries, migrations, CI, and cross-source integrations; stage those edits
serially or assign each shared path to exactly one agent. If ownership overlaps
or a shared interface must change, stop the conflicting edits and have the
coordinator resolve the boundary before work continues.

Agents work from the agreed base commit in isolated worktrees/branches. They
commit only their owned changes, report the commit and changed paths, and never
push or integrate another agent's branch. The coordinator reviews each result
against its assignment and incorporates commits in dependency order. Do not
create task plans, sprint notes, or handoff documents; the assignment and
completion report belong in the task conversation and Git history.

## Source registration and durable docs

When a task makes a source a tracked source, register it through the existing
authorities: unique source ID and machine descriptor in
[`pipeline/source_registry.json`](../../pipeline/source_registry.json),
evidence-backed source state in [`source-status.json`](../source-status.json),
and source facts in the appropriate country/source page, terms record, and
row-free manifest. Link the page from the owning source index. Include adapter
contract/tests when an adapter is implemented. Keep source facts and status in
their owners; do not copy them into agent reports or this workflow. Do not
register reconnaissance-only leads as implemented adapters or imply that
registration permits acquisition or publication. Follow
[`docs/ETHICS.md`](../ETHICS.md) for source terms, private inputs, evidence,
privacy, and release boundaries.

## Evidence and completion

An agent is complete only when its assigned outcome is implemented, its owned
checks pass, its changes are committed, and its report names the commit,
changed paths, exact commands/results, and any skipped or blocked checks. State
whether evidence is synthetic, local-artifact, or live; give aggregate counts
only when safe. Never attach or commit source rows, addresses, coordinates,
credentials, restricted payloads, or geocoder responses. A passing test proves
only the behavior it exercises.

Use **strict live private E2E** only for one bounded run that acquires the
current source from its live upstream route, records provenance, runs the real
source adapter through normalized/quarantined output and candidate handoff,
imports into a disposable private database, and verifies the run and private
database results, including zero public rows. Retain row-free aggregate
manifests/reports and record the exact commands and evidence location. A replay,
fixture, local artifact, adapter-only test, or database test without live
acquisition is not strict live E2E. The label describes that run only: it does
not prove recurring health, completeness, factual accuracy, terms clearance,
privacy approval, project approval, or publication authority. Record source
status and source-specific counts only in the canonical source-status record
and its supporting manifest/page.

## Integration and CI

Integrate in dependency order: review ownership and commit scope; incorporate
isolated source changes; resolve shared registry/contracts/migrations once;
run focused checks for each changed component; then run the repository's
standard pipeline and documentation/hygiene checks, followed by configured CI.
For database-backed work, the canonical local pipeline command is
[`pipeline/tests/run-standard.ps1`](../../pipeline/tests/run-standard.ps1);
use its documented disposable environment and do not run it against a
persistent database. Run additional strict/live E2E only when the assignment
requires it and its source access and terms are authorized. Integration is not
complete until the final integrated commit has passing required checks; report
any unavailable gate explicitly, never as a pass. Do not update product or
source readiness claims based merely on integration or CI.
