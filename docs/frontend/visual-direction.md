# Visual direction and tokens

## Direction: field notebook, not dashboard

The visual system should feel like a well-made field atlas: restrained, legible,
quiet at rest, and precise when inspected. It should avoid the existing V2's
heavy panels, decorative gradients, and “control room” density. The subject is
serious; the interface should not use shock imagery or gamified urgency to make
the data feel important.

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

The base is warm paper/near-white with deep charcoal text and one muted green-
blue accent. Category colors are functional accents, not a rainbow background:

- slaughter/activity: deep red;
- processing: slate/graphite;
- laboratory/research: violet;
- breeder/farm: ochre;
- dealer: burnt orange;
- exhibitor: green.

Each category must also have a shape, label, or pattern equivalent. Confidence
bands use tone and text, not color alone. A high-confidence inferred edge is not
colored as exact.

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

## Map style

Use a low-contrast base that lets points and boundaries read. Satellite should
not be the default: it adds external requests, visual noise, and false authority
for approximate locations. Attribution and tile-provider disclosure are part of
the visible methodology/credits path.

