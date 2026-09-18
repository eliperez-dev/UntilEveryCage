# Private accountability graph query contract

The authenticated endpoints under `/api/private/graph` are private review
tools. They require `X-UEC-Private-Graph-Token`; missing or invalid
authentication returns `404` to avoid endpoint discovery. The token is never
accepted on public routes.

`GET /entities` supports bounded name lookup (`q`, max `limit=100`) and a
stable UUID cursor. `GET /entities/{id}/neighborhood` supports one-hop
relationship traversal only, with allowlisted type/source/date filters and a
maximum of 100 rows. Queue endpoints expose only structured review metadata:
`contradictions`, `unresolved-identities`, `quarantine`, and `statistics`.

All reads use deterministic tie-breakers, explicit limits, and the private
tables. Raw payloads, addresses, geocoder queries, and private notes are not
returned. No endpoint infers ownership, merges identities, computes targeting
scores, or publishes a release. Database/auth failures fail closed with a
versioned error envelope.
