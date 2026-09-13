# Ethics policy implementation checklist

Governing policy: [ETHICS.md](../ETHICS.md), version 1.0, not yet publicly published; see the [summary](../ETHICS-SUMMARY.md) and [changelog](ethics-changelog.md). This is an implementation backlog, not a completed runbook or a claim of operational protection. All tasks below remain open until supported by reviewable evidence. Assign a maintainer, target date, and implementation/test reference when taking up a task.

## 1. Removal and correction runbook

- [ ] Write a private-data-safe runbook covering the policy's reporting mailbox, case IDs, minimum necessary evidence, acknowledgement, triage, and responsible maintainer/backup.
- [ ] Define urgent temporary suppression for credible exposure concerns without waiting for upstream correction; specify how unresolved cases receive follow-up and reconsideration.
- [ ] Define residential/private and mixed-use location review, wrong-property corrections, address-plus-coordinate suppression, whole-record withdrawal, and safe coarse-location alternatives.
- [ ] Separate public suppression from private retention/redaction/deletion decisions; identify approval authority and a second reviewer where practical.
- [ ] Specify propagation and verification across pages, maps, APIs, search, downloads, embeds, previews, caches, and historical release artifacts; track any incomplete work and notify known recipients where appropriate.
- [ ] Define requester communications and minimal audit events without private payloads; document limitations on recalling third-party copies.

**Done when:** A maintainer other than the author can follow a tabletop case from intake to verified resolution, including an urgent case and a contested case, without improvising retention policy.

## 2. Access, retention, and exceptional removal

- [ ] Implement distinct public-eligible, restricted-review, and non-retained states; separate scope classification from privacy eligibility.
- [ ] Inventory raw artifacts, staging outputs, database tables, geocoder responses, logs, submissions, fixtures, backups, and public releases that can contain protected details.
- [ ] Set justified retention/review periods and access owners for private evidence and requester contact data; minimize collection and public diagnostic output.
- [ ] Design and implement a narrowly authorized removal path compatible with append-only protections. Include dependent references, safe audit events, and evidence of authorization; do not globally disable triggers.
- [ ] Implement persistent suppression references sufficient to prevent re-exposure without retaining unnecessary sensitive payloads; only explicit review may lift a restriction.
- [ ] Define backup expiry/removal and restore handling, with restrictions applied before restored data can be served.

**Done when:** Authorized removal is possible and auditable while routine imports cannot mutate history or bypass publication restrictions.

## 3. Release checks and regression tests

- [ ] Make privacy eligibility a release gate for every public surface, including optional profiles and direct record lookups.
- [ ] Verify restricted data cannot leak through source fields, links, geocoder queries, attachments, old releases, or exports even when address columns are hidden.
- [ ] Verify source origin, review status, observation/retrieval dates, legacy labels, and uncertainty remain accurate in pages and exports.
- [ ] Test that failed imports leave only a still-eligible prior release available; old release membership must not override a newer restriction.
- [ ] Add a synthetic end-to-end removal scenario: publish an eligible fixture, raise a credible residential/wrong-location concern, suppress address and coordinates, complete retention/removal review, and verify every controlled output.
- [ ] Continue that scenario through the same source reimport, a new source snapshot, renewed geocoding, release reconstruction, and backup restore. None may re-expose removed details.
- [ ] Confirm audit events and test outputs do not copy the sensitive fixture payload unnecessarily; use no real resident or requester data.

**Done when:** Automated checks and a recorded manual propagation exercise demonstrate the whole scenario, including cache behavior and restore handling. Database trigger existence alone is not proof.

## 4. Public policy and contributor readiness

- [ ] Publish an accessible ethics/privacy/correction page with policy version, review date, reporting route, process commitments, and honest implementation limitations before v2 publication.
- [ ] Link reporting from facility pages and exports; direct sensitive reports away from public issue trackers.
- [ ] Establish a policy-change review owner, conflict-of-interest handling, and periodic review of unresolved cases and retention schedules.
- [ ] Obtain qualified review for jurisdiction-specific obligations and public legal terms; do not describe this policy as immunity for maintainers or contributors.
- [ ] Add release documentation identifying which checks were satisfied, known gaps, and which public capabilities remain restricted because of those gaps.

**Done when:** Contributors know where to escalate, visitors can request corrections privately, and public statements match demonstrated behavior.

## 5. Visitor privacy audit and controls

- [ ] Inventory browser network requests and deployed application, hosting/CDN, proxy, error reporting, map tile, geocoding, asset, and analytics services. Record actual data sent, identifiers, log fields, retention, access, and configuration control.
- [ ] Remove advertising/cross-site tracking and unnecessary identifiers or query payloads; justify any audience measurement and keep it aggregate without visitor profiles or precise locations.
- [ ] Set and verify explicit short retention periods for necessary operational/security logs; document provider limits and deletion behavior rather than asserting zero logging.
- [ ] Test that location entry is optional, device geolocation is not required, and precise visitor locations or home addresses do not enter shared links or analytics.
- [ ] Explain relevant third-party disclosures at location search and in the public privacy page; keep statements tied to audited deployment settings.

