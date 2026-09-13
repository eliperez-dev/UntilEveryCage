# Legacy source registry

[`pipeline/source_registry.json`](../../pipeline/source_registry.json) is the machine-readable inventory of source identities represented by the current legacy application data. It is an evidence register, not a claim that any upstream source is current, complete, licensed for redistribution, or approved for publication.

The registry contains one entry per source identity currently represented in `pipeline/source-inventory.csv`. A legacy path proves only that a repository artifact exists; it does not prove the artifact's upstream origin. URLs are populated only where repository scripts or documentation provide them. Every unresolved value is the literal `unknown`, and unresolved work is listed in `blockers`.

Validate it offline from the repository root:

```powershell
python -m unittest pipeline.tests.test_source_registry
```

The loader checks the version, required fields, unique IDs, explicit unknowns, safe HTTP(S) URLs, recognized adapter statuses, and that each referenced legacy path exists inside the repository. It never downloads URLs or reads legacy facility contents. A future adapter must separately record retrieval time, byte size, checksum, publication/effective date, code/configuration version, and source terms for each acquired artifact.

Do not add raw or derived facility data to this registry. Split mixed or derived legacy material into separately evidenced source IDs before implementing acquisition.
