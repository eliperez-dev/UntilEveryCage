# Sprint 02 integration and storage ledger

Status: lane 8 kickoff checkpoint, 2026-09-19. This is a row-free engineering handoff; it is not a release approval or a claim that source acquisition is complete.

## Ownership and baseline

- Contract: [`SPRINT-02-CONTRACT.md`](SPRINT-02-CONTRACT.md)
- Required baseline: `5570b6ab42e74dc5227e08c2cd7c1ac7f08aab96`
- Lane worktree: `C:\Users\pnael\.codex\worktrees\8a23\UntilEveryCage`
- Lane branch: `codex/sprint02-integration-lane8`
- Integration target: `origin/eli/front-end-overhaul`
- Raw evidence boundary: `C:\New Projects\UntilEveryCage\.private\sprint02-20260919\`

## Storage checkpoint

The shared private root exists with separate directories for `aphis-core`, `aphis-inspections`, `fsis`, `france`, `italy`, `integration`, and `qa`. The repository-level `/.private/` rule is active in the shared checkout and this lane worktree. Raw records, URLs, identifiers, payloads, and derived rows remain outside Git and task reports.

Verification commands:

```powershell
git -C 'C:\New Projects\UntilEveryCage' check-ignore -v --no-index '.private/sprint02-20260919/aphis-core/probe.bin'
git check-ignore -v --no-index '.private/sprint02-20260919/probe.bin'
powershell -ExecutionPolicy Bypass -File pipeline/tests/verify-docker-context.ps1
```

The Docker context test creates synthetic sentinels under both `data/` and `.private/`; the context image fails if either sentinel is copied. The shared Docker ignore rules exclude `.private/` and `**/.private/`, and the tracked worktree rules carry the same boundary.

Kickoff validation: `npm ci` completed with no vulnerabilities; `python -m unittest scripts.test_dev` passed (7 tests); `python scripts/dev.py --json doctor` passed (database not probed because `UEC_DATABASE_URL` is unset); `git diff --check` passed; both shared-root and lane-worktree `git check-ignore` probes matched `/.private/`. `powershell -ExecutionPolicy Bypass -File pipeline/tests/verify-docker-context.ps1` was attempted with and without escalation but remains blocked because Docker Desktop's Linux engine pipe is unavailable: the client is installed, Docker Desktop processes are running, `com.docker.service` is stopped, and starting that service returns `Cannot open ... service on computer '.'`. No private data or database was used.

## Integration ledger

| Area | Owner/interface | Acceptance state |
| --- | --- | --- |
| APHIS registrations/reports | Lane 1 handoff under private storage | Pending source handoff and review |
| APHIS inspections | Lane 2 handoff under private storage | Pending source handoff and review |
| FSIS current parity | Lane 3 handoff under private storage | Pending source handoff and review |
| France candidate | Lane 4 handoff under private storage | Pending source handoff and review |
| Italy candidate | Lane 5 handoff under private storage | Pending source handoff and review |
| Evidence integration | Lane 6 existing APHIS/FSIS contracts | Pending reviewed handoffs |
| Independent QA | Lane 7 replay and review | Pending reviewed handoffs |
| CI/build/release engineering | Lane 8 | Storage and context boundary implemented; native CI and final integration pending |

## Release gate

No public release, deployment, or publication approval is implied. Before final integration, lane 8 must verify reviewed commits, migration reservations, private-artifact availability, reproducible commands, native Linux CI for the exact integrated SHA, and the remaining coverage/privacy/rights limitations. Failed acquisition leaves the previous validated release available subject to current restrictions.
