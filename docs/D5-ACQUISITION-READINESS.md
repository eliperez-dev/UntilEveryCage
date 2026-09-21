# D5 acquisition and automation-readiness checklist

This checklist describes the boundary between an existing source-specific
operator path and a future unattended refresh. It is an operational aid, not
an authorization to fetch, publish, or schedule a source.

## Current audit

Run the no-network, row-free audit from the repository root:

```powershell
python pipeline/scripts/diagnostics/d5-live-readiness.py `
  --as-of-utc 2026-09-21T00:00:00Z `
  --output <private-or-reviewed-aggregate-report.json>
```

The report covers exactly the thirteen D2/D3 source IDs. It records the
existing operator command, authorization boundary, source kind, cadence, and
control checks. It must report zero network requests and must not contain rows,
source values, raw artifacts, credentials, or private filesystem paths.

## Source onboarding gate

Before a source can be called `unattended-live-ready`, an authorized operator
must record all of the following in restricted operational storage:

- source terms, rate limits, attribution, and permitted access method;
- stable source URL or documented portal/export route;
- source-specific adapter and schema versions;
- bounded timeout, maximum bytes, retry count, and backoff;
- response/content validation and fail-closed schema drift behavior;
- source URL, retrieval timestamp, effective/publication date when supplied,
  byte size, checksum, redirect facts, and code/configuration versions;
- content-addressed preservation and no-change detection;
- prior validated state to retain when acquisition or validation fails;
- quarantine behavior for malformed, conflicting, private, or ambiguous data;
- private candidate/evidence handoff and review packet;
- idempotent private insertion and a row-free operator exit report;
- a negative test proving no publication, promotion, or public projection;
- a failure-isolation test proving unrelated sources continue after failure.

## Classification meanings

- `unattended-live-ready`: authorized, bounded, tested source acquisition is
  wired into the shared runner and can run without an operator session.
- `authenticated-live-ready`: the source can run unattended with a managed
  credential or token whose storage/rotation is explicitly approved.
- `browser-assisted`: an operator must select/export/capture the source in an
  authorized browser or portal session.
- `preserved-artifact-only`: only a previously captured private artifact is
  available to the adapter.
- `terms-blocked`: a bounded fetch exists, but no approved terms decision is
  available for this run.
- `technically-broken`: the existing path fails for a technical reason that is
  independent of the human/terms gates.

These labels describe acquisition operations only. They do not establish
source accuracy, completeness, privacy eligibility, project approval, or
publication eligibility.

## Versioned all-source plan (future D7)

The eventual refresh plan should be a versioned, reviewable configuration,
not a scheduler full of source-specific logic:

1. Select explicitly named sources or an allowlisted `all-eligible` cohort.
2. Execute sequentially by default with bounded retries and per-source time
   limits.
3. Preserve each source artifact and metadata before parsing.
4. Normalize, validate, quarantine, and create private candidate/evidence
   handoffs.
5. Retain the previous validated state if the new run fails or becomes
   suspicious.
6. Record row-free per-source and aggregate outcomes; continue after an
   isolated source failure.
7. Import only into the private candidate database when explicitly requested.
8. Keep release creation, approval, promotion, and publication as separate
   human-gated actions.

D5 does not install cron, a task scheduler, a persistent worker, credentials,
or a weekly job. A future scheduler may invoke this versioned plan only after
each selected source passes the onboarding gate and the operator has confirmed
the current terms and privacy boundaries.
