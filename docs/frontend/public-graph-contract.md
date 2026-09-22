# Public graph contract required for frontend implementation

This is the frontend integration contract for the release-scoped read-only
projection. The implementation is additive to the private evidence graph: the
`/api/v2/graph/*` routes expose only rows whose endpoints pass the selected
promoted release/profile and current suppression/privacy gates. The
`/api/private/graph/*` handlers remain operator-only.

## Minimum MVP route

`GET /api/v2/locations/{facility_id}/connections`

Required query controls:

- `profile` (default official; explicit community/secondary only);
- `connection_type` (`exact` or `inferred`);
- `min_confidence`;
- `confidence_band` (repeatable or comma-separated);
- `include_conflicting` (default true for transparency);
- `cursor` and bounded `limit`;
- optional relationship/source filters supported by the release.

The response must use the normal V2 envelope and carry release/profile scope.
The endpoint is a read-only projection; it must not reveal private graph routes,
raw evidence, restricted identifiers, or unpublished rows.

## Minimum edge fields

| Field | Meaning |
| --- | --- |
| `edge_id` | Stable public edge identifier within the release/profile |
| `from` / `to` | Public-safe endpoint summaries, not private source identities |
| `relationship_type` | Typed relationship wording with source semantics preserved |
| `connection_type` | `exact` or `inferred` |
| `confidence` | Numeric deterministic score, nullable only for exact if needed |
| `confidence_band` | `exact`, `high`, `medium`, or `low` |
| `match_method` | Human-readable method label |
| `supporting_signals` | Grouped safe signals, not raw restricted values |
| `contradictions` | Safe contradictory signal labels/counts |
| `source_references` | Publication-safe source names/links/observation context |
| `ruleset_version` | Version used to compute the edge |
| `observed_at` / `computed_at` | Dates with their actual semantics |
| `publication_warning` | Persistent inference/profile limitation text |

## Safety invariants

- Release membership, profile eligibility, current suppression, and privacy
  checks are evaluated for every response.
- Exact edges mean an authoritative shared identifier or explicit source
  assertion; they do not imply universal identity beyond that evidence.
- Inferred edges are algorithmic estimates. They are never labeled confirmed,
  ownership, same-entity, or supply-chain proof.
- Conflicting edges remain visible and filterable with a contradiction label.
- Exact edges already represented by the same source assertion are not duplicated
  as inferred edges.
- No human-confirmed state is introduced.
- No endpoint allows a public user to traverse arbitrary private nodes.
- Empty graph output is a valid result and is not a failure.

## Frontend integration gate

The frontend implementation may use a fixture adapter, but the fixture must
validate the same field semantics. Production wiring is blocked until backend
tests prove public/private separation, suppression across graph reads, profile
separation, cursor determinism, and safe edge explanations.
