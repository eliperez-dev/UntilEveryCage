# F0 frontend reset safety ledger

Status: reset boundary and acceptance record, 2026-09-22. This page records
the disposable V2 preview reset; it does not authorize a backend, API, data,
or V1 change. [PRODUCT-READINESS.md](PRODUCT-READINESS.md) remains the sole
product readiness and roadmap authority. The durable design and future stages
remain in [the frontend design package](frontend/README.md), its
[implementation sequence](frontend/implementation-sequence.md), and
[roadmap](frontend/roadmap.md).

## Recovery point and reference boundary

The complete pre-reset tree is preserved by the annotated tag
`archive/v2-preview-before-reset-2026-09-22`, which resolves to commit
`60c7a750ba5869185580ad19fdf7373597e472fc`. This tag is the recovery point for
the V2 preview. Do not move or recreate it. Verify it with
`git rev-parse "archive/v2-preview-before-reset-2026-09-22^{commit}"`.

The immutable V1 reference is that same checkpoint, especially the production
vanilla-JavaScript app under `static/` and the behavior inventory in
`docs/frontend/v1-behavioral-contract.{md,json}`. The tag preserves the exact
files for comparison; the contract says what user-critical behavior a future
V2 must preserve or intentionally replace. It is not permission to edit V1 or
to copy its unreviewed data into a V2 bundle.

## Reset ledger

| Disposition | Scope | Reason / boundary |
| --- | --- | --- |
| Intentionally removed from the active build | The old Svelte preview application and its preview-only presentation, shell, styling, fixture UI, and local preview wiring in `frontend/src/`. | This was disposable launchpad code, not the accepted production frontend. Its pre-reset implementation remains recoverable from the archive tag. |
| Intentionally retired when no longer referenced | Preview-only scripts, tests, build configuration, and package dependencies in `frontend/` that exist solely to start, stage, or verify the removed preview. | Remove only after checking each item for shared contract or safety coverage. Keep/add the small F0 boundary guard described below; do not discard checks that protect the V1/API boundary. |
| Preserved as product authority | `docs/frontend/**`, including the design decisions, Map/Database information architecture, interaction and safety requirements, capability matrix, V1 contract, implementation sequence, and future roadmap. | These are the approved design and staged work, not the disposable preview implementation. |
| Preserved as public V1 and migration reference | All `static/**` files, including `static/index.html`, `static/app.js`, `static/style.css`, `static/modules/**`, locale files, existing pages, and the V1-serving build/deploy path. | V1 remains the public product and rollback target until a controlled cutover is approved. The reset must not edit or remove this tree. |
| Preserved as backend/API contract | `src/**`, `pipeline/**`, `Cargo.toml`, `Cargo.lock`, `docs/api/**`, and backend schemas, migrations, and contracts. | F0 consumes the frozen contracts. It adds no endpoint, DTO, migration, backend behavior, or contract change. |
| Preserved as evidence and data | `data/**`, `static_data/**`, `dirty-datasets/**`, `Old CSVs/**`, `Old scripts/**`, and source/release evidence. | No dataset, manifest, migration history, source artifact, or release state is reset, rewritten, or promoted by F0. |
| Preserved as separate operator surfaces | Existing private review and graph tools in `static/` and their backend controls. | They are not the disposable V2 public preview and remain subject to their existing access and ethics boundaries. |

The removal scope is deliberately limited to the old preview runtime. If a
file under `frontend/` supports a frozen API contract, a V1 safety boundary,
or an approved future-stage requirement, retain it or replace that check in
the same change before removing it. Preview staging output is disposable and
must remain ignored/local; it is not a release artifact.

## Reset acceptance criteria

F0 is accepted only when all of these statements are demonstrated in the
integrated change:

1. The archive tag resolves to the recorded commit and remains available.
2. The reset diff is limited to the old V2 preview runtime and this readiness /
   safety documentation. V1 runtime, backend/API, pipeline, and data/evidence
   paths are unchanged.
3. An automated boundary check compares the V1 production tree against the
   archive checkpoint and fails on changed, added, or removed V1 files. A
   scoped diff check also rejects changes to `src/`, `pipeline/`, `data/`,
   `static_data/`, frozen API contracts, and migration history. Documentation
   changes to `docs/PRODUCT-READINESS.md` and this ledger are allowed.
4. The new starting shell builds from synthetic fixtures only. It does not
   stage private rows, call private preview APIs by default, introduce a live
   data path, or change publication state.
5. The two approved destinations (Map and Database), shared record/detail
   model, the V1 migration contract, and later roadmap stages remain linked
   and discoverable after preview files are removed.
6. The product readiness page continues to identify V1 as public, V2 as
   unfinished/private, and the explicit later gates for private release,
   end-to-end trial, parallel comparison, and controlled cutover.

The guard is a reset-scoped regression check, not a claim that V1 behavior is
correct or that the future V2 is release-ready. Run it with the frontend's
focused boundary/documentation checks before integrating F0.

## Safety coverage after the shell reset

The structural shell has no record, search, export, location, or private-preview
data flow. Browser checks therefore assert that public and preview-looking URLs
stay local, render no records or controls, and make no API requests. Contract
behavior remains covered outside that empty shell: frontend unit tests cover
profile validation, malformed and failed responses, query/cursor requests,
abort handling, export profile/origin checks, and stale-response generations;
the repository API E2E suites continue to cover publication profiles,
suppression, private preview authorization, and CSV output. When a future UI
connects those contracts, restore interaction-level coverage for each exposed
flow before removing or replacing its contract tests.

## Post-reset build sequence

The reset is a clean implementation starting point; it does not close the
frontend milestone. Continue in this order, keeping the completion status and
release gates in [PRODUCT-READINESS.md](PRODUCT-READINESS.md):

1. **Shell and route state:** establish the approved Map and Database routes,
   shared design tokens, responsive shell, release context, URL state, and
   accessible loading/error announcements. Use synthetic fixtures.
2. **Contracts and repositories:** consume the frozen public DTOs through
   typed clients; keep unsupported evidence, event, source-record, and
   all-record search capabilities visibly gated by the readiness gap ledger.
3. **Database and semantic list:** implement search, facets, deterministic
   rows, cursor paging, bounded exports, and an accessible list before map
   polish; disclose current facility/location field limits.
4. **Map and shared details:** benchmark the map adapter on synthetic scale
   fixtures; synchronize map/list state, precision strata, filters, stable
   links, shared details, and the supported release-scoped one-hop graph.
5. **Quality and release gates:** complete keyboard and screen-reader review,
   small-screen and zoom checks, performance budgets, content/privacy/export
   review, and suppression/revocation behavior. Then run the private end-to-end
   trial and V1/V2 parallel comparison. Public cutover remains a separate,
   explicit maintainer decision with rollback available.

See [implementation-sequence.md](frontend/implementation-sequence.md) for the
full phase-level requirements and [roadmap.md](frontend/roadmap.md) for
sequenced later features; neither is replaced by this reset ledger.
