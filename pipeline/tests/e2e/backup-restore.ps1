param([switch]$KeepArtifacts)
$ErrorActionPreference = 'Stop'
if ($env:UEC_RUN_E2E -ne '1') { throw 'Set UEC_RUN_E2E=1 to run the disposable backup/restore verification.' }
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$project = "uec-backup-$([Guid]::NewGuid().ToString('N').Substring(0,8))"
$compose = Join-Path $root 'docker-compose.e2e.yml'
$portlessCompose = Join-Path $PSScriptRoot 'docker-compose.backup-restore.yml'
$composeArgs = @('-p', $project, '-f', $compose, '-f', $portlessCompose)
$dump = Join-Path ([IO.Path]::GetTempPath()) "$project.dump"
$migrationFile = Join-Path ([IO.Path]::GetTempPath()) "$project-migrations.sql"
$seedFile = Join-Path $PSScriptRoot 'backup_restore_seed.sql'
$suppressionFile = Join-Path $PSScriptRoot 'backup_restore_current_suppression.sql'

function Invoke-FixtureSql([string]$path) {
  Get-Content -LiteralPath $path -Raw | & docker compose @composeArgs exec -T postgres psql -1 -v ON_ERROR_STOP=1 -U uec -d uec
  if ($LASTEXITCODE -ne 0) { throw "Fixture SQL failed: $path (exit $LASTEXITCODE)." }
}

