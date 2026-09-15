# Candidate storyboard: individual → scale → proximity

This is an internal prototype, not a launch specification.

## 1. Opening: one life, without a fabricated story

**Screen:** A quiet, accessible statement: “Every number in this story refers to individual animals, even when the number is too large to picture.”

**Evidence boundary:** This is moral/editorial framing, not a claim about a particular animal. Do not show an invented name, face, facility, or biography.

**Interaction:** “How this works” opens the claim ledger and distinguishes observed, modeled, and interpretive language.

## 2. Scale: a dated range, not a magic total

**Screen:** A scroll/animation where visual distance is proportional to a reviewed annual estimate. The scale label remains fixed and readable.

**Required copy:** “Modeled annual estimate for [scope], [year]: [low–high]. This is not a live count.”

**Interaction:** Source, denominator, exclusions, formula, and uncertainty stay visible. Users can pause, reduce motion, jump by keyboard, and switch to a table.

**Guardrail:** If no reviewed numeric source packet exists, show the method with synthetic placeholder values labeled “prototype only,” or omit the quantitative animation.

## 3. Time: derived rate with visible assumptions

**Screen:** Convert the annual range into per-day and per-second ranges.

**Formula:** `per_second = annual / days_per_year / 86,400`. Use an explicitly named year convention; do not silently imply real-time events.

**Required copy:** “This clock is a mathematical translation of the annual estimate. It does not measure events as they happen.”

## 4. Proximity: optional, coarse, and safety-screened

**Screen:** “Where is this documented?” with optional town/region entry. Device geolocation is not required.

**Interaction:** A user can choose a country/region and see only the selected public release/profile. Exact points are shown only when eligible; otherwise use city/coarse/unmapped states.

**Guardrail:** Never imply that a facility is operating now, that a home is near a facility, or that a person is associated with a record. A removed/restricted location must disappear from this narrative path too.

## 5. Evidence return path

Every claim card needs: source origin, source name/URL where safe, retrieval/observation date, release/profile, review/approval state when actually available, uncertainty, and a correction/privacy link. “Government-sourced” must not be rendered as “verified.”

## Editorial and accessibility cautions

- Avoid historical-atrocity analogies in public copy; describe the project’s moral position directly.
- Avoid gore, graphic imagery, countdown pressure, autoplay audio, and language that shames visitors.
- Do not rely on color, motion, hover, or proximity alone to communicate status.
- Provide reduced-motion behavior, pause/step controls, keyboard navigation, screen-reader text, a text/table equivalent, sufficient contrast, and a clear “what this number means” explanation.
- Do not put precise user-entered locations in URLs, analytics, shared links, or error messages.
- Keep activist urgency separate from factual certainty; emotional effect is a test outcome, not evidence of truth.
