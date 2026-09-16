# Geospatial readiness rehearsal

`pipeline/scripts/diagnostics/geospatial_readiness_audit.py` performs a deterministic offline audit of normalized `static_data/*/locations.csv` files. It never calls a geocoder and emits only aggregate counts plus sanitized sample composition. Source coordinates are retained conceptually as source evidence; this report does not copy them.

The funnel distinguishes valid source coordinates, geocode candidates, city/coarse candidates, review-required/privacy-restricted candidates, unresolved rows, and `map_ready_under_current_rules`. Map readiness is not publication approval: a future geocode result must retain provider, query hash, timestamp, precision, and review state, and the release projection must independently pass privacy and approval gates. Residential-risk flags are conservative indicators for human review, not factual classifications.

Run with `python pipeline/scripts/diagnostics/geospatial_readiness_audit.py --output data/reports/geospatial-readiness.json --as-of 2026-09-16T00:00:00Z`. The report is row-free with respect to source names, addresses, identifiers, and coordinates. Real corpus totals and limitations must be reviewed before release; this rehearsal does not authorize publication or paid geocoding.
