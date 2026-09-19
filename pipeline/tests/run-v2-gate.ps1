param([switch]$SkipDocker)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Push-Location $root
try {
  & pwsh -NoProfile -ExecutionPolicy Bypass -File pipeline/tests/run-standard.ps1
  if ($LASTEXITCODE -ne 0) { throw "Standard gate failed (exit $LASTEXITCODE)." }
  & npm test -- --runInBand
  if ($LASTEXITCODE -ne 0) { throw "npm tests failed (exit $LASTEXITCODE)." }
  if (-not $SkipDocker) {
    $env:UEC_RUN_E2E = '1'
    pwsh -NoProfile -ExecutionPolicy Bypass -File pipeline/tests/e2e/backup-restore.ps1
    if ($LASTEXITCODE -ne 0) { throw "Backup/restore E2E failed (exit $LASTEXITCODE)." }
  }
  Write-Host 'PASS: V2 unit, pipeline, frontend, and synthetic backup/restore gates passed.'
} finally { Pop-Location }
