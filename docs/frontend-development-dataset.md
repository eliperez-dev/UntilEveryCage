# E1 frontend development dataset

The frontend launchpad consumes a dataset directory produced by
`pipeline/scripts/fixtures/build_frontend_dataset.py`. The directory is a
development boundary, not a release. It contains `manifest.json`,
`locations.jsonl`, `graph_edges.jsonl`, `ui_states.json`, and
`public_projection.json`.

Representative mode is a compact deterministic synthetic corpus covering exact,
city, coarse, and unmapped locations; dense and sparse map distributions;
multiple countries/categories/sources; lifecycle and freshness; restrictions
and suppression; pagination; and exact/inferred graph edges at high, medium,
and low confidence, including contradiction examples. Rows are synthetic and
must be labelled as development data.

Performance mode requires at least 100,000 facilities and 100,000 graph edges.
It streams JSONL with fixed-seed city-density skew, overlapping points, sparse
rural points, and every coordinate state. It is generated outside Git so the
design team can compare clustering, heatmaps, aggregate cells, and
approximate-location treatments without the dataset layer selecting one.

Private mode requires an operator-supplied row-free manifest and allowlists
only `dk.smiley`, France DGAL sections I/II, `it.853-2004`, and `us.fsis`.
It emits aggregate source inventory only; no rows, artifacts, private paths,
addresses, credentials, or release claims are copied. The private database
handoff may use the inventory to select source IDs.

`public_projection.json` is always empty. A future release builder must make an
explicit profile/release decision before any facility or graph row appears on a
public surface. Development graph rows expose exact/inferred type, confidence,
signals, contradictions, and disclaimers; they never represent universal
identity merges.

The launchpad should verify manifest digests and reject a missing manifest,
digest mismatch, or non-empty public projection. `ui_states.json` supplies
loading, empty, 404, 429, 503, stale, restricted, suppressed, unmapped, and
no-connection journeys.

