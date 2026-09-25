# Documentation hub

Read in this order for every task: [`AGENTS.md`](../AGENTS.md) →
[`ETHICS.md`](ETHICS.md) → [`VISION.md`](VISION.md) → this hub → the task
documents selected below. Policy governs all work; the vision describes intent,
not current readiness.

## Where durable facts live

| Fact or decision | Canonical destination |
| --- | --- |
| Product purpose and enduring direction | [VISION.md](VISION.md) — **Canonical** |
| Policy, privacy, provenance, and publication | [ETHICS.md](ETHICS.md) — **Canonical** |
| Product readiness, launch gates, and roadmap | [PRODUCT-READINESS.md](PRODUCT-READINESS.md) — **Canonical** |
| Current source-level evidence status | [source-status.md](source-status.md) and [source-status.json](source-status.json) — **Canonical** |
| Source-specific facts, terms, provenance, and scope | Country reconnaissance, source descriptors/crosswalks, terms reviews, manifests, and the relevant canonical source page — **Canonical** or **Generated** as marked in the owning index |
| Implementation claims | [claim/evidence ledger](governance/v2-mvp-claim-evidence.json) — **Generated** from repository evidence |

Write durable facts into their canonical destination and link them from the
owning index. Do not create agent plans, temporary plans, sprint/kickoff/
handoff/status Markdown, duplicate review packets, or date-named progress docs.
Task progress belongs in the conversation and Git history. A new document needs
a named owner, a specific purpose, and an entry in the owning tree/index. Source
facts go in the source descriptor, terms record, manifest, or canonical source
page; do not copy the same facts into another status ledger. Retain exceptional
historical evidence only when its unique evidentiary value cannot be represented
by the active canonical record.

## Documentation map

| Area | Start here | Contents and status |
| --- | --- | --- |
| Architecture | [architecture/README.md](architecture/README.md) | Cross-source data model, API contracts, import/release, and V1 migration — mostly **Canonical**; superseded decision records are marked **Historical evidence**. |
| Sources | [sources/README.md](sources/README.md) and [countries/README.md](countries/README.md) | Country reconnaissance, descriptors, terms, lineage, and acquisition evidence — **Canonical**, **Reference**, or **Generated** per entry. |
| Frontend | [frontend/README.md](frontend/README.md) | Current V2 interaction, visual, safety, and implementation specifications — **Canonical**; V1 contract is **Reference** for migration. |
| Operations | [operations/README.md](operations/README.md) | Development, deployment, source refresh, geocoding, recovery, and performance — **Canonical** runbooks/specifications. |
| Governance | [governance/README.md](governance/README.md) | Ethics amendments, implementation gaps, privacy, suppression, and evidence — **Canonical** policy/records; machine ledgers are **Generated**. |
| Product readiness | [PRODUCT-READINESS.md](PRODUCT-READINESS.md) | Sole product completion/roadmap authority — **Canonical**; [source status](source-status.md) remains source-scoped. |
| Historical evidence | [archive/README.md](archive/README.md) | Exceptional unique audits/rehearsals only — **Historical evidence**; not a source of current direction or readiness. |

### Labels

- **Canonical** — authoritative current fact, policy, specification, or decision.
- **Reference** — useful implementation detail or migration baseline subordinate
  to a canonical authority.
- **Generated** — machine-produced output; update its source and regenerate it.
- **Historical evidence** — immutable evidence for a dated event; not current
  guidance. Ordinary plans, status notes, and duplicate packets are deleted,
  not archived.

Country reconnaissance currently lives at `country-recon-<code>.md`, with
detailed country directories under [`countries/`](countries/README.md). Use the
[source index](sources/README.md) to find the appropriate country page. Do not
infer current source status from historical evidence.
