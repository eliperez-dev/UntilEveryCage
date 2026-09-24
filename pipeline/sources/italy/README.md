# Italy Ministry 853/2004 private source

`it.853-2004` is the Ministry of Health open-data catalog for establishments
recognized under Regulation (EC) 853/2004. The catalog page is the stable
authority boundary; `acquire.py` discovers its current same-origin CSV link,
archives the raw bytes under ignored `data/raw/italy/`, and records the
requested catalog URL, final download URL, retrieval time, response metadata,
SHA-256, byte size, supplied catalog/file dates, source ID, code/configuration
versions, and terms-review evidence. Network acquisition is bounded and
requires an approved private terms-review JSON file.

Run the complete current acquisition-to-private-preview flow as one
non-interactive, source-scoped command while the isolated local preview
database service is running:

```text
python scripts/real_preview.py refresh --source it.853-2004
```

The command discovers and downloads the current catalog CSV, records source
and retrieval provenance, validates the schema, parses and quarantines unsafe
rows, normalizes the handoff, and atomically imports the exact run under the
generic preview-enabled policy. It has bounded acquisition timeouts and a
nonblocking per-source lock. A failed step returns a nonzero status and does
not replace the existing preview snapshot; it never falls back to stale or
synthetic data. Omit neither `--source` nor its value: refresh requires an
explicit source. `--all-due` scheduling is not yet implemented. The browser is
read-only and loads the updated preview automatically; Playwright verifies
that the CLI-acquired run is selectable and rendered.

The lower-level commands remain available for restricted diagnosis, but are
not the acceptance workflow:

```text
python -m pipeline.sources.italy.acquire --fetch --terms-review <review.json> --output-root data/raw --run-id <id>
python -m pipeline.sources.italy.refresh --raw data/raw/it.853-2004/<id>/source.csv --run-dir data/staging/italy-853/<id>
```

The refresh uses `run_private_lifecycle`, producing parsed, normalized,
quarantined, row-free QA, restricted run status, and deterministic private
health artifacts. The shared runner carries the exact acquired artifact
through the generic preview policy gate. Preview rows are available only to the
authenticated local loopback API. No release is promoted and public visibility
remains zero.

The adapter treats each establishment/activity row as an observation. It
preserves source values privately, retains source identifiers, represents
unknown dates/geography/coordinates explicitly, and quarantines malformed
rows, unknown statuses, missing identifiers/activity codes, invalid dates,
and repeated recognition/activity identities. Repeated rows are not merged.
Addresses and tax identifiers are never copied into normalized fields. Valid
source coordinates are retained in restricted handoff evidence with
`source-precision-unknown`, shown as approximate in the private preview, and
disclosed as unverified. Incomplete or out-of-range pairs are quarantined;
`(0, 0)` pairs remain non-map evidence. Unmapped rows receive no substitute
point. Public coordinate use still requires separate review.

## 1069/2009 boundary

The Ministry's animal-by-products catalog is a separate source with a separate
schema, recognition semantics, activity/product codes, and optional links to an
853 recognition number. It is not included in `it.853-2004`, its row counts,
identity rules, candidate release, health snapshot, or API filters. A future
`it.1069-2009` adapter must have its own source ID, acquisition evidence,
schema dictionary, normalization/quarantine rules, privacy review, and an
explicit reviewed identity/linking event before any cross-source relationship
is shown. It must never be silently unioned with 853/2004 facilities.

This is private staging evidence, not a completeness, accuracy, project-
approval, or publication claim. The catalog notes that some coordinates came
from OpenStreetMap contributors; that provenance does not itself authorize
precise-coordinate publication.

## Sprint 02 live handoff

The 2026-09-19 private refresh is recorded in
`data/manifests/italy-sprint02-20260919.json` and
`docs/reports/italy-sprint02-20260919.md`. The exact raw and staging paths are
restricted under the sprint's excluded private root; no row-level artifact is
tracked. The source run had 47,375 observations, 41,849 normalized rows, and
5,526 quarantined repeated recognition/activity observations. A registered
office is not supplied by this source: the source address is a recognized-
establishment location and is not treated as proof of current operation.

The preferred replay command is the `acquire.py --fetch` command above. If the
local Python TLS stack cannot negotiate the Ministry host, use the ordinary
HTTPS `curl.exe --http1.1 --tlsv1.2` catalog-then-discovered-CSV capture route
documented in the private handoff, preserving both response headers and the
catalog-discovered URL before running `refresh.py`. This is a transport
fallback only; it does not bypass access controls or change source scope.
