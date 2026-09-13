# V2 Priority 1: Data Pipeline Implementation Plan

## Outcome

Governed by [ETHICS.md](../ETHICS.md), particularly sections 2, 5, 6, 8, and 9. All preservation and reconstruction requirements below apply to evidence eligible for retention; controlled removals and current publication restrictions take precedence. See the [policy implementation checklist](../governance/policy-implementation-todo.md).

Build a maintained data system independent of the current website. It must preserve the existing files as immutable `legacy` snapshots, acquire each current upstream source through a registered adapter, retain raw evidence and run history, normalize and validate records, reconcile durable facility identities, and emit reviewed releases without automatically changing production.

## Recommended first architecture

Use a Python ingestion package for acquisition/parsing and PostgreSQL + PostGIS for maintained data. Keep raw source artifacts in filesystem/object storage addressed by SHA-256; the database stores metadata and lineage, not a second mutable copy of raw files. A small CLI and scheduler execute the same adapter contract locally, in CI, or on a scheduled worker.

```text
source registry -> acquire -> raw artifact (hash)
                         -> normalize -> validate/quarantine
                         -> identity reconciliation
                         -> append observation history
                         -> review gate -> immutable release manifest
```

Production reads only a named release later. A failed run never replaces the last successful release.

Ordinary pipeline stages preserve evidence and append new timestamped observations, processing results, and decisions. Authorized exceptional redaction/deletion is a separate maintainer-controlled process under ETHICS.md, with minimal audit events. Public suppression and private retention are independent decisions; an optional filter is never a privacy boundary. Releases must apply current restrictions even when serving older observations.

## Core contracts

Every adapter implements:

```text
discover(config) -> acquisition plan
acquire(plan) -> raw artifact(s)
parse(artifact) -> source records
normalize(records) -> canonical candidates + provenance
validate(candidates) -> accepted, rejected, warnings
```

The runner supplies retries, rate limiting, conditional requests, content hashing, run status, logging, metrics, and artifact storage. Adapters own source-specific selectors, pagination, file formats, field mappings, and classification rules. Browser automation is an adapter capability, not the platform default.

## Database model

Start with these tables (all IDs UUIDs unless otherwise noted):

- `sources`: stable source ID, country/scope, official URL, access method, cadence, license/attribution, expected schema, adapter/version, status, manual steps.
- `acquisition_runs`: source, checked/retrieved/ingested timestamps, status (`unchanged`, `changed`, `failed`, `review_required`), request metadata, code/config versions, error summary.
- `raw_artifacts`: immutable object key, SHA-256, media type, byte size, source URL, retrieved time, publication/effective date, run ID.
- `source_records`: source-specific identifier and raw/normalized payload, linked to artifact and run.
- `facilities`: stable project identity for a physical site; canonical name/address and PostGIS point.
- `facility_source_links`: source ID + source record key -> facility, with match method and review state.
- `observations`: append-only facility attributes/activities/species/coordinates in ordinary processing, subject to documented exceptional removals.
- `corrections` and `identity_decisions`: attributed overrides, merges/splits, reason, citation, actor, timestamp, tool version.
- `releases` and `release_members`: named validated snapshots, review decision, diff summary, and included observations.
- `validation_findings`: rule, severity, record, value, and resolution/quarantine status.

Use explicit null semantics (`unknown`, `unavailable`, `not_applicable`) and coordinate provenance (`method`, precision, source, review status). Do not infer closure from disappearance; mark a facility `not_observed` in a new observation.

## Repository shape

Create a separate pipeline tree so legacy frontend loaders remain untouched initially:

```text
pipeline/
  pyproject.toml
  src/uec_pipeline/{cli,runner,models,storage,validation,reconciliation}/
  src/uec_pipeline/adapters/{fsis,aphis,fsa,bvl,dk,fr,es,mx,nz,ca,it}/
  configs/sources/*.yaml
  tests/fixtures/<source>/
  migrations/
  reports/
```

Add a source-registry document and machine-readable registry. Existing scripts under `Old scripts/`, `dirty-datasets/`, and `static_data/*` are migration references and fixture candidates, not production adapters.

## Source inventory and acquisition strategy

First inventory every checked-in dataset and split compound countries into separate source IDs. At minimum, cover US FSIS locations, US APHIS license/registrant and inspection-report sources, UK FSA, Germany BVL, Denmark Fødevarestyrelsen, France DGAL, Spain’s competent-authority source, Mexico’s current official source, New Zealand MPI, Canada federal/Ontario, and Italy’s Ministry source. Confirm whether any current dataset is derived from more than one upstream source before coding.

Classify each source after a live probe:

1. Direct CSV/XLSX/XML/KML download: HTTP client, checksum, schema snapshot.
2. Paginated JSON/API: API client with pagination and response fixtures.
3. Interactive search/export: Playwright/Selenium adapter with explicit browser version, selectors, pagination, downloaded artifact, and a manual fallback.
4. PDF-only: download and parse only if stable; retain the PDF and quarantine ambiguous rows.
5. Unavailable/blocked: record the blocker and assisted acquisition procedure; do not count legacy data as fresh coverage.

