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

## Local real-preview exception

The fixture modes above remain the default and remain the only modes that may
produce frontend dataset artifacts. A separate, operator-started **local real
preview** may query an already-prepared disposable candidate release through
the loopback-only `/api/dev/preview/test-release/*` boundary for map rendering
and interaction testing. It is not a dataset mode, a release, an export, or a
public projection.

It must be enabled explicitly for one local process, use a selected candidate
release, and preserve the existing visibility, privacy-screening, restriction,
and coordinate-review gates. The approved rehearsal corpus is bounded to the
50,750-row legacy V1 snapshot (48,703 mapped and 2,047 unmapped), labeled
legacy/development-only/not-V2-reviewed, and is never promoted. The map uses
viewport-bounded queries rather than a browser-wide row payload. The browser
requests it only with the
`X-UEC-Dev-Preview-Token` header held in memory. Do not write real rows,
tokens, manifests, screenshots containing sensitive details, or source paths
to Git, frontend fixtures, browser storage, logs, or generated artifacts.

The exception is loopback-only; no tunnel, remote preview, analytics, export,
or public `/api/v2/*` route is permitted. Stop the local stack and clear the
process environment after testing. Deleting a release does not erase browser
caches, logs, or copied files, so those prohibited outputs must never be made.

The launchpad should verify manifest digests and reject a missing manifest,
digest mismatch, or non-empty public projection. `ui_states.json` supplies
loading, empty, 404, 429, 503, stale, restricted, suppressed, unmapped, and
no-connection journeys.

