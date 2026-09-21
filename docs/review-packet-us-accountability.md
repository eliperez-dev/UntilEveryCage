# US accountability pilot review packet

Status: private/test-only implementation evidence, not publication approval.

## What this pilot proves

The bounded synthetic fixture demonstrates a deterministic candidate contract
for 12 relationships and 13 distinct typed entities. It keeps FSIS facility
and establishment-approval identifiers separate from APHIS operator and
inspection observations. It also represents legal entity, parent, brand,
violation, enforcement, laboratory, and aggregate observation nodes without
turning any of them into a facility master record.

Each accepted relationship carries the evidence source, subject/object/evidence
source-native IDs, observation date, retrieval timestamp, relationship type,
confidence, review state, match method, and an evidence URL/excerpt. An
ownership change is represented by non-overlapping temporal relationships.

The tests cover entity ambiguity, ownership changes, duplicate names,
subsidiaries/parents, stale evidence, conflicting identifiers, schema drift,
suppression, deterministic output, and V1 reconciliation.

## What remains inference or blocked

- The checked-in rows and CIK values are synthetic/sanitized. They do not
  assert a live SEC, EPA, OSHA, FSIS, or APHIS match.
- A source-native ID is evidence of identity within that source, not a legal
  conclusion about ownership or operation.
- An explicit reviewed link is a candidate relationship, not project approval.
- A missing source observation is not closure. An APHIS inspection or aggregate
  is not an FSIS facility-master observation.
- Address, phone, DUNS, and precise coordinates remain private/pending review;
  geocoding is disabled.

## Source rights and acquisition

FSIS uses the existing operator-assisted official-export contract because the
direct route returned HTTP 403 during reconnaissance. The pilot does not retry
around, bypass, or disguise that control. APHIS uses its existing explicit
registrations/annual-reports/inspections assisted-export profiles. Any SEC,
EPA, OSHA, or other government source needs its own official URL, retrieval
date, checksum, artifact retention decision, and terms/reuse review before a
relationship can be used outside a synthetic fixture.

Government-sourced does not mean project-approved, current, complete, or
independently verified. The candidate run remains `private-candidate`,
`release_state=not-created`, and publication-blocked.

## Coverage and scaling cost

The checked-in coverage is a contract fixture only and makes no national
completeness claim. A real bounded run would require source-specific exports,
schema/count review, exact source-key reconciliation, stale/conflict scans,
privacy review, rights review, and human approval for every link family.
The dominant scaling cost is per-relationship evidence review and retention;
bulk fuzzy resolution is intentionally out of scope. No graph migration,
frontend, target scoring, activist targeting, residential-person exposure,
publication, or UI work is included.

## Review gates

1. Verify source authority, selected profile, URL, edition/search date, terms,
   attribution, and retention for each source artifact.
2. Confirm that every relationship has source-native IDs and evidence and that
   no name/address/geocoder identity inference was introduced.
3. Inspect quarantine counts and conflicts; treat stale or missing evidence as
   uncertainty, not closure.
4. Complete privacy/suppression review and retain no raw rows in Git.
5. Obtain authorized project review and release approval separately. This pilot
   itself never promotes a release.
