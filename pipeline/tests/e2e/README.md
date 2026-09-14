# V2 API end-to-end tests

These tests exercise the compiled Rust service over real HTTP while it uses a disposable PostGIS container. They never use the Denmark database or real personal data.

Run them from the repository root:

```powershell
$env:UEC_RUN_E2E = "1"
python -m unittest discover -s pipeline/tests/e2e -p "test_*.py" -v
```

This requires Docker Desktop, Cargo, and the pinned Python dependencies. The fixture uses isolated random ports and tears down its Compose project even after setup failures. Fast non-Docker checks remain available with `python -m unittest discover -s pipeline/tests -p "test_*.py" -v`.

`fixture.py` owns the environment lifecycle: it selects isolated ports, starts Docker Compose, applies migrations as UTF-8, builds and starts the backend from a per-run temporary Cargo target directory, waits for readiness, and tears everything down. The isolated target prevents E2E builds from contending with a developer's running backend binary. Setup failures also trigger cleanup. Run the API modules sequentially (`test_public_api`, `test_community_api`, `test_seeded_api`, and `test_candidate_import`) because each module owns a disposable PostGIS environment; running all classes in one discovery process can create avoidable Docker resource/lifecycle contention.

`test_public_api.py` verifies the publication boundary with an empty database: candidate data and filters remain unavailable, and malformed pagination is rejected.

`test_seeded_api.py` uses `seed_official_scenario()` to create synthetic exact, city-level, unmapped, lifecycle, category, and safety-restricted records in a promoted release. This is the reusable starting point for future user-submission and moderation scenarios.

Tests should assert both positive behavior and absence of disclosure. A record being present in the database is not sufficient to make it public; every public response must pass release, visibility, and safety filtering.

The public API suite also seeds a synthetic candidate-only record whose review and geocode fields look publishable. It verifies that candidate data is absent from public list, detail, and export routes. This is not a private preview API: any future end-user candidate preview must be a separate dev/test-only server or route, bound to loopback/private access, unavailable in production mode, and fail closed for remote or ambiguous configuration.
For a local run that exactly matches the standard GitHub Actions database
job, use PowerShell 7 (`pwsh`) and run:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File pipeline/tests/run-standard.ps1
```

The runner destroys the named test volume before startup, applies all
migrations, seeds only synthetic contract fixtures, runs the Rust and Python
test suites, and removes the database in a `finally` block.
