# Narrative evidence lane

This directory contains internal narrative and evidence-planning materials for V2. It is not a publication approval, a source archive, or a substitute for `docs/ETHICS.md`. No claim in this directory is public copy until its source, scope, calculation, date, and review status are recorded.

## Working narrative contract

The experience may take a clear moral position: animal suffering matters and deserves attention. It must still separate observed facts, calculated estimates, interpretations, and moral judgments. A facility row is not an animal, a map pin is not a death count, and a modeled clock is not a live measurement.

The first prototype should move through:

1. **One life:** establish that a counted animal is an individual, without inventing a biography or assigning a facility-specific animal to a named story.
2. **Scale:** show a dated, sourced annual range and explain its denominator, exclusions, and uncertainty.
3. **Time:** derive a transparent per-day/per-second rate from the annual range; label it as a model.
4. **Proximity:** invite an optional region search and show only public-eligible, coarse or approved locations; never use proximity to expose a home or private person.
5. **Evidence:** let visitors inspect source, date, calculation, release/profile, and limitations at the point of use.

The mechanism is inspired by scale demonstrations that use scrolling distance and familiar comparisons to make very large quantities legible. The reference mechanism is not evidence for any animal claim and should not be copied as public factual support.

See [claim-ledger.md](claim-ledger.md) — **Canonical** claim boundary,
[storyboard.md](storyboard.md) — **Reference** prototype, and
[user-test-plan.md](user-test-plan.md) — **Reference** validation plan.

## Initial source-verification result

The retained [aggregate catalog](../../data/manifests/animal-scale-statistics-catalog.json)
and claims C-16/C-17 define the selected 2024 FAOSTAT scope: sixteen
non-aggregate World meat items with the Producing Animals/Slaughtered element.
Converting `1000 An` components to animals and summing gives **87,892,277,479
animals**. A 366-day calendar-year model yields **240,142,834.64 per day** or
**2,779.43 per second**. The earlier seventeen-item total and 365.2425-day
calculation in this page were inconsistent with that catalog and are superseded.
This is a selected-scope estimate, not all animal deaths or event-timed data.

The catalog records retrieval on 2026-09-15 and archive SHA-256
`c5835418c18f9322e7decbd6800f93a216eaae3cdfa31acb08f0518c0c6d6853`.
The 2026-10-24 launch check reproduced the arithmetic from its sixteen
components and checked the FAO methodology, but the named raw archive was not
available locally. That check does not reverify the archive hash or upstream
row extraction. The catalog retains its existing private-validation status;
do not describe a UI counter as publication of the raw statistical archive or
as independent confirmation of the underlying observations.

The exact selected item list, units, exclusions, formula, retrieval date, source links, and limitations are recorded in claim C-16/C-17. The FAO catalog currently identifies the dataset license as CC BY 4.0, but the release/terms should be rechecked before redistribution or embedding raw data. Before public use, the maintainer should confirm that the selected scope is described prominently enough not to be mistaken for all-animal mortality.

No aquatic individual-count range is approved in this lane. Biomass, capture/landing totals, and farmed production cannot be converted to individuals without species- and size-specific assumptions. A striking familiar-scale comparison is also blocked until its denominator is independently sourced and made commensurate with the chosen animal scope.
