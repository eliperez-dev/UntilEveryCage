# Synthetic backup/restore verification

This check uses only disposable PostGIS containers and synthetic records. It applies every migration, seeds a promoted release plus an active suppression case, creates a custom-format `pg_dump`, rolls back to that older backup, rejects the stale restriction snapshot, replays the independent payload-free ledger, and verifies the promoted release survives while restricted records remain excluded by the current public restriction view.

From PowerShell:

```powershell
$env:UEC_RUN_E2E = "1"
pwsh -NoProfile -ExecutionPolicy Bypass -File pipeline/tests/e2e/backup-restore.ps1
```

The script uses a unique Compose project and removes its volume in `finally`. `-KeepArtifacts` retains the temporary dump for local inspection only. It never reads project data or credentials. No application service is started during the drill; the point of the gate is to prove that an old restore stays stopped until current restrictions are replayed.
