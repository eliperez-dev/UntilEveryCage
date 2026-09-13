$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$env:UEC_DATABASE_URL = if ($env:UEC_DATABASE_URL) { $env:UEC_DATABASE_URL } else { 'postgresql://uec:uec-local-development-only@localhost:5433/uec' }
$env:PORT = '18080'
$baseUrl = 'http://localhost:18080'
$server = $null
$logPath = Join-Path $repo 'target/e2e-api.log'
$errorPath = Join-Path $repo 'target/e2e-api-error.log'

try {
    & cargo build --quiet
    $server = Start-Process -FilePath (Join-Path $repo 'target/debug/heatmap-backend.exe') -WorkingDirectory $repo -PassThru -WindowStyle Hidden -RedirectStandardOutput $logPath -RedirectStandardError $errorPath
    $ready = $false
    for ($i = 0; $i -lt 60; $i++) {
        try { $null = Invoke-WebRequest "$baseUrl/api/v2/locations?country_code=DK&limit=1" -UseBasicParsing; $ready = $true; break } catch { Start-Sleep -Milliseconds 250 }
    }
    if (-not $ready) { throw "API did not become ready on port 18080. See $logPath" }

    $response = Invoke-RestMethod "$baseUrl/api/v2/locations?country_code=DK&limit=1"
    if ($response.api_version -ne 'v2') { throw 'Wrong API version' }
    if ($null -eq $response.data) { throw 'Missing data envelope' }
    if (@($response.data).Count -gt 1) { throw 'Pagination limit was not enforced' }

    foreach ($uri in @(
        "$baseUrl/api/v2/locations?category=logistics_and_storage&limit=1",
        "$baseUrl/api/v2/locations?display_precision=city&lifecycle_status=active_observed&limit=1"
    )) {
        $filtered = Invoke-RestMethod $uri
        if ($filtered.api_version -ne 'v2') { throw "Filter failed: $uri" }
    }

    $raw = (Invoke-WebRequest "$baseUrl/api/v2/locations?country_code=DK&limit=1" -UseBasicParsing).Content
    foreach ($forbidden in @('raw_fields', 'street_address', 'phone', 'private_address')) {
        if ($raw.Contains($forbidden)) { throw "Forbidden field leaked: $forbidden" }
    }

    $malformedFailed = $false
    try { Invoke-RestMethod "$baseUrl/api/v2/locations?limit=not-a-number" | Out-Null }
    catch {
        $malformedFailed = $true
        if ($_.Exception.Response.StatusCode.value__ -ne 400) { throw }
    }
    if (-not $malformedFailed) { throw 'Malformed limit was accepted' }

    Write-Host 'E2E API tests passed'
}
finally {
    if ($server -and -not $server.HasExited) { Stop-Process -Id $server.Id -Force }
}
