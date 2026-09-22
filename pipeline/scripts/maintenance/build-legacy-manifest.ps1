param(
    [string]$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path,
    [string]$OutputPath = '',
    [string]$StatusOutputPath = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $RepositoryRoot 'data\manifests\legacy-files.csv'
}
if ([string]::IsNullOrWhiteSpace($StatusOutputPath)) {
    $StatusOutputPath = Join-Path $RepositoryRoot 'data\manifests\legacy-status.json'
}

$outputDirectory = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
$statusDirectory = Split-Path -Parent $StatusOutputPath
New-Item -ItemType Directory -Force -Path $statusDirectory | Out-Null

$legacyRoots = @('static_data', 'Old CSVs', 'dirty-datasets')
$files = @(
    foreach ($legacyRoot in $legacyRoots) {
        $rootPath = Join-Path $RepositoryRoot $legacyRoot
        if (Test-Path -LiteralPath $rootPath -PathType Container) {
            Get-ChildItem -LiteralPath $rootPath -Recurse -File | Where-Object {
                $_.Extension.ToLowerInvariant() -in @('.csv', '.xml', '.kml', '.txt')
            }
        }
    }
    $rootKml = Join-Path $RepositoryRoot 'france-data.kml'
    if (Test-Path -LiteralPath $rootKml -PathType Leaf) {
        Get-Item -LiteralPath $rootKml
    }
) | Sort-Object FullName

$generatedAt = (Get-Date).ToUniversalTime().ToString('o')
$rows = @(foreach ($file in $files) {
    $relative = [System.IO.Path]::GetRelativePath($RepositoryRoot, $file.FullName).Replace('\', '/')
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

# This ledger deliberately contains only repository-relative metadata.  It is
# an integrity and migration-boundary record, not a second copy of the legacy
# data and not evidence that any source is current or publication-eligible.
$statusRows = @($rows | ForEach-Object {
    $pathParts = $_.path.Split('/')
    $legacyGroup = if ($pathParts.Count -gt 1) { $pathParts[0] } else { 'repository-root' }
    [ordered]@{
        path = $_.path
        legacy_group = $legacyGroup
        artifact_state = 'present'
        integrity_state = 'sha256_verified'
        data_origin = 'legacy'
        lineage_state = 'unknown'
        currentness_state = 'unknown'
        database_migration_status = 'metadata_only_not_migrated'
        publication_status = 'not_eligible'
    }
})
$ledger = [ordered]@{
    schema_version = 'legacy-status-v1'
    generated_at_utc = $generatedAt
    scope = 'repository-relative legacy artifact metadata; no raw payloads'
    totals = [ordered]@{
        files = $statusRows.Count
        bytes = [int64](($rows | Measure-Object -Property bytes -Sum).Sum)
        present = @($statusRows | Where-Object artifact_state -eq 'present').Count
        sha256_verified = @($statusRows | Where-Object integrity_state -eq 'sha256_verified').Count
        metadata_only_not_migrated = @($statusRows | Where-Object database_migration_status -eq 'metadata_only_not_migrated').Count
        database_migrated = @($statusRows | Where-Object database_migration_status -eq 'db_migrated').Count
        lineage_unknown = @($statusRows | Where-Object lineage_state -eq 'unknown').Count
    }
    records = $statusRows
}
$ledger | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $StatusOutputPath -Encoding UTF8
Write-Output "Wrote $($rows.Count) legacy file records to $OutputPath and status ledger to $StatusOutputPath"
