# Shared private refresh framework

`pipeline.refresh_private` is the source-neutral control plane for D2. It
selects source IDs from `pipeline/source_registry.json`, checks the versioned
capability registry, and invokes only explicitly registered adapter hooks.

```powershell
python -m pipeline.refresh_private --source dk.smiley --mode fixture
python -m pipeline.refresh_private --source a --source b --mode local-artifact --artifact a=a.csv --artifact b=b.csv
python -m pipeline.refresh_private --all-eligible --mode live-acquisition --resume
```

Execution is sequential. A source failure is isolated and later sources run;
the aggregate command returns nonzero when any source failed or was
unsupported. `--resume` reuses a completed per-source manifest for the same
deterministic plan. Retry count is bounded to five. In D2, `--all-eligible`
means the seven first-wave adapters with explicit shared-runner hooks; other
registry entries remain selectable only when their own bridge is onboarded.
The plan and manifests are aggregate-only and must not contain rows or source
payloads.

Modes are explicit: `fixture`, `local-artifact`, and `live-acquisition`. The
runner never guesses how to acquire an artifact. A source without a registered
hook is reported as `unsupported`, including reference-only sources; it is
never silently run. Adapter hooks return row-free summaries and remain the
only owners of source parsing/normalization. SQL is not part of this control
plane.

Candidate import is an opt-in boundary for a later integration lane. The
runner rejects non-loopback PostgreSQL URLs before invoking an importer and
never creates a release, promotes a release, publishes, or geocodes.
