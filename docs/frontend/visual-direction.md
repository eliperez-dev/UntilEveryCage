# Visual direction and tokens

## Direction: dark field atlas, not dashboard

The visual system should feel like a dark, well-made field atlas: restrained,
legible, quiet at rest, and precise when inspected. It should be minimal in
color, labels, and ornament while still feeling authored rather than like blank
HTML. Avoid the existing V2's heavy panels, decorative gradients, bright
dashboard conventions, and “control room” density. The subject is serious; the
interface should not use shock imagery or gamified urgency to make the data feel
important. Show the evidence and its relationships; let the interface explain
itself through structure rather than decoration.

## Type

- Primary UI: a highly legible humanist sans with tabular numerals available.
- Optional display face: a restrained serif only for the project name or short
  editorial heading, never for tables or dense controls.
- Use sentence case, short labels, and visible units.
- Numeric counts, confidence scores, coordinates, and dates use tabular figures
  and consistent precision.

The implementation should self-host only fonts whose licensing and loading cost
are understood; system fallbacks are acceptable and preferable to a blocking
font request.

## Palette intent

The base is near-black charcoal with layered graphite surfaces, warm off-white
text, muted secondary text, and one restrained signal accent. Category colors
are sparse functional accents, not a rainbow background:

- slaughter/activity: deep red;
- processing: slate/graphite;
- laboratory/research: violet;
- breeder/farm: ochre;
- dealer: burnt orange;
- exhibitor: green.

Each category must also have a shape, label, or pattern equivalent. Confidence
bands use tone, text, and line treatment, not color alone. A high-confidence
inferred edge is not colored or worded as exact.

## Spacing and surfaces

- Use an 8px base rhythm with generous outer margins and compact table rows.
- Keep one primary surface and a small number of quiet elevated sheets.
- Borders and rules carry hierarchy better than shadows.
- Map overlays should be translucent only where contrast remains reliable.
- Avoid full-screen cards inside cards; use a single detail surface with sections.

## Components

The first implementation should define a small composable vocabulary:

- site shell and route navigation;
- search combobox;
- filter group/chip;
- coverage/release notice;
- result row/card;
- precision badge;
- lifecycle badge;
- graph confidence badge and evidence row;
- map controls and cluster summary;
- detail surface/section;
- empty/error/loading state;
- export/share action.

Do not create a large design-system abstraction before two real pages exist.

## Motion and interaction tone

Motion is limited to map transitions, sheet entry, and loading state, all with a
reduced-motion path. No bouncing markers, number counters, or attention pulses.
Focus rings are visible and high contrast. Hover can enrich a row, but never
reveals the only source, confidence, or action.

## Map style and imagery

Use a low-contrast vector base by default so points and boundaries read, with a
prominent selectable satellite view for investigation. A MapLibre-compatible
licensed raster provider is a provider choice—not a hard-coded promise. Mapbox
Standard Satellite may be evaluated only as a separate Mapbox-compatible
renderer/provider stack under its own terms; it is not assumed to be a
drop-in MapLibre style. Street View and historical imagery are optional
provider layers and must carry their own availability and attribution states.
Satellite imagery can add context but does not make a location exact or current.

Exact pins use the restrained V1 pin family at launch for continuity. The
roadmap includes replacing them with a better, accessible symbol system once
the exact/coarse grammar has been tested. Coarse locations use area/halo/count
grammar, not a pin recolor. A fallback halo is a visual grouping device, not a
measured uncertainty radius; only supplied authoritative city/area boundaries
may be drawn as boundaries.
