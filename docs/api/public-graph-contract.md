# Public accountability graph contract

Status: additive V2 frontend contract, release-gated and read-only.

The public graph is a projection of `uec.graph_connection_edges`. It is not a
direct query of private evidence. A request is evaluated against one promoted,
non-test release/profile and returns only source-qualified endpoints whose
identifiers passed that same release's public and privacy gates. If no eligible
release exists, the API returns `404 release_not_found`; it never falls back to
private or candidate rows.

## Endpoints

* `GET /api/v2/graph/connections`
* `GET /api/v2/graph/entities`
* `GET /api/v2/graph/entities/{entity_id}/neighborhood`

All endpoints are GET-only, bounded, and use the normal `{api_version, error}`
envelope. The graph page maximum is 100. Cursors are opaque UUID continuation
tokens for the selected release snapshot. A response includes `release_id` and
`ruleset_version`; clients must not combine pages from different snapshots.

Connection filters are `profile`, `connection_type` (`exact` or `inferred`),
`min_confidence`, `max_confidence`, `confidence_band` (`exact`, `high`,
`medium`, `low`), `include_conflicting`, `source_id`, `entity_id`, `cursor`,
and `limit`. Entity search additionally accepts `q` and `entity_type`.

The database retains the historical `probable` and `possible` labels. The
public contract normalizes those to `high` and `medium`; this is a display band,
not a new probability model.

## Edge semantics

`exact` means that the source-backed edge has an explicit shared identifier or
source assertion. `inferred` means that a versioned deterministic ruleset
combined signals. The `confidence` number is a ruleset estimate, explicitly not
a measured probability. Every inferred row includes its method, signal groups,
contradictions, source IDs, observation date, ruleset, and the disclaimer:

> Confidence is a deterministic ruleset estimate, not a measured probability.
> An inferred connection is not proof of ownership, identity, or supply-chain
> control.

All exact, high-, medium-, and low-band rows may be queried. Conflicting rows
are excluded by default and become visible only when `include_conflicting=true`.
Suppressed rows are never selectable. There is no `human_confirmed` state.
Edges do not merge universal identities, transfer claims, or assert ownership
without source evidence. Raw source-record payloads, private queue state,
suppression reasons, and review identities are never returned.

The graph is a public product capability only after a named release is promoted.
Publication approval, source rights, privacy screening, factual review, and
release membership remain independent gates. A public graph response does not
certify the truth or completeness of a relationship.
