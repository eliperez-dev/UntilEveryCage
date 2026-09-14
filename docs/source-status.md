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
| `fr.locations` | verified | blocked | not_run | blocked | DGAL/Alim’confiance/SIRENE/HVE/Agence Bio/Géorisques reconnaissance; acquire permitted official artifact and review terms/privacy |
| `it.locations` | verified | artifact_private_only | not_run | blocked | Current 853/2004 and 1069/2009 CSVs were privately acquired with provenance; schemas remain distinct and require dictionary/privacy mapping plus separate adapters |
| `mx.locations` | verified | blocked | not_run | blocked | DENUE/SENASICA/DGSIAP reconnaissance; resolve token, directory, terms, and schema |
| `nz.locations` | verified | blocked | not_run | blocked | MPI/Stats NZ reconnaissance; resolve 403/access and aggregate-vs-facility boundaries |
| `uk.locations` | partial | artifact_private_only | not_run | blocked | Private England/Wales monthly candidate is validated; NI and Scotland remain separate, with withheld-address/duplicate/coverage/terms/release review open |
| `dk.smiley` | partial | not_run | not_run | blocked | SourceArtifact and registered-adapter contracts are documented; official live acquisition, endpoint/licence/coverage/release verification remain open |
| `de.locations` | partial | not_run | not_run | blocked | Legacy session URL and current BVL endpoint/schema/terms remain unresolved |
| `ca.locations` | verified | not_run | not_run | blocked | Federal/export and Ontario candidates are documented separately; verify permitted artifact, terms, schema, coverage, and privacy before acquisition |
| `es.locations` | partial | blocked | not_run | blocked | AESAN RGSEAA and MAPA sector routes are documented, but direct acquisition was refused; rights, export/schema, effective dates, sector coverage, privacy, and legacy/source boundaries remain unresolved |
| `us.fsis` | verified | not_run | not_run | blocked | FSIS MPI route is documented; acquire a permitted current artifact and treat legacy inventory only as a comparison |
| `us.aphis` | partial | not_run | not_run | blocked | APHIS export workflow and separate report/license provenance require review |
| `us.inspections` | partial | not_run | not_run | blocked | Inspection observations require a current export and explicit identity matching |

The machine-readable file is the source of truth for these statuses. `.locations` IDs may represent composite legacy coverage rather than one upstream source. Candidate feeds mentioned in the France, Mexico, New Zealand, and Italy reconnaissance documents are not silently conflated into a single healthy source; source splitting remains a next action. Country reconnaissance documents provide evidence and next actions; they do not override this status vocabulary or authorize publication.
