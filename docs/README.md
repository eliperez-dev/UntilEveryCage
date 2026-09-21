# Documentation guide

## Product readiness authority

[PRODUCT-READINESS.md](PRODUCT-READINESS.md) is the sole product-level source of
truth for V2 completeness, launch gates, and the overall roadmap. Supporting
documents may provide source, architecture, policy, or review evidence, but no
other active document is the overall V2 roadmap. Dated historical planning and
integration inputs are preserved in [archive/README.md](archive/README.md).

Documentation is grouped by the kind of decision it records:

- [ETHICS.md](ETHICS.md) — governing policy for credibility, provenance, uncertainty, privacy, and publication; takes precedence over conflicting supporting guidance.
- [Ethics summary](ETHICS-SUMMARY.md) — short orientation for people and agents; full policy remains authoritative.
- [Ethics changelog](governance/ethics-changelog.md) — versioned amendments and their rationale, distinct from implementation status.
- [Policy implementation checklist](governance/policy-implementation-todo.md) — outstanding runbook, retention, release-check, removal-test, and public-policy tasks. Unchecked tasks are not implemented guarantees.
- `architecture/` — cross-country pipeline, storage, and import design.
- `countries/<country>/` — source-specific workflows, classifications, and mapping decisions.
- `governance/` — provenance, review, publication, and user-submission policy.

Keep source-specific assumptions in the relevant country directory. Cross-country rules belong in `architecture/`; publication and credibility rules belong in `governance/`.
