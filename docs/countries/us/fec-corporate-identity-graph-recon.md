# US FEC and corporate-identity graph reconnaissance

Status/date: private research design, observed 2026-09-18 UTC. This document
does not authorize acquisition, graph import, publication, or a claim that a
facility, organization, committee, candidate, donor, officer, parent, or
subsidiary is related to another entity. All proposed examples and tests are
synthetic/test-only. The governing policy is [`docs/ETHICS.md`](../../ETHICS.md).

## Executive finding

There is no single public, authoritative US corporate master that covers all
private companies, public issuers, nonprofits, political committees, and state
registrations. The safe design is a set of source-qualified evidence families:

| Source family | Strong identifier and useful evidence | Boundary that must remain explicit |
| --- | --- | --- |
| Federal Election Commission (FEC) | `committee_id`/`CMTE_ID`, `candidate_id`/`CAND_ID`, filing/image/file identifiers, candidate-to-committee linkage, Form 1 connected organization/sponsor fields, Schedule A/B/E transactions | FEC records describe filers and reported transactions. A committee name, contributor name, employer string, or donation does not establish a legal parent, facility operator, ownership, control, wrongdoing, or facility connection. |
| Securities and Exchange Commission (SEC) EDGAR | CIK, accession number, filing form/date, company submissions, former names/tickers, Form 10-K/20-F exhibits, Forms 3/4/5, Schedules 13D/13G | EDGAR is primarily a filer/disclosure system, not a complete private-company or ownership registry. Exhibit 21 subsidiary lists may be incomplete, unstructured, omitted, or not assigned a CIK. |
| Internal Revenue Service (IRS) TEOS/EO BMF | EIN, legal name, exempt status, Form 990 XML/index, Schedule R related-organization disclosures | Primarily tax-exempt organizations; not a general corporate registry. IRS status, name, and filing data do not prove current operations or a facility relationship. |
| SAM.gov | UEI, legal business name, physical address, registration status, CAGE/award context where public | Federal-award registration is scoped to participating entities. Records can be private/opted out, expire or change, and do not prove corporate ownership or facility operation. |
| State Secretary of State registries | State-scoped entity number, formation/qualification filings, status, registered agent, and sometimes annual-report officers/directors | Fragmented by state, access and terms vary, some records are paid/manual, registered-agent data is not ownership, and there is no national state-registry identifier. |

The existing graph foundation is compatible with this approach: keep each
native identifier source-qualified, store dated observations rather than
mutable edges, preserve contradictions, and keep factual review, privacy, and
publication states independent. Until a relationship is explicitly supported
by a source record and reviewed, it is a private candidate only.

## Official source reconnaissance

### FEC: committees, candidates, filings, and transactions

Primary references:

