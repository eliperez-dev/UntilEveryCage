# Content, terminology, and safety

## Canonical vocabulary

| Use | Avoid | Reason |
| --- | --- | --- |
| Facility | “site” when the physical scope is unclear | The data model distinguishes physical facilities from organizations and source records |
| Organization | Owner, parent, or operator unless sourced | An edge is not automatically ownership |
| Record | Facility when the object is not spatial | Evidence, events, organizations, and source rows can be records too |
| Source-supported connection | Confirmed connection | Exact means an explicit source key/assertion, not universal truth |
| Inferred connection | Linked, owned by, or same as | Inference is algorithmic and may be wrong |
| Exact public point | Verified location | Exact display precision is not a factual guarantee |
| City-level approximation | Approximate pin without qualifier | The public must not mistake a centroid for a facility point |
| Not observed recently | Closed | Absence from a source is not proof of closure |
| Project-published | Approved or verified | Publication, project approval, factual review, and source origin differ |

## Required labels

Every record has a visible path to source origin, retrieval/observation dates,
release/profile, precision, lifecycle, and relevant review/privacy context. The
default label for an inferred relationship is:

> Inferred connection — a deterministic estimate based on the displayed signals
> and ruleset. It is not proof of ownership, identity, or supply-chain activity.

For community profile rows, the warning must precede access and persist in the
result list, map/list detail, direct link, and export. Color never carries this
meaning by itself.

## Copy tone

Use direct, non-sensational language. Explain limitations without apologizing for
the existence of uncertainty. Source terminology may be quoted, but the project
explanation is separate. Avoid animal totals or global claims unless the page
has a named, cited aggregate product.

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
- Do not turn a city/coarse record into a facility-shaped pin, street-view
  target, directions link, or exact-looking SEO description.
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

- No results: “No eligible records match these filters in this release. This
  does not establish that no facility exists.”
- No point: “This record is public but has no publishable coordinate.”
- City point: “Approximate city-level location; not a facility point.”
- Stale/unknown lifecycle: “Not observed recently; this is not proof of closure.”
- Service error: “The current release could not be loaded. Try again; the last
  response was not substituted as if current.”