The current web verification supports these initial probes: [US FSIS establishments](https://www.fsis.usda.gov/inspection/establishments), [USDA APHIS search](https://direct.aphis.usda.gov/awa/public-search), [UK monthly approved-establishments dataset](https://www.data.gov.uk/dataset/2c80e0ce-ee1c-4f26-ba6f-1e1ae1bd8ee9/approved-food-establishments), [BVL approved establishments](https://www.bvl.bund.de/DE/Arbeitsbereiche/01_Lebensmittel/01_Aufgaben/05_GrenzueberschreitenderHandel/lm_grenzueberschrHandel_basepage.html), [Denmark bulk XML/Excel](https://www.findsmiley.dk/om-smiley/statistik-og-data/hent-smileydata), [France daily DGAL lists](https://agriculture.gouv.fr/liste-des-etablissements-agrees-ce-conformement-au-reglement-ce-ndeg8532004-lists-ue-approved), and [New Zealand MPI registers/listings](https://www.mpi.govt.nz/food-business/meat-game-processing-requirements/meat-industry-registers-and-lists). These are availability checks, not yet proof that each source’s exact current payload matches the legacy dataset.

## Delivery sequence

### Phase 0 — Freeze and inventory

- Hash every existing source file and create a manifest with original path, byte size, checksum, detected schema, approximate vintage, and unknown dates.
- Copy originals to immutable legacy storage; import them under `data_origin=legacy` with a migration snapshot.
- Produce a source matrix: country, dataset, upstream owner, URL, scope, access mode, terms, current status, cadence, adapter owner, and open questions.

### Phase 1 — Vertical slice

Choose one stable, downloadable source—Denmark XML or UK monthly CSV is a good first checkpoint. Implement registry entry, acquisition, raw archival, parsing, canonical normalization, validation report, durable identity mapping, append-only observation, release manifest, and rerun idempotency. Do not start with APHIS browser automation; use the vertical slice to settle contracts.

### Phase 2 — Database and review mechanics

- Add migrations, indexes, PostGIS geography, uniqueness constraints on `(source_id, source_record_key, artifact_id)` and release membership.
- Add deterministic validation rules: required identity, country, coordinate bounds, duplicate source key, schema drift, row-count change, coordinate movement, and unexpected category.
- Add quarantine and a compact HTML/JSON review report with additions, removals, changes, merges/splits, warnings, and source-artifact links.
- Add correction and identity-decision workflows before importing ambiguous matches.

### Phase 3 — Roll out adapters

Implement source-by-source, preserving fixtures from real downloaded artifacts. Prioritize all sources currently represented in the website, not merely one adapter per country. For each adapter, prove: live acquisition, fixture parsing, source-to-canonical traceability, deterministic rerun, failure behavior, and a documented schedule/manual fallback.

### Phase 4 — Operate

Schedule weekly checks by default with source-specific overrides. Send actionable notifications only for failures, schema changes, unusual volume/coordinate changes, unresolved identity conflicts, or review-required releases. Keep the last validated release active on failure. Test backup restore and historical release reconstruction before any production integration.

## Scraper rules

- Prefer official bulk exports and APIs over DOM scraping.
- Respect robots/terms, identify the client, rate-limit, retry only safe failures, and cache downloads.
- Store request URL, parameters, headers needed for reproduction, retrieval timestamp, response status, and artifact hash.
- Never scrape through a frontend proxy just to make the website work.
- Use browser automation only where the official interface is the actual public access path; save the resulting export, not just parsed rows.
- Treat a changed layout or an empty result as a failed/review-required run, never as a valid zero-row dataset.
- Never geocode every refresh blindly. Cache normalized address queries and retain geocoder, response, timestamp, precision, and review status.

## Acceptance tests

The first vertical slice is complete when a fresh run can be reproduced solely from retained artifacts and pinned code/config; every accepted record links to source evidence; rejected rows are inspectable by authorized reviewers; rerunning creates no duplicate facility or observation; an unchanged source is recorded as a successful unchanged run; a failed run leaves the prior release available subject to current restrictions; and a named release can be reconstructed without fetching the upstream source. Sensitive payloads removed under ETHICS.md must not be reconstructed or republished. Test this separately through the policy checklist before production integration.

The data-phase milestone is complete when every legacy source has a tested automated or documented assisted path, unresolved sources are explicit, history and restoration work, and no production deployment is required.

### Future contributor data boundary

After government-source acquisition and release workflows are stable, support submissions as a separate claim system under [the submission plan](../governance/user-submitted-data.md). Factually unreviewed claims may be publicly queried after privacy/abuse screening through an explicitly selected, prominently labeled community profile. Unscreened, sensitive, or rejected material remains non-public. Separate source origin, community/project factual review events with outcomes, privacy/moderation eligibility, project approval, and actual publication; government origin is not a truth guarantee. Retain submissions only as permitted by ETHICS.md. All public surfaces and exports must preserve claim status and active restrictions, and keep opt-in community counts separate from default curated project totals.
