# Source redistribution decisions

The release gates require a recorded redistribution decision for every
immutable source artifact that contributes a default-visible row to the
selected release. The decision key is the canonical `source_id`, release
`profile`, `release_id`, and the exact `raw_artifacts.artifact_id` plus its
immutable SHA-256 digest. A release that combines two source snapshots needs
two decisions even when both snapshots use the same source ID.

For an isolated frozen cohort, the explicit `--apply` path of
`pipeline/scripts/stages/record-release-cohort-review.py` records one operator-
authored rights decision for each covered source/artifact pair in the same
transaction as the release-scoped cohort review. Its default mode is
read-only. The local review document must name the decision actor, reference,
time, and redistribution status for every artifact; the command does not
infer clearance from source attribution, a review conversation, or successful
acquisition. Use the same release/profile/artifact scope used by downstream
rights validation.

`uec.source_rights_decisions` is append-only. Each entry records
`cleared`, `unknown`, or `restricted`, an attributable decision actor, a
decision reference, and the decision time. The actor value is an audit
reference; it does not establish that the actor was authorized. The trusted
operator and approval boundary must enforce that separately. Validation,
promotion, discovery, and package export evaluate recorded decisions; they do
not make them. The cohort recorder persists the operator's explicit status,
but does not grant legal authority or establish that the cited review took
place.

The shared gate evaluates all exact requirements. It uses the newest decision
time for each source/artifact/release scope. Multiple decisions at that time
are acceptable only when they agree; conflicting newest decisions are
ambiguous and block. Missing, `unknown`, `restricted`, profile-mismatched,
release-mismatched, and artifact-mismatched decisions block closed-world.
Attribution text remains source metadata and may describe an attribution
obligation, but it never substitutes for a redistribution decision.

Acquisition permission is a separate source or run decision. A permitted
acquisition does not imply redistribution permission, and a cleared
redistribution decision does not authorize a new acquisition. This sprint
checks the decision at validation, promotion, discovery read-model build, and
package export time. It does not implement ongoing revocation or expiry of
already-served releases; those remain launch blockers.

## License alignment review, 2026-10-05

This is a repository review, not clearance of every source or a deployment
certification. The existing license grants are retained.

| Material | Verified terms | Alignment and remaining work |
| --- | --- | --- |
| Project software | Root `LICENSE` contains AGPLv3; Rust and V1 source headers grant version 3 or later. The legacy root npm test package incorrectly declared ISC. | Cargo, root/frontend npm metadata and README now use `AGPL-3.0-or-later`. Keep a visible source link; deployed modified software needs the actual Corresponding Source, including build material, rather than merely an unrelated repository branch. |
| Project compilation rights | Root `DATA_LICENSE` contains CC BY-NC-SA 4.0. | Its introductory notice now distinguishes rights held by the project from upstream content and uses the current GitHub URL. The legal code is unchanged. Preserve upstream attribution and indicate changes; do not describe this compilation as unrestricted open data. |
| Upstream records and evidence | Source-specific terms, public-domain status and release/artifact decisions. | A project notice cannot relicense third-party content, create rights in facts or public-domain material, or clear redistribution. Keep the gates above; an export must carry its applicable source terms/credits. Mixed-license derivatives need an actual compatibility decision. |
| Frontend dependencies | Installed Swagger UI is Apache-2.0, MapLibre BSD-3-Clause, Zod/Svelte MIT, and axe-core Playwright MPL-2.0. All 349 frontend lockfile package entries declare license metadata. Swagger LICENSE, NOTICE and bundled notices are emitted by the Vite reference plugin. | Metadata is an inventory, not a complete compatibility or notice audit. Check final served bundle notices before release; do not label dependency code AGPL merely because project code is AGPL. Rust/transitive dependency and copied-asset clearance remains incomplete. |
| Maps and legacy assets | Existing map attribution is retained. V1 footer credits ADAPTT and Final Nail, and V2 reuses legacy marker/logo assets. | Credits/inspiration do not establish permission for copied assets. Review asset origin, applicable map/imagery service terms and attribution before publication. The new informational footer does not reintroduce the V1 kill counter. |
| Community contributions | Current intake consent permits review; no verified contributor license grant exists for publishing newly submitted narrative or attachments. | Keep intake private. Before publishing a screened derivative, agree clear contribution terms covering the contributor's own rights and source attribution; links alone do not grant rights to their contents. Optional contact email is private operational information, never a licensed data export. |

Code and data need not use the same license: they govern different material.
The important alignment is consistent scope, attribution and actual permission.
CC BY-NC-SA's noncommercial condition belongs to the project's licensed
compilation rights; it must not be portrayed as a restriction on all upstream
facts or as a condition on reuse of the AGPL software.

Primary references checked for this review:

- [GNU AGPL, section 13](https://www.gnu.org/licenses/agpl-3.0.html#section13)
  defines the network source-offer obligation.
- [CC BY-NC-SA 4.0 legal code](https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode.en)
  defines attribution, noncommercial use, ShareAlike and excluded rights.
- [Creative Commons licensing FAQ](https://creativecommons.org/faq/#what-things-should-i-think-about-before-i-apply-a-creative-commons-license)
  explains that licensors need the relevant rights; third-party/public-domain
  material is not automatically covered by their notice.
- [Open Source Definition](https://opensource.org/osd)
  distinguishes open-source software from terms that restrict fields of use.

Maintainer decisions remain: contributor publication terms, source/asset
clearances and final release notice completeness. No license change or
commercial-use permission was granted by this review.
