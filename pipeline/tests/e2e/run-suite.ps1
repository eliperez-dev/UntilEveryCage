param(
  [ValidateSet('core', 'full')]
  [string]$Suite = 'core'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$core = @(
  'pipeline.tests.e2e.test_public_api',
  'pipeline.tests.e2e.test_community_api',
  'pipeline.tests.e2e.test_seeded_api',
  'pipeline.tests.e2e.test_public_surface_safety',
  'pipeline.tests.e2e.test_candidate_import',
  'pipeline.tests.e2e.test_private_graph',
  'pipeline.tests.e2e.test_readiness'
)
$extended = @(
  'pipeline.tests.e2e.test_suppression_lifecycle',
  'pipeline.tests.e2e.test_release_summary_component',
  'pipeline.tests.e2e.test_public_discovery_read_model',
  'pipeline.tests.e2e.test_italy_candidate_import',
  'pipeline.tests.e2e.test_germany_belgium_candidate_import'
)
$tests = if ($Suite -eq 'full') { $core + $extended } else { $core }

Push-Location $root
try {
  $env:UEC_RUN_E2E = '1'
  foreach ($test in $tests) {
    Write-Host "[e2e] running $test"
    & python -m unittest $test -v
    if ($LASTEXITCODE -ne 0) { throw "E2E module failed: $test (exit $LASTEXITCODE)" }
  }
  Write-Host "[e2e] $Suite suite passed ($($tests.Count) isolated modules)"
}
finally {
  Remove-Item Env:UEC_RUN_E2E -ErrorAction SilentlyContinue
  Pop-Location
}
