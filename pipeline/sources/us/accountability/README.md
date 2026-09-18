# US accountability pilot

This is a private, synthetic/test-only pilot for the forthcoming graph
foundation. It writes candidate JSONL and a row-free manifest; it does not
write a graph database, create migrations, publish records, score targets, or
expose people or residential locations.

## Bounded source scope

The facility side starts with an FSIS establishment identifier and approval
identifier. The regulatory side starts with the already-modeled APHIS
registration and inspection identifiers. APHIS registrations, inspections,
annual reports, laboratories, and aggregate observations remain separate
evidence families. A link ledger may include a legal entity, parent, or brand
only when a source-native identifier and an explicit reviewed link event are
recorded.

SEC, EPA, and OSHA are deferred source routes in this pilot. The checked-in
fixture uses sanitized identifiers such as `CIK-TEST-001`; it is a contract
fixture, not a claim that a live filing, environmental record, or workplace
record was matched. A production run needs the applicable terms/reuse decision,
official URL, retrieval timestamp, checksum, and retained source artifact.

## Candidate contract

Each relationship in `candidate/relationships.jsonl` includes:

- typed subject/object references and source-native IDs;
- the evidence source and evidence-native ID;
- observation date and timezone-qualified retrieval date;
- relationship type, confidence, review state, match method, and evidence;
- temporal validity where ownership changes are observed;
- blocked publication and test-only markers.

Entities are emitted separately in `candidate/entities.jsonl`. The adapter
does not collapse a facility, establishment approval, operator, legal entity,
parent, brand, inspection, violation, enforcement, laboratory, or aggregate
observation. Name-only, address-only, phone-only, fuzzy, and geocoder matches
are not defensible and quarantine. Stale, conflicting, overlapping ownership,
and suppressed/restricted relationships also quarantine. Non-overlapping
ownership versions remain as history rather than overwriting one another.

`quarantined/relationships.jsonl` retains only the sanitized source values and
reason metadata inside the private run. No quarantine payload is checked in.

## Run boundary

First use the source-local assisted contracts in `pipeline/sources/us/fsis`
and `pipeline/sources/us/aphis`. FSIS direct 403 responses remain fail-closed;
the pilot never bypasses access controls. Then run the explicit reviewed link
ledger:

```text
python -m pipeline.sources.us.accountability.refresh \
  --raw <private-link-ledger.csv> \
  --run-dir <private-run-directory>
```

The run emits acquisition metadata, a candidate manifest, candidate JSONL,
quarantine JSONL, an assisted-capture contract, a run status, and a human
review packet. `release_state=not-created`, `publication_state=private-candidate`,
and `publication_gate=blocked` are invariants. Geocoding is disabled.

## Reconciliation

`reconcile.build_v1_crosswalk` compares only the exact FSIS establishment key
to FSIS facility candidates. It is row-free and observation-only: a missing
current observation is `not-observed`, never closure; it creates no identity,
suppression, or publication decision and does not inherit V1 assumptions.

## Current identity integration

`current_identity.py` consumes accepted records from the APHIS and FSIS
source-local adapters and emits a private, deterministic crosswalk handoff.
It links:

* APHIS registrations to annual reports, explicit amended-report versions, and
  inspections by certificate and/or customer number;
* FSIS establishments to FSIS observation records by establishment and/or
  approval number.

Each emitted edge retains both source-record keys, profile-specific artifact
hash/URL/retrieval provenance, the matched identifier types, observation dates,
confidence, review state, and independent private/publication gates. It does
not emit canonical IDs, merge source entities, geocode, or write a database.

Name/address agreement is limited to a bounded `candidate` with
`match_method=alternate_name_address_exact`, low confidence, and mandatory
review. Name-only, address-only, conflicting, ambiguous, missing-provenance,
and suppressed/restricted matches are quarantined. Alternate matching is
never attempted across APHIS and FSIS source families.

The checked-in `fixtures/current_identity.json` is synthetic and test-only.
No current real source artifact is committed. Existing V1-derived real rows
remain legacy regression inputs and are not promoted to current evidence.
