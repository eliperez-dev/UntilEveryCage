# Product vision

**Owner:** project maintainers. **Purpose:** preserve the enduring product
direction that should guide design and tradeoffs. This page is not an execution
plan, readiness claim, publication authorization, or evidence of implementation.
See [PRODUCT-READINESS.md](PRODUCT-READINESS.md) for current state and
[ETHICS.md](ETHICS.md) for binding policy.

## Purpose

Until Every Cage helps people understand the scale and reach of animal
exploitation, discover documented infrastructure around them, and inspect the
evidence and uncertainty behind each claim. The project can take a clear moral
position while making its factual claims traceable and carefully scoped.

## Visitor journey

1. Understand the scale through a sourced, bounded story.
2. Choose a place and discover documented activity nearby.
3. Inspect a record's source, dates, classification, history, and limitations.
4. Share or export the finding with its evidence context intact.

Discovery should not obstruct evidence access. Narrative estimates must state
their population, time period, units, method, exclusions, and uncertainty; they
must not imply that a facility pin is an animal count or that a modeled rate is
a live measurement.

## Product shape

- **Map:** a calm place-first discovery experience with optional location input,
  clear precision and coverage limits, and a useful list for records without
  eligible coordinates.
- **Database:** a research-oriented search and export surface for records,
  sources, observations, relationships, and releases.
- **Evidence and story:** a bounded, accessible explanation of scale that
  connects to inspectable source material and local discovery.
- **Shared record model:** stable record URLs, explicit source identity, and
  source, review, privacy, approval, and publication states kept distinct.

The frontend's current approved specification is indexed in
[frontend/README.md](frontend/README.md). This vision describes intent; that
specification and [the product readiness roadmap](PRODUCT-READINESS.md) define
what is currently approved or implemented.

## Design principles

- Lead with understandable evidence and documentary restraint; do not use shock
  imagery or unsourced comparisons as substitutes for explanation.
- Preserve original source statements separately from project interpretations,
  classifications, estimates, and user submissions.
- Make unknowns, missing coverage, approximate locations, unresolved identity,
  and review status visible instead of guessing or silently dropping them.
- Make location search optional. Do not expose private addresses or retain
  precise visitor locations by default.
- Support keyboard use, reduced motion, mobile layouts, and a useful non-map
  path through the same evidence.
- Prefer maintainable infrastructure when it makes evidence more reliable,
  repeatable, or understandable.

## Success looks like

Visitors can find relevant evidence, explain what a claim means and does not
mean, inspect how it was produced, and reproduce a shared or exported result.
The product remains useful when source coverage is incomplete because those
limits are visible. No visual or narrative goal overrides the project policy.

## Source note

This curated vision consolidates durable direction from the former V2 design
and implementation proposal. Proposed names, technology choices, speculative
statistics, feature checklists, old code audits, and superseded delivery
sequences were not carried forward as current commitments. Unique historical
audit evidence is indexed in [archive/README.md](archive/README.md).
