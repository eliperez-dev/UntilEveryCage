# Germany BVL BLtU private staging

Use the stable [BVL BLtU landing page](https://www.bvl.bund.de/bltu) and select
the current general-list CSV export in the portal. Save that export outside Git
and run the assisted refresh:

```text
python -m pipeline.sources.germany.refresh --raw <private/bltu-export.csv> --run-dir <private/run> --retrieved-at-utc 2026-09-15T00:00:00Z
```

The typed adapter preserves repeated activity columns and source evidence,
quarantines schema and mapping anomalies, emits shared health evidence, and
cannot create a release. Address/coordinate review, BVL reuse terms, and human
publication approval remain blocked.
