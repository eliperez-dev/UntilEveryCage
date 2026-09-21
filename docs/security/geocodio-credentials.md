# Geocodio credential handling

The historical Italy geocoding scripts read `GEOCODIO_API_KEY` from the
process environment only when a geocoding request is invoked. Importing the
scripts and running repository tests do not contact Geocodio. If the variable
is absent, the scripts fail with an actionable configuration error.

For a private local run, configure the variable through the process environment
or a secret manager, for example:

```powershell
$env:GEOCODIO_API_KEY = '<value supplied by the secret manager>'
python dirty-datasets/it/geocode_italy_v2.py
```

Do not put a real key in Python, CSV, documentation, shell history, or a
committed environment file. The key previously present in the repository must
be treated as compromised and revoked/rotated with Geocodio outside the
repository. Removing the literal from source does not revoke or rotate it.
