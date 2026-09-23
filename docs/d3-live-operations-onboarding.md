# D3 live-operations onboarding checklist

This checklist is for source-owned registration and private refreshes. It does
not authorize publication, promotion, a scheduler, or unattended acquisition.

## Before registering a source

- [ ] Confirm the authoritative `source_registry.json` entry, source ID, scope,
      source URL, expected artifact schema, cadence, and blockers.
- [ ] Record the permitted access mode: public download, bounded fetch, or
      operator-assisted/manual capture. Do not infer permission from a URL.
- [ ] Record source terms, attribution, rate limits, retention, and privacy
      review state. A terms note is not project approval.
- [ ] Supply a synthetic fixture and, where permitted, a preserved private
      artifact path. Record retrieval timestamp, byte size, and SHA-256 in the
      private run metadata; reports expose only aggregate metadata.
- [ ] Implement a deterministic, rerunnable adapter hook that returns an
      aggregate summary only. Raw rows remain in private staging.

## Before a live or assisted run

- [ ] Use the existing source command and its documented authorization path;
      do not add browser automation, hidden endpoints, credentials, or rate
      limit workarounds.
- [ ] Set an explicit retry bound and capture each attempt outcome and the
      final failure reason without copying raw payloads or private paths.
- [ ] Confirm the previous valid state is discoverable and remains available
      when acquisition, parsing, schema validation, or privacy checks fail.
- [ ] Confirm manual fallback instructions and the next operator action.
- [ ] Keep candidate import explicit and limited to a loopback disposable DB.

## Before integration or release review

- [ ] Run the D3 mixed rehearsal: the nine D2 facility lanes plus
      `us.fsis`, `us.aphis`, and `us.inspections`.
- [ ] Treat unsupported or failed lanes as a nonzero operator result; do not
      silently remove them from `--all-eligible` output.
- [ ] Verify review-required defaults, zero public API/map/CSV/cache/history
      exposure, no release creation, and no promotion.
- [ ] Have an authorized maintainer review terms, privacy, factual evidence,
      coverage, and publication eligibility separately.

The D3 rehearsal deliberately reports `live_access.performed=false` until a
source-owned registration and terms authorization are integrated. Fixture
passes demonstrate runner and adapter contracts only; they do not establish
live coverage or publication readiness.
