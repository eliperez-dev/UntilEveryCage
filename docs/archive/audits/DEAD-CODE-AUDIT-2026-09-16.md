# Dead-code and documentation audit — 2026-09-16

Scope: root-level and cross-cutting tooling/documentation. Backend, pipeline,
frontend, source adapters, and research evidence were inspected for references
but were not removed or redesigned.

## Confirmed cleanup

* Fixed the broken accountability-pilot link in
  `docs/countries/us/README.md`. The document lives three directories below the
  repository root, so the previous `../../pipeline/...` target resolved outside
  the repository; `../../../pipeline/...` resolves to the existing README.
* Removed nine accidentally tracked files under `node_modules/` from version
  control. `.gitignore` already excludes `/node_modules/`, and these files are
  package-manager installation output rather than project source. The local
  dependency directory is left untouched.

## Retained candidates and rationale

* `Old scripts/` is unreferenced by current entrypoints and CI, but it is
  explicitly identified by `AGENTS.md`, `docs/architecture/data-pipeline-plan.md`,
  and `pipeline/README.md` as migration/reference material. The scripts include
  source-specific transformations and are retained as historical method
  records; removing them would erase reproducibility context.
* `Old CSVs/`, `dirty-datasets/`, `static_data/`, and `france-data.kml` are
  legacy or research inputs referenced by the source inventory and country
  crosswalks. They are data evidence, not dead code, and the governing policy
  requires preserving provenance and recovery boundaries. No files were deleted.
* The former `docs/archive/research/v2-ideas.md` proposal and
  `docs/archive/sprints/V2-IMPLEMENTATION-TODO.md` are now preserved under the
  archive; current completeness is tracked only in
  `docs/PRODUCT-READINESS.md`.
* `docs/archive/sprints/V2-SPRINT-2026-09-13.md`,
  `docs/archive/sprints/V2-INTEGRATION-BASELINE.md`, and
  `docs/archive/audits/V2-REVIEW-CLEANUP-2026-09-13.md` are dated integration
  evidence with explicit non-production and evidence-scope language. Their
  overlap is historical reporting, not redundant current instructions.
* `docs/PIPELINE-MIGRATION.md` was last updated on 2026-09-16 and documents the
  shared artifact-boundary migration. Its “next consolidation target” language
  is source-specific status, not an unused entrypoint; it is retained.

## Current root entrypoints

`scripts/dev.py` is referenced by `docs/development.md`, wrapped by
`scripts/dev.ps1`, and covered by `scripts/test_dev.py`. CI invokes the canonical
pipeline/frontend test runners directly. No root script was proven unreachable
or safe to remove.

## Verification method

References were searched with `rg` across tracked source, documentation, CI,
package scripts, and entrypoints. Relative Markdown/JSON links were checked
against the filesystem. The audit found one broken repository-relative link,
now fixed; external URLs were not claimed reachable. Generated dependency
output was checked against Git tracking and `.gitignore`.