function Get-Snapshot {
  $sql = @"
SELECT count(*) FROM uec.releases WHERE release_id='e2e-promoted' AND status='promoted';
SELECT count(*) FROM uec.release_manifests WHERE release_id='e2e-promoted' AND manifest_sha256='cabe8641a05beb76c9517006a8ec4cdd60b3bad58aa5b0fc29335fee1ac7d5dd';
SELECT count(*) FROM uec.suppression_cases WHERE case_id='00000000-0000-0000-0000-000000000003' AND status='active';
SELECT count(*) FROM uec.suppression_references WHERE case_id='00000000-0000-0000-0000-000000000003' AND source_id='e2e.backup' AND source_record_key='restricted' AND scope='whole_record';
SELECT count(*) FROM uec.public_access_restricted WHERE source_record_id='00000000-0000-0000-0000-000000000002';
SELECT count(*) FROM uec.map_facilities_display WHERE source_record_id='00000000-0000-0000-0000-000000000002';
SELECT count(*) FROM uec.map_facilities_display_history WHERE source_record_id='00000000-0000-0000-0000-000000000002';
"@
  $result = @(& docker compose @composeArgs exec -T postgres psql -v ON_ERROR_STOP=1 -U uec -d uec -At -c $sql)
  if ($LASTEXITCODE -ne 0) { throw "Restore gate query failed (exit $LASTEXITCODE)." }
  return @($result | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' })
}

function Assert-Snapshot([string]$phase, [string]$expected) {
  $actual = (Get-Snapshot) -join ','
  if ($actual -ne $expected) { throw "$phase invariant failed (expected $expected; got $actual). Public service must remain stopped." }
  Write-Host "[backup-restore] ${phase}: $actual"
}

function Test-SyntheticServiceGate {
  # The external synthetic restriction is required in the restored DB and both
  # public projections must exclude it. A query error stops the drill.
  return ((Get-Snapshot) -join ',') -eq '1,1,1,1,1,0,0'
}

try {
  if (-not (Test-Path -LiteralPath $seedFile) -or -not (Test-Path -LiteralPath $suppressionFile)) {
    throw 'Synthetic seed or current-suppression fixture is missing; public service gate stays closed.'
  }
  $configuration = & docker compose @composeArgs config --format json | ConvertFrom-Json
  if ($LASTEXITCODE -ne 0) { throw "Docker Compose configuration failed (exit $LASTEXITCODE)." }
  if ($configuration.services.postgres.ports) { throw 'Backup/restore drill must not publish a PostgreSQL host port.' }
  & docker compose @composeArgs up -d --wait
  if ($LASTEXITCODE -ne 0) { throw "Docker startup failed (exit $LASTEXITCODE)." }
  $ready = $false
  $stableChecks = 0
  for ($attempt = 0; $attempt -lt 60; $attempt++) {
    & docker compose @composeArgs exec -T postgres psql -U uec -d uec -c 'SELECT 1' *> $null
    if ($LASTEXITCODE -eq 0) { $stableChecks++ } else { $stableChecks = 0 }
    if ($stableChecks -ge 5) { $ready = $true; break }
    Start-Sleep -Milliseconds 250
  }
  if (-not $ready) { throw 'PostgreSQL did not remain ready after container health reported healthy.' }
  foreach ($migration in (Get-ChildItem (Join-Path $root 'pipeline\migrations') -Filter '*.sql' | Sort-Object Name)) {
    Write-Host "[backup-restore] applying $($migration.Name)"
    $migrationSql = Get-Content $migration.FullName -Raw
    Set-Content -LiteralPath $migrationFile -Value $migrationSql -Encoding UTF8
    & docker compose @composeArgs cp $migrationFile postgres:/tmp/migration.sql
    if ($LASTEXITCODE -ne 0) { throw "Migration upload failed for $($migration.Name) (exit $LASTEXITCODE)." }
    $migrationApplied = $false
    for ($attempt = 0; $attempt -lt 3; $attempt++) {
      & docker compose @composeArgs exec -T postgres psql -1 -v ON_ERROR_STOP=1 -U uec -d uec -f /tmp/migration.sql
      if ($LASTEXITCODE -eq 0) { $migrationApplied = $true; break }
      Start-Sleep -Seconds 2
    }
    if (-not $migrationApplied) { throw "Migration $($migration.Name) failed (exit $LASTEXITCODE)." }
  }
  Invoke-FixtureSql $seedFile
  Assert-Snapshot 'older eligible state' '1,1,0,0,0,1,1'
  & docker compose @composeArgs exec -T postgres pg_dump -U uec -d uec --format=custom --file=/tmp/uec.dump
  if ($LASTEXITCODE -ne 0) { throw "Backup creation failed (exit $LASTEXITCODE)." }
  & docker compose @composeArgs cp postgres:/tmp/uec.dump $dump
  if ($LASTEXITCODE -ne 0) { throw "Backup extraction failed (exit $LASTEXITCODE)." }
  Invoke-FixtureSql $suppressionFile
  Assert-Snapshot 'later restriction active' '1,1,1,1,1,0,0'
  if (-not (Test-SyntheticServiceGate)) { throw 'Current synthetic restriction did not close both public projections.' }

  # No application service is started anywhere in this drill. An old restore
  # loses the newer case, so the service gate MUST reject it before replay.
  & docker compose @composeArgs exec -T postgres pg_restore -U uec -d uec --clean --if-exists --exit-on-error /tmp/uec.dump
  if ($LASTEXITCODE -ne 0) { throw "Restore failed (exit $LASTEXITCODE)." }
  Assert-Snapshot 'old backup restored, before replay' '1,1,0,0,0,1,1'
  if (Test-SyntheticServiceGate) { throw 'Unsafe drill gate accepted an old backup before current restriction replay.' }
  Write-Host '[backup-restore] PASS: synthetic pre-service gate rejects the old backup before replay.'

  Invoke-FixtureSql $suppressionFile
  Assert-Snapshot 'current restriction replayed' '1,1,1,1,1,0,0'
  if (-not (Test-SyntheticServiceGate)) { throw 'Synthetic pre-service gate rejected the replayed current restriction.' }
  Write-Host 'PASS: synthetic old-backup restore remains gated until current restriction is replayed and both public projections exclude it.'
  Write-Host 'TEST ONLY: production still needs an independent durable restriction ledger and an enforced service-start gate.'
} finally {
  $savedPreference = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try { & docker compose @composeArgs down -v --remove-orphans *> $null } catch { }
  $ErrorActionPreference = $savedPreference
  if (-not $KeepArtifacts -and (Test-Path -LiteralPath $dump)) { Remove-Item -LiteralPath $dump -Force }
  if (Test-Path -LiteralPath $migrationFile) { Remove-Item -LiteralPath $migrationFile -Force }
}
