# France DGAL Section I/II private pipeline

Status: implemented private candidate pipeline; no release or public API exposure.

The source registry keeps the Ministry's daily Regulation (EC) 853/2004 lists
as two identities: Section I (`SSA1_VIAN_ONG_DOM.txt`, domestic ungulates) and
Section II (`SSA1_VIAN_COL_LAGO.txt`, poultry and lagomorphs). The Ministry's
current 853/2004 page and the file host are the authoritative route evidence.
The adapter preserves every source cell in restricted parsed evidence and
derives only conservative category labels from the source category/activity
strings. Approval number is a source identifier, not permission to merge rows
or evidence that the site is operating.

Lifecycle:

`bounded fetch or assisted capture -> immutable hash/size/URL metadata ->
encoding/delimiter/schema validation -> parsed JSONL -> normalized JSONL with
street address/coordinates suppressed -> quarantine JSONL -> row-free QA,
health, and operator review packet -> private candidate handoff`.

The adapter supports UTF-8/CP1252, semicolon/tab/comma/pipe-delimited inputs,
stable schema fingerprints, duplicate detection, missing identity/name/commune
quarantine, explicit unclassified activity quarantine, deterministic row IDs,
and reruns. A missing row in a later snapshot is `not observed`, never closure.
Geocoding is disabled. Address, SIRET, names, and any future coordinates remain
restricted pending privacy review. Terms/attribution evidence is not treated as
publication approval; the current site-wide Etalab indication still needs
file-specific confirmation.

Run with `python -m pipeline.sources.france.refresh --section I --raw <restricted.txt> --run-dir <restricted-run>` or `--fetch --terms-review <approved-terms.json>`. Raw artifacts belong in ignored private storage only.
