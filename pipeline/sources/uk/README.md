# UK source adapters

The canonical source IDs are `fsa_approved_establishments` and
`fss_approved_establishments`. `uk.locations` is a legacy umbrella identity,
not evidence of a complete national pipeline.

- [FSA](fsa_approved/README.md): the feed's documented England/Wales scope;
  do not silently include Northern Ireland or Crown Dependencies.
- [FSS](fss_approved/README.md): Scotland.

The `approved/` composition layer retains each source's full manifest, nation,
authority, lifecycle and terms/review context. It does not merge source
identities. An exact trading-name/postcode signal links references rather than
combining observations. Restrictions remain keyed by source and source record.
Missing/failed outputs or incompatible schemas do not replace a prior view.
Composition does not create a candidate release, geocode or publish.

Use [source-status.json](../../../docs/source-status.json) for actual source
readiness, not historical D2/D3 cohort membership.
