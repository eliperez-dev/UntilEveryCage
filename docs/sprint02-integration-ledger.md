# Sprint 02 integration and storage ledger

Status: partial reviewed country checkpoint, 2026-09-19. France and Italy are accepted for private candidate/replay integration; this is not a release approval or a claim that Sprint 02 source acquisition is complete.

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

## Reviewed country checkpoint

- France commit `707ac93e` was independently replayed from retained Section I/II raw artifacts and approved by QA; it is integrated as `fbf4e682` on `eli/front-end-overhaul` with unresolved identity signals preserved, no automatic merges, and publication/DB import blocked.
- Italy commits `e04adecf` and `291ad21` were independently replayed byte-for-byte and approved by QA; they are integrated in the same checkpoint with quarantine, location/privacy, rights, and publication gates preserved.
- The combined local validation passed 256 pipeline tests, 25 Jest tests, 7 developer tests, doctor, and diff checks. Native GitHub Actions run [98](https://github.com/eliperez-dev/UntilEveryCage/actions/runs/35461131905) succeeded for exact SHA `fbf4e6824792078a4c3aa5ac1f730e0629039224`.
- FSIS current files remain blocked after bounded ordinary GETs to the three displayed official routes returned HTTP 403; no response body was retained. The row-free evidence is private at `C:\New Projects\UntilEveryCage\.private\sprint02-20260919\fsis\handoff\bounded-get-20260919.json`.
- APHIS registration/report and inspection lanes are still in progress; their real handoffs require independent replay before integration.
- APHIS inspection code chain `addcef0c` -> `4518bce6` -> `8b4d3c68` is QA-approved and integrated as `e946d15e`. The authoritative replay accepted 1,075 input rows, 1,071 candidates, and 4 exact-duplicate quarantines, with every source row mapped to verified original-page lineage. Public release/import remains blocked.
- APHIS registration/annual-report per-row lineage is not yet accepted; the core/evidence owners are correcting that gap before integration.
- The authoritative APHIS evidence-consumer stack `8430572b` -> `4ee87737` -> `3124696e` -> `285ef119` -> `da17cc34` -> `9b026c13` is code-QA approved and integrated as lane commits through `8dc35b98`. The integrated checks fail closed on quarantine accounting, origin metadata consensus, and original-page lineage; this does not accept the still-held annual/registration rows.

## Integration ledger

| Area | Owner/interface | Acceptance state |
| --- | --- | --- |
| APHIS registrations/reports | Lane 1 handoff under private storage | Pending per-row lineage correction and QA |
| APHIS inspections | Lane 2 handoff under private storage | QA-approved and integrated for private candidate/replay |
| FSIS current parity | Lane 3 handoff under private storage | Pending source handoff and review |
| France candidate | Lane 4 handoff under private storage | QA-approved and integrated for private candidate/replay |
| Italy candidate | Lane 5 handoff under private storage | QA-approved and integrated for private candidate/replay |
| Evidence integration | Lane 6 existing APHIS/FSIS contracts | Authoritative APHIS consumer stack integrated; core annual/registration lineage still held |
| Independent QA | Lane 7 replay and review | Pending reviewed handoffs |
| CI/build/release engineering | Lane 8 | Storage/context boundary implemented; focused integration tests pass; native CI pending for current SHA |

## Release gate

No public release, deployment, or publication approval is implied. Before final integration, lane 8 must verify reviewed commits, migration reservations, private-artifact availability, reproducible commands, native Linux CI for the exact integrated SHA, and the remaining coverage/privacy/rights limitations. Failed acquisition leaves the previous validated release available subject to current restrictions.
