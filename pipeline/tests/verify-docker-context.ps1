param()

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$sentinel = Join-Path $root 'data\.docker-context-sentinel'
$privateSentinel = Join-Path $root '.private\.docker-context-sentinel'
$tag = "uec-docker-context-test-$([Guid]::NewGuid().ToString('N'))"

New-Item -ItemType File -Path $sentinel -Force | Out-Null
New-Item -ItemType Directory -Path (Split-Path -Parent $privateSentinel) -Force | Out-Null
New-Item -ItemType File -Path $privateSentinel -Force | Out-Null
try {
  & docker build --file (Join-Path $root 'Dockerfile.context-test') --tag $tag $root
  if ($LASTEXITCODE -ne 0) { throw "Docker context sentinel proof failed (exit $LASTEXITCODE)." }
  Write-Host 'PASS: synthetic private Docker context sentinel was excluded.'
} finally {
  if (Test-Path -LiteralPath $sentinel) { Remove-Item -LiteralPath $sentinel -Force }
  if (Test-Path -LiteralPath $privateSentinel) { Remove-Item -LiteralPath $privateSentinel -Force }
  & docker image rm --force $tag *> $null
}
