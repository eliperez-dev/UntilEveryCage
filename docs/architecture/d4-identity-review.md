# D4 identity candidates and review lineage

Status: private review contract; no public identity merge or graph release.

D4 retains uncertain connections as evidence-bearing candidate edges. A
candidate edge is not a canonical identity and cannot transfer claims,
ownership, operator status, review approval, or publication eligibility.

Each candidate records a source-qualified endpoint pair, confidence score and
band, matching method, contributing features, contradictory evidence,
provenance, observed timestamp, algorithm/ruleset version, reviewer state, and
a user-facing disclaimer. The private database migration
`042_identity_candidate_review_lineage.sql` makes these fields append-only and
fail-closed for publication and automatic merging.

Matching policy:

- exact source-native identifiers and authoritative crosswalks can produce a
  high-confidence review-required candidate, never automatic acceptance;
- name, address, phone, proximity, and geocoder signals can produce bounded
  probable/possible candidates only when the signal set is sufficiently
  supported; single-signal cases remain unresolved or quarantined;
- APHIS-to-APHIS and FSIS-to-FSIS source-scoped candidates are permitted;
  APHIS-to-FSIS automatic links are always zero, and an explicit bridge is
  still review-required;
- merge, split, supersede, and reversal are append-only lineage events. They
  record review history without rewriting source identifiers or canonical rows.

Review packets are aggregate-only in the repository. Synthetic accuracy is
reported separately from authorized human adjudication. Human precision stays
unknown until a reviewer assesses a sample; recall stays unavailable without a
gold set. Candidate rows and source payloads remain in restricted local
storage, never Git or public projections.
