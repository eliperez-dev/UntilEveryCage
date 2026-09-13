# Community submissions, review, and publication

Governed by [ETHICS.md](../ETHICS.md), especially section 5's terminology and sections 2, 6, 8, and 9's retention, privacy, and removal requirements. See the [implementation checklist](policy-implementation-todo.md). This is a design contract; it does not claim the community workflow is implemented.

## Separate properties, not a single credibility tier

- **Source origin:** government-sourced, secondary-source, or community-submitted. Cite underlying evidence separately: a user attaching a government document does not silently turn their entire claim into a government statement.
- **Factual review:** record community review and project review as distinct events with actor role, date, evidence, scope, and outcome. Community-unreviewed means no completed factual review; community-reviewed does not necessarily mean corroborated or accepted.
- **Privacy/moderation eligibility:** unscreened, restricted, public-eligible, or removed, independent of factual review. Screening for exposure and abuse is not fact checking.
- **Project approval:** an authorized maintainer's documented decision for a specific record/version and curated release/profile. Community review alone does not grant this approval.
- **Publication:** whether and where the project has made the record available, with release/profile identifiers. Project-published is not synonymous with project-approved.

Avoid the bare label “official” and the previous mixed enum of `official`, `project_reviewed`, `user_unreviewed`, and `rejected`. Those mix origin and decisions. Any implementation migration must preserve old values and provenance while mapping them to the separate properties; do not silently relabel existing records.

## Lifecycle and profiles

A submission enters restricted intake, receives privacy/abuse screening, and may then be made explicitly queryable in the community profile while factually unreviewed. Subsequent community or project factual reviews append their outcomes. Admission to the default curated project dataset requires a separate project approval decision and public eligibility. A rejected or restricted claim is not public merely because someone selects a broader profile.

The default dataset initially focuses on government-sourced records, but can include secondary or community evidence that meets the documented approval requirements. Approval never changes source origin. A reviewed community claim can remain disputed and unapproved; a government-sourced record can remain unapproved or unpublished. Preserve these distinctions on records and in counts.

## Public query contract

- Ordinary map, search, API, and export defaults use the curated project dataset. Opt-in community exploration requires an explicit page/profile selection or query parameter.
- Prominently label **“Community-unreviewed — not factually verified or project-approved by Until Every Cage.”** Community-reviewed claims instead show the reviewer role, review outcome, and separate project approval status. Do not use a generic “verified” badge.
- Display context before access, persist it on results/maps, and repeat it on every record and direct-link page. Do not rely on color or tooltips.
- Keep opt-in community counts separate from the curated dataset. If a claim later gains project approval, use explicit membership and identity decisions to avoid double-counting.
- Every API object and exported row carries source origin, review status/role/outcome, project approval, and release/profile context. Explain that public availability is not factual endorsement.
- Privacy restrictions override all profile selections, including historical views, previews, exports, and caches. Reimports must not revive withdrawn locations.

## Retention and people

Collect only the evidence needed to assess the claim; keep optional submitter contact separate and restricted. Set justified retention/review periods. Unscreened and harmful payloads are not public. Follow ETHICS.md for residential/private addresses, incorrect coordinates, minimization, controlled removal, and safe audit records.

Requests go through the private route in ETHICS.md section 9 without requiring government correction first. No factual-review status or project approval exempts a record from suppression or removal.

## Implementation order

1. Stabilize source acquisition, history, validation, and curated releases.
2. Model source claims and separate review, moderation, approval, and publication events.
3. Add constrained intake and privacy screening with restricted storage.
4. Add explicitly labeled public querying of eligible unreviewed claims.
5. Add community and project review workflows with scoped outcomes and dispute handling.
6. Add admission to curated releases only through explicit project approval and identity reconciliation.

Test the combinations in ETHICS.md section 5 and the implementation checklist before exposing community data. Existing acquisition work remains the first priority.
