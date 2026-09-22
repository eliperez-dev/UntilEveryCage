# Releases and the shared record model

## Release naming recommendation

The recommended human-readable display convention for public dataset releases
is CalVer with a sequence for multiple releases in one month:

`YYYY.MM.N`

Examples: `2026.09.1`, `2026.09.2`, `2027.01.1`. This is a recommendation
pending maintainer approval, not a new API requirement.

The release manifest also carries:

- the actual stable machine identity exposed by the manifest (`release_id`);
- the independent manifest checksum (`manifest_sha256`);
- a short human title, such as `September 2026 public release`;
- creation/promotion time and source cut-off/currentness metadata;
- profile (`official`, `secondary`, or `community` where enabled);
- ruleset and schema versions;
- artifact references;
- coverage and limitation summary.

CalVer is for people and display; `release_id` and `manifest_sha256` are
separate machine fields and must not be treated as interchangeable. A release
and its source/version lineage should be reproducible, but current suppression,
revocation, or other policy-authorized removal may change what an older release
reference is allowed to expose. Immutable source/version identity never
bypasses those current safety gates. A superseding release normally gets a new
display sequence and identity, while old release references remain resolvable
only when policy permits.

Do not use application/API SemVer for data releases. Software and wire
contracts use normal SemVer (for example, API `2.1.0`); source adapter versions
and graph rulesets are independently versioned. The frontend must display both
the selected data release and the API/software contract only when those values
are available, so users do not confuse code changes with data refreshes.

## Record identity

All public-facing objects share a record envelope:

| Record family | Spatial by default? | Example role |
| --- | --- | --- |
| Facility | Often | A slaughterhouse, farm, laboratory, breeder, dealer, or exhibitor |
| Organization | No | A company, operator, parent, or public body as sourced |
| Evidence | No | A report, inspection document, image, dataset row, or source assertion |
| Inspection/event | Sometimes | An inspection, permit event, closure observation, or dated action |
| Source record | No | The source-qualified row from which a normalized claim came |
| Community submission | Sometimes | Future untrusted tip, correction, or user-submitted facility |

Each record has a stable opaque `record_id`, record type, canonical display
label, provenance, release/profile eligibility, source references, and a
canonical URL. A readable slug may be appended for SEO, but it is not identity.
Records are not silently merged merely because they look similar.

Only records with a publication-eligible spatial representation appear as map
items. Exact coordinates, city-level approximations, and broader coarse areas
are separate display precisions. Non-spatial evidence and organization records
remain full searchable records and can be graph endpoints.

Source observation dates, retrieval dates, release creation dates, and promotion
dates remain independent fields; the CalVer display date must never be read as
the observation date.

## Graph semantics

The public graph connects records, not just facilities. An edge is either:

- `exact`: an authoritative shared identifier or explicit source assertion;
- `inferred`: a deterministic estimate with score, confidence band, grouped
  signals, contradictions, provenance, and ruleset.

Both types are public when their endpoints and evidence pass release,
suppression, privacy, and profile gates. Inferred edges remain visible and
filterable at high, medium, and low confidence. They never become identity
merges, ownership facts, or confirmed claims merely because they are rendered
as a line.

## Future community dataset

Community submissions are a separate untrusted intake dataset, not a backdoor
into the curated release. Tips, facilities, evidence, and corrections have
independent submission IDs and moderation/provenance/privacy/abuse controls.
They can be linked to curated records as a submission relationship, but are not
automatically merged, published, geocoded to a precise point, or included in
graph/map counts. Explicit release promotion creates a traceable new source
record and preserves the submission history.
