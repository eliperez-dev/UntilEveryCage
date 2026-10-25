# Documentation hub

Start with [AGENTS.md](../AGENTS.md), [ETHICS.md](ETHICS.md) and
[VISION.md](VISION.md), then this hub and only the task's references below.

## Current instructions

| Task | Read |
| --- | --- |
| Product state, launch requirements, future features | [PRODUCT-READINESS.md](PRODUCT-READINESS.md): the only product roadmap |
| Source readiness, metadata, evidence, next action | [source-status.json](source-status.json): the only source inventory; [reading guide](source-status.md) |
| Frontend behavior, layout and exact copy | [frontend/README.md](frontend/README.md): the current frontend specification |
| Local setup and real-data development | [development.md](development.md) |
| Adding a source | [pipeline onboarding](../pipeline/ONBOARDING.md), [adapter template](../pipeline/contracts/SOURCE-ADAPTER-TEMPLATE.md) |
| Coordinating agents | [parallel-agent-workflow.md](operations/parallel-agent-workflow.md) |
| Render deployment, configuration and recovery | [production operations](deployment/production-operations.md) |

## Task references

| Area | Index |
| --- | --- |
| Country research and source field mappings | [countries/README.md](countries/README.md) |
| Architecture, imports, releases and graph model | [architecture/README.md](architecture/README.md) |
| API routes and machine schemas | [api/README.md](api/README.md) |
| Refresh, geocoding and operator commands | [operations/README.md](operations/README.md) |
| Restrictions, contributions and visitor privacy | [governance/README.md](governance/README.md) |
| Performance and diagnostic methods | [performance/README.md](performance/README.md) |
| Aggregate statistics | [statistics/aggregate-statistics-spec.md](statistics/aggregate-statistics-spec.md) |

## Where durable facts live

Update the existing owner above rather than creating another document.
Product completion belongs only in the roadmap; source state belongs only in
the source inventory. Source URLs, field mappings and rights evidence belong
in the relevant country page, descriptor, terms record or aggregate manifest.
The machine registry defines executable source identities; it is not a second
readiness tracker.

Do not create agent plans, sprint reports, handoffs, duplicate review packets,
date-named status documents or a separate frontend roadmap. Assignments and
progress belong in the conversation; completed work is recoverable in Git.
Do not move discarded reports into an archive just to retain them.

Keep useful contracts, source research, policy decisions and operational
instructions. A new document requires a distinct purpose and a link from its
owning index. Historical machine evidence and frozen test contracts are
references, not current instructions. Do not restore old UI or reopen release
approvals because a dated reference describes a different state.

Labels: **Canonical** owns current instructions; **Reference** explains a
specific method; **Generated** is machine-produced evidence or a schema;
**Historical evidence** describes a dated run, not current readiness.
