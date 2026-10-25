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

## Private explorer and legacy analysis

`/private-graph.html` is a restricted research surface, not public navigation
or an authentication mechanism. Put it behind the private environment's access
control. It preserves source/date/conflicting observations and must not expose
addresses, raw payloads or targeting scores.

`python -m pipeline.common.d5_connection_analysis --manifest <aggregate.json>
--output <private-report.json>` is the historical aggregate analyzer. Optional
`--rows source_id=<private-handoff.jsonl>` supplies retained normalized or graph
handoffs. Output is counts and hashed review tokens, not source payloads.
It checks source-native IDs, VAT/CVR candidates, evidence links, conflicts and
multi-signal matches; it does not import, merge, geocode or publish. Its older
`review_required` analysis terminology is not a third graph connection state
and does not reinstate per-edge human approval. Accuracy requires real controls,
not synthetic scores represented as measured real precision or recall.

Candidate/merge/split lineage from migration 042 is append-only evidence.
It does not override the exact/inferred API or transfer source claims between
identities. Current public graph behavior is owned by the separate public
contract, not a dated D4/D5 analysis report.
