# Belgium FASFC private pipeline

The source pair is the official FASFC weekly operator CSV plus the official
LAP/PAP activity-code catalogue. The shared runner performs both bounded
downloads, append-only artifact preservation with independent hashes and
response provenance, exact schema-fingerprint validation, CP1252/CSV parsing,
quarantine, normalization, and (when explicitly requested) private database
candidate import in one invocation:

```powershell
python -m pipeline.refresh_private `
  --source be.locations `
  --mode live-acquisition `
  --authorize-live-source be.locations `
  --terms-review be.locations=data/terms-reviews/be.locations.json `
  --output-root data/staging/private-refresh `
  --retries 1 `
  --import-candidates `
  --disposable-db `
  --database-url-env UEC_DATABASE_URL
```

`UEC_DATABASE_URL` must point to the project's loopback disposable database
that passes the existing database marker/safety guard. The command explicitly
requests source-scoped live access and separately acknowledges the disposable
database boundary. Each invocation receives a unique immutable acquisition
run ID unless an operator supplies `--run-id` for deliberate resume. Two
bounded HTTP attempts are allowed per artifact with a 180-second request
timeout; the shared runner allows one additional bounded source retry.

The activity-code catalogue is joined by exact PAP ID. Animal-scope candidates
are selected only when that ID and its exact place/activity/product code tuple
match the explicit allowlist in `config.json`. Descriptive labels are not used
to infer scope. Counts for total input rows, accepted activity observations, selected
animal-scope observations, quarantines, and distinct source-scoped facility
identifiers are reported separately. These must never be added together as a
facility total.

Normalized and candidate-handoff records suppress names, operator/approval
numbers, addresses, postcodes, and coordinates. Immutable source bytes remain
in restricted ignored storage. Candidate handoffs are further limited to
animal-scope observations and coarse municipality values. The current
operator/codebook header fingerprints are pinned from the prior verified
official capture; changed headers fail closed as schema drift.

The explicit operator approval in `data/terms-reviews/be.locations.json`
authorizes restricted private processing under the stated conditions only. The
FASFC operator feed is broader than animal facilities. Any future public map
requires separate category coverage, factual, privacy/safety, attribution,
latest-update, and release review. No live acquisition, candidate import, or
successful tests make this source public-release-ready.

The fixtures in this package are synthetic test data and do not contribute to
live counts.
