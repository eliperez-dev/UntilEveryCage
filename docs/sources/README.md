# Source documentation

**Owner:** source maintainers. **Purpose:** route source facts, scope,
provenance, terms, and current status to the authoritative source record.

| Need | Start here | Label |
| --- | --- | --- |
| Current status across registered sources | [source-status.md](../source-status.md) and [source-status.json](../source-status.json) | **Canonical** |
| Source IDs and machine descriptors | [`pipeline/source_registry.json`](../../pipeline/source_registry.json) and country descriptors | **Canonical** registry / descriptors |
| National/country reconnaissance | [`country-recon-<code>.md`](../country-recon-us.md) (replace code with ISO-style country code) | **Canonical** research page |
| Detailed country field mappings | [`countries/<code>/`](../countries/us/README.md) | **Canonical** or **Reference**, per page |
| Pipeline source adapter and supported behavior | [`pipeline/sources/`](../../pipeline/sources/us/fsis/README.md) and each source README | **Canonical** implementation contract |
| Retrieval evidence and hashes | `data/manifests/` and source artifact metadata | **Generated**; aggregate metadata only in the repository |
| Source rights decisions | [source-rights-decisions.md](../architecture/source-rights-decisions.md) | **Canonical** |

Country research documents remain at `docs/country-recon-<code>.md` for
continuity with the source registry and consistency tests. Keep source facts in
the descriptor, terms review, manifest, or canonical country page; update
[`source-status.json`](../source-status.json) only for evidence-backed state.
Do not copy source rows, private payloads, or full research into a new packet.
Use [countries/README.md](../countries/README.md) for the folder-level index.
