# V2 API end-to-end tests

These tests exercise the compiled Rust service over real HTTP while it uses a disposable PostGIS container. They never use the Denmark database or real personal data.

Run them from the repository root:

```powershell
$env:UEC_RUN_E2E = "1"
python -m unittest discover -s pipeline/tests/e2e -p "test_*.py" -v
```

This requires Docker Desktop, Cargo, and the pinned Python dependencies. The fixture uses isolated random ports and tears down its Compose project even after setup failures. Fast non-Docker checks remain available with `python -m unittest discover -s pipeline/tests -p "test_*.py" -v`.

`fixture.py` owns the environment lifecycle: it selects isolated ports, starts Docker Compose, applies migrations as UTF-8, builds and starts the backend, waits for readiness, and tears everything down. Setup failures also trigger cleanup.

`test_public_api.py` verifies the publication boundary with an empty database: candidate data and filters remain unavailable, and malformed pagination is rejected.

`test_seeded_api.py` uses `seed_official_scenario()` to create synthetic exact, city-level, unmapped, lifecycle, category, and safety-restricted records in a promoted release. This is the reusable starting point for future user-submission and moderation scenarios.

Tests should assert both positive behavior and absence of disclosure. A record being present in the database is not sufficient to make it public; every public response must pass release, visibility, and safety filtering.
