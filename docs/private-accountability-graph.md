# Private accountability-graph explorer

`/private-graph.html` is a restricted research surface for source-qualified
graph evidence. It is not linked from the public map and does not call the
`/api/v2` release routes. The private API is bounded to 100 search results and
200 observations per traversal, supports direction and depth controls, and
returns evidence-state fields separately (review, privacy, and publication).

The explorer preserves contradictory dated observations instead of resolving
them into an ownership or operational-status claim. It shows source IDs and
observation dates, confidence, unknown reasons, and notes when present. It
does not return addresses, coordinates, raw source payloads, risk scores,
targeting recommendations, or a claim that an entity owns or operates a site.

The database migrations remain the authority for append-only behavior and
source-scoped identity. Deployment must place this surface behind the
project's private environment access control; the route itself is not an
authentication mechanism.
