# Narrative claim ledger

Status vocabulary: **candidate** means a source still needs review; **ready-for-prototype** means the method and source scope are documented but not public approval; **blocked** means do not use in public copy.

| ID | Candidate claim/copy | Type | Required evidence and scope | Calculation / uncertainty | Status |
|---|---|---|---|---|---|
| C-01 | “Animals are individuals, not database rows.” | Moral/editorial framing | No factual source required; must not be presented as a measured statistic. | Avoids anthropomorphic biography and facility attribution. | ready-for-prototype |
| C-02 | “This map records places and evidence; it does not count animals at each pin.” | Product limitation | V2 API release-scoped public facility projections, release/profile metadata, source/provenance fields. | API list/detail/facet counts are facilities/records in a selected public release, not animals or worldwide totals. Directly state that facility rows are not animal counts. | ready-for-prototype |
| C-03 | “A source record can be outdated, incomplete, inaccurate, or ambiguous.” | Policy-backed factual limitation | `docs/ETHICS.md` §§4-5, dated policy version. | No numeric estimate. | ready-for-prototype |
| C-04 | “The annual total is an estimate for [defined population/scope] in [year/range], not a live count.” | Modeled quantitative claim | Primary statistical source(s), exact species, geography, production/use category, year, unit, denominator, coverage. | `annual_low <= annual_estimate <= annual_high`; publish source range and exclusions. | blocked until source review |
| C-05 | “On the same assumptions, the modeled rate is [range] per second.” | Derived quantitative claim | Approved C-04 inputs and formula. | `rate_per_second = annual_count / 365.2425 / 24 / 60 / 60`; show leap-year convention and propagated range. | blocked until C-04 |
| C-06 | “One pixel represents [N] animals in this view.” | Visualization contract | C-04 approved range and chosen scale. | Pixel/bin rounding must not imply precision below source uncertainty; expose scale and total. | blocked until C-04 |
| C-07 | “You may be near a mapped facility.” | Proximity framing | User-entered region only; approved public release; current coordinate/display precision and safety review. | No claim that the nearest facility is operating or that a visitor’s home is near it. | blocked until privacy/location audit |
| C-08 | “This facility was observed in [date].” | Record-level observed fact | API `last_observed_at`, source retrieval/observation date, release ID. | Do not translate to “operating now” or “closed.” | ready when API fields present |
| C-09 | “Government-sourced” | Source-origin label | Source registry identity, URL, retrieval date. | Does not imply truth, approval, review, or currentness. | ready with provenance UI |
| C-10 | “Project-approved in release [ID]” | Publication decision | Publication review event, release membership, approval actor/scope. | Approval is version/release scoped; changed records do not inherit automatically. | blocked until release evidence |
| C-11 | “An individual animal’s day looked like [specific biography].” | Narrative factual claim | Specific welfare/behavior source and lawful, non-identifying provenance. | Must not be invented or inferred from a facility row. | **blocked** |
| C-12 | “Most animals live in conditions of [specific welfare assertion].” | Welfare/generalization | Primary species-specific welfare research, population/scope, definition, date. | Separate observed conditions from moral interpretation; avoid universal wording. | blocked until review |
| C-13 | “Death is much closer than you imagined.” | Interpretive/moral thesis | No empirical source as written; must be framed as the project’s interpretation. | Do not imply a tested psychological effect. | candidate editorial line |
| C-14 | “The industry hides this from you.” | Intentionality claim | Evidence of intentional concealment and defined actor/scope. | Not supported by current repository evidence. | **blocked** |
| C-15 | “Over 56,000 locations” | Legacy aggregate claim | Dated release manifest, country/scope, inclusion rules, suppression state. | Must distinguish facilities/records from animals and current from legacy. | blocked until release audit |
| C-16 | “FAOSTAT reports an annual number of animals slaughtered for a defined set of land-animal meat items.” | Observed/statistical-source claim | FAOSTAT **Livestock primary (Global, National - Annual)** normalized bulk release, 2024, Area=World, Element=Producing Animals/Slaughtered. Private retrieval 2026-09-15 from [FAO bulk data](https://bulks-faostat.fao.org/production/Production_Crops_Livestock_E_All_Data_(Normalized).zip); source catalog [FAO catalog](https://data.fao.org/catalog/iso/55375b1e-51d0-47db-ac9b-536ac8a1c738); [FAO methodology](https://files-faostat.fao.org/production/QCL/QCL_methodology_e.pdf). | The 16 selected non-aggregate `Meat of ...` rows (asses, buffalo, camels, cattle, chickens, ducks, geese, goats, mules, other domestic camelids, other domestic rodents, pigs, pigeons/other birds n.e.c., rabbits/hares, sheep, and turkeys), converting `1000 An` to heads, sum to **87,892,277,479 heads in 2024**. Excludes aggregate rows, dairy/egg culls not represented in these meat rows, aquatic animals, non-meat commodities, and categories without a selected 2024 World leaf row. FAO states national values concern slaughter within national boundaries and inputs may be reported, estimated, supplemented, or imputed. This is a selected-scope estimate, not “all animals killed.” | **ready-for-prototype with scope label; not a universal total** |
| C-17 | “The selected 2024 FAOSTAT scope averages about 240.1 million heads per day, or 2,779 heads per second.” | Derived calculation | C-16 exact selected item list and 2024 value. | `daily = 87,892,277,479 / 366 = 240,142,834.64`; `per_second = 87,892,277,479 / (366 * 86,400) = 2,779.43`. Use “modeled average” and explain the 366-day 2024 calendar-year convention; do not call it live or event-timed. | **ready-for-prototype; public release needs maintainer/source review** |
| C-18 | “A separate global aquatic-animal annual range is [X–Y].” | Quantitative estimate | Must use a primary fish/aquatic source with explicit species, wild/captured vs farmed scope, unit, year, and conversion from biomass to individuals. | Biomass-to-individual conversion requires species/size assumptions and should be a range; fish-count methods are not interchangeable with FAOSTAT land-animal heads. | **blocked: no reviewed primary estimate yet** |
| C-19 | “This is comparable to [familiar object/person/lifespan].” | Scale comparison | Comparison denominator must be independently sourced, dated, and commensurate with the same unit and scope. | Avoid comparisons that imply equivalence or certainty; show both original values and conversion. | **blocked pending independent source packet** |

## Required source packet for any numeric claim

Before a quantitative line moves beyond internal prototype, attach:

- primary source URL or artifact ID;
- publication/effective year and retrieval timestamp;
- exact geography, species, category, and inclusion/exclusion rules;
- original unit and any conversion;
- low/high or confidence interval, with method;
- formula and constants used;
- code/configuration version;
- reviewer and review outcome;
- known gaps, likely undercount/overcount direction, and a correction path.

Candidate sources such as FAOSTAT, national competent-authority statistics, and peer-reviewed welfare research are leads only until the exact table/version and license are reviewed. Do not use a source family name as if it were a checked citation.
