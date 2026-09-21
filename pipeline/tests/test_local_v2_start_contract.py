"""Safe PowerShell contract checks for the local synthetic V2 launcher."""

import os
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[2]
LAUNCHER = ROOT / "pipeline" / "scripts" / "maintenance" / "local-v2.ps1"
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")


@unittest.skipUnless(POWERSHELL, "PowerShell is unavailable")
class LocalV2StartContractTests(unittest.TestCase):
    def run_powershell(self, script):
        environment = os.environ.copy()
        environment["UEC_TEST_LAUNCHER"] = str(LAUNCHER)
        result = subprocess.run(
            [POWERSHELL, "-NoProfile", "-Command", script],
            cwd=ROOT, env=environment, text=True, capture_output=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return result.stdout

    def test_launcher_parses_and_has_explicit_local_artifact_declaration(self):
        output = self.run_powershell(r"""
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($env:UEC_TEST_LAUNCHER, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw ($errors | Out-String) }
$promotion = @($ast.FindAll({param($node) $node -is [System.Management.Automation.Language.CommandAst] -and $node.GetCommandName() -eq 'python' -and $node.Extent.Text -like '*promote-release.py*'}, $true))
if ($promotion.Count -ne 1) { throw "Expected one local promotion command; found $($promotion.Count)" }
$elements = @($promotion[0].CommandElements | ForEach-Object { $_.Extent.Text })
if (($elements -join '|') -ne 'python|pipeline/scripts/stages/promote-release.py|standard-candidate|--no-distributed-artifacts') { throw "Unexpected promotion command: $($elements -join '|')" }
Write-Output 'PARSE_AND_COMMAND_OK'
""")
        self.assertIn("PARSE_AND_COMMAND_OK", output)

    def test_start_branch_uses_declaration_without_external_side_effects(self):
        output = self.run_powershell(r"""
function docker {
  $global:LASTEXITCODE = 0
  $commandLine = $args -join ' '
  if ($commandLine -like '*to_regclass*') { return 't' }
  if ($commandLine -like '*SELECT status FROM uec.releases*') { return 'validated' }
}
function python {
  $global:LASTEXITCODE = 0
  if ($args[0] -like '*promote-release.py') { $global:promotionArguments = @($args) }
}
function New-Item { param($ItemType, [switch]$Force, $Path) }
function Test-Path { param($Path); return ($Path -like '*uec-api.exe') }
function Start-Process { param($FilePath, $WorkingDirectory, $WindowStyle, $RedirectStandardOutput, $RedirectStandardError, [switch]$PassThru); return [pscustomobject]@{Id=12345} }
function Set-Content { param($Path, $Value, [switch]$NoNewline) }
& $env:UEC_TEST_LAUNCHER -Command start
if (($global:promotionArguments -join '|') -ne 'pipeline/scripts/stages/promote-release.py|standard-candidate|--no-distributed-artifacts') { throw "Unexpected promotion arguments: $($global:promotionArguments -join '|')" }
Write-Output 'MOCKED_START_OK'
""")
        self.assertIn("MOCKED_START_OK", output)


if __name__ == "__main__":
    unittest.main()
