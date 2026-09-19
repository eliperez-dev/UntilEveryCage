param()

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$sentinel = Join-Path $root 'data\.docker-context-sentinel'
$tag = "uec-docker-context-test-$([Guid]::NewGuid().ToString('N'))"

New-Item -ItemType File -Path $sentinel -Force | Out-Null
try {
  & docker build --file (Join-Path $root 'Dockerfile.context-test') --tag $tag $root
  if ($LASTEXITCODE -ne 0) { throw "Docker context sentinel proof failed (exit $LASTEXITCODE)." }
  Write-Host 'PASS: synthetic private Docker context sentinel was excluded.'
} finally {
  if (Test-Path -LiteralPath $sentinel) { Remove-Item -LiteralPath $sentinel -Force }
  & docker image rm --force $tag *> $null
}
