# Sprint 02 integration and storage ledger

Status: partial reviewed candidate/replay checkpoint, 2026-09-20. France, Italy, APHIS core/inspection, evidence integration, and the accepted FSIS backend scope are integrated for private candidate/replay use; this is not a release approval or a claim that Sprint 02 source acquisition is complete.

## Ownership and baseline

- Contract: [`SPRINT-02-CONTRACT.md`](SPRINT-02-CONTRACT.md)
- Required baseline: `5570b6ab42e74dc5227e08c2cd7c1ac7f08aab96`
- Lane worktree: managed integration worktree (local path intentionally omitted)
- Lane branch: `codex/sprint02-integration-lane8`
- Integration target: `origin/eli/front-end-overhaul`
- Raw evidence boundary: private Sprint 02 evidence root outside Git (local path intentionally omitted)

## Storage checkpoint

The shared private root exists with separate directories for `aphis-core`, `aphis-inspections`, `fsis`, `france`, `italy`, `integration`, and `qa`. The repository-level `/.private/` rule is active in the shared checkout and this lane worktree. Raw records, URLs, identifiers, payloads, and derived rows remain outside Git and task reports.

Verification commands:

```powershell
git check-ignore -v --no-index '.private/sprint02-20260919/probe.bin'
powershell -ExecutionPolicy Bypass -File pipeline/tests/verify-docker-context.ps1
```

The Docker context test creates synthetic sentinels under both `data/` and `.private/`; the context image fails if either sentinel is copied. The shared Docker ignore rules exclude `.private/` and `**/.private/`, and the tracked worktree rules carry the same boundary.

Kickoff validation: `npm ci` completed with no vulnerabilities; `python -m unittest scripts.test_dev` passed (7 tests); `python scripts/dev.py --json doctor` passed (database not probed because `UEC_DATABASE_URL` is unset); `git diff --check` passed; both shared-root and lane-worktree `git check-ignore` probes matched `/.private/`. `powershell -ExecutionPolicy Bypass -File pipeline/tests/verify-docker-context.ps1` was attempted with and without escalation but remains blocked because Docker Desktop's Linux engine pipe is unavailable: the client is installed, Docker Desktop processes are running, `com.docker.service` is stopped, and starting that service returns `Cannot open ... service on computer '.'`. No private data or database was used.

## Reviewed country checkpoint

- France and Italy are QA-approved and integrated for private candidate/replay use with unresolved identity signals, quarantine, location/privacy, rights, and publication gates preserved.
- APHIS core/annual-report and inspection v4 handoffs have final QA acceptance and are integrated for private candidate/replay use. Row-free handoffs, source lineage, quarantine accounting, and publication/DB-import gates remain enforced; public release/import remains blocked.
- Lane 6 evidence-consumer contracts have final QA acceptance in the current integrated checkpoint. The consumer fails closed on quarantine accounting, origin metadata consensus, and original-page lineage; this is not publication approval.
- FSIS backend guard, operator-directory URL provenance, and missing-orchestration-URL fallback are accepted in checkpoint `41057011`. QA also recorded successful browser-backed acquisition evidence for the establishment-name directory and demographics; the reusable browser-acquisition implementation remains a separate author lane.
- Earlier bounded ordinary GETs to official FSIS routes returned HTTP 403. That transport diagnostic is retained as context and does not override the separately reviewed browser-backed evidence; no response body, raw row, private path, or artifact hash is recorded here.

## Integration ledger

| Area | Owner/interface | Acceptance state |
| --- | --- | --- |
| APHIS registrations/reports | Lane 1 handoff | QA-approved and integrated for private candidate/replay; publication/import blocked |
| APHIS inspections | Lane 2 handoff | Final QA-approved and integrated for private candidate/replay |
| FSIS current parity | Lane 3 handoff | Backend guard/provenance/fallback accepted; browser-acquisition implementation remains separate |
| France candidate | Lane 4 handoff under private storage | QA-approved and integrated for private candidate/replay |
| Italy candidate | Lane 5 handoff under private storage | QA-approved and integrated for private candidate/replay |
| Evidence integration | Lane 6 existing APHIS/FSIS contracts | Final QA-approved and integrated; fail-closed lineage and quarantine gates retained |
| Independent QA | Lane 7 replay and review | Current handoffs reviewed; durable row-free final signoff in preparation |
| CI/build/release engineering | Lane 8 | Checkpoint `41057011` accepted; 282 pipeline tests passed and hosted CI [run 116](https://github.com/eliperez-dev/UntilEveryCage/actions/runs/35551000683) passed for exact SHA `4105701131fb990499c75b39c66560e527a04a89` |

## Release gate

No public release, deployment, or publication approval is implied. Before release, maintainers must still verify migration reservations, private-artifact availability, reproducible commands, exact-SHA CI, and the remaining coverage/privacy/rights limitations. Failed acquisition leaves the previous validated release available subject to current restrictions.
