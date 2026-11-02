# Product readiness and V2 roadmap

**Canonical authority:** this document is the sole product-level readiness and overall V2 roadmap authority.

**Owner:** project maintainer. **Updated:** 2026-11-01, Pacific.
Source readiness belongs in [source-status.json](source-status.json), frontend
behavior in [the frontend guide](frontend/README.md), and data policy in
[ETHICS.md](ETHICS.md). Update these owners rather than adding sprint reports.

V2 is the product. Its `2.0.0` version comes from the Rust crate. Datasets use
release dates. The original website has not been replaced and its domain has
not been changed.

## Live deployment

The integrated application is live at <https://untileverycage.onrender.com/>.
The current dataset is **October 31, 2026**, `release-2026-10-31`.

| Area | Verified state |
| --- | --- |
| Dataset | 149,091 records; 116,840 mapped and 32,251 unmapped; 22 facility sources across 33 countries, with points in 32 |
| Graph | 83,067 connections: 23,874 exact and 59,193 inferred; 1,024 APHIS evidence references |
| Historical dataset | October 18 remains accessible, including all 69,526 original graph edges |
| V0 | Retired from production at the maintainer's request; seven old projection copies removed, reclaiming 521,412,608 bytes. The local development baseline and source evidence remain |
| Application | `52d0e4742b820e497cc11eb87f99e42b65836244` on `eli/v2`; reviewed frontend checkpoint `075e6026` is included |
| CI | All seven jobs passed in [run 41261561005](https://github.com/eliperez-dev/UntilEveryCage/actions/runs/41261561005) |
| Render | Deployment `dep-dbk22jijnfac739c80mg`, serving database `uec_serving_country_20261031`; Auto-Deploy remains off |
| Contributions | Existing intake and bug-report capabilities remain enabled; community data was not moved or modified |

The country first pass is complete. Germany, national Spain, Catalonia, France,
Mexico, the UK, New Zealand, EEA livestock, Norway aquaculture and Poland GIW
are included. Unresolved geocoding attempts remain recorded for a later pass.
Do not restart failure retries or source expansion as part of this closeout.
Detailed source coverage, precision and remaining source work belong in the
source inventory. Source rows are not a globally deduplicated premises census.

## Acceptance

- 129 local real-data API checks and 132 production-mode checks against the
  isolated Render copy passed. They cover source lists/search/detail, complete
  map membership, country facets, graph samples and retained history.
- Four real APHIS cases returned pre-2025 links: 21 annual-report links and
  38 inspection links in the samples. This is sample coverage, not an archive audit.
- 22 read-only requests passed at the public Render origin. Post-cleanup
  checks confirmed readiness, the new default release, October 18 and contribution
  capabilities. V0 now returns 404/410.
- Runtime TLS, read-only serving-role permissions, constraints and restriction
  replay passed. Source payloads, private graph evidence and credentials are
  excluded from the public serving package.

The aggregate completion receipt is retained locally in ignored
`data/staging/country-release-20261031/acceptance.json`. Its component receipts
record the exact checks, package digest and V0 cleanup. Earlier prepared
October 27 snapshots were never published and are not the current release.

## Remaining before replacing the original website

1. Complete the maintainer's final frontend pass using the live Render build.
   The frontend lane owns wording, layout and interaction changes; the backend
   lane owns data and API changes. Preserve the reviewed UI without redesigns.
2. Finish the operating handoff for monitoring, recovery, contribution review
   and retention using [production operations](deployment/production-operations.md).
3. Perform the separately agreed domain, canonical URL and redirect cutover.

## Measured backend follow-ups

- Full filter counts remain slow: about 14 seconds warm and 27 seconds cold
  in the isolated cloud check; 13.8 seconds at the public origin. Cache or
  precompute these counts with release and restriction-generation invalidation.
- Generalize the exact canonical graph-alias rebinding used for reused private
  handoffs in this release. Original identifiers and evidence must remain intact.
- Apply the human-readable French ICPE source label in the next source projection.

These are tracked follow-ups, not reasons to repeat the completed country
geocoding pass or begin another broad backend redesign.

## After launch

Keep future country/source additions, accessible pin artwork, coverage layers,
graph visualization, record timelines, historical imagery and community accounts
separate from the launch closeout. Category colours require maintainer agreement.
Further translations use the existing language system. The current reviewed
interface has seven locales; some secondary operator and generated API text is
still English. Publication of community data is separate from contribution intake.

### D6.2 — Backend architecture closure and contract freeze

D6.2 integration froze major backend redesign while allowing source additions
and measured maintenance. The historical 5,000 probabilistic-candidate analysis
was not a storage cap. Human adjudication is not a graph connection state or a prerequisite
for exact/inferred edge persistence. These retained contract invariants do not
override the current launch checklist.
