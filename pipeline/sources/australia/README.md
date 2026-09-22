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
