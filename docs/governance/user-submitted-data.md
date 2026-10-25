# Community contribution contract

**Owner:** project maintainer. Intake is implemented; accounts and automatic
publication are not. [ETHICS.md](../ETHICS.md) governs screening, removal and
publication. [Frontend instructions](../frontend/README.md) own visible UX;
[production operations](../deployment/production-operations.md) own roles,
secrets, caps and retention; [API contract](../api/v2-contract.md) owns routes.

## Implemented scope

| Type | Purpose |
| --- | --- |
| Facility | A new facility/location tip |
| Evidence | A source or explanation supporting an existing record |
| Correction | A proposed change to a target record |
| Duplicate | A proposed relationship between two records, not an automatic merge |
| Privacy/removal | A private request concerning a record or location |

Bug reports use the same restricted intake infrastructure as a separate kind;
they are not facility claims and must be saved, not composed as email drafts.
No uploads, accounts, automated email, password recovery or arbitrary source-URL
fetching are part of this implementation.

Contributors receive a Track submission link. Its secret capability belongs in
the fragment; the client sends credentials in a POST body for status lookup.
Status returns processing state and an eligible link, not raw intake, contact,
operator notes or another person's submission. Do not log tokens or include
them in URL queries. Optional email is separately stored private contact, not
a subscription or authentication.

## Data and access boundaries

Production serving reads and community intake use separately restricted
connections. The public serving role must not read intake/contact tables.
Operator review requires its distinct token, never a contributor capability.
Use the production runbook for exact configuration and grants.

Submissions do not create curated facilities, release membership, map pins,
graph edges or source records. An operator `link_community` action can link
a screened submission only to an already eligible community source record
and named release. It does not publish intake text or coordinates.

Community browsing requires an eligible published community release and
explicit community context. Keep unreviewed community claims, warnings and
counts separate from the curated project dataset. Preserve original source
origin when evidence is reviewed or promoted.

## Operations and acceptance

- Use bounded fields, escaped text, URL validation, rate/admission caps and
  separate contact storage. No hidden uploads or automatic URL fetching.
- Prioritize privacy/removal; suppress affected public records through the
  [suppression runbook](suppression-runbook.md). Removing intake and suppressing
  its target are different actions.
- Apply configured payload/contact/capability expiry. Authenticated
  `POST /api/private/community/maintenance` needs a verified periodic caller
  for idle cleanup; intake-triggered cleanup alone is not a schedule.
- Retain payload-free decision events. Restricted information must not return
  through restore, historical releases, caches, graph or exports.
- At cutover verify operator access, queue ownership/caps, retention maintenance
  and removal/recovery. Implemented forms alone do not establish staffed operation.
- Test all five kinds, bug persistence, target links, status isolation/revocation,
  malformed inputs, admission limits and no automatic curated-data mutation.

Accounts, contributor history, email delivery and screened community publication
may be considered later through [the sole roadmap](../PRODUCT-READINESS.md).
Do not reintroduce an accounts-provider proposal or a separate feature roadmap.
