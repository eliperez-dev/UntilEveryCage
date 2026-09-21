# Sprint 4 real-corpus regression lane

`pipeline/scripts/diagnostics/real_corpus_regression.py` produces a private,
row-free report from the existing `static_data/*/locations.csv` snapshots.
The default run hashes each input, selects at most 50,000 rows by a stable
row fingerprint, and reports country/source/category/accepted-quarantine/
coordinate-precision/identity-quality strata without writing row data.

Run locally with:

```powershell
python pipeline/scripts/diagnostics/real_corpus_regression.py `
  --output sprint4-real-corpus-regression.json `
  --as-of 2026-09-16T00:00:00Z
```

The output is private and publication-blocked. The current checkout contains
nine country snapshots and roughly 50k existing V1-derived rows, but no raw
source bytes or V2 normalized handoffs. The report therefore records those
stages as unavailable rather than claiming raw-preserving acquisition,
candidate import, or private API/export coverage. A later run with authorized
raw artifacts can extend the same manifest contract without committing rows.