**Done when:** A reviewed inventory and browser/infrastructure checks support every published visitor-privacy statement, with known limits visible.

## 6. Availability, publication authority, and legal demands

- [ ] Record the responsible maintainer and approval authority; appoint a backup only with their agreement and verified access. Document what happens if no backup exists.
- [ ] Implement and test least-privilege deployment/release controls and pause new human-reviewed publication when no reviewer is available, without disabling authorized urgent suppression.
- [ ] Write a handover procedure for pending privacy cases, deadlines, eligible existing releases, compliant acquisition, and restricting a feature when exposure cannot be isolated.
- [ ] Write a legal-demand runbook covering private receipt, deadlines, authenticity/scope assessment, qualified advice, preservation, authorized minimal disclosure, and permitted notification/transparency.
- [ ] Identify a realistic route to qualified advice without claiming an unconfirmed legal relationship; ensure ordinary correction requests through counsel can still be handled promptly.
- [ ] Tabletop an absence scenario and a legal demand arriving during a removal request; verify deadline tracking and separation of public suppression from retention decisions.

**Done when:** Authority and escalation are explicit, technical controls support the pause rule, and a recorded exercise exposes no reliance on an imaginary reviewer or standing counsel.

## 7. Security reporting and release integrity

- [ ] Publish a monitored `/.well-known/security.txt` with contact and expiry information following [RFC 9116](https://www.rfc-editor.org/rfc/rfc9116.html); document triage, renewal ownership, and actual monitoring capacity. It advertises a reporting route, not a security guarantee.
- [ ] Publish output checksums and versioned release manifests, with consumer verification instructions and clear source/process lineage.
- [ ] Once the release process is stable, evaluate and implement release signing with trusted key distribution, key custody, rotation/revocation, and compromised-release handling.
- [ ] Explain that checksums detect alteration relative to a trusted reference and signatures support authenticity; neither proves factual accuracy. Keep withdrawn/sanitized release handling consistent with privacy policy.

**Done when:** Consumers can verify a release against documented references; any signing claim is backed by tested verification and key-management procedures.

## 8. Explicit public access to unreviewed community claims

The V2 API now implements the screened-but-unreviewed contract for synthetic
claims, including profile separation, persistent list/detail warnings, and
default exclusion. The items below remain open where they require frontend,
export, aggregate-count, historical/cache, or production operational controls.

- [ ] Model factual review separately from privacy/abuse screening and publication eligibility. Raw unscreened and rejected submissions remain non-public.
- [ ] Add explicit unreviewed-community profiles/query parameters; verify ordinary map, search, API, and export defaults exclude those claims.
- [ ] Show persistent prominent warnings before access, on each record, and on direct links; keep community counts separate from default curated project totals.
- [ ] Preserve source origin and factual review status in every API object and exported row, with download profile context and the same restrictions for historical views/previews.
- [ ] Test that opting in cannot expose restricted material and that later suppression revokes access across all public surfaces, including caches and reimports.

**Done when:** A screened but factually unreviewed synthetic claim is available only through unmistakable community context, without contaminating default curated project results, while an unscreened/restricted claim is never exposed.

## 9. Source, review, approval, and publication terminology

- [ ] Replace ambiguous “official” badges/enums with independent source origin, factual review events (community/project actor, scope, outcome, date), privacy eligibility, project approval, and publication/profile fields.
- [ ] Preserve original values and history when migrating any older mixed-tier representation. Government documents cited by a community claim remain separately attributable evidence.
- [ ] Require authorized project approval for default curated release membership; community review alone is insufficient. Opt-in publication of eligible unreviewed claims must not imply factual approval.
- [ ] Show these distinctions on direct links, list/map context, API objects, exported rows, and download manifests; avoid generic “verified” badges.
- [ ] Test government-sourced but unapproved, community-reviewed but inconclusive/unapproved, eligible unreviewed and project-published, and community-origin project-approved records. Confirm publication is separate from approval and reviewed does not mean accepted.
- [ ] Test later review/approval transitions without silently changing origin, carrying approval to a changed version, bypassing privacy restrictions, or double-counting records.

**Done when:** Each combination is represented and labeled accurately across public interfaces and exports, with no single “official” flag substituting for independent decisions.

## Current implementation boundary

The documentation is aligned with ETHICS.md. The current database migration rejects updates/deletes on evidence tables; a policy-compliant exceptional-removal path and end-to-end publication enforcement have not been established by this documentation task. Do not treat unchecked work as complete or launch affected public capabilities based on policy text alone. Independent acquisition work may continue within the governing retention/access rules.
