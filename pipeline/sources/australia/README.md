# Australia NPI facilities

`au.npi.facilities` is the first Australia source with a shared-runner adapter.
The National Pollutant Inventory is an environmental reporting overlay, not a
complete list of slaughterhouses, farms, or animal facilities. The adapter
keeps ANZSIC and activity values as source evidence, preserves source
coordinates without geocoding, and quarantines missing identities or invalid
points.

The checked-in CSV is synthetic and exists only to exercise the contract. A
real NPI edition remains a private ignored artifact with its URL, retrieval
time, checksum, byte size, and schema recorded in the Australia artifact
metadata. Acquisition is assisted/local-artifact only until an authorized
current edition and terms review are supplied; live mode fails closed before
any network request.

Run the source directly through the common runner with a fixture request, or
provide a preserved local artifact with `mode=local-artifact`. No release or
public projection is created by this source package.

## South Australia EPA licensed activities

`au.sa.epa.licensed-activities` is available through the shared runner as a
local-artifact-only adapter. It parses GeoJSON Point features, retains each
source activity row as a child observation, and writes normalized parent rows
aggregated by EPA licence. Approximate source points are reduced to a coarse
0.01-degree representation, never geocoded, and remain behind privacy and
publication gates. Environmental activity does not establish slaughter,
animal use, or current operation.

The checked-in fixture is fully synthetic. The existing real artifact remains
ignored and private; its tracked checksum and retrieval metadata are evidence,
not permission to ingest or publish. Terms remain unresolved, so live and
assisted acquisition fail closed. No release file is created.
Local-artifact runs must supply `options.artifact_metadata` containing the
official resource URL, UTC retrieval time, SHA-256, byte size, and edition
date; the adapter verifies the hash and size before parsing.

Run focused contracts with:

```text
python -m unittest -q pipeline.sources.australia.test_sa_epa
```