* [OpenFEC API documentation](https://api.open.fec.gov/developers/)
* [FEC browse/download data](https://www.fec.gov/data/browse-data/)
* [Candidate-committee linkage file description](https://www.fec.gov/campaign-finance-data/candidate-committee-linkage-file-description/)
* [Contributions by individuals file description](https://www.fec.gov/campaign-finance-data/contributions-individuals-file-description/)
* [FEC Form 1: Statement of Organization](https://www.fec.gov/resources/cms-content/documents/policy-guidance/fecfrm1.pdf)
* [FEC public-record research and use restrictions](https://www.fec.gov/introduction-campaign-finance/how-to-research-public-records/)

Useful API route families (the API documentation and `/swagger/` schema are
the authority for fields and changes):

| Route family | Stable keys / evidence | Suggested use |
| --- | --- | --- |
| `/v1/candidates/`, `/v1/candidates/search/` | `candidate_id` (`CAND_ID`), office, state, cycle, reported candidate data | Create a source-local candidate entity and link it only through the FEC's candidate/committee data. A candidate is a person, not a company. |
| `/v1/committees/`, `/v1/committees/{committee_id}/` | `committee_id` (`CMTE_ID`), committee type/designation, name, treasurer, address, connected organization/sponsor/affiliation fields where filed | Create a source-local committee organization. Preserve each Form 1 filing/version and distinguish connected organization, affiliated committee, sponsor, and treasurer roles. |
| `/v1/candidate/{candidate_id}/committees/` and linkage/bulk files | `CAND_ID` + `CMTE_ID` + election/designation/linkage ID | Emit an explicit FEC `authorized_by`/`candidate_committee` observation with its cycle and filing support. Do not infer a company relationship from the candidate's employer. |
| `/v1/committee/{committee_id}/filings/`, `/v1/filings/` | filing ID, report type, amendment indicator, receipt/coverage dates, image/file IDs | Keep filing versions append-only. Amendments and terminations are observations, not destructive updates. |
| `/v1/schedules/schedule_a/` | committee, contributor name/type, `other_id` when reported, date, amount, memo/transaction IDs, filing/image support | Model a reported financial transaction event. If `other_id` is a committee ID, it is a source-native committee reference; otherwise contributor text is not an organization identity. |
| `/v1/schedules/schedule_b/` and Schedule E/F families | committee, payee/recipient, `other_id` where available, date, amount, purpose/candidate references | Model disbursement or independent-expenditure events. Do not turn payee text into a parent, operator, or facility edge. |

The FEC says API data are updated nightly, each API call is limited to 100
results per page, and a normal key permits up to 1,000 calls per hour; the
documentation describes a possible 7,200-call/hour key by request. Use the
documented pagination fields and checkpoint every page. Treat those limits as
operational guidance that can change, not as a license to crawl.

FEC bulk data is preferable for historical or broad pulls. The browse-data
page exposes candidate master, candidate-committee linkage, committee master,
committee summary, Form 1/Form 2, daily filing, and transaction/database dump
families. The page states that update cadence varies by file (daily to weekly)
and that transaction-level files can be very large. Record the exact linked
file URL, release/period label, retrieval time, content type, byte size, hash,
header description, and adapter version. Never treat an FEC page's current
result as a timeless fact.

FEC matching hazards:

* `CMTE_ID` and `CAND_ID` are useful source identifiers; names are not.
  Committee names and connected-organization strings can change across Form 1
  amendments and may be abbreviated, sponsored, or affiliated rather than the
  legal parent.
* Candidate-to-committee linkage is a filed electoral relationship, not an
  ownership relationship. A candidate's employer field is a reported
  individual attribute, not proof that the employer funded a committee or
  operates a facility.
* Schedule A/B data contain amended reports, memo items, transfers,
  earmarking, refunds, and different entity types. Deduplicate only within a
  documented filing/transaction-version model; retain the original report and
  all amendments.
* For an individual contributor, employer and occupation are reported text.
  They are not a corporate identifier. A corporate-sounding contributor name
  can still be a person, trade name, intermediary, or data-entry variant.
* FEC public-record pages state that copied contributor information may not be
  sold or used for soliciting contributions or for commercial purposes. Raw
  contributor names, addresses, occupations, employers, and officer contact
  data must remain restricted pending policy and legal review; do not put them
  in logs, fixtures, public graph responses, or exports.

### SEC EDGAR: public issuers and disclosed corporate relationships

Primary references:

* [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
* [SEC developer resources / fair-access FAQ](https://www.sec.gov/about/webmaster-frequently-asked-questions)
* [SEC company ticker/CIK associations](https://www.sec.gov/files/company_tickers.json)
* [SEC submissions API](https://data.sec.gov/submissions/CIK##########.json)
* [SEC forms](https://www.sec.gov/forms)

The submissions endpoint is keyed by a zero-padded 10-digit CIK and returns
current/former names, tickers/exchanges, and filing history. The SEC describes
the submissions and XBRL APIs as unauthenticated JSON services updated in real
time, with nightly bulk archives for `submissions.zip` and
`companyfacts.zip`. EDGAR does not support CORS; an automated client must use
the SEC's access rules and an honest identifying `User-Agent`.

The SEC currently states a maximum access rate of 10 requests/second and asks
clients to declare a user agent. Use a lower bounded rate, conditional/cache
headers when available, retries with backoff for 429/5xx, and the nightly bulk
archives for wide historical work. Record an HTTP error or HTML challenge as a
quarantined acquisition, never as an empty dataset.

Relationship-bearing filing evidence includes:

* Form 10-K/20-F/40-F business and property disclosures and Exhibit 21
  subsidiary schedules;
* Forms 3, 4, and 5 for officer/director and beneficial-ownership filings;
* Schedules 13D/13G for certain beneficial ownership disclosures; and
* 8-K, merger, registration, and other filed exhibits when they explicitly
  state a transaction or corporate relationship.

These should be represented as `disclosed_subsidiary`, `disclosed_officer`,
`beneficial_owner_disclosure`, or another narrowly scoped observation with
form, accession, filing date, and exhibit/page/anchor support. An Exhibit 21
list is evidence that the filer disclosed a subsidiary at a point in time; it
is not a complete, current, or independently verified ownership graph. An
officer/director filing connects a person to a filer for the filed role and
period; it does not connect that person's employer text to a facility.

CIK is strong for an SEC registrant, but subsidiary names in exhibits often do
not have a CIK. Names may be historical, abbreviated, foreign, or omitted for
immaterial subsidiaries. Exact CIK/name evidence can create a candidate
crosswalk; automatic parent/subsidiary merging is prohibited.

### IRS TEOS and EO BMF: tax-exempt identity and related organizations

Primary references:

* [IRS Tax Exempt Organization Search](https://www.irs.gov/charities-non-profits/search-for-tax-exempt-organizations)
* [IRS TEOS bulk downloads](https://www.irs.gov/charities-non-profits/tax-exempt-organization-search)
* [IRS Form 990 XML downloads](https://www.irs.gov/charities-non-profits/form-990-series-downloads)
* [IRS EO Business Master File extract](https://www.irs.gov/charities-non-profits/exempt-organizations-business-master-file-extract-eo-bmf)

TEOS exposes exempt-organization status, filings, determination letters, and
bulk data. EO BMF files are CSV by state/region and are keyed/sorted by EIN;
the IRS describes them as the latest information it has for organizations with
an exempt determination. Form 990 XML and indices can provide related-
organization and officer/key-employee evidence (for example, Schedule R and
Part VII), subject to redaction and privacy review.

This is a useful identity source for nonprofit political, trade, advocacy, and
animal-welfare organizations, but it is not a general business registry. The
IRS says its searchable name data are official names submitted to the IRS and
that DBA/common names may be absent in some datasets. Status can be revoked or
reinstated; an absence or stale row is not closure. Store EIN and form/index
IDs source-scoped, preserve raw XML privately, and never expose officer names
or addresses merely because a Form 990 is public.

### SAM.gov: federal-award entity identity

Primary references:

* [SAM.gov entity information](https://sam.gov/entity-information)
* [SAM.gov entity registration and UEI](https://sam.gov/entity-registration)
* [SAM.gov about/data services](https://sam.gov/about/this-site)

SAM.gov provides a governmentwide Unique Entity ID (UEI), legal business name,
physical address, registration status, and federal-award context for entities
that register or request an identifier. SAM says registration must be renewed
every 365 days and provides entity extracts and Entity Management APIs/system
connections. Public visibility is configurable, and some records are not
available to ordinary public search.

Use `UEI` as a source-qualified identity only. A UEI is evidence of a SAM
entity record, not proof of a corporate parent, beneficial owner, operating
facility, or current activity. A SAM address is a validation/disclosure field,
not permission to publish a private or residential location. Acquisition must
record whether the observation came from a public search, official extract, or
authenticated API, and must preserve active/inactive/expired status and
observation dates.

### State Secretary of State registries

State registries are the primary source for many privately held US entities,
but they must be handled one jurisdiction at a time. For example, [Delaware's
Division of Corporations online services](https://corp.delaware.gov/services/)
offers business-entity search, status, annual-report, and document services;
its FAQ says a free search can return name, file number, formation date,
registered-agent information, entity kind/type, and residency, while more
detailed status/history may be fee-based. Delaware also states that current
officers/directors can be found on the most recent annual report, while
shareholder/owner information is not on file. Its search page prohibits data
mining and excessive/repeated searches.

Accordingly:

* use a state entity number plus jurisdiction as the native identifier;
* prefer official filing copies or explicitly permitted downloads/API access;
* do not automate a search form or mine a registry when its terms prohibit it;
* treat registered agent, principal address, annual-report officer, and owner
  as different fields with different meanings; and
* model foreign qualification in another state as a source observation that
  may support a reviewed crosswalk, not as a universal identity.

There is no safe nationwide state-SOS bulk adapter implied by this document.
Start with one state only after a terms/access review and an operator-assisted
capture contract. A state filing can be strong evidence of formation, status,
or a filed officer/director role, but not automatically of current operation,
ownership, or facility control.

## Proposed graph and evidence contracts

### Source-native entities

The current `graph-candidate-handoff-v1` contract should be reused. Add no
universal-ID field. Suggested identifier types are:

| Entity | Identifier type | Example semantics |
| --- | --- | --- |
| FEC committee | `fec_committee_id` | Stable FEC `CMTE_ID`; source-scoped to FEC committee records. |
| FEC candidate | `fec_candidate_id` | Stable FEC `CAND_ID`; person entity, not a company. |
| SEC registrant | `sec_cik` | CIK for a registrant; accession is evidence-record identity, not entity identity. |
| IRS exempt organization | `irs_ein` | EIN in TEOS/EO BMF; availability is limited to applicable exempt records. |
| SAM entity | `sam_uei` | UEI in the observed extract/API/search result. |
| State entity | `state_entity_number` | Always paired with `jurisdiction` and filing/source ID. |
| facility source row | existing source-native facility ID | Never replace this with an organization name or address match. |

Every identifier observation carries `source_id`, `source_record_id`,
`value_as_observed`, normalized value (if any), observed time, source URL,
artifact hash/bytes, record/form/file/image/accession ID, and independent
review/privacy/publication states. Raw names, addresses, coordinates, and
personal roles remain private until the applicable policy gates pass.

### Relationship and event types

Use existing `organization_relationship_observations` only for a narrowly
defined assertion that fits its direction and time semantics:

* `parent` / `owner` / `operator` / `brand` for organization-to-organization
  or organization-to-facility evidence;
* `regulatory_authority_for` only when the source explicitly describes that
  authority scope; and
* a future source-specific role or claim for `fec_connected_organization`,
  `fec_candidate_committee`, `sec_disclosed_subsidiary`, and
  `officer_of` unless the schema is deliberately extended.

Do not encode a contribution as `owner`, `parent`, `operator`, or `supplier`.
Use a separate append-only financial-event contract with:

```text
financial_event {
  source_id, source_record_id, filing_id, image_id, transaction_id,
  amendment/version, observed_at, transaction_date,
  payer_source_ref?, payee_source_ref?, recipient_committee_source_ref?,
  candidate_source_ref?, amount, currency, schedule, line/category,
  memo/earmark state, raw-party-name-private, review/privacy/publication state
}
```

`payer_source_ref` or `payee_source_ref` is populated only when the source
provides an explicit source-native identifier (for example FEC `other_id` for
another committee). A free-text contributor/payee name remains a claim or
unresolved candidate, never an organization edge. Each event must retain the
filed direction and not imply that a facility was involved.

### Evidence state and confidence

Confidence is scoped to one claim and one source observation; it is not a
probability that the whole graph is true. Store both a bounded numeric value
(nullable) and an explanation, and keep `assertion_status`, factual
`review_state`, `privacy_status`, and `publication_status` separate.

Recommended evidence grades:

| Grade | Permitted interpretation | Default result |
| --- | --- | --- |
| A — explicit | The source provides a stable ID or explicit filed relationship: FEC candidate/committee linkage, Form 1 connected organization, SEC filed exhibit/ownership form, IRS EIN/form relationship, SAM UEI record, or state filing. | Private review-required observation for that exact role/date. Never a universal merge or facility claim. |
| B — concordant | Two or more independent source records agree on a legal name plus scoped identifier/address/date, but no source explicitly states the relationship. | Candidate crosswalk only; human review required. |
| C — discovery | Name similarity, suffix-stripped match, website, shared address, registered agent, common officer name, employer string, proximity, or contribution alone. | Discovery queue only; no relationship row and no automatic crosswalk. |
| 0 — unresolved/contradicted | Missing IDs, conflicting filings, ambiguous same-name entities, or source disagreement. | Quarantine with explicit unknown/disputed/rejected state. |

Do not average evidence grades or let a high-confidence identity claim upgrade a
low-confidence relationship. A direct source statement about a parent may be
Grade A for `disclosed_parent_at_time`, but only Grade C for a facility
operator edge unless the facility source itself names the organization or a
reviewer records a separate supported link.

## Conservative matching and review rules

1. Normalize only for candidate search. Preserve the original name, suffix,
   punctuation, case, address, and source values beside any normalized key.
2. Require at least one explicit source-native key for an accepted crosswalk;
   exact name alone is not enough. A legal-name match across FEC, SEC, IRS,
   SAM, or a state registry remains source-scoped until reviewed.
3. Keep multiple same-name organizations alive. Never collapse different CIKs,
   EINs, UEIs, state entity numbers, or FEC IDs because names are similar.
4. Require direction and time. Parent and subsidiary directions must not be
   reversed; officer roles and filing periods are dated; source disappearance
   means `not_observed`, never closure.
5. Keep committee/filer identity separate from the connected organization,
   sponsor, treasurer, candidate, and contributor. A committee can be
   sponsored or affiliated without being owned by that organization.
6. Do not create a facility edge from an FEC contribution, individual employer,
   SEC officer, registered agent, mailing address, or shared name. An explicit
   facility source ID or a separately reviewed source-supported observation is
   required.
7. Preserve contradictions and amendments. A later filing is a new
   observation; it does not erase an earlier claim or turn an absent row into a
   closure event.
8. Keep names/addresses of individual contributors, officers, registered-agent
   contacts, and private persons out of public projections and test fixtures.
   Public release needs a privacy decision that covers maps, APIs, exports,
   old releases, caches, raw previews, and reimports.

## Reusable acquisition/query plan

These are bounded private research queries, not public API promises:

1. **FEC exact committee:** search `/v1/committees/` by a reviewed exact
   `CMTE_ID`; retrieve filing history and current/previous Form 1 observations.
2. **FEC candidate linkage:** join only the official linkage file on
   `CAND_ID + CMTE_ID + election year`; retain linkage ID, designation, and
   period.
3. **FEC connected organization:** extract the filed Form 1 connected-
   organization/sponsor/affiliation field into a private organization candidate
   with source text and filing support; do not resolve it by name alone.
4. **FEC transaction:** retrieve Schedule A/B/E by committee, date window, and
   filing/transaction ID; resolve `other_id` only to the matching FEC source
   entity type; preserve memo/amendment state.
5. **SEC registrant:** resolve an already reviewed CIK using submissions JSON,
   then fetch only selected filing accessions/exhibits. Store an exhibit-21 or
   officer observation with accession and anchor/page support.
6. **IRS exempt organization:** resolve EIN in EO BMF/TEOS, then inspect the
   relevant Form 990 XML/index (especially related-organization disclosures)
   under the private retention policy.
7. **SAM entity:** query an exact UEI or approved bounded name search, record
   whether the result is public search, extract, or API, and capture status and
   observation date.
8. **State registry:** use an exact state entity number or a single reviewed
   name search through the state-approved route; do not crawl or mine the
   registry.
9. **Facility connection:** query existing facility source IDs only. A corporate
   identity result can enter a facility relationship queue, but cannot create
   the edge by proximity, name, address, contribution, or officer overlap.

Every acquisition writes a source manifest with official URL, retrieval UTC,
publication/effective date if supplied, content type, byte size, SHA-256,
source terms/access notes, parser/configuration version, and a fail-closed
status. Raw and parsed layers stay in ignored private staging. A failed or
blocked refresh leaves the prior validated release available subject to
current suppression.

## Test plan

Use sanitized or synthetic fixtures only. Tests should cover:

* FEC pagination, 100-row page boundaries, nightly/bulk manifest capture,
  429/backoff, malformed JSON, HTML/403 responses, missing IDs, and exact
  source-record provenance;
* FEC amendment/version handling: the same transaction ID across an original
  and amendment remains one event lineage with both filed observations, and
  memo/earmarked/refund rows are not silently counted as ordinary donations;
* candidate-to-committee linkage keeps `CAND_ID`, `CMTE_ID`, election year,
  designation, and linkage ID, and never emits an owner/operator edge;
* a Form 1 connected-organization string yields a review-required private
  candidate; two committees with similar names do not merge;
* a Schedule A employer string and a corporate-looking contributor name never
  create an organization or facility edge; an explicit `other_id` committee
  reference may create only a typed FEC event reference;
* SEC CIK/ticker/former-name observations remain source-qualified; an Exhibit
  21 name without a CIK remains a candidate, and two CIKs with the same name
  remain distinct;
* synthetic SEC exhibit, IRS Schedule R, state filing, and SAM UEI fixtures
  preserve accession/form/entity numbers, observation dates, direction, and
  unknown/withheld values;
* parent/subsidiary direction is validated, officer role periods do not become
  ownership, and a source disappearance produces `not_observed`, not closure;
* state registry access is blocked when terms say no mining, and manual capture
  records operator/context rather than inventing an API contract;
* graph candidate validation rejects `canonical_id`, `global_id`, or
  `universal_identity`, rejects public/released state, requires source-local
  identifiers, and preserves contradictory observations;
* public projection tests prove that FEC contributor/officer names, addresses,
  raw filing payloads, facility coordinates, and restricted source values are
  absent even when a related organization is otherwise eligible; and
* failed acquisition, privacy suppression, restore, and reimport tests never
  resurrect a suppressed edge or release a private candidate.

## Recommendation and next bounded slice

Prioritize an FEC adapter for synthetic/test-only ingestion of committee master,
candidate master/linkage, Form 1 metadata, and a very small Schedule A/B
fixture. Add SEC CIK/submissions metadata next, without fetching broad filing
corpora. Defer state-registry automation until one state's terms and permitted
access path are documented. Treat IRS and SAM as scoped identity corroboration,
not as facility or corporate-master sources.

The first implementation should add source-specific event/claim contracts and
fixtures rather than expanding the canonical graph relationship enum. No
production import, public projection, contribution-derived facility link,
automatic parent/subsidiary merge, or ownership inference is justified by this
reconnaissance.
