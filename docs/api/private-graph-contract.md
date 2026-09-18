# Private accountability graph query contract

The authenticated endpoints under `/api/private/graph` are private review
tools. They require `X-UEC-Private-Graph-Token`; missing or invalid
authentication returns `404` to avoid endpoint discovery. The token is never
accepted on public routes.

`GET /entities` supports bounded name lookup (`q`, max `limit=100`) and a
stable UUID cursor. `GET /entities/{id}/neighborhood` supports bounded one- or
two-hop relationship traversal (`direction=in|out|both`, `depth=1|2`) with
allowlisted type/source/date filters and a maximum of 100 rows. The response
echoes the effective direction and depth so an operator can verify the query
that was executed. Queue endpoints expose only structured review metadata:
`contradictions`, `unresolved-identities`, `quarantine`, `claims`,
`rejected-candidates`, `suppression`, and `statistics`. Claim rows include
support/contradiction counts but never claim values or source payloads;
suppression rows expose only opaque case IDs and policy/status metadata.

All reads use deterministic tie-breakers, explicit limits, and the private
tables. Raw payloads, addresses, geocoder queries, and private notes are not
returned. No endpoint infers ownership, merges identities, computes targeting
scores, or publishes a release. Database/auth failures fail closed with a
versioned error envelope.
