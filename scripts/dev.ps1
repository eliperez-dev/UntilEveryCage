param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Args)
$ErrorActionPreference = 'Stop'
python (Join-Path $PSScriptRoot 'dev.py') @Args
exit $LASTEXITCODE
