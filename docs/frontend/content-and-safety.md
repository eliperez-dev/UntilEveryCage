# Content, terminology, and safety

## Canonical vocabulary

| Use | Avoid | Reason |
| --- | --- | --- |
| Facility | “site” when the physical scope is unclear | The data model distinguishes physical facilities from organizations and source records |
| Organization | Owner, parent, or operator unless sourced | An edge is not automatically ownership |
| Record | Facility when the object is not spatial | Evidence, events, organizations, and source rows can be records too |
| Exact source | Confirmed connection | An exact connection uses explicit source evidence, not independent verification |
| Inferred connection | Linked, owned by, or same as | Inference is algorithmic and may be wrong |
| Exact public point | Verified location | Exact display precision is not a factual guarantee |
| City-level approximation | Approximate pin without qualifier | The public must not mistake a centroid for a facility point |
| Not observed recently | Closed | Absence from a source is not proof of closure |
| Project-published | Approved or verified | Publication, project approval, factual review, and source origin differ |

## Required labels

Every record has a visible path to source origin, retrieval/observation dates,
release/profile, precision and relevant review/privacy context. Retain lifecycle
metadata without displaying an unknown-status field. Label exact connections
"Exact source" once. Label inferred connections "Inferred" with their recorded
confidence. Keep method and evidence available per connection; do not repeat a
general disclaimer paragraph above the list. Display `source_assertion` as
"Source", not "Source assertion". These shorter labels do not change matching
semantics or establish ownership.

For community profile rows, the warning must precede access and persist in the
result list, map/list detail, direct link, and export. Color never carries this
meaning by itself.

## Copy tone

Use the maintainer's supplied wording verbatim where specified. Do not add
unsolicited disclaimer blocks, internal audit narrative, revision history,
repeated uncertainty paragraphs or polite filler. Prefer a short factual label
and the actual source/evidence fields over a general warning paragraph. Removing
copy does not delete provenance or change publication controls. Required public
unreviewed-community labels and map-provider attribution remain in place.
The removed About Sources and methods section and counter Source and method
disclosure must not be reintroduced elsewhere as replacement copy. Review every
new public-facing sentence against the task's exact copy requirements.

Use direct, non-sensational language. Explain limitations without apologizing for
the existence of uncertainty. Source terminology may be quoted, but the project
explanation is separate. Avoid animal totals or global claims unless the page
has a named, cited aggregate product.

Private contribution forms use familiar task names: Add a facility, Add
evidence, Correct a record, Report a duplicate, and Privacy or removal.
Ask for country names rather than codes; country and evidence links are
optional for facility tips. Explain a map pin as choosing the location, not as
a geocoding operation. Use one concise note that submissions are reviewed
before publication, without repeating pilot/review badges throughout the form.
Keep map-provider attribution visible on the map.
Public unreviewed community results retain the warning required above.

Label the task links **Choose a contribution type** so the alternatives are
discoverable. Evidence supports an existing record: ask for its record link or
ID and explain that a submission is reviewed before changing published data.
Do not imply that sending evidence immediately edits or appends to the curated
record. Help uses short steps and media with an equivalent written explanation;
API guidance distinguishes published downloads from private preview data.

Keep informational copy short and concrete. Omit decorative eyebrows such as
“Reading the map” and repeated explanations around a form. A bug-report page
keeps its existing four practical fields and saves the report through restricted
intake, with a confirmation and tracking link rather than an email draft.
Optional fields use “(optional)” without instructions such as
“enter it yourself”. The form still avoids collecting credentials or silently
copying private page context; concise copy does not weaken those behaviors.

Facility details show the broad category once, followed by distinct readable
activities rather than repeated category/provenance summaries. Keep taxonomy
and crosswalk versions in machine provenance, not visible page copy. A compact
Location section groups the available address or locality, coordinates and
recorded location method/provider/confidence. Label source coordinates
"Source-provided coordinates"; do not imply independent validation or invent
a confidence score. Do not label a locality as a street address. On mobile,
the map detail fills the viewport with a visible close control and scrolling
content. Its "Open facility page" header link opens the stable record URL in
the selected release; desktop panel layout is unchanged.

Use one accessible chain-icon "Copy facility link" action beside the facility
name, not a separate copy-ID action. Source classification is inline, not a
disclosure: retain distinct native information without repeating the broad
category or showing internal mapping/version labels. Display animal-count
estimates in animals while retaining source-native units in data.

Full facility pages may show a compact, single-record location map: satellite
for source/exact coordinates, a wider road map for approximate locations, and
no map for an unmapped record. Reuse the existing tile providers and category
pins. A road map is not street-level panorama imagery. Do not fetch the global
facility projection for this preview or invent a street address from locality.
Order full pages as facility name/share action, Location facts, location map,
then activities/classification and remaining facts. Satellite previews use
zoom 15 and approximate road-map previews use zoom 9. Keep them noninteractive.

APHIS report controls belong only on relevant APHIS records. Load them on
request and preserve explicit loading, empty, error and retry states. Distinguish
report files and source-provided report details from metadata references that
only open an APHIS search page. Do not call the latter full reports or invent
exception-report coverage. Unrelated records must not issue APHIS requests.

Release selection and history live in Tools. Public map URLs omit fixture
parameters such as `scenario=default`; old links remain readable. Public debug
controls may change display settings, but must not enable private routes or
development mode.

## Safety rules in UI

- Do not expose private-person names, residential addresses, worker details, or
  targetable personal information.
- Do not offer directions for city/coarse/unmapped or restricted locations.
- Do not reveal suppressed records through counts, clusters, search suggestions,
  stale cache, export, history, or error text.
- Do not provide a “report this person” action. Corrections/privacy requests use
  the governed contact path and minimal information.
- Do not imply that the public graph proves wrongdoing or a supply chain.
- Do not show raw matching identifiers where they could expose restricted data;
  show safe source labels and links.
- Do not present a city/coarse record as an exact facility point, street-view
  target, directions link, or exact-looking SEO description. The maintainer's
  approved ordinary pin artwork may be reused for a singleton, with its
  approximation disclosed in the accessible label, tooltip and record details.
  Its selected-only red area is 500 metres across, a display convention rather
  than a confidence interval or measured location accuracy.
- Do not allow canonical metadata, sitemap entries, graph node previews, or
  aggregate counts to leak suppressed/restricted/community-intake records.

## Community intake safety

Future tips, corrections, evidence, and facility submissions are untrusted
intake. They require abuse/rate controls, privacy and consent checks, moderation
state, provenance, and an explicit warning before any reviewer or downstream
process opens them. A submission may be linked to a curated record as a
separate source relationship, but it cannot automatically publish, merge,
geocode, or influence the public graph. User-submitted claims must not be
presented as project-reviewed facts.

## Empty and error copy patterns

- No results: “No records match these filters.”
- No point: “No mapped location.”
- City point: “Approximate location.”
- Unknown lifecycle: omit the field rather than adding an unknown-status message.
- Service error: “Could not load this release. Try again.”
