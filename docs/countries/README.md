# Country source pages

**Owner:** source maintainers. **Purpose:** route country-specific source
research and technical details. Source-level status is canonical only in
[`../source-status.md`](../source-status.md) and
[`../source-status.json`](../source-status.json).

Country reconnaissance files use `docs/country-recon-<code>.md`. They are
**Canonical** for source research, route/coverage observations, and unresolved
country questions; they do not override status or authorize publication.
Detailed folders below are **Canonical** source specifications, field
crosswalks, terms records, and source-specific pipeline details, or **Reference**
when they describe migration context. JSON manifests and descriptors are
**Generated** only where their producing workflow says so; otherwise the
owning country page identifies their authority.

| Country or family | Start here | Label |
| --- | --- | --- |
| United States | [Country reconnaissance](../country-recon-us.md), [source index](us/README.md) | **Canonical** |
| Australia | [Country reconnaissance](../country-recon-au.md), [source crosswalk](australia/source-crosswalk.json) | **Canonical** |
| Brazil | [Country reconnaissance](../country-recon-br.md), [field crosswalk](br/v1-field-crosswalk.json) | **Canonical** |
| Canada | [Country reconnaissance](../country-recon-ca.md), [pipeline specification](canada/meat-plants-pipeline.md) | **Canonical** |
| Denmark | [Data flow](denmark/denmark-data-flow.md), [classification scope](denmark/denmark-classification-scope.md) | **Canonical** |
| France | [Country reconnaissance](../country-recon-fr.md), [DGAL pipeline](france/dgal-853-pipeline.md) | **Canonical** |
| United Kingdom | [Country reconnaissance](../country-recon-uk.md), [Scotland source assessment](uk/fss-approved-establishments-source-assessment.md) | **Canonical** |
| Other countries | `country-recon-<code>.md` | **Canonical** research pages |

Do not create a country packet for a task or copy source facts into a second
status file. Update the relevant country page, descriptor, terms record, or
manifest and point the source status entry to it.
