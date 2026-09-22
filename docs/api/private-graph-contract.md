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

## Connection edge semantics

The graph connection API exposes exactly two `connection_type` values:

- `exact` — an authoritative source assertion or shared source identifier;
- `inferred` — an algorithmic ruleset result with confidence, supporting
  signals, contradiction handling, source-qualified evidence references, and
  an uncertainty disclaimer.

There is no `human_confirmed` connection state. Human review may gate source
rights, privacy, factual claims, release approval, or publication, but it does
not gate private exact/inferred persistence. Inferred edges remain visible to
private callers through type, confidence, conflict, source/entity, suppression,
and cursor filters. They never merge universal identities, transfer claims,
infer ownership/closure, authorize publication, or create APHIS-to-FSIS links.

The private connection page maximum is 100 and the cursor is deterministic;
the page bound is not a storage cap. A versioned `{api_version, error:{code,
message}}` envelope is used for invalid queries, missing authorization, and
database failures. Current suppression is applied before returning a page.
Private graph rows are never part of the public location, map, export, or
release projection unless a separate approved contract explicitly adds them.
