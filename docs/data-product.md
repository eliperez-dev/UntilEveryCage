# Public data product

UEC public snapshots are release-scoped projections, not raw source dumps. A snapshot is available only for an explicitly promoted, non-test release/profile whose rows have passed the current publication and privacy gates. The packager fails closed when a row is suppressed, belongs to another profile/release, is not privacy-screened, is not approved for the selected profile, or has unclear/restricted reuse rights.

## Package contents

`pipeline/scripts/stages/export-release.py` creates a deterministic package containing:

- `locations.csv`: stable column order, UTF-8, LF line endings, and spreadsheet-formula neutralization for text beginning with `=`, `+`, `-`, or `@`.
- `locations.geojson`: a GeoJSON `FeatureCollection` with the same public properties. Coordinates are emitted only for `exact` or `city` display precision; `city` is a coarse/approximate display point and an unmapped or restricted point is `null`.
- `data-dictionary.json`: machine-readable field semantics and coordinate/unknown-value policy.
- `manifest.json`: release/profile identity, generated and retrieved timestamps, source coverage, schema and data-product versions, row counts, review/publication state, limitations, supersession, and artifact checksums.
- `SHA256SUMS.json`: checksum sidecar covering the manifest and package artifacts.

Run this only after an authorized release has been promoted:

```powershell
python pipeline/scripts/stages/export-release.py RELEASE_ID `
  --profile official `
  --output-dir data/releases/RELEASE_ID-official
```

The database query uses a repeatable-read snapshot and repeats the release/profile, publication review, privacy screening, and current suppression gates. It does not validate, promote, deploy, or publish a release. Source `attribution` is treated as `attribution_required`; missing attribution is `unknown` and blocks packaging until reuse status is reviewed. This is a conservative source-rights gate, not a claim that attribution alone grants redistribution rights.

## Release metadata

`release_id` and `profile` are the citation scope. `generated_at` is the release/package generation time and `retrieved_at` is the earliest source-artifact retrieval represented by the package. `source_coverage` reports each source ID, included row count, retrieval interval, and per-source rights status. `row_counts.eligible_rows` must equal the packaged row count; the package never truncates a large release.

Review, privacy screening, project approval, and publication are independent states. A community profile can carry a privacy-screened but factually unreviewed claim and must retain the row warning `Unreviewed community claim — not verified by Until Every Cage`. A community review does not grant project approval. No profile or export implies factual completeness, current operation, an animal count, a story-wide denominator, a project licence, or an availability SLA.

## Verification

Consumers should obtain the package and its trusted manifest digest through a project-controlled channel, then verify the sidecar and listed artifacts:

```powershell
python pipeline/scripts/maintenance/verify-data-product.py data/releases/RELEASE_ID-official `
  --manifest-sha256 TRUSTED_MANIFEST_SHA256
```

The Python contract also exposes `verify_package(Path(...))` for local verification. Checksums detect byte changes relative to the trusted manifest; they do not establish factual accuracy, source correctness, privacy eligibility, or reuse rights.

## Compatibility and deprecation

The stable public contract is the versioned `data_product_version` plus `schema_version`. Additive nullable fields may be added in a minor contract revision. Existing field meanings, identifiers, profile names, and coordinate safety rules are not changed silently. A breaking field/type/meaning change requires a new schema version and a documented migration note; old packages remain labeled rather than rewritten. Deprecated fields remain for one documented release cycle where safe, then are removed only in a new major schema version. Release IDs and artifact bytes are immutable; a correction creates a new release and records `supersedes`.

The API remains a bounded convenience surface (`GET /api/v2/locations.csv`, maximum 1,000 rows). Reproducible bulk distribution uses the CLI package above. API and package consumers must treat `(profile, release_id, schema_version, query)` as the snapshot key and must not infer omitted rows as suppressed, closed, or absent from the underlying story.
