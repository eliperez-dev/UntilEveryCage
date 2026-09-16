# ADR: Accountability Graph Foundation

Status: accepted foundation; no production graph import or publication

## Decision

Use PostgreSQL tables and read-only views as a compact evidence graph. A
facility is a place/entity and an organization is a legal/operating entity;
neither is represented as the other. Source-native identifiers are retained in
`uec.source_entity_identifiers`. A crosswalk links two such identifiers with a
source-scoped decision (`candidate`, `accepted`, `disputed`, or `rejected`),
but never merges rows or creates a universal identity.

Relationship rows are dated observations, not mutable edges. They support
operator, owner, parent, brand, supplier, and customer assertions, including
explicit unknown observations. Conflicting observations remain queryable and
are not resolved by a latest-write overwrite. `uec.organization_relationship_current`
is only a convenience projection over retained observations.

Claims are append-only, source-backed facts or unknowns targeting one facility
or organization. `claim_support` links them to source records and/or preserved
artifacts and labels corroborating, contradicting, primary, and contextual
support. Inspection, violation, commitment, investigation, public funding,
and animal-count domains are reserved attachment points. Domain-specific
schemas, scoring, and workflow are deferred until evidence and governance
requirements are known.

All graph evidence carries storage, review, privacy, and publication state.
Released rows must be accepted, privacy-passed, tied to a release, and marked
released; public views additionally require a promoted release and exclude
active `uec.public_access_restricted` source records. This is compatibility
with the existing release/suppression controls, not a claim that a release is
automatically approved.

## Threats and mitigations

* Residential identities, doxxing, and mixed-use addresses: source values stay
  private; graph rows default to pending privacy and public projections require
  an explicit passed decision. Facility suppression propagates through the
  existing payload-free restriction views.
* Uncertain ownership, stale operator edges, and source disappearance: validity
  dates and observation time are separate; no disappearance implies closure;
  contradictions and rejected findings remain append-only.
* Community allegations and contested evidence: source origin/review/approval
  remain separate, and claim support records can be marked contradicting.
* Cross-source false matches: identifiers remain source-qualified and
  crosswalks are source-scoped, reviewable, and never universal IDs.
* Suppression reimports/restores: public graph views resolve current
  `public_access_restricted` state at query time; raw/private evidence is not
  exposed by these projections.

## Consequences

Country adapters can hand off a deterministic private candidate without knowing
the final canonical entity. A later importer may create a facility or
organization projection and append observations/claims. No graph database,
traversal language, automatic identity merge, relationship inference, or UI is
introduced in this sprint.
