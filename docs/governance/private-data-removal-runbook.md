# Private-data suppression and removal runbook

This runbook is an operational checklist, not legal advice. Use a private reporting route; never put addresses, coordinates, contact details, or attachments in a public issue.

## Intake

1. Assign a case ID and record only the minimum evidence needed to locate the record.
2. Acknowledge receipt privately. Record the responsible maintainer and due date.
3. For a credible exposure concern, create an active suppression immediately. Do not wait for upstream correction.
4. Record a payload-free audit event: case ID, scope, reason category, policy version, actor, decision, and time.

## Triage and decision

Classify the request as residential/private or mixed-use location, wrong property/coordinate, whole-record withdrawal, legal demand, or other. Separate public suppression from retention, redaction, or deletion of private evidence. Escalate uncertain legal or jurisdictional questions to qualified advice; do not improvise.

An authorized maintainer reviews the proposed scope. A second reviewer is used where practical. If no authorized reviewer is available, keep the suppression active and pause new publication that requires approval; existing eligible releases may continue.

## Propagation verification

Verify the case against list/detail APIs, maps, search, downloads, embeds, previews, caches, historical releases, reimports, release reconstruction, and backups/restores. Record each check and any incomplete surface. Never put the sensitive payload into logs or test output. Notify known downstream recipients where appropriate; third-party copies cannot be reliably recalled.

## Reconsideration and closure

Only an explicit reviewed lift may remove a suppression. New evidence creates a new event; it does not mutate evidence history. If removal or retention is authorized, preserve only the minimum payload-free audit record needed to explain the action and verify dependent references. Re-run propagation checks after any lift or corrected version.
