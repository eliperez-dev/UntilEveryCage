# Product readiness and V2 roadmap

**Canonical authority:** this document is the sole product-level readiness and overall V2 roadmap authority.

**Owner:** project maintainer. **Updated:** 2026-11-09, Pacific.
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
| Application | `128b6ae002e76cf95bd2ed0a4447d91ab67e835e` on `eli/v2` |
| CI | All seven jobs passed in [run 42678002156](https://github.com/eliperez-dev/UntilEveryCage/actions/runs/42678002156) |
| Render | Deployment `dep-dbp1q00n74is73abql10`, serving database `uec_serving_country_20261031`; Auto-Deploy remains off |
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
- The November 9 integration adds the reviewed compact mobile search sheet,
  staged filters and scope controls. Initial unfiltered lists reuse verified
  facet totals; live eligibility still applies before pagination. Lower-cost
  HTTP compression prevents large map responses from delaying record requests.
  Identity, suppression, pagination, current/history/V0 and decoded gzip/Brotli
  parity checks passed. Six public API checks passed: the first 100-record
  response took 0.68 seconds, then 0.62 seconds, versus 12.4/10.8 seconds before,
  with the full response unchanged. Counts and October 18 remain unchanged;
  V0 still returns 410. Production warmed facets before traffic in 12.5 seconds.
  A fresh public mobile-sized browser showed usable rows in 2.86 seconds;
  its initial list/map transfers took 0.51/0.62 seconds. Selection, scope clearing,
  sheet positions and map geometry passed without JavaScript exceptions.
  A retired-V0 availability probe returned 404; one other resource error remained unattributed.
- Global native-category lists now reuse exact counts from the existing facet
  cache. Overlapping categories count each facility once; page selection still
  checks current eligibility. All 24 old/new local response comparisons passed,
  including pagination, combined-filter fallbacks, history and restricted local
  V0. The 157 Rust unit tests, 12 suppression/cache E2E tests and final CI passed.
  Nine public checks passed. Slaughter, Processing and their OR combination took
  1.27, 1.20 and 1.07 seconds, versus 3.0, 12.7 and 15.3 seconds just before
  deployment, with complete responses unchanged. Unfiltered lists took 0.67
  seconds; October 18 remains accessible and V0 returns 410. Production prepared
  facets before listening in 19.6 seconds. No frontend or database changes were made.
  A fresh public mobile-sized browser showed each category selection in 2.1–2.2
  seconds, with API transfers of 0.75–1.11 seconds. Pagination reached 200 unique
  rows without changing totals, canvas or geometry. No JavaScript exceptions or
  overflow occurred; the known retired-V0 availability request returned 404.

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

- Combined-filter lists and filtered facet queries retain the exact-count path.
  The global-category repair does not accelerate arbitrary combinations of
  country, source, text, precision and spatial filters. The earlier wide-radius
  category sample took 7.2 seconds; optimize further only against a measured case.
- A graceful service restart was observed November 3 at 12:08 PM Pacific.
  Its trigger remains unknown; no matching deploy or OOM event was found.
- Generalize the exact canonical graph-alias rebinding used for reused private
  handoffs in this release. Original identifiers and evidence must remain intact.
- Apply the human-readable French ICPE source label in the next source projection.
- Remove the automatic retired-V0 archive-availability request on map entry.

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
