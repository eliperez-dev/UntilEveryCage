$ErrorActionPreference = 'Stop'
$gate = Join-Path $PSScriptRoot 'run-v2-gate.ps1'
$tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$sandbox = [System.IO.Path]::GetFullPath((Join-Path $tempRoot ('uec-v2-gate-test-' + [guid]::NewGuid().ToString('N'))))
if (-not $sandbox.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw 'Test sandbox resolved outside the system temporary directory.'
}

try {
  $testDir = Join-Path $sandbox 'pipeline/tests'
  $binDir = Join-Path $sandbox 'bin'
  New-Item -ItemType Directory -Path $testDir, $binDir -Force | Out-Null
  Copy-Item -LiteralPath $gate -Destination (Join-Path $testDir 'run-v2-gate.ps1')
  $standard = Join-Path $testDir 'run-standard.ps1'
  $fakeNpm = Join-Path $binDir 'npm.cmd'
  $priorPath = $env:PATH
  $env:PATH = "$binDir;$priorPath"
  try {
    foreach ($case in @(
      @{ Name = 'standard failure'; StandardExit = 17; NpmExit = 0; ExpectExit = 1; ExpectText = 'Standard gate failed (exit 17).'; NpmRan = $false; Pass = $false },
      @{ Name = 'npm failure'; StandardExit = 0; NpmExit = 19; ExpectExit = 1; ExpectText = 'npm tests failed (exit 19).'; NpmRan = $true; Pass = $false },
      @{ Name = 'success'; StandardExit = 0; NpmExit = 0; ExpectExit = 0; ExpectText = 'PASS: V2 unit, pipeline, frontend, and synthetic backup/restore gates passed.'; NpmRan = $true; Pass = $true }
    )) {
      Set-Content -LiteralPath $standard -Encoding utf8 -Value "Write-Output 'FAKE_STANDARD_RAN'; exit $($case.StandardExit)"
      Set-Content -LiteralPath $fakeNpm -Encoding ascii -Value ("@echo off" + [Environment]::NewLine + "echo FAKE_NPM_RAN" + [Environment]::NewLine + "exit /b $($case.NpmExit)")
      if ((Get-Command npm).Source -ne $fakeNpm) { throw 'Fake npm command did not take precedence.' }
      $output = (& pwsh -NoProfile -ExecutionPolicy Bypass -File (Join-Path $testDir 'run-v2-gate.ps1') -SkipDocker 2>&1 | Out-String)
      $exitCode = $LASTEXITCODE
      if ($exitCode -ne $case.ExpectExit) { throw "$($case.Name): exit $exitCode, expected $($case.ExpectExit). Output: $output" }
      if (-not $output.Contains($case.ExpectText)) { throw "$($case.Name): missing expected result. Output: $output" }
      if ($output.Contains('FAKE_NPM_RAN') -ne $case.NpmRan) { throw "$($case.Name): npm execution was unexpected. Output: $output" }
      if ($output.Contains('PASS: V2') -ne $case.Pass) { throw "$($case.Name): PASS reporting was unexpected. Output: $output" }
      Write-Host "PASS: $($case.Name)"
    }
  } finally {
    $env:PATH = $priorPath
  }
} finally {
  if ((Test-Path -LiteralPath $sandbox) -and $sandbox.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    Remove-Item -LiteralPath $sandbox -Recurse -Force
  }
}
