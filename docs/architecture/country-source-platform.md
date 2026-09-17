# Country/source platform contract

The country platform is an offline, row-free registry view built from two
existing sources of truth:

- [`pipeline/source_registry.json`](../../pipeline/source_registry.json) owns
  source identity, URL, access method, cadence, expected schema, attribution
  notes, and known blockers.
- [`docs/source-status.json`](../source-status.json) owns the conservative
  metadata, acquisition, runtime-health, publication-eligibility, evidence,
  and next-action status for each source.

`pipeline/platform_registry.py` joins those files into country contracts and
source records. It currently materializes 234 sources across the registered
country/cross-border prefixes and is designed for the 100+ country / hundreds
of source target without copying every source row into a second hand-maintained
registry. `pipeline/platform_registry.json` records the grouping rule and
scale target.

## Contracts

`pipeline/contracts/country_contract.py` validates each country contract. Every
country must state its source IDs, scope, included and excluded populations,
non-closure disappearance semantics, attribution/terms status, owner-review
state, publication state, and readiness state. Completeness is explicitly
`not-claimed` until a separate evidence-backed decision changes it.

`pipeline/contracts/readiness.py` is the shared state machine. Acquisition or
runtime health never implies approval. A privately acquired lane can reach
`private-validated` and then stops at `awaiting-owner-review`; only an explicit
owner decision can move it to `approved-for-release`. The platform builder
currently records all derived lanes as owner-review pending and publication
blocked.

## Review packets and private preview

The existing v1 review packet schemas remain compatible. They now carry a
row-free `platform` context with coverage, attribution, readiness, and the
explicit publication boundary. The packet states that it cannot approve or
promote a release. Address, coordinate, source-row, geocoder, and contact
payloads are rejected from the packet.

`pipeline/scripts/maintenance/rehearse_candidate_private_frontend.py` checks
an aggregate candidate manifest and, optionally, the authenticated
`/api/dev/preview/candidates` endpoint. It verifies `test_only` and
`private_preview` metadata, treats missing private handoffs as unavailable
rather than zero coverage, and emits only aggregate evidence. The helper is
available through:

```text
python scripts/dev.py private-frontend <candidate-manifest> <output-report>
python scripts/dev.py platform-registry
```

These commands support private staging and rehearsal only. They do not create,
approve, promote, or publish a release. A human owner remains responsible for
terms, privacy, factual review, project approval, and publication decisions.
