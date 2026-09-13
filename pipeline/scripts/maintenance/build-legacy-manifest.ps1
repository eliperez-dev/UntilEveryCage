param(
    [string]$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path,
    [string]$OutputPath = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $RepositoryRoot 'data\manifests\legacy-files.csv'
}

$outputDirectory = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null

$excludedDirectories = @('node_modules', '.git', 'target')
$files = Get-ChildItem -LiteralPath $RepositoryRoot -Recurse -File | Where-Object {
    $relative = $_.FullName.Substring($RepositoryRoot.Length).TrimStart('\')
    ($relative -notlike 'data\manifests\*') -and
    ($excludedDirectories | ForEach-Object { $relative -notlike "$_\*" }) -notcontains $false -and
    ($_.Extension.ToLowerInvariant() -in @('.csv', '.xml', '.kml', '.txt')) -and
    ($relative -like 'static_data\*' -or $relative -like 'Old CSVs\*' -or $relative -like 'dirty-datasets\*' -or $relative -eq 'france-data.kml')
} | Sort-Object FullName

$generatedAt = (Get-Date).ToUniversalTime().ToString('o')
$rows = @(foreach ($file in $files) {
    $relative = $file.FullName.Substring($RepositoryRoot.Length).TrimStart('\').Replace('\', '/')
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hash = ([System.BitConverter]::ToString($sha256.ComputeHash([System.IO.File]::ReadAllBytes($file.FullName))) -replace '-', '').ToLowerInvariant()
    }
    finally {
        $sha256.Dispose()
    }
    [pscustomobject]@{
        path = $relative
        bytes = $file.Length
        sha256 = $hash
        data_origin = 'legacy'
        source_retrieval_date_status = 'unknown'
        source_retrieval_date = 'unknown'
        source_observation_date_status = 'unknown'
        source_observation_date = 'unknown'
        generated_at_utc = $generatedAt
    }
})

$rows | Export-Csv -LiteralPath $OutputPath -NoTypeInformation -Encoding UTF8
Write-Output "Wrote $($rows.Count) legacy file records to $OutputPath"
