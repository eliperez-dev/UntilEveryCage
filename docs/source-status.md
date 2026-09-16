# Source status baseline

This is the canonical human-readable view of [`source-status.json`](source-status.json). It records repository evidence and reconnaissance state; it is not a live monitor, acquisition log, pipeline health dashboard, release approval, or publication authorization.

## How to read it

- `metadata` describes whether a source route/scope was documented from repository or reconnaissance evidence.
- `acquisition` describes only bounded acquisition evidence. `not_run` and `blocked` do not mean zero rows or source failure.
- `runtime_health` is `not_run` unless a repeatable current pipeline check is recorded. No source here is claimed healthy.
- `publication_eligibility` is separate from source origin and metadata. These sources remain `blocked` until privacy, terms, validation, review, release, and maintainer approval gates are satisfied.

No last-success timestamp is invented. Private artifacts are not proof of a public release. “Government-sourced” does not mean current, complete, project-approved, or safe to expose.

## Current baseline

| Source ID | Metadata | Acquisition | Runtime health | Publication | Evidence / next action |
|---|---|---|---|---|---|
| `be.locations` | verified | blocked | not_run | blocked | Shared private adapter, row-length/quarantine checks, and assisted two-file refresh are covered by synthetic fixtures; obtain an authorized operator capture and compare live schema before any real run; see `docs/review-packet-belgium.md` |
| `fr.locations` | verified | blocked | not_run | blocked | DGAL/Alim’confiance/SIRENE/HVE/Agence Bio/Géorisques reconnaissance; acquire permitted official artifact and review terms/privacy |
| `it.853-2004` | verified | artifact_private_only | not_run | blocked | Catalog acquisition, shared lifecycle, source-category/activity diagnostics, private candidate import, and guarded API checks remain review-gated; repeated activity identity, coordinate/address privacy, coverage, and project approval remain open; see `docs/review-packet-italy.md` |
| `it.1069-2009` | verified | not_run | not_run | blocked | Separate by-products catalog candidate; no adapter or integration decision; assess scope, schema, terms, identity links, and privacy |
| `mx.locations` | verified | blocked | not_run | blocked | DENUE/SENASICA/DGSIAP reconnaissance; resolve token, directory, terms, and schema |
| `nz.locations` | verified | blocked | not_run | blocked | MPI/Stats NZ reconnaissance; resolve 403/access and aggregate-vs-facility boundaries |
| `uk.locations` | partial | artifact_private_only | unknown | blocked | FSA and FSS private V2 lifecycle paths, nation-qualified identity, coordinate precision states, and synthetic handoff tests pass; no real UK candidate has been imported or previewed; privacy/coordinate, source-rights, duplicate, coverage, and release review remain open; NI/Scotland stay separate; see `docs/review-packet-united-kingdom.md` |
| `dk.smiley` | verified | verified | unknown | blocked | Shared private lifecycle and registered adapter are validated on synthetic/retained evidence with explicit not-observed semantics; coverage/effective-date uncertainty and terms/privacy/release review remain open; see `docs/review-packet-denmark.md` |
| `de.locations` | partial | artifact_private_only | not_run | blocked | Stable BVL `/bltu` landing and portal route are verified; typed private adapter and assisted export refresh now include duplicate-approval and coordinate-precision checks, while export-specific terms/privacy/release review remain unresolved; see `docs/review-packet-germany.md` |
| `ca.locations` | verified | not_run | not_run | blocked | Federal/export and Ontario candidates are documented separately; verify permitted artifact, terms, schema, coverage, and privacy before acquisition |
| `es.locations` | partial | blocked | not_run | blocked | AESAN RGSEAA and MAPA sector routes are documented, but direct acquisition was refused; rights, export/schema, effective dates, sector coverage, privacy, and legacy/source boundaries remain unresolved |
| `us.fsis` | verified | blocked | not_run | blocked | Official FSIS MPI route is documented, but current CSV access returned 403; obtain authorized export access and record provenance/schema before adapter or publication review |
| `us.aphis` | partial | not_run | not_run | blocked | APHIS export workflow and separate report/license provenance require review |
| `us.inspections` | partial | not_run | not_run | blocked | Inspection observations require a current export and explicit identity matching |

The machine-readable file is the source of truth for these statuses. Legacy `.locations` paths may represent composite coverage, but the Italy Ministry candidates are now split into explicit 853/2004 and 1069/2009 source IDs. Candidate feeds mentioned in the France, Mexico, and New Zealand reconnaissance documents are not silently conflated into a single healthy source. Country reconnaissance documents provide evidence and next actions; they do not override this status vocabulary or authorize publication.
