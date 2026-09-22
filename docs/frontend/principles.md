# Frontend principles and audiences

## Product promise

UEC helps people locate, understand, and investigate documented infrastructure
of animal exploitation. It is an evidence index and accountability layer, not
an authoritative global registry. Every visible claim should answer: what is
this, where did it come from, how precise is the location, how current is the
observation, and what remains uncertain?

## Design principles

### 1. Quiet entry, deep evidence

The first screen should communicate one action—search or explore the map—without
making a visitor learn the data model. Detail, provenance, history, graph
signals, filters, and exports appear progressively.

### 2. Map for orientation; database for investigation

The Map answers “what is near this place?” The Database answers “show me the
records matching these conditions.” Neither should pretend to be the other.

### 3. Uncertainty is part of the interface

Coordinate precision, lifecycle, source origin, review state, and relationship
confidence are first-class fields. A low-confidence inferred edge remains
findable but is visually quieter and textually qualified.

### 4. Preserve V1 utility, replace V1 ambiguity

The V1 contract preserves name/activity search, category filters, country and
region semantics, marker-to-detail discovery, clustering, shareable map state,
reset, visible-result CSV export, translations, and lazy reports where a V2
endpoint exists. V2 replaces array-wide loading, opaque popups, unsafe routing,
and implied completeness with server queries, semantic lists, release context,
precision-aware actions, and explicit scope.

### 5. Speed is a product feature

Use server-side viewport queries, bounded payloads, cancellable requests,
progressive rendering, stable URL state, and measured budgets. Avoid clever
client architecture that does not improve interaction latency or reliability.

### 6. Privacy is visible, not hidden

The UI must make public eligibility and precision understandable. A suppressed
or restricted record is not hinted at by a stale cache, cluster count, export,
or search suggestion. City-level rendering must not be used to guess a private
point.

## Audiences and their jobs

| Audience | Primary job | Default surface | Needs | Does not need first |
| --- | --- | --- | --- | --- |
| Curious visitor | Understand what is near a place | Map | Plain search, simple filters, legible detail | Database vocabulary |
| Local activist | Find facilities and supporting source context | Map → detail | Distance, activity, source, precision, share link | Every historical version |
| Journalist | Verify and connect claims | Database → detail/graph | Provenance, source IDs, dates, graph explanations, export | Decorative story flow |
| Researcher | Query a reproducible slice | Database | Facets, stable sorting, cursor pages, CSV, release metadata | Animated map effects |
| Maintainer | Diagnose coverage and restrictions | Database/detail | State labels, release/profile context, errors, bounded diagnostics | Private controls in public UI |

## Success measures

- A visitor can search a town/postcode without granting device location.
- A researcher can reproduce a filtered result set from a stable URL and named
  release.
- Every public graph connection can be inspected for type, confidence band,
  signals, contradictions, source references, and ruleset.
- Map movement remains responsive at 100k facilities without downloading the
  entire dataset.
- A user can distinguish an exact public point, a city/coarse placement, and an
  unmapped record before using distance or directions.

