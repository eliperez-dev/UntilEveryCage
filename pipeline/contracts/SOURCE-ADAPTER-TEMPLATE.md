# Country-source adapter template

Use this template for each source under `pipeline/sources/<country>/<source>/`.
It is deliberately small so ten or more countries can share the same review
and import seams without sharing source-specific assumptions.

## Required configuration

Keep a checked-in, non-secret JSON configuration beside the adapter:

```json
{
  "source_id": "gb.example-register",
  "source_url": "https://example.test/register.csv",
  "adapter_version": "example-v1",
  "schema_version": "example-schema-v1",
  "config_version": "example-config-v1",
  "coverage": "publisher-defined scope; not a completeness claim",
  "terms_status": "pending_confirmation",
  "geocoding": "disabled"
}
```

`source_id`, adapter/schema/config versions, URL, and coverage are required
metadata. Retrieval time, SHA-256, byte size, and any publisher-supplied
publication/effective date come from the preserved acquisition and are passed
as `SourceArtifact`; they must not be guessed in the adapter.

Python callers may validate the same fields with
`pipeline.contracts.source_lifecycle.SourceConfig`; older JSON callers can
continue passing a mapping through the compatibility boundary.

## Minimal Python interface

```python
from pathlib import Path
from pipeline.contracts.adapter_contract import SourceArtifact

class ExampleAdapter:
    source_id = "gb.example-register"
    adapter_version = "example-v1"
    schema_version = "example-schema-v1"

    def run(self, raw_path: str | Path, run_dir: str | Path,
            artifact: SourceArtifact) -> dict:
        """Parse one preserved artifact into private staging only."""
```

`run` must preserve source values and write deterministic
`parsed/records.jsonl`, `normalized/records.jsonl`,
`quarantined/records.jsonl`, and `manifest.json`. Use
`source_lifecycle.atomic_jsonl` and `private_manifest` for the shared file and
count invariants. A malformed or unresolved row goes to quarantine with an
explicit reason; no row is silently dropped, merged, or assigned a guessed
identity.

Run the adapter through the shared seam:

```python
from pipeline.common.orchestrator import run_private_lifecycle

status = run_private_lifecycle(
    raw_path, runs_dir, artifact, ExampleAdapter(),
    health_as_of_utc="2026-09-15T00:00:00Z",
)
```

The seam emits row-free `qa.json`, a restricted `run-status.json`, and (when
provenance is complete) `source-health.json`. It never imports a release,
promotes data, or enables a public API. Candidate import and the guarded
test-only API remain explicit, separately authorized operations.

## Review checklist

1. Acquire only through an approved source-specific command; preserve the raw
   bytes and acquisition metadata before parsing.
2. Keep parsed, normalized, quarantined, reviewed, and released artifacts in
   separate locations.
3. Keep source identity and source values beside normalized interpretations.
4. Validate schema, required identifiers, duplicates, dates, coordinates, and
   count drift; retain aggregate anomaly counts.
5. Run malformed-input and byte-identical rerun tests. A failed rerun must not
   replace the prior validated release.
6. Record privacy, terms, factual-review, project-approval, and publication
   states independently. Successful acquisition or validation is never
   publication authorization.
