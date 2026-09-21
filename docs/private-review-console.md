# Private candidate review console

The local `/private-review.html` page is a read-only operator surface for
candidate evidence. It combines the row-free launch matrix with authenticated
candidate preview, private graph queues, bounded entity traversal, and local
review-packet inspection. It is not a public release view and has no approve,
promote, publish, or export action.

The page is intentionally framework-free: static HTML, vanilla ES modules, and
custom CSS served by the existing Axum application. Its UX is a read-only
operator workspace with four bounded areas: candidate preview, separate graph
queues, a direction/depth-controlled entity neighborhood, and a derived
country readiness matrix. Tokens stay in page memory; no browser storage or
mutation API is used.

## Start locally

1. Build the derived matrix when the source registry or source-status baseline
   changes:

   ```text
   python scripts/dev.py review-console-snapshot
   ```

2. Start the development service in loopback mode with a database and the
   existing private tokens configured. The candidate preview token is accepted
   only by the loopback, test-only endpoint. The graph token is accepted only
   by `/api/private/graph/*`.

3. Open `http://127.0.0.1:8000/private-review.html`. Tokens are held in page
   memory only. A missing or invalid token fails closed; the page never treats
   an unavailable queue as an empty queue.

4. Optionally load a row-free `review-packet.json` using the local file picker.
   The browser validates the packet schema by allowlist, then displays only
   aggregate counts/deltas, quarantine reasons, provenance/schema facts,
   geospatial gates, release gates, attribution metadata, and blockers. Unknown
   fields, raw values, addresses, coordinates, geocoder fields, contact fields,
   and row-shaped payloads are rejected.

## Matrix semantics

The matrix is derived by `pipeline/common/review_console.py` from the existing
platform registry; it does not create a second readiness state machine.

- `blocked`: at least one registered source reports `acquisition=blocked`.
- `acquisition-ready`: all sources have verified/partial metadata and none has
  run acquisition yet; this is not permission to acquire.
- `private-candidate-ready`: at least one source is privately acquired while
  another registered source is still pending.
- `human-review-ready`: every registered source is privately acquired or
  verified and awaits explicit human review; this is not approval.
- `publication-eligible`: only explicit owner approval, release permission,
  and an approved/published publication state can produce this label.
- `infrastructure-only`: registry context exists, but acquisition status is
  incomplete or not classifiable.

The current checked-in baseline has 45 countries and 254 sources. It is
conservative: 34 countries are blocked, 3 are acquisition-ready, 3 are
private-candidate-ready, and 5 are human-review-ready. No country is
publication-eligible in this baseline. These are planning labels, not claims
of source completeness, factual truth, privacy clearance, or publication.

## Evidence boundary

Preview rows are explicitly labeled `Private development candidate — not
project-approved or published`. Candidate records expose only the fields
already allowed by the authenticated test-only contract, plus coordinate
precision/review state and suppression status. Private graph queues return
opaque IDs and review metadata; claim values, raw source payloads, addresses,
geocoder queries, reviewer identities, and private notes remain excluded.
Claims show supporting/contradicting observation counts, rejected crosswalks
remain visible as rejected candidates, and suppression shows only opaque case
and policy/status metadata. Contradictions and unresolved identity candidates
are never silently merged.

If a source is missing from the matrix, the snapshot is stale or the platform
registry failed validation; do not infer zero coverage or closure. Regenerate
the snapshot and resolve the contract error before relying on the console.
