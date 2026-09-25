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

## Two adapter interfaces

The repository has two deliberately separate interfaces. A lifecycle
`SourceAdapter` interprets a preserved artifact and writes private row-level
staging evidence. A strict-refresh `RefreshAdapter` is the runner-facing
control-plane hook: it selects an artifact, invokes source-owned processing,
and returns aggregate facts only. It may expose a bounded `acquire` method,
which the runner calls only after its authorization and terms checks. Do not
make parsing, acquisition, preview import, or publication implicit in either
interface.

### Lifecycle adapter

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
count invariants. The manifest must reconcile input, normalized, and
quarantined counts and retain `release_state: not-created`. A malformed or unresolved row goes to quarantine with an
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

### Strict refresh adapter and bridge

The refresh hook has a different signature and returns no records or row
payloads:

```python
from pathlib import Path
from typing import Any, Mapping

class ExampleRefreshAdapter:
    source_id = "gb.example-register"
    adapter_version = "example-v1"
    source_kind = "facility_master"  # optional; defaults to this for older hooks

    def refresh(self, *, mode: str, run_dir: Path, artifact: Path | None,
                options: Mapping[str, Any]) -> Mapping[str, Any]:
        # Select fixture or caller-supplied preserved artifact, build its
        # SourceArtifact from recorded acquisition facts, and call
        # run_private_lifecycle(..., ExampleAdapter()).
        # Return counts, status, drift signals, and gate state only.
        return {"input_rows": 0, "normalized_rows": 0,
                "quarantined_rows": 0, "review_required": True}

    # Optional. Never fetch merely because live mode was requested; runner
    # authorization and terms checks happen before this hook is called.
    def acquire(self, *, run_dir: Path,
                options: Mapping[str, Any]) -> Mapping[str, Any]:
        raise NotImplementedError
```

`pipeline.sources.first_wave.FirstWaveRefreshAdapter` is the repository
bridge pattern: it owns fixture/local/live selection and provenance
conversion, then invokes a source-specific `SourceAdapter` through
`run_private_lifecycle`. Other refresh adapters may use source-specific
bridges where formats require multiple files or special acquisition steps;
keep those rules in the source package. The shared runner validates the
refresh interface at registration and rejects row-bearing summaries.

The refresh runner's candidate handoff and any strict real-preview importer
have their own registry, allowlist, and privacy/publication gates. Implementing
either adapter interface does not grant access to preview import, release
approval, or public publication. Preserve existing `run_registered` and
legacy refresh entry points as compatibility shims while migrating callers.

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
