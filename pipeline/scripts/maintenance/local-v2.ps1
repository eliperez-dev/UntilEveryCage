param([ValidateSet('start','status','stop','probe')][string]$Command='status')
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$compose=Join-Path $root 'docker-compose.pipeline.yml'
$project='uec-local-v2'; $dbPort=5433; $apiPort=8000
$db="postgresql://uec:uec-local-development-only@127.0.0.1:$dbPort/uec?sslmode=disable"
$stateDir=Join-Path $root 'target\local-v2'; $pidFile=Join-Path $stateDir 'uec-api.pid'; $logFile=Join-Path $stateDir 'uec-api.log'; $errorFile=Join-Path $stateDir 'uec-api-error.log'
$env:UEC_PIPELINE_DB_PORT="$dbPort"; $env:UEC_DATABASE_URL=$db; $env:PORT="$apiPort"
$env:UEC_CORS_ORIGIN="http://127.0.0.1:4173"

function Get-OwnedApiProcess {
  if (!(Test-Path $pidFile)) { return $null }
  $processId=[int](Get-Content $pidFile -Raw).Trim(); $process=Get-Process -Id $processId -ErrorAction SilentlyContinue
  if ($process -and $process.ProcessName -eq 'uec-api' -and $process.Path -eq (Join-Path $root 'target\debug\uec-api.exe')) { return $process }
  return $null
}

Push-Location $root
try {
  switch ($Command) {
    'start' {
      New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
      & docker compose -p $project -f $compose up -d --wait
      if ($LASTEXITCODE) { throw 'Postgres startup failed.' }
      python pipeline/scripts/maintenance/apply-migrations.py
      if ($LASTEXITCODE) { throw 'Migration application failed.' }
      $seeded=& docker compose -p $project -f $compose exec -T postgres psql -U uec -d uec -Atc "SELECT to_regclass('uec.local_v2_fixture_seed') IS NOT NULL"
      if ($seeded.Trim() -ne 't') {
        Get-Content pipeline/tests/standard_contract_seed.sql -Raw | & docker compose -p $project -f $compose exec -T postgres psql -v ON_ERROR_STOP=1 -U uec -d uec
        if ($LASTEXITCODE) { throw 'Synthetic seed failed.' }
        & docker compose -p $project -f $compose exec -T postgres psql -v ON_ERROR_STOP=1 -U uec -d uec -c "CREATE TABLE IF NOT EXISTS uec.local_v2_fixture_seed (seed_name text primary key, seeded_at timestamptz not null default now()); INSERT INTO uec.local_v2_fixture_seed(seed_name) VALUES ('standard-contract') ON CONFLICT DO NOTHING;"
      }
      $releaseStatus=(& docker compose -p $project -f $compose exec -T postgres psql -U uec -d uec -Atc "SELECT status FROM uec.releases WHERE release_id = 'standard-candidate'")
      if ($releaseStatus.Trim() -eq 'candidate') {
        python pipeline/scripts/stages/validate-release.py standard-candidate --expected-records 1 --mark-validated
        if ($LASTEXITCODE) { throw 'Synthetic release validation failed.' }
        $releaseStatus='validated'
      }
      if ($releaseStatus.Trim() -eq 'validated') {
        python pipeline/scripts/stages/promote-release.py standard-candidate --no-distributed-artifacts
        if ($LASTEXITCODE) { throw 'Synthetic release promotion failed.' }
      } elseif ($releaseStatus.Trim() -ne 'promoted') {
        throw "Synthetic release has unexpected status: $($releaseStatus.Trim())"
      }
      if (!(Get-OwnedApiProcess)) {
        $api=Join-Path $root 'target\debug\uec-api.exe'; if (!(Test-Path $api)) { cargo build --bin uec-api --quiet }
        $process=Start-Process -FilePath $api -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $logFile -RedirectStandardError $errorFile -PassThru
        Set-Content -Path $pidFile -Value $process.Id -NoNewline
      }
      Write-Host "Local V2 ready: http://127.0.0.1:$apiPort (database $dbPort)."
    }
    'status' {
      & docker compose -p $project -f $compose ps
      $api=Get-OwnedApiProcess; if ($api) { Write-Host "Axum running: PID $($api.Id), port $apiPort" } else { Write-Host 'Axum not managed by local-v2.ps1.' }
    }
    'stop' {
      $api=Get-OwnedApiProcess; if ($api) { Stop-Process -Id $api.Id -Force; Remove-Item $pidFile -Force }
      & docker compose -p $project -f $compose stop
      if ($LASTEXITCODE) { throw 'Postgres stop failed.' }
      Write-Host 'Local V2 Axum and Postgres stopped; data volume preserved.'
    }
    'probe' { & node frontend/scripts/probe-local-v2.mjs "http://127.0.0.1:$apiPort"; if ($LASTEXITCODE) { throw 'Local V2 probe failed.' } }
  }
} finally { Pop-Location }
