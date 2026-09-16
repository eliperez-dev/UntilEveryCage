# Developer entrypoint

Use `python scripts/dev.py --help` (or `scripts/dev.ps1 --help` on Windows) to discover the V2 workflow. Commands are thin wrappers around the existing project tools:

```text
doctor                 prerequisites, ports, configuration, and optional DB reachability
up/down/status/probe   local V2 environment
logs                   recent Compose logs
test [--full]          JavaScript tests (full runs the configured suite)
pipeline [pytest args] Python pipeline tests
contracts              database and adapter contract tests
review-packet RUN_DIR  deterministic, row-free private review packet
```

`python scripts/dev.py --json doctor` (and any command with the global `--json` flag) emits a final machine-readable summary. Diagnostics report only whether environment variables are set; values and database credentials are never printed. `up` may apply migrations and seed the synthetic local fixture through the existing `local-v2.ps1` workflow. It does not publish a release.
