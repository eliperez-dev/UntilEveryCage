# Repository Guidelines

## Project Structure & Module Organization

The current public application is a Rust/Axum backend in `src/` with a vanilla JavaScript frontend in `static/`. Country datasets are currently checked in under `static_data/`; historical inputs and earlier processing scripts are under `Old CSVs/`, `Old scripts/`, and `dirty-datasets/`. V2 ingestion code lives under `pipeline/`, while acquired and generated artifacts live under `data/`, intentionally separate from the production application. Planning and methodology documentation belongs in `docs/`.

## Build, Test, and Development Commands

- `python scripts/dev.py --help` is the preferred V2 developer entrypoint; use
  `python scripts/dev.py --json doctor` before starting local services.
- Run `npm ci` once at the repository root before `npm test`; `npm test` runs
  the legacy/static Jest suite. The Svelte preview has separate dependencies:
  run `npm --prefix frontend ci` before using its commands.
- `cargo run` starts the current application on port 8000 when its configured
  database is available; `python scripts/dev.py up` is the reproducible local
  V2 setup path.
- `npm run test:coverage` runs Jest with coverage.
- `powershell -ExecutionPolicy Bypass -File pipeline/scripts/maintenance/build-legacy-manifest.ps1` regenerates the legacy file inventory and SHA-256 manifest in `data/manifests/`.
- `python pipeline/scripts/diagnostics/inspect-denmark-smiley.py static_data/dk/Smiley_xml.xml` inspects the Danish XML without transforming it.

For a clean database-backed validation, use
`pwsh -NoProfile -ExecutionPolicy Bypass -File pipeline/tests/run-standard.ps1`.
The persistent `uec-local-v2` database rejects changed migration checksums on
purpose. If local setup reports `migration checksum changed after application`,
the named volume belongs to an older checkout; preserve it unless it is known
to be disposable, and follow the reset/troubleshooting instructions in
`docs/development.md` rather than editing migration history.

## Data Credibility and Provenance

Start with the [ethics summary](docs/ETHICS-SUMMARY.md) for orientation; it does not replace the full policy. Visitor-data handling, legal demands, and publication authority also follow ETHICS.md sections 11–14. Do not claim no logging, legal immunity, a backup reviewer, or enforced approval controls without evidence. Pause new publication needing human approval if no authorized reviewer is available; compliant acquisition and eligible existing releases may continue, and urgent suppression follows policy. Assess preservation obligations before exceptional deletion when a legal demand is involved; escalate to the responsible maintainer rather than making novel legal judgments.

Data credibility is a non-negotiable project requirement. Ordinary acquisition and processing must preserve original source artifacts and record the official URL, retrieval timestamp, content hash, byte size, publication/effective date when supplied, and code/configuration version. Retention is subject to the controlled privacy/removal exceptions in the governing policy.

The governing project policy is [docs/ETHICS.md](docs/ETHICS.md). Read it before changing acquisition, transformation, storage, review, or publication behavior. It takes precedence over conflicting retention or publication guidance. [Policy implementation tasks](docs/governance/policy-implementation-todo.md) track outstanding protections; do not claim they are implemented just because they are documented.

Keep raw, parsed, normalized, enriched, reviewed, and released data distinct. Never silently drop, merge, classify, geocode, or overwrite a record. Preserve source identifiers and source values alongside normalized interpretations. Represent unknown, unavailable, approximate, and unresolved values explicitly. Geocoded coordinates must record the provider, query, timestamp, precision, and review state; they must not replace missing source coordinates invisibly.

Retained research evidence is append-only by default. Ordinary corrections and new observations create linked versions/events. Privacy restrictions and authorized exceptional redaction/deletion follow ETHICS.md sections 2, 6, 8, and 9; append-only rules must not prevent them. Restrict credible exposure promptly, escalate retention/removal decisions to the responsible maintainer, and keep a minimal audit event without copying sensitive payloads. Do not improvise destructive database operations or globally disable evidence protections.

Government source origin does not guarantee factual accuracy. Use ETHICS.md section 5's separate labels: government/secondary/community source origin; community or project factual review with outcome; privacy eligibility; project approval; and actual publication. Never equate project-published with project-approved or community-reviewed with project-reviewed. Public filters do not grant access to restricted data. Suppression applies to maps, APIs, exports, old releases, caches, artifact previews, reimports, and restores. Geocoding success is not permission to publish a residential or private location.

Every published record must trace to source evidence. Suspicious records, schema changes, sharp count changes, coordinate anomalies, and ambiguous identity matches belong in quarantine or a review report. A source disappearance is “not observed,” not proof of closure. Legacy data must remain visibly tagged as legacy and must never be presented as freshly verified.

## Testing Guidelines

ETHICS.md section 5 permits public queries of factually unreviewed community claims only after privacy/abuse screening and explicit profile selection. Do not equate factual review with safety screening. Defaults exclude these claims; prominently label records and direct links, keep community counts separate, and include status/provenance in API objects and exported rows. Restricted, unscreened, or rejected material is never exposed by opt-in.

Pipeline adapters must be deterministic and rerunnable. Preserve real downloaded artifacts as fixtures only where licensing and ETHICS.md permit; use synthetic or sanitized fixtures for privacy tests. Test malformed and missing fields, and verify that failed acquisitions leave the previous validated release available subject to current restrictions. Database history, release reconstruction, and end-to-end suppression across reimports/restores must be tested before production integration.

## Commit & Pull Request Guidelines

Keep acquisition, transformation, schema, and documentation changes separately reviewable. Do not commit secrets or silently replace legacy data. Pull requests affecting data must include source coverage, retrieval/provenance implications, validation results, and any unresolved limitations.
