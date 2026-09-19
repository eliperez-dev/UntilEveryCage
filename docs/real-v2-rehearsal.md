# 50k Real-Row V2 rehearsal

This is a private compatibility rehearsal for the existing V1-derived corpus,
not a current-data release and not evidence that V2 is ready for publication.
The row-free evidence is in
[`data/manifests/real-v2-rehearsal-report.json`](../data/manifests/real-v2-rehearsal-report.json).

## Reproduce the conversion

Use a private temporary output directory. The script references the existing
`static_data/*/locations.csv` files and does not copy them into Git:

```powershell
$out = Join-Path $env:TEMP 'uec-real-v2-rehearsal'
python pipeline/scripts/maintenance/rehearse_real_v2.py `
  --output $out `
  --as-of 2026-09-16T00:00:00Z
```

Each country receives parsed, normalized, quarantined, candidate-handoff,
manifest, and review-packet files. Every normalized row is labeled
`legacy-v1-derived-snapshot`, `private`, and `publication_gate=blocked`.

## Disposable database rehearsal

The guarded importer requires a loopback database on a non-default port and
the exact disposable marker. Import each country handoff with the same
`candidate-legacy-v2` release ID. Re-running is safe and returns zero newly
inserted rows because IDs and conflict keys are deterministic.

The local API must be started with `UEC_TEST_RELEASE_ID=candidate-legacy-v2`,
`UEC_TEST_RELEASE_TOKEN`, and the preview token. Use only the
`/api/dev/preview/test-release/*` routes. `/api/v2/*` remains empty until an
authorized release is promoted. The candidate is never default-visible,
publication-eligible, or map-projected.

The rehearsal verified list pagination, detail lookup, facets, bounded export,
and append-only suppression/reinstatement. It did not run backup/restore or
claim current-source quality; those limitations are intentional and recorded
in the manifest.
