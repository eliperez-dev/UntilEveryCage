# Public accountability graph contract

Status: additive V2 frontend contract, release-gated and read-only.

The public graph is a release-scoped projection built from
`uec.graph_connection_edges`. It is not a direct query of private evidence.
A request is evaluated against one promoted,
non-test release/profile and returns only source-qualified endpoints that
resolve through that same release's public read model and privacy gates. Private
graph facility identifiers map to canonical facility UUIDs only through an
unambiguous source-record identity already present in the selected release;
ingestion does not release those identifiers. If no eligible
release exists, the API returns `404 release_not_found`; it never falls back to
private or candidate rows.

## Endpoints

* `GET /api/v2/graph/connections`
* `GET /api/v2/graph/entities`
* `GET /api/v2/graph/entities/{entity_id}/neighborhood`

All endpoints are GET-only and bounded; explicit handler errors use the normal
`{api_version, error}` envelope. Framework extraction failures may differ.
The graph page maximum is 100 (default 50). Cursors are opaque UUID continuation
tokens for the selected release snapshot. A response includes `release_id` and
`ruleset_version`; clients must not combine pages from different snapshots.

Connection filters are `profile`, `connection_type` (`exact` or `inferred`),
`min_confidence`, `max_confidence`, `confidence_band` (`exact`, `high`,
`medium`, `low`), `include_conflicting`, `source_id`, `entity_id`, `cursor`,
and `limit`. Entity search additionally accepts `q` and `entity_type`.

Effective entity-search inputs are `profile`, `q`, `entity_type`, `cursor` and
`limit`; connection-specific filters do not apply to that route. Neighborhood
returns connections adjacent to its path entity using the connection filters.
Although `direction` and `depth` are validated, they currently do not change
traversal or provide multi-hop results. Graph routes select the latest eligible
profile. Supplying `release_id` pins the query to that release when it is an
eligible promoted release or a validated release already recorded in public
release history. Refresh pagination when response release metadata changes.
The [public OpenAPI document](public-openapi.json) exposes effective inputs.

The database retains the historical `probable` and `possible` labels. The
public contract normalizes those to `high` and `medium`; this is a display band,
not a new probability model.

Each endpoint resolves unambiguously to a canonical facility or organization
UUID in the same selected release. Facility endpoints must map by their source
record lineage to exactly one facility in that release's public discovery
projection. The Italy 853/2004 adapter additionally binds by exact source
artifact plus unique native recognition-number/activity-code pair because its
current row key differs from the approved snapshot's historical row key;
repeated candidate pairs and ambiguous release mappings are excluded. This
adds graph identifier metadata only and leaves review/privacy/release states
unchanged. Inferred facility-to-facility edges require both endpoints to
resolve independently through that release. A public business-organization
node is eligible only when a VAT-class identifier and an eligible facility
assertion occur on the same approved source record. Exact organization edges
remain limited to source-reported operator relationships; inferred edges may
connect independently eligible business nodes when their evidence records
also pass the selected-release support gate. These edges are not ownership
claims. Organization nodes are returned with an opaque source-scoped ID and no
name or identifier value.
Natural-person fiscal-code identifiers are never exposed. The DTO's required
`source_identifier` string is an opaque `entity:<UUID>` token derived from the
release-qualified canonical endpoint UUID; raw source identifier values remain
restricted. Missing, ambiguous, suppressed, or
cross-release endpoints are excluded.

An edge is selectable only when it has nonempty supporting source references
that resolve to exact source-record versions in that release. Direct release
members and append-only rows in `uec.graph_record_release_bindings` are
accepted; a binding is valid only when its private and canonical records retain
the same source and artifact and its canonical record is still eligible in the
selected release. Shared identifiers alone do not qualify edge evidence.
Missing version IDs, unbound support records, suppressed edges, and support
from another artifact or release are excluded.

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

The indexed graph projection is built explicitly for a release with
`pipeline/scripts/maintenance/build-public-graph-projection.py`. It reuses the
same release, endpoint, and support selector as the graph API. Edge generation
changes invalidate the active projection; read-time release, support, rights,
and suppression gates remain live. Endpoint/source-assertion changes invalidate
the projection through a graph-generation counter. A stale projection therefore
fails closed until rebuilt. Projection v2 stores each exact source-qualified
endpoint and its anchors once, then references that opaque build-local endpoint
from each edge. The qualification retains source, identifier type, native
identifier, entity type, and public entity UUID during the private build; native
identifier values are not persisted in serving tables or the package. Migration
078 makes prior v1 projections fail closed until rebuilt. Its API role can read
the safe current projection view but not private edges, identifiers, support
references, or anchor records.

The selected-column `release_serving` package now includes this safe projection
and migration 077 adds its serving view and exact read-only grant. This supports
a local production-package rehearsal only; no Render deployment or hosted
graph access is authorized or claimed by this contract update.
