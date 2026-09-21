# Sprint 3 accountability graph rehearsal

Status: private/test-only implementation evidence; no release or publication approval.

The rehearsal runner is `pipeline/graph_rehearsal.py`. It samples authorized
local artifacts deterministically, records only aggregate metadata and hashes in
the report, and keeps sampled rows under an ignored `private/` output directory.
The checkout used for this slice contained no authorized raw row artifacts, so
no real-country/source run was claimed. Existing row-free metadata under
`data/raw/` was inspected but not treated as relationship evidence.

Candidate edges are emitted only when a single source row contains both explicit
source-native identifiers. Facility–organization and organization–organization
edges retain source qualification, method, confidence, observed date, review
state, and evidence key. Name-only matching, coordinate/distance proximity,
geocoding, and automatic merging are rejected by contract. Conflicts and missing
keys remain in the manual-review queue; disappearance is not closure.

Metrics are deliberately split. Synthetic controls report their labeled-control
rates and are not estimates of production accuracy. Observed candidates report
yield and manual-review volume only; accuracy is “not measured” until authorized
human adjudication exists. Privacy, suppression, publication, and release gates
remain blocked, and raw rows must not be committed.

Consolidation order for a future authorized run:

1. verify source URL, retrieval time, checksum, byte size, terms, and retention;
2. import source-native identifiers and append-only evidence records idempotently;
3. quarantine missing keys, duplicate keys, schema drift, and conflicting claims;
4. review privacy/suppression and edge evidence manually;
5. record adjudicated outcomes and only then calculate observed error metrics;
6. obtain project approval and publication approval separately.

Tests cover deterministic sampling, explicit-key edge generation, rejection of
implicit/proximity matching, private storage gates, and separation of synthetic
controls from observed candidate yield.

The aggregate report schema (v3) additionally records, for each requested
stratum, exact source-native-ID linkage rate and endpoint availability; it also
records distinct/duplicate source-key counts, explicit contradiction status,
candidate graph yield, and review-queue counts. These are observations about
the supplied private sample only. Accuracy remains “not measured” until an
authorized human adjudicates the queued relationships; synthetic control
precision/recall must not be combined with observed sample metrics.
