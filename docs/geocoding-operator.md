# Unattended geocoding operations

This lane performs private enrichment only. It cannot approve or publish a
record. Geocoding jobs, events, and provider evidence remain append-only, and
the worker checks current restrictions before and after each provider request.

After reviewing the provider's terms and rate limits, supply the API key only
through the environment and start the optional worker profile:

```powershell
$env:GEOAPIFY_API_KEY = "..."
docker compose -f docker-compose.pipeline.yml --profile geocoding up -d geocode-worker
```

Never place the key in source control, Compose files, command arguments,
reports, or logs. Worker output is limited to provider, aggregate status, and
processed counts.

Inspect the queue without exposing facility records:

```powershell
python pipeline/scripts/diagnostics/geocode-operator-status.py --pretty
```

The report includes aggregate state, provider and country counts; recent daily
usage; retry-state wording; and an estimated completion time based on the last
seven days. It excludes addresses, queries, provider payloads, job and record
identifiers, and credentials. A null ETA means recent throughput is
insufficient to estimate completion; it is not a completion promise.
