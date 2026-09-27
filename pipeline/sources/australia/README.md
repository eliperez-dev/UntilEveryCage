# Australia NPI facilities

`au.npi.facilities` is the first Australia source with a shared-runner adapter.
The National Pollutant Inventory is an environmental reporting overlay, not a
complete list of slaughterhouses, farms, or animal facilities. The adapter
keeps ANZSIC and activity values as source evidence, preserves source
coordinates without geocoding, and quarantines missing identities or invalid
points.

The checked-in CSV is synthetic and exists only to exercise the contract. The
live adapter verifies the official data.gov.au package and Facilities CSV
resource on every acquisition, checks the listed CC BY 4.0 licence and schema,
then stores the raw CSV and acquisition metadata in ignored private staging.
Each retrieval needs a new run ID so provenance history is not overwritten.

The adapter preserves valid source coordinates and full source rows in private
evidence. Its normalized candidate rows contain no coordinates and are outside
the default map scope until residential, mixed-use, site-identity, and source
precision review. The published primary ANZSIC value remains a source claim;
codes 0171 and 1111–1113 are labeled as industry candidates, not proof of
current operation or a complete animal-facility record. No release or public
projection is created.

Run the source directly through the common runner with a fixture request, or
provide a preserved local artifact with `mode=local-artifact`. No release or
public projection is created by this source package.
