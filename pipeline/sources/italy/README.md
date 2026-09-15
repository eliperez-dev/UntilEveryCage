# Italy Ministry 853/2004 private source

`it.853-2004` is the Ministry of Health open-data catalog for establishments
recognized under Regulation (EC) 853/2004. The catalog page is the stable
authority boundary; `acquire.py` discovers its current same-origin CSV link,
archives the raw bytes under ignored `data/raw/italy/`, and records the
requested catalog URL, final download URL, retrieval time, response metadata,
SHA-256, byte size, supplied catalog/file dates, source ID, code/configuration
versions, and terms-review evidence. Network acquisition is bounded and
requires an approved private terms-review JSON file.

Run private acquisition and staging with:

```text
python -m pipeline.sources.italy.acquire --fetch --terms-review <review.json> --output-root data/raw --run-id <id>
python -m pipeline.sources.italy.refresh --raw data/raw/it.853-2004/<id>/source.csv --run-dir data/staging/italy-853/<id>
```

The refresh uses `run_private_lifecycle`, producing parsed, normalized,
quarantined, row-free QA, restricted run status, and deterministic private
health artifacts. It ends at `candidate-ready`; candidate import and guarded
test-only API checks are separate explicit steps. No release is promoted and
default/public visibility remains zero.

The adapter treats each establishment/activity row as an observation. It
preserves source values privately, retains source identifiers, represents
unknown dates/geography/coordinates explicitly, and quarantines malformed
rows, unknown statuses, missing identifiers/activity codes, invalid dates,
and repeated recognition/activity identities. Repeated rows are not merged.
Addresses, tax identifiers, and source coordinates are never copied into the
normalized public-shaped fields; any future coordinate or address use requires
separate privacy and project review.

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
