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

## Historical frozen-source terms references

The following 2026-10-05 source review is retained from the retired v0 packet.
It describes those sources/artifacts at that time, not new terms verification
or an instruction to reopen completed dataset approvals. Current recorded
artifact/release decisions remain authoritative.

### Source-rights verification (2026-10-05)

Current publisher pages were checked for the frozen sources below. This is
licence/reuse evidence, not an artifact-scoped rights decision or privacy
approval. Exact candidate artifact digests remain in the linked taxonomy
inventory; do not substitute a current upstream download for the frozen bytes.
Licence exceptions, source dates, attribution and no-endorsement conditions
must accompany any approved output. A missing original capture remains
`not_retained`, not retrospectively byte-verified.

| Frozen source | Primary reuse evidence and remaining conditions |
| --- | --- |
| Australia NPI | [Exact Facilities CSV resource](https://www.data.gov.au/data/dataset/npi/resource/f83cdee9-ebcb-4f24-941b-34bb2f0996cf?inner_span=True) identifies CC BY 4.0; preserve Commonwealth/NPI credit and stated exceptions. This is the CSV, not the separately licensed GeoJSON resource. |
| South Australia EPA | [Government resource metadata](https://data.gov.au/data/dataset/https-www-waterconnect-sa-gov-au-content-downloads-dewnr-topo-epa-activities-sag-shp-zip/resource/26e076f3-c37f-4089-8f28-3f7c9afd997e) records CC BY 3.0 Australia and approximate locations; publisher-side catalogue verification was unavailable in this check. |
| Belgium FASFC | [Open-data terms](https://www.foodweb.favv-afsca.be/professionelen/praktisch/opendata/) support reuse with source/latest-update credit and non-misleading presentation; account for both operator-list and activity-code evidence. |
| Brazil SIF | [MAPA resource](https://dados.agricultura.gov.br/pt_PT/dataset/servico-de-inspecao-federal-sif/resource/97277e92-264a-4dc0-9aea-f87b8ea93798) records CC Attribution; retain MAPA credit and assess excluded personal/third-party material separately. |
| Ontario meat plants | [Catalogue](https://data.ontario.ca/dataset/provincially-licensed-meat-plants) records OGL-ON-1.0; contact data and third-party material are not cleared merely by that label. |
| Denmark Find Smiley | [Download/use conditions](https://www.findsmiley.dk/om-smiley/statistik-og-data/hent-smileydata) require authority credit and prohibit logo use; displayed individual smiley status has currentness/design requirements. A dated facility snapshot is not a claim of current smiley status. |
| Catalonia feed/SANDACH | [Exact national-government catalogue entry](https://datos.gob.es/es/catalogo/a09002970-registro-de-establecimientos-del-sector-de-la-alimentacion-animal-y-del-ambito-de-los-sandach) identifies `m48e-zdz9` and links Generalitat reuse licensing. Preserve source/update-date context, no endorsement and stated exceptions; this evidence is not a recorded release rights decision. |
| France DGAL I and II | [Source lists](https://agriculture.gouv.fr/liste-des-etablissements-agrees-ce-conformement-au-reglement-ce-ndeg8532004-lists-ue-approved) and [legal notice](https://agriculture.gouv.fr/mentions-legales) require citation/integrity and distinguish non-commercial reuse from commercial/advertising reuse requiring prior request. Do not describe these snapshots as unrestricted commercial open data without an applicable basis. |
| UK FSA | [Catalogue](https://www.data.gov.uk/dataset/2c80e0ce-ee1c-4f26-ba6f-1e1ae1bd8ee9/approved-food-establishments) records OGL; preserve the frozen snapshot date, attribution and licence exceptions. |
| UK FSS | [Source portal](https://www.foodstandards.gov.scot/open-data-portal/approved-establishments-in-scotland) records OGL v3; retain Scotland-only scope, frozen edition and attribution. |
| Italy 1069 and 853 | [1069](https://www.dati.salute.gov.it/it/dataset/stabilimenti-italiani-i-sottoprodotti-di-origine-animale/) and [853](https://www.dati.salute.gov.it/it/dataset/stabilimenti-italiani-gli-alimenti-di-origine-animale/) record IODL v2.0 and identify some coordinates as OSM-derived without identifying individual rows. Preserve attribution and assess the applicable ODbL/derived-database duties; do not silently label all coordinates exclusively Ministry-origin or impose a blanket OSM ban. |
| Netherlands NVWA | [Copyright policy](https://www.nvwa.nl/service/copyright) establishes a CC0 default with item-specific exceptions and no implied endorsement; privacy/third-party rights remain separate. |
| US FSIS | [Directory](https://www.fsis.usda.gov/inspection/establishments/meat-poultry-and-egg-product-inspection-directory) offers the CSV; [USDA rights policy](https://www.usda.gov/about-usda/policies-and-links) permits copying/distributing public-domain material, requests USDA credit and identifies exceptions. This supports a conditional reuse basis, not a blanket assumption that every embedded item is unrestricted or a requirement for fresh permission solely because the CSV lacks a licence banner. |

Provider-derived geometry is separate evidence. [Geoapify terms](https://www.geoapify.com/terms-and-conditions/)
and [geocoding documentation](https://www.geoapify.com/geocoding-api/) support
storage/reuse subject to source attribution, OSM obligations and Geoapify credit
on the free plan. Preserve datasource provenance; provider permission does not
clear the original facility data, establish an operating-site address or resolve
privacy eligibility. Mixed-source outputs must retain their distinct terms;
this review does not establish one blanket licence for the combined dataset.
