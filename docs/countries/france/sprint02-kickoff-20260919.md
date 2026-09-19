# France Sprint 02 kickoff

Recorded before any Sprint 02 retained download: 2026-09-19.

This is a row-free lane report. Facility names, addresses, SIRET values,
coordinates, raw responses, and normalized records remain in the shared
restricted handoff only.

## Frozen existing registry sources

| Source ID | Existing source scope | Official route |
| --- | --- | --- |
| `fr.dgal.section-i` | France DGAL Regulation (EC) 853/2004 Section I; domestic ungulate establishments | `https://fichiers-publics.agriculture.gouv.fr/dgal/ListesOfficielles/SSA1_VIAN_ONG_DOM.txt` |
| `fr.dgal.section-ii` | France DGAL Regulation (EC) 853/2004 Section II; poultry and lagomorph establishments | `https://fichiers-publics.agriculture.gouv.fr/dgal/ListesOfficielles/SSA1_VIAN_COL_LAGO.txt` |

These IDs and scopes are taken from the existing `pipeline/source_registry.json`
and are not newly invented for this lane. Section I and Section II remain
separate source scopes; overlap is reconciled as observations and is not an
automatic facility merge.

## Intended private handoff

The restricted handoff root is:

`C:\New Projects\UntilEveryCage\.private\sprint02-20260919\france`

The lane will preserve one new run directory per source retrieval, including
the original response bytes, acquisition metadata, parsed/normalized output,
quarantine, QA/health/review artifacts, and candidate handoff. Geocoding is
disabled. The output is a private candidate only; no release or public API
promotion is performed by this lane.

## Coverage and unresolved gates

- Retrieval is a current snapshot of each published DGAL file, not a claim of
  historical completeness or operating status.
- A missing later row means `not observed`, never closure.
- Source category/activity labels remain alongside conservative derived labels;
  unknown categories, duplicate observations, identity ambiguity, and missing
  location precision remain review states.
- File-specific terms/attribution, privacy screening, coordinate review, and
  project approval remain human gates. No paid geocoding or guessed coordinate
  is used.
