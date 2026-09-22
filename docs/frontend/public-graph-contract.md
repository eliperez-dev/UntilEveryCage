# Public graph contract and frontend view-model boundary

This document distinguishes the currently implemented public graph wire
contract from the proposed shared-record frontend abstraction. The graph is a
public, release-gated, read-only projection. It is not a direct query of
private evidence. The private graph routes remain operator-only.

## Implemented endpoints

The frontend must call these routes exactly as implemented:

* `GET /api/v2/graph/connections`
* `GET /api/v2/graph/entities`
* `GET /api/v2/graph/entities/{entity_id}/neighborhood`

All are GET-only, bounded, and use the `v2-graph-v1` envelope. The page maximum
is 100. Cursors are opaque UUID continuation tokens for the selected promoted
release snapshot. Responses include `release_id` and `ruleset_version`; clients
must not combine pages from different snapshots. `profile` selects the current
promoted release/profile; the current API does not let the frontend choose an
arbitrary historical release ID.

Implemented query controls are `profile`, `connection_type` (`exact` or
`inferred`), `min_confidence`, `max_confidence`, one `confidence_band` value
(`exact`, `high`, `medium`, or `low`), `include_conflicting`, `source_id`,
`entity_id`, `cursor`, and `limit`. Entity search additionally accepts `q` and
`entity_type`. The frontend may offer multi-band filters by issuing separate
requests or composing already loaded pages; it must not claim that the current
endpoint accepts a repeated/comma-separated `confidence_band` parameter.

## Implemented edge fields

The current public DTO uses these names. Frontend view-model aliases are
allowed internally, but must be explicit and tested:

| Wire field | Frontend meaning |
| --- | --- |
| `connection_edge_id` | Stable public edge key |
| `from`, `to` | Source-qualified endpoint summaries |
| `relationship_type` | Typed relationship wording with source semantics |
| `connection_type` | `exact` or `inferred` |
| `confidence` | Deterministic ruleset score, not a probability |
| `confidence_band` | `exact`, `high`, `medium`, or `low` |
| `match_method` | Human-readable method label |
| `signals` | Grouped safe signal data |
| `contradictions` | Safe contradictory signal data |
| `provenance` | Source IDs, observed date, and release ID |
| `source_references` | Publication-safe source references |
| `observed_at`, `computed_at` | Dates with their actual semantics |
| `ruleset` | Ruleset identifier used to calculate the score |
| `conflicting` | Whether contradictory evidence is present |
| `publication_warning`, `disclaimer` | Persistent public limitation copy |

Endpoint fields currently include `entity_id`, `entity_type` (`facility` or
`organization`), `source_id`, `identifier_type`, and `source_identifier`. Entity
summaries currently include `entity_id`, `entity_type`, `display_name`, and
`country_code`. They do not currently carry canonical URLs, map precision, or a
record-type union beyond facility/organization.

## Proposed shared-record extensions

The frontend design may compose a richer Record model, but these are future
contract work, not current API promises:

- `GET /api/v2/records/{record_id}` and record-wide global search;
- canonical URLs on graph entity summaries;
- public evidence, inspection/event, and source-record DTOs;
- graph endpoints that return richer non-facility record summaries;
- historical release selection by explicit release ID;
- a repeated/multi-value confidence-band query.

Do not invent compatibility aliases for routes that do not exist. A current
facility entity can be resolved through the existing location API only when its
public identity mapping is explicit. An organization node may be displayed as
a graph summary and selected in the canvas, but it does not gain a fake detail
page until a public organization/record endpoint exists. These gaps are tracked
in the frontend capability matrix and the single product readiness tracker.

## Edge semantics

`exact` means the source-backed edge has an explicit shared identifier or source
assertion. `inferred` means a versioned deterministic ruleset combined signals.
The `confidence` number is a ruleset estimate, explicitly not a measured
probability. Every inferred row includes method, signal groups, contradictions,
source IDs, observation date, ruleset, and the disclaimer:

> Confidence is a deterministic ruleset estimate, not a measured probability.
> An inferred connection is not proof of ownership, identity, or supply-chain
> control.

All exact, high-, medium-, and low-band rows may be queried. Conflicting rows
are excluded by default and become visible only when
`include_conflicting=true`. Suppressed rows are never selectable. There is no
`human_confirmed` state. Edges do not merge universal identities, transfer
claims, or assert ownership without source evidence. Raw source-record payloads,
private queue state, suppression reasons, and review identities are never
returned.

## Visualization boundary

The frontend may render a bounded one-hop node/edge visualization from the
implemented neighborhood response. For MVP:

- render at most 50 nodes and 100 edges on the canvas;
- use deterministic ordering, preserving all confidence bands in the loaded
  response and never silently dropping low-confidence edges;
- keep the accessible edge list as the authoritative alternative, paginated at
  the API's maximum of 100;
- show a persistent “bounded neighborhood” / “canvas limited to the first 100
  edges” disclosure even when the response has no cursor, because the canvas
  cap is a presentation limit rather than a completeness claim; offer a Load
  more action when a cursor remains;
- selecting an edge reveals the exact wire fields above;
- selecting a facility node may resolve to its existing public location detail;
  an organization node is selectable as a summary until a public record route
  exists.

The user's shared-parent example is not a direct A→B fact by default. If A and
B both point to parent organization P, the supported baseline is A → P, then
select P to inspect its neighborhood and reach B. A direct derived A → B edge
may be added only under a future, explicitly versioned graph rule with its own
provenance and confidence semantics; the frontend must not invent or compound
that edge merely because two nodes share a visible parent.

The canvas must not draw graph edges as geographic lines on the map unless a
selected facility explicitly requests a separate, clearly labelled map overlay.
No endpoint permits public traversal of arbitrary private nodes. Empty graph
output is valid and is not a failure.
