param([switch]$KeepArtifacts)
$ErrorActionPreference = 'Stop'
if ($env:UEC_RUN_E2E -ne '1') { throw 'Set UEC_RUN_E2E=1 to run the disposable backup/restore verification.' }
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$project = "uec-backup-$([Guid]::NewGuid().ToString('N').Substring(0,8))"
$compose = Join-Path $root 'docker-compose.e2e.yml'; $env:UEC_E2E_DB_PORT = '55433'
$dump = Join-Path ([IO.Path]::GetTempPath()) "$project.dump"
$migrationFile = Join-Path ([IO.Path]::GetTempPath()) "$project-migrations.sql"
try {
  & docker compose -p $project -f $compose up -d --wait
  if ($LASTEXITCODE -ne 0) { throw "Docker startup failed (exit $LASTEXITCODE)." }
  $ready = $false
  $stableChecks = 0
  for ($attempt = 0; $attempt -lt 60; $attempt++) {
    & docker compose -p $project -f $compose exec -T postgres psql -U uec -d uec -c 'SELECT 1' *> $null
    if ($LASTEXITCODE -eq 0) { $stableChecks++ } else { $stableChecks = 0 }
    if ($stableChecks -ge 5) { $ready = $true; break }
    Start-Sleep -Milliseconds 250
  }
  if (-not $ready) { throw 'PostgreSQL did not remain ready after container health reported healthy.' }
  foreach ($migration in (Get-ChildItem (Join-Path $root 'pipeline\migrations') -Filter '*.sql' | Sort-Object Name)) {
    Write-Host "[backup-restore] applying $($migration.Name)"
    $migrationSql = Get-Content $migration.FullName -Raw
    Set-Content -LiteralPath $migrationFile -Value $migrationSql -Encoding UTF8
    & docker compose -p $project -f $compose cp $migrationFile postgres:/tmp/migration.sql
    if ($LASTEXITCODE -ne 0) { throw "Migration upload failed for $($migration.Name) (exit $LASTEXITCODE)." }
    $migrationApplied = $false
    for ($attempt = 0; $attempt -lt 3; $attempt++) {
      & docker compose -p $project -f $compose exec -T postgres psql -1 -v ON_ERROR_STOP=1 -U uec -d uec -f /tmp/migration.sql
      if ($LASTEXITCODE -eq 0) { $migrationApplied = $true; break }
      Start-Sleep -Seconds 2
    }
    if (-not $migrationApplied) { throw "Migration $($migration.Name) failed (exit $LASTEXITCODE)." }
  }
  Get-Content (Join-Path $root 'pipeline\tests\e2e\backup_restore_seed.sql') -Raw | & docker compose -p $project -f $compose exec -T postgres psql -1 -v ON_ERROR_STOP=1 -U uec -d uec
  if ($LASTEXITCODE -ne 0) { throw "Synthetic seed failed (exit $LASTEXITCODE)." }
  & docker compose -p $project -f $compose exec -T postgres pg_dump -U uec -d uec --format=custom --file=/tmp/uec.dump
  if ($LASTEXITCODE -ne 0) { throw "Backup creation failed (exit $LASTEXITCODE)." }
  & docker compose -p $project -f $compose cp postgres:/tmp/uec.dump $dump
  if ($LASTEXITCODE -ne 0) { throw "Backup extraction failed (exit $LASTEXITCODE)." }
  & docker compose -p $project -f $compose exec -T postgres pg_restore -U uec -d uec --clean --if-exists /tmp/uec.dump
  if ($LASTEXITCODE -ne 0) { throw "Restore failed (exit $LASTEXITCODE)." }
  $checks = & docker compose -p $project -f $compose exec -T postgres psql -U uec -d uec -At -c "SELECT count(*) FROM uec.releases WHERE release_id='e2e-promoted' AND status='promoted'; SELECT count(*) FROM uec.release_manifests WHERE release_id='e2e-promoted' AND manifest_sha256='cabe8641a05beb76c9517006a8ec4cdd60b3bad58aa5b0fc29335fee1ac7d5dd'; SELECT count(*) FROM uec.public_access_restricted WHERE source_record_id='00000000-0000-0000-0000-000000000002'; SELECT count(*) FROM uec.map_facilities_display WHERE source_record_id='00000000-0000-0000-0000-000000000002'; SELECT count(*) FROM uec.map_facilities_display_history WHERE source_record_id='00000000-0000-0000-0000-000000000002';"
  if (($checks | Where-Object { $_ -eq '1' }).Count -ne 3 -or ($checks | Where-Object { $_ -eq '0' }).Count -ne 2) { throw "Backup/restore invariant failed (expected 1,1,1,0,0): $checks" }
  Write-Host 'PASS: promoted synthetic release restored; restricted source is excluded from both public projections.'
} finally {
  $savedPreference = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try { & docker compose -p $project -f $compose down -v --remove-orphans *> $null } catch { }
  $ErrorActionPreference = $savedPreference
  if (-not $KeepArtifacts -and (Test-Path -LiteralPath $dump)) { Remove-Item -LiteralPath $dump -Force }
  if (Test-Path -LiteralPath $migrationFile) { Remove-Item -LiteralPath $migrationFile -Force }
}
