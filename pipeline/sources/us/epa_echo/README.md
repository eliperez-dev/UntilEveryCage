# EPA ECHO animal-production source

**Source ID:** `us.epa.echo-animal-production`
**Publisher:** U.S. Environmental Protection Agency
**Authority:** [ECHO Facilities ArcGIS layer](https://echogeo.epa.gov/arcgis/rest/services/ECHO/Facilities/MapServer/0)
**License reference:** [EPA data license and disclaimer](https://pasteur.epa.gov/license/sciencehub-license.html)

This source captures EPA ECHO facility records that are associated with Clean
Water Act/NPDES data and carry a native livestock/poultry NAICS 112* or selected
SIC 02 classification. This is an industry-classified permit-associated list,
not a confirmed CAFO inventory, proof of current operation, animal-count
dataset, or complete census. ECHO may contain state-submitted source fields;
EPA's default public-domain notice is not treated as publication clearance for
every upstream value.

The source-owned bounded REST capture validates the official HTTPS host,
response schema, selected object IDs and row count, data-size bounds, and a
source-specific terms-review decision. It preserves exact response pages in a
restricted ZIP artifact. The adapter retains source classification and permit
fields, normalizes source-reported coordinates without geocoding, and emits a
private human-gated candidate handoff. Publication remains blocked.

From the repository root, after source registration and an operator-authored
terms-review file exist:

```powershell
python -m pipeline.sources.us.epa_echo.refresh --fetch --terms-review pipeline/sources/us/epa_echo/terms-review.json
```

The CLI's default output is under ignored `data/staging/source-expansion-20261020/`.
Do not print or commit raw captures, normalized facility rows, names, addresses,
or coordinates. The source test module uses synthetic records only.
