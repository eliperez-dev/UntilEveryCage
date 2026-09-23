param()

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$compose = Join-Path $root 'docker-compose.pipeline.yml'
$project = 'uec-standard'
$port = '55434'
$databaseUrl = "postgresql://uec:uec-local-development-only@localhost:$port/uec"

Push-Location $root
try {
  # Always begin from the same clean database state locally and in CI.
  $env:UEC_PIPELINE_DB_PORT = $port
  & docker compose -p $project -f $compose down -v --remove-orphans *> $null
  & docker compose -p $project -f $compose up -d --wait
  if ($LASTEXITCODE -ne 0) { throw "PostGIS startup failed (exit $LASTEXITCODE)." }

  $env:UEC_DATABASE_URL = "${databaseUrl}?sslmode=disable"
  python pipeline/scripts/maintenance/apply-migrations.py
  if ($LASTEXITCODE -ne 0) { throw "Migration application failed (exit $LASTEXITCODE)." }
  python pipeline/tests/db_schema_preflight.py
  if ($LASTEXITCODE -ne 0) { throw "Database/schema preflight failed (exit $LASTEXITCODE)." }

  Remove-Item Env:UEC_RUN_E2E -ErrorAction SilentlyContinue
  cargo test --locked
  if ($LASTEXITCODE -ne 0) { throw "Rust tests failed (exit $LASTEXITCODE)." }

  Get-Content (Join-Path $root 'pipeline\tests\standard_contract_seed.sql') -Raw |
    & docker compose -p $project -f $compose exec -T postgres psql -v ON_ERROR_STOP=1 -U uec -d uec
  if ($LASTEXITCODE -ne 0) { throw "Synthetic fixture seeding failed (exit $LASTEXITCODE)." }

  # The rights proof owns its own disposable PostGIS stack and is mandatory
  # in the canonical standard run; it must never become an accidental skip.
  $env:UEC_RUN_RIGHTS_DB = '1'
  python pipeline/tests/run_unittest.py --start-directory pipeline/tests
  if ($LASTEXITCODE -ne 0) { throw "Python tests failed (exit $LASTEXITCODE)." }

  python -m unittest -q pipeline.germany.test_adapter pipeline.germany.test_orchestrator pipeline.common.test_delta pipeline.common.test_orchestrator pipeline.common.test_registry pipeline.contracts.test_adapter_contract pipeline.contracts.test_candidate_handoff pipeline.sources.denmark.test_adapter pipeline.sources.australia.test_npi pipeline.sources.australia.test_sa_epa pipeline.sources.uk.fsa_approved.test_adapter pipeline.sources.uk.fsa_approved.test_handoff pipeline.sources.uk.fss_approved.test_adapter pipeline.sources.uk.fss_approved.test_handoff pipeline.sources.uk.approved.test_compose
  if ($LASTEXITCODE -ne 0) { throw "Country adapter tests failed (exit $LASTEXITCODE)." }
}
finally {
  Remove-Item Env:UEC_RUN_RIGHTS_DB -ErrorAction SilentlyContinue
  $savedPreference = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  & docker compose -p $project -f $compose down -v --remove-orphans *> $null
  $ErrorActionPreference = $savedPreference
  Pop-Location
}
