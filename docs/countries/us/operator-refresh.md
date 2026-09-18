# US current-refresh operator workflow

This is a private/test-only workflow for current FSIS and APHIS observations. It
does not approve, publish, or replace a validated release. The two source lanes
remain separate: FSIS is the federal establishment-directory spine, while APHIS
captures registrations, inspections, and annual reports as distinct evidence
profiles. No cross-source identity join is attempted.

## Browser checkpoint

Use an authorized browser session when the source requires an interactive
export. Save the source-provided file without editing it, and record the final
URL, displayed edition/year or amendment state, retrieval time, and any shown
result count in the plan's `query_context`. A failed, empty, HTML/challenge, or
403 response is not a zero-row observation. Do not probe hidden endpoints,
reuse browser credentials, or bypass an access control.

For FSIS, save the current MPI Directory CSV and, when available, the
Establishment Demographic CSV from the official directory page. For APHIS,
select exactly one profile per entry (`registrations`, `inspections`, or
`annual_reports`); linked documents or amendments are retained separately and
are not automatically merged into rows.

## One-command private refresh

Create a row-free plan outside Git. Paths may be absolute or relative to the
plan file:

```json
{
  "schema_version": "us-operator-plan-v1",
  "retry": {
    "max_attempts": 3,
    "retry_delay_seconds": 1,
    "max_retry_delay_seconds": 30
  },
  "sources": [
    {
      "source": "fsis",
      "directory": "private-captures/fsis-directory.csv",
      "demographics": "private-captures/fsis-demographics.csv",
      "retrieved_at_utc": "2026-09-18T00:00:00Z",
      "effective_date": "2026-09-14",
      "previous_manifest": "private-runs/previous/fsis/lifecycle/manifest.json"
    },
    {
      "source": "aphis",
      "profile": "annual_reports",
      "raw": "private-captures/aphis-annual-reports.csv",
      "retrieved_at_utc": "2026-09-18T00:00:00Z",
      "query_context": {
        "selected_year": "2025",
        "amended_reports_included": true,
        "displayed_result_count": "recorded-in-private-notes"
      }
    }
  ]
}
```

Run a dry-run first:

```powershell
python -m pipeline.sources.us.refresh `
  --plan C:\path\to\private-us-plan.json `
  --run-root C:\path\to\private-us-runs\2026-09-18 `
  --mode dry-run `
  --as-of-utc 2026-09-18T12:00:00Z
```

The row-free `us-refresh-report.json` reports, per source, acquisition facts,
freshness, schema/count drift, exact-key reconciliation, normalized and
quarantined counts, private-import readiness, and the retained previous-valid
state. Review it and the source-specific private artifacts before using
`--mode handoff` for FSIS. APHIS's adapter emits its private candidate handoff
after validation; that remains a human-gated test artifact.

The aggregate command always keeps `release_state=not-created`,
`release_promoted=false`, `public_exposure=false`, and all public surfaces
disabled. A failed lane cannot delete or replace the previous-valid manifest.
The failure record contains an actionable class and fallback without copying
source rows into the aggregate report.

## Diagnostics and retry behavior

Inspect an existing run without opening raw, parsed, normalized, or quarantine
rows:

```powershell
python -m pipeline.sources.us.refresh `
  --run-root C:\path\to\private-us-runs\2026-09-18 `
  --diagnose `
  --as-of-utc 2026-09-18T12:00:00Z
```

Network acquisition is still opt-in and requires the source-specific approved
terms record. The shared acquisition primitive retries only bounded network,
rate-limit, timeout, and interrupted-download failures. It uses temporary
partial files, removes them after an interrupted read, and records every
attempt. HTTP 403, HTML/login/challenge responses, invalid content types,
malformed exports, schema drift, and count drift fail closed; use the browser
capture checkpoint instead of bypassing the restriction.

## Scheduling guidance

FSIS documents a weekly replacement cadence: check the displayed edition before
each weekly run, and treat a missing or changed edition as `not observed`, not
closure. The operations schedule treats a capture older than 240 hours as
stale, with three bounded attempts before the manual two-file capture fallback.

APHIS profile cadence is not established by this project. Trigger it when a
documented source update, selected-year change, amendment, or operator review
requires a new observation. Its freshness is reported as `unknown` unless an
explicit project schedule is later justified by source evidence. Keep each
profile and year/amendment context as a separate observation.

Scheduling private acquisition is not publication authorization. Privacy,
source-rights, factual review, project approval, and release publication remain
separate gates under `docs/ETHICS.md`.
