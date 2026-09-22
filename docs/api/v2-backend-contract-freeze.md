# V2 backend contract freeze

This page records the backend boundary consumed by the V2 frontend. The
machine-readable summary is [`v2-backend-contract-freeze.json`](v2-backend-contract-freeze.json);
the public location wire remains defined by [`v2-contract.json`](v2-contract.json)
and [`v2-location.schema.json`](v2-location.schema.json).

## Public location DTO

`GET /api/v2/locations` and `GET /api/v2/locations/{facility_id}` return only
the selected promoted release/profile projection. The DTO fields, nullability,
controlled values, provenance fields, and error envelope are frozen by the
location schema. A list uses `{api_version, data, meta}` and includes a
deterministic `next_cursor`; detail uses the same envelope. No endpoint reads
raw candidate/evidence tables.

List pagination defaults to 100 and is capped at 1,000. `cursor` is preferred,
`offset` remains a bounded compatibility parameter, and they are mutually
exclusive. Cursor pages are scoped to the selected `(profile, release_id,
ruleset_version, query)` snapshot. A missing promoted release is an empty
successful list, while manifest/export absence is an error according to the
public contract.

## Private graph DTO

The authenticated private graph API is bounded and never part of the public
projection. Each connection has source-qualified endpoints, a stable edge key,
one of exactly two `connection_type` values, provenance/evidence references,
confidence (when applicable), explanation/signals, ruleset version, observed
time, conflict/suppression flags, and a disclaimer.

The only connection states are:

- `exact`: a source assertion or authoritative shared identifier.
- `inferred`: an algorithmic ruleset result with a confidence estimate, signal
  explanation, contradiction handling, and explicit uncertainty disclaimer.

There is deliberately no `human_confirmed` state. Human review may be required
for a release, source terms, privacy, factual claims, or publication, but it is
not required to make a private exact/inferred edge exist. Inferred edges are
visible through confidence/type/conflict filters and never imply universal
identity, ownership, claim transfer, closure, targeting, or publication.

Private graph responses use the same versioned error envelope shape and a
maximum page size of 100. `cursor` is deterministic and source/entity/type,
confidence, conflict, and suppression filters are additive. A page limit is a
response bound, not a graph storage cap; complete traversal requires cursors.

## Release, suppression, and public-zero boundary

Release/profile selection, source rights, privacy screening, factual review,
project approval, promotion, and publication remain independent gates. Current
suppression is authoritative on reads and applies to APIs, maps, exports,
history, reimports, and restores. Private graph/candidate rows remain
`not_eligible` until an explicit release projection permits them. The public
relationship projection is empty unless a separately approved public contract
adds it; private graph existence never promotes a row or edge.

No contract surface performs universal entity merging, automatic claim
transfer, human-confirmed graph state, or APHIS-to-FSIS automatic linking.
Additive changes require schema/contract tests; breaking changes require a new
contract identifier and migration path.
