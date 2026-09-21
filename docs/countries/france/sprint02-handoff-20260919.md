# France Sprint 02 private handoff

This row-free report records the completed private candidate handoff. It does
not contain facility names, addresses, SIRET values, coordinates, or source
rows. The retained source and derived row payloads remain under the ignored
private root below.

## Handoff location

`C:\New Projects\UntilEveryCage\.private\sprint02-20260919\france`

The shared checkout verifies this path as ignored by:

```powershell
git -C 'C:\New Projects\UntilEveryCage' check-ignore -v --no-index '.private/sprint02-20260919/france/probe'
```

The verified rule is `/.private/` in the shared checkout's `.gitignore`, with
an additional local `.private/.gitignore` containing `*`.

## Captured sources

| Source ID | Scope | Retrieved UTC | Source effective/last-modified date | Bytes | SHA-256 | Input | Normalized | Quarantined |
| --- | --- | --- | --- | ---: | --- | ---: | ---: | ---: |
| `fr.dgal.section-i` | DGAL 853/2004 Section I; domestic ungulates | 2026-09-19T17:58:11Z | 2026-09-19T02:21:55Z | 204401 | `30375dc6d426ae723496d2a777e99b43328920f7d50a39ebd2e5fb3baf4bf933` | 1449 | 1449 | 0 |
| `fr.dgal.section-ii` | DGAL 853/2004 Section II; poultry and lagomorphs | 2026-09-19T17:58:27Z | 2026-09-19T02:22:19Z | 136766 | `f011341de6fcaf352b625d7dbee4fb9252f5722d7f598d3e35bed0b044dab9e1` | 1068 | 1068 | 0 |

Both official routes returned one bounded response and were captured. No
failed acquisition partition occurred. Combined input/normalized/quarantine
totals are 2517/2517/0, and the partition check is valid. The two scopes are
not summed as unique facilities. The row-free reconciliation counted 233
shared provisional approval-number signals; this is an unresolved identity
review signal and no automatic merge was performed. `unique_facility_count`
remains intentionally unknown/null. The corrected v2 replay reports 2
shared-SIRET groups spanning approval/category observations across 4 Section I
rows and 0 Section II groups/rows. These remain accepted source observations
with an explicit unresolved identity-review state. Source address-state
counts are 1434 present / 15 blank-or-whitespace for Section I and 1037 / 31
for Section II; normalized address and coordinate fields remain suppressed.

## Exact private artifacts

- Section I raw run: `raw\fr.dgal.section-i\section-i-20260919T175808Z\source.txt`
- Section I lifecycle run (v2 replay): `refresh-section-i-replay-v2-20260919T\lifecycle\30375dc6d426ae72-5p9j19m3`
- Section I candidate handoff (v2 replay): `refresh-section-i-replay-v2-20260919T\lifecycle\30375dc6d426ae72-5p9j19m3\candidate-handoff`
- Section II raw run: `raw\fr.dgal.section-ii\section-ii-20260919T175824Z\source.txt`
- Section II lifecycle run (v2 replay): `refresh-section-ii-replay-v2-20260919T\lifecycle\f011341de6fcaf35-mkj1wakx`
- Section II candidate handoff (v2 replay): `refresh-section-ii-replay-v2-20260919T\lifecycle\f011341de6fcaf35-mkj1wakx\candidate-handoff`
- Row-free reconciliation: `france-reconciliation-20260919.json`
- Private acquisition terms record: `terms-review-private-acquisition.json`

Each lifecycle run contains acquisition metadata, immutable source hash/size,
parsed and normalized JSONL, quarantine JSONL, QA, health, run status, review
packet, release diff, history ledger, and candidate handoff. The normalized
records retain source provenance while suppressing address and coordinates
from normalized location fields; original source values remain restricted.

## Reproduction and verification

From the repository checkout, with the shared private root already present:

```powershell
python -m unittest pipeline.sources.france.test_adapter pipeline.sources.france.test_refresh pipeline.sources.france.test_reconcile -v
python -m pipeline.sources.france.reconcile --section-i-run '<private>\refresh-section-i-replay-v2-20260919T\lifecycle\30375dc6d426ae72-5p9j19m3' --section-ii-run '<private>\refresh-section-ii-replay-v2-20260919T\lifecycle\f011341de6fcaf35-mkj1wakx' --output '<private>\france-reconciliation-20260919.json'
Get-FileHash -Algorithm SHA256 '<private>\raw\fr.dgal.section-i\section-i-20260919T175808Z\source.txt'
Get-FileHash -Algorithm SHA256 '<private>\raw\fr.dgal.section-ii\section-ii-20260919T175824Z\source.txt'
```

The corrected v2 replay lifecycle states are `candidate-ready` /
`private-candidate`,
`publication_state=human-gate-required`, `release_state=not-created`, and
`geocoding=disabled` for both sources. The replay uses adapter
`fr-dgal-853-v2` and schema `fr-dgal-853-txt-v2`. No public release, API
promotion, or paid geocoding was performed.

## Remaining gates

File-specific reuse/attribution terms, privacy and address screening,
coordinate review, category-code review, cross-section identity review, and
project publication approval remain open. A source disappearance is not
interpreted as closure. This handoff is suitable for restricted review and
replay only, not public redistribution.
