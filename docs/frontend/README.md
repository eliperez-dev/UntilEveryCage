# V2 frontend design authority

Status: design specification for implementation planning, 2026-09-21

This folder defines the fresh V2 frontend direction. It is intentionally
documentation-only: it contains no Svelte, HTML, CSS, JavaScript, image, or
runtime asset changes. The existing V2 preview is disposable scaffolding. The
V1 behavior inventory remains the migration baseline; it is not a visual
constraint.

## Product decision

V2 has two primary destinations:

1. **Map** — the default, quiet place-first discovery experience.
2. **Database** — the dense, research-oriented search and export experience.

Facility detail is a stable URL and a shared drawer/split/fullscreen state, not
a third top-level destination. Graph connections are a public product feature
within map detail and database detail/search; they are not a separate social
network or a claim of universal identity.

The product principle is **quiet on first contact, powerful when investigated**.

## Reading order

- [principles and audiences](principles.md)
- [backend capability matrix](capability-matrix.json)
- [information architecture](information-architecture.md)
- [wireframes](wireframes.md)
- [interaction specification](interactions.md)
- [UI state matrix](ui-state-matrix.json)
- [content, terminology, and safety](content-and-safety.md)
- [visual direction and tokens](visual-direction.md)
- [performance and technology assessment](performance-and-technology.md)
- [MVP cuts and implementation sequence](implementation-sequence.md)
- [maintainer approval decisions](approval-decisions.md)

The normative V1 migration inventory is [v1-behavioral-contract.md](v1-behavioral-contract.md).
The product-level readiness tracker is [../PRODUCT-READINESS.md](../PRODUCT-READINESS.md).

## Non-negotiable boundaries

- Public output is release/profile scoped and suppression-aware.
- Exact and inferred graph edges are both discoverable, but probability is never
  presented as fact, ownership, universal identity, or supply-chain proof.
- Exact, city/coarse, and unmapped records are visibly distinct.
- Source origin, factual review, privacy screening, project approval, and
  publication are separate labels.
- A missing record does not prove closure or absence.
- Device location is optional and is not persisted in URLs or analytics.
- Private preview routes, raw evidence, credentials, and retained private rows
  never enter the public bundle. Public graph reads use only the release-scoped
  `/api/v2/graph/*` projection; the `/api/private/graph/*` routes remain
  operator-only.
