# Mexico DENUE source

This source slice uses the official INEGI DENUE API for SCIAN 2023 classes
311611–311614. It is a business-directory extract, not evidence of TIF
certification or current operation. The API token is supplied as
`INEGI_DENUE_TOKEN`; it is never written into source artifacts, manifests, or
diagnostics. The acquisition helper first calls `Cuantificar` for the selected
classes by state, refuses a scope above its record limit, then fetches bounded
pages through `BuscarAreaAct`. It preserves a field-minimized private JSON
artifact with the source identifiers, names, activity, address, source
coordinates, filters, counts, retrieval time, checksum, and byte size.

The adapter retains `Id` and `CLEE`, the original relevant DENUE fields, and
the source address/coordinate values. It omits telephone, email, and website
fields. Coordinates retain unknown precision and are not geocoded. Privacy,
terms attribution, classification fit, operating status, and publication all
remain separate review gates. Attribute use as “Source: INEGI, DENUE” with the
retrieval date where available, identify transformations, and do not imply
INEGI endorsement.

Run the synthetic checks with:

```powershell
python -m unittest pipeline.sources.mexico.test_adapter
```

The shared runner does not register or import this source yet; source registry,
runner wiring, readiness metadata, and private database integration are owned
by the coordinator.
