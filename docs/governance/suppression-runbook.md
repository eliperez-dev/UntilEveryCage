# Suppression and re-exposure runbook

This is the operator procedure for a credible residential, private-location,
wrong-property, or harmful-identifying-information concern. Until Every Cage
currently has one authorized publication operator. Do not imply that a backup
reviewer, legal guarantee, or emergency-response service exists.

## Urgent intake

Use `untileverycageproject@protonmail.com` and ask the requester to provide the
public record ID/link, concern, requested action, and optional supporting
evidence. Ask for the least intrusive verification needed; do not request an
identity document or another private address. Keep the case ID and requester
details in restricted operator storage, not in a public issue.

1. Assign a case ID and log only the reason category, affected opaque record
   reference, decision, operator, timestamps, and affected systems. Never copy
   an address, coordinates, private text, requester identity, or raw payload
   into a suppression event or test output.
2. Urgently suppress the source record. The command below creates an active,
   append-only case plus a source ID/record-key reference and a legacy access
   revocation event. It does not mutate retained evidence:

   ```powershell
   python pipeline/scripts/stages/restrict-record.py <source-record-uuid> `
     --reason privacy --scope whole_record --policy-version ethics-v1 `
     --maintainer <operator-id> --database-url <disposable-or-authorized-db>
   ```

   `whole_record` is the safe default for an unresolved residential or
   wrong-location concern. Address/coordinate scopes are retained for the
   case reference, but current public projections fail closed for the whole
   source record because the current V2 API has no public field-level address
   projection.
3. Verify list/detail API, map and facet queries, CSV exports, promoted and
   historical release projections, candidate previews, and any known embeds or
   caches. Record aggregate pass/fail results and opaque IDs only.

## Review, retention, and lift

Assess relevance, source evidence, residential/private overlap, accuracy, and
whether restricted evidence is still necessary to retain. A source being
government-published does not defeat the concern. Preserve non-sensitive
history; consider redaction or deletion of protected evidence separately and
assess preservation obligations before exceptional removal.

If the concern remains unresolved, keep the case active or in review and set a
next review date. Closure or expiry does not restore access. Only an explicit,
documented review decision may lift a restriction:

```powershell
python pipeline/scripts/stages/lift-suppression.py <case-uuid> `
  --policy-version ethics-v1 --maintainer <operator-id> `
  --database-url <disposable-or-authorized-db>
```

This appends a `lifted` case event and an explicit restoration event; it never
updates or deletes the original case, reference, source record, geocode result,
release member, or artifact. Reconsideration should use new evidence and a
second reviewer where one is actually available; do not invent one.

## Propagation checklist

The durable reference is keyed by `source_id` + `source_record_key`, so the
restriction follows same-source reimports and new snapshots. Before any
release is served, verify:

- `/api/v2/locations`, detail, facets, CSV, and the loopback-only candidate
  preview omit the restricted record;
- `map_facilities_public`, `map_facilities_display`, and
  `map_facilities_display_history` return no restricted row;
- renewed geocoding is not queued or performed for a restricted source record,
  and any already-retained geocode evidence remains private;
- validation and promotion reject a reconstructed release containing the
  restricted record;
- the current restriction ledger digest is replayed into a restored database
  before service start. An old backup must fail the pre-service gate;
- known distributed artifacts, previews, and caches are withdrawn or rebuilt.

There is no V2 persistent application cache or raw-artifact preview endpoint in
this checkpoint. V2 responses are generated from the suppression-aware SQL
projections. The legacy embedded `/api/locations` route has no reviewed V1/V2
identity crosswalk and is not a route for the maintained V2 release; no
crosswalk must be added without a suppression propagation design and test.
Independent third-party copies cannot be recalled by the project; disclose
that limitation and take feasible correction steps.

## Evidence of completion

Run the synthetic lifecycle test and the backup/restore drill with
`UEC_RUN_E2E=1`. Attach only aggregate results, commit ID, policy version, and
opaque case/record references to the operator log. If any controlled surface
fails, keep the affected publication capability stopped or restricted and
escalate to the responsible maintainer.
