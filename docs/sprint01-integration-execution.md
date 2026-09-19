# Sprint 01 integration execution

Status: active engineering integration evidence (2026-09-18)

- Baseline: `a45ebe55f7291378db1f1b43d9cc7240372664cc`
- Revision: `2a1103f5` (`codex/sprint01-integration`)
- Scope: private graph correctness, authenticated populated graph coverage, rights and worker acceptance integration, CI/Compose/build-context safeguards.
- Evidence: Rust `cargo test --locked` passed (83 tests); standard Python run passed (288 tests, 22 documented E2E skips); graph E2E passed 6/6; public API E2E passed 11/11; worker E2E passed 8/8 with the real image; rights DB proof passed 4/4; backup/restore passed; Docker context sentinel passed; root Jest passed 25/25.
- Extended E2E modules were run serially against disposable databases. Readiness, suppression-budget, and interrupted-discovery fixtures each received a narrow fixture correction and their targeted reruns passed. No live credentials, private rows, provider calls, publication, or deployment were used.
- Remaining milestone boundary: retained authorized APHIS inputs were unavailable in this checkout, so no real-input rehearsal is claimed. Production publication, ongoing rights revocation, and deployment review remain deferred launch work.
