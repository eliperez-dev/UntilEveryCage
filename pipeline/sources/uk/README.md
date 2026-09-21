# UK adapter registry boundary

The global `pipeline/source_registry.json` currently has one legacy umbrella
entry, `uk.locations`, because the checked-in V1 dataset combined multiple UK
jurisdictions. The source-owned registry in `pipeline/sources/uk/registry.json`
deliberately keeps two separate adapter identities:

- `fsa_approved_establishments`: FSA coverage for England, Wales, and
  Northern Ireland, subject to the source's own scope.
- `fss_approved_establishments`: Food Standards Scotland coverage for
  Scotland.

These local identities must not be silently collapsed into `uk.locations` or
counted as one complete UK pipeline. Until the global registry is split into
matching canonical IDs, the adapters remain compatibility/private refresh
lanes and are not part of the D2 seven-source readiness cohort.
