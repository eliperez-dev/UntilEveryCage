# Private real-data preview

Use [development](development.md) for the approved v0 baseline and current local
database targets. The preview is not a public release, a substitute baseline
or evidence that source acquisition ran freshly.

The existing developer entry point provides:

```powershell
python scripts/dev.py real-preview up
python scripts/dev.py real-preview status
python scripts/dev.py real-preview probe
python scripts/dev.py real-preview down
```

Inspect status/allocated ports rather than assuming a historic localhost URL.
`down` preserves the isolated database. `reset` is destructive: use only after
verifying the exact owned disposable Compose project/volume and retention.
Never take over a foreign listener or point reset at a retained database.

The private API runs in development on loopback, with `UEC_DEV_PREVIEW=true`
and a process-only preview token supplied through a header. The Vite server
proxy holds that token server-side; never place it in URLs, public bundles,
logs, screenshots, Git or persistent browser storage. Production rejects the
private route. See [the preview contract](api/real-preview-contract.md).

Imports verify explicit handoff manifests, bytes/hashes and counts, then insert
idempotently. Missing source artifacts stay unavailable, not zero or fabricated
verification. Use the shared source-specific runner for new source refreshes;
the historical `import-real-preview.py` allowlist is not national coverage.

After a Docker restart inspect `status`, then start the assigned stack again.
Do not bypass artifact/authentication checks or silently fall back to synthetic
data. Record current source/map counts only in the source inventory and its
aggregate acceptance, not this runbook.
