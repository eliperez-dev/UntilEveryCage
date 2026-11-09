# Product readiness and V2 roadmap

**Canonical authority:** this document is the sole product-level readiness and overall V2 roadmap authority.

**Owner:** project maintainer. **Updated:** 2026-11-03, Pacific.
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
| Application | `a71a5d1cf748aa3a35877e7b5570b0494aaacd01` on `eli/v2` |
| CI | All seven jobs passed in [run 41720735466](https://github.com/eliperez-dev/UntilEveryCage/actions/runs/41720735466) |
| Render | Deployment `dep-dbl5afei0phs738hl4k0`, serving database `uec_serving_country_20261031`; Auto-Deploy remains off |
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
- The November 2 API repair preserves exact radius memberships and facet bodies.
  Nine live checks passed: overlapping radius matches and records returned in
  0.65/0.69 seconds; unfiltered facets in 0.35 seconds, versus 10–13 seconds
  before the repair. The bounded facet cache checks current release, content and
  restriction identity. Local suppression/cache tests and the frozen V0 baseline
  passed. No database cutover or source changes were needed.
- A live mobile WebKit location/filter flow also passed without server errors;
  100 results loaded and the landing-page checkpoint was confirmed. A wider,
  category-filtered radius query still took 7.2 seconds in that flow.
- Landing country totals now come from the same cached aggregate as the other
  totals. A fresh live mobile WebKit load completed all four totals in 1.4 seconds,
  versus 15.9 seconds before, using one facet request and no precision partitions.
  Current and historical aggregate comparisons, suppression tests and the public
  API contract checks passed; existing counts are unchanged.
  Sources and method notes are now shorter in all seven locales, with rates,
  dates and source links retained; focused browser checks and live inspection passed.
- Landing totals now use one authoritative facet response; offscreen story
  canvases defer setup until visible. Local contract/suppression tests, current
  and historical aggregate equality, and six final live API checks passed. A controlled
  mobile-sized test with 6x CPU slowdown and 500 ms API latency completed totals
  in 2.4 seconds; this is not a physical-phone measurement. Production now builds
  the current facet cache before accepting traffic: Render warmed it in 12.2 seconds,
  then the first checked public facet request took 0.36 seconds. A fresh local
  production process returned its first HTTP facets in 0.25 seconds; unavailable
  data stopped startup before bind. Live totals and deferred canvases were verified.
- The November 3 native-category repair shares candidate filtering, exact counts
  and bounded page enrichment. Current, historical and local V0 API comparisons
  preserved memberships and DTOs; latest-assignment, pagination and suppression
  cases passed. Nine live API checks passed: concurrent map/list requests for the
  reported 3,318-record area took 3.3–3.6 seconds, versus the earlier 31-second
  failed map request and 44-second list. Global Slaughter matches/list took
  4.0/2.7 seconds with the same 11,255 records and 7,832 mapped IDs. Temporary
  search failures retain the map and Retry; failed release validation removes it.
  The unchanged validation test and Chromium/WebKit recovery cases passed.
  One live mobile-sized WebKit flow completed a 50-mile LA radius search in
  1.1 seconds: seven rows, unchanged canvas/camera and no page errors. Its
  headless screenshot did not verify tiles or pins. A normal browser separately
  rendered street tiles and red pins without captured warnings or errors.

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

- Initial unfiltered record browsing took 10.2 seconds in the live mobile flow;
  filtered facet queries and broad concurrent category queries also need work.
  Global Processing returned 52,941
  matches in about 6.8 seconds locally; the reported area repair is not a claim
  that every global filter is fast.
- A graceful service restart was observed November 3 at 12:08 PM Pacific.
  Its trigger remains unknown; no matching deploy or OOM event was found.
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
