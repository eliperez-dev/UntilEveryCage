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

See [claim-ledger.md](claim-ledger.md), [storyboard.md](storyboard.md), and [user-test-plan.md](user-test-plan.md).

## Initial source-verification result

FAOSTAT is a defensible primary source for a bounded land-animal slaughtering figure. A private retrieval of the 2024 normalized bulk release on 2026-09-13 found 17 direct meat items with head units for Area=World and Element=Producing Animals/Slaughtered. After converting `1000 An` rows to heads and excluding aggregate rows and duplicate meat by-products, the selected items sum to **87,896,729,120 heads**. The modeled average is **240,653,071 heads/day** or **2,785 heads/second**, using 365.2425 days/year. This is not a universal total or live counter: it excludes items not in the selected set, includes FAO estimates where present, and spreads annual observations evenly across a calendar-year convention. The source archive hash was `C5835418C18F9322E7DECBD6800F93A216EAAE3CDFA31ACB08F0518C0C6D6853`; raw data remains outside the repository.

The exact selected item list, units, exclusions, formula, retrieval date, source links, and limitations are recorded in claim C-16/C-17. The FAO catalog currently identifies the dataset license as CC BY 4.0, but the release/terms should be rechecked before redistribution or embedding raw data. Before public use, the maintainer should confirm that the selected scope is described prominently enough not to be mistaken for all-animal mortality.

No aquatic individual-count range is approved in this lane. Biomass, capture/landing totals, and farmed production cannot be converted to individuals without species- and size-specific assumptions. A striking familiar-scale comparison is also blocked until its denominator is independently sourced and made commensurate with the chosen animal scope.
