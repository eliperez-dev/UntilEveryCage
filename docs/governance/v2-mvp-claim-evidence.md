# V2 MVP claim-evidence matrix

Status: Sprint 1 working contract, reviewed 2026-09-16  
Machine-readable source: [v2-mvp-claim-evidence.json](v2-mvp-claim-evidence.json)

This matrix is the boundary between what V2 can honestly demonstrate and what
remains a design goal, a private prototype, or a human decision. It is governed
by [ETHICS.md](../ETHICS.md). A repository test, schema, or private rehearsal
is evidence of that bounded behavior; it is not evidence of deployment,
complete country coverage, factual truth, legal clearance, or operational
capacity beyond the stated scope.

## Status vocabulary

| Status | Meaning |
| --- | --- |
| `implemented_tested` | Code plus an automated test or deterministic rehearsal proves the behavior within the stated scope. |
| `implemented_not_exercised` | Code or a harness exists, but the full-scale, live, or operational exercise has not completed. |
| `prototype_only` | A schema, contract, research lane, or partial implementation exists; the promised product capability is not ready to claim. |
| `planned` | The policy or roadmap requires it, but implementation evidence is not present. |
| `human_policy` | An authorized maintainer, qualified advice, or operational review is required; software cannot replace the decision. |

## Matrix

The JSON file is canonical so tooling can reject missing evidence links or
invented status values. The table below is intentionally compact; each ID
links to the full claim, evidence paths, and limitations in the JSON source.

| ID | Area | Status | Short claim |
| --- | --- | --- | --- |
| `provenance.raw-lineage` | Provenance | `implemented_tested` | Raw artifacts and normalized records have a lineage model. |
| `provenance.append-only-history` | Provenance | `implemented_tested` | Ordinary processing appends evidence rather than silently overwriting it. |
| `provenance.deterministic-rerun` | Provenance | `implemented_tested` | Candidate imports are transactional, deterministic, and idempotent. |
| `provenance.legacy-separation` | Provenance | `implemented_tested` | Legacy evidence remains explicitly tagged and private in rehearsal. |
| `provenance.current-source-coverage` | Provenance | `prototype_only` | Fresh current-source coverage is not complete or locally available. |
| `ethics.governing-policy` | Ethics | `human_policy` | ETHICS.md governs the work; open controls remain explicitly open. |
| `publication.explicit-gate` | Publication | `implemented_tested` | Acquisition and government origin do not automatically publish. |
| `publication.public-projection` | Publication | `implemented_tested` | Public routes use eligible promoted projections, not raw evidence. |
| `publication.profile-separation` | Publication | `implemented_tested` | Official, secondary, and community profiles remain separate. |
| `publication.export-integrity` | Publication | `implemented_tested` | Exports carry bounded provenance and release-manifest metadata. |
| `privacy.public-suppression` | Privacy | `implemented_tested` | Tested suppression removes records from controlled public surfaces. |
| `privacy.exceptional-removal` | Privacy | `planned` | The full authorized removal/redaction workflow remains open. |
| `privacy.people-not-targets` | Safety | `human_policy` | Human review must prevent targeting and personal exposure. |
| `privacy.visitor-data` | Privacy | `planned` | Hosting, logs, tiles, geocoding, and visitor privacy are not fully audited. |
| `safety.uncertainty-labels` | Safety | `implemented_tested` | Unknown and approximate states remain explicit. |
| `safety.no-closure-inference` | Lifecycle | `implemented_tested` | Missing source rows do not become closure claims. |
| `lifecycle.history` | Lifecycle | `implemented_tested` | Lifecycle events and observations are separate and dated. |
| `geospatial.precision` | Geospatial | `implemented_tested` | Exact, coarse, unmapped, restricted, and geocoder states are distinct. |
| `geospatial.current-coverage` | Geospatial | `implemented_not_exercised` | Full current-corpus coordinate coverage is not yet measured. |
| `geospatial.provider-controls` | Geospatial | `implemented_tested` | Geocoder attempts retain provenance and review state. |
| `graph.source-qualified-identities` | Graph | `implemented_tested` | Crosswalks remain source-scoped and reviewable. |
| `graph.public-product` | Graph | `prototype_only` | No production public accountability graph is claimed yet. |
| `scale.indexed-discovery` | Scale | `implemented_tested` | Discovery plans were measured at 25k/100k/150k rows. |
| `scale.concurrent-http-capacity` | Scale | `implemented_not_exercised` | Full post-optimization concurrent HTTP evidence remains open. |
| `operations.resilience` | Operational | `implemented_not_exercised` | The 50k resilience harness exists; full Postgres rehearsal is pending. |
| `operations.health-diagnostics` | Operational | `planned` | Deployment observability and alerting are not yet proven. |
| `operations.release-authority` | Operational | `human_policy` | Publication authority and least privilege require operational ownership. |
| `rights.source-licensing` | Provenance | `human_policy` | Rights and attribution need source-specific human decisions. |
| `product.narrative` | Safety | `prototype_only` | The story is specified, not yet a finished public experience. |
| `product.reviewer-mvp` | Operational | `planned` | Independent reviewer usability is the later demonstrator goal. |

## Sprint 1 blockers

These items prevent declaring the Sprint 1 backend-proof goal complete:

1. Run the full post-optimization HTTP rehearsal and record concurrency and
   p95/p99 evidence.
2. Run the full disposable Postgres resilience rehearsal, or preserve a clear
   environment blocker and do not claim representative backup/restore proof.
3. Produce the current-corpus geospatial report from actual private normalized
   handoffs rather than the current `unavailable_private_handoff` result.
4. Keep the contract freeze and this matrix synchronized with the API schema,
   endpoint inventory, and tests.

The last item is automated by
[test_v2_mvp_contract.py](../../pipeline/tests/test_v2_mvp_contract.py). The
first three are execution/rehearsal gates, not documentation claims.
