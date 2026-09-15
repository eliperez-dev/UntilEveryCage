# Aggregate statistics evidence specification

Status: v1 private-validated contract; not a publication approval.

## Purpose and boundary

Aggregate statistics are versioned evidence objects, separate from facilities and their observations. A statistic can describe a population, place, period, and unit without asserting that any facility in the map produced a particular number of animals. It is not permissible to allocate a national or global total to nearby facilities without facility-specific evidence.

The contract is designed for a dated annual edition. It preserves source values and source item names alongside project interpretations. Unknown, unavailable, approximate, unresolved, and qualitative uncertainty remain explicit rather than being converted into a fabricated range.

## Required object shape

Each `statistics[]` entry in `aggregate-statistics-catalog-v1` contains:

| Field | Required meaning |
| --- | --- |
| `statistic_id`, `version_id`, `status` | Stable identity, immutable version identity, and `validated-private` until an authorized release approves publication. |
| `source` | Publisher, dataset name, source origin, dataset URL, and license. Source origin is not review or approval. |
| `population_scope` | `scope_id`, named included populations, animal class, activity, and a scope note. |
| `geography` | Geography level and source-compatible area name. |
| `period` | Period kind and inclusive start/end dates; annual editions also carry `calendar_year`. |
| `unit` | Kind, display name, numerator, denominator, and scale. Counts are heads/animals, not mass. |
| `estimate` | `central` plus optional `low`/`high`; bounds must satisfy low ≤ central ≤ high. Missing bounds mean no numeric interval is published. |
| `method` | Direct, converted, or derived method, with a plain-language description and formula. |
| `components` / `aggregation` | Optional source rows, unit conversions, overlap assessment, and reconciled sum for derived aggregates. |
| `exclusions` | Explicit exclusions, including populations, products, periods, and rows omitted to prevent double counting. |
| `uncertainty` | Named uncertainty kind and statement. FAO flags and coverage limits are not a confidence interval. |
| `provenance` | Private artifact ID/path, checksum, byte size, retrieval timestamp, effective/publication dates, retrieval URL, code/config versions, and public-artifact flag. |
| `revision` | Revision ID, released date, superseded version when any, and change note. New source revisions create new entries. |
| `citations` / `citation_ids` | HTTPS citations with title, locator, access date, and explicit references from the entry. |

Validation is implemented in [`pipeline/statistics/catalog.py`](../../pipeline/statistics/catalog.py) and exercised by synthetic fixtures. It rejects missing dimensions, invalid dates, non-whole converted counts, non-reconciled component totals, repeated overlap groups, missing citations, insecure URLs, missing revision metadata, numeric ranges without bounds, and ambiguous publication status.

## Selected land-animal edition

The first private catalog entry is `land-animals-slaughtered-for-meat-world-2024`, based on FAOSTAT's `Livestock primary (Global, National - Annual)` domain and its normalized bulk archive. The selection is:

- Area: `World`.
- Year: 2024 calendar year.
- Element: `Producing Animals/Slaughtered`.
- Rows: the 16 named, non-aggregate `Meat of ...` item rows with head-based units.
- Conversion: rows reported as `1000 An` are multiplied by 1,000; rows reported as `An` are kept as heads.
- Result: **87,892,277,479 heads**, a source-backed selected-scope estimate.

The result is not “all animals killed for food.” It excludes aggregate rows, aquatic animals, dairy/egg culls not represented in these meat rows, non-meat commodities, and categories without a selected 2024 World leaf row. FAO explains that source values may be reported, estimated, supplemented, or imputed and are flagged accordingly; the catalog therefore carries qualitative uncertainty and no invented low/high interval.

The raw archive is retained in ignored local storage at `data/raw/animal-scale/faostat-qcl/`. The tracked manifest records its SHA-256 checksum, byte size, retrieval timestamp, source URLs, effective date, revision, and citations. Raw data is not a repository fixture or public artifact.

## Aquatic animals: separate later integration

Aquatic animals remain a separate statistic family. Do not add fish, crustaceans, molluscs, or other aquatic estimates to the land-animal head count. Candidate aquatic work must first identify:

1. wild capture versus farmed populations;
2. species or taxonomic groups and geographic coverage;
3. year/period and whether the source reports biomass, landed weight, harvest weight, or individuals;
4. the size/weight distribution and conversion method if biomass is converted to individuals;
5. numeric ranges and sensitivity to the conversion assumptions; and
6. discard/bycatch treatment and overlap with any farmed or slaughtered category.

Integration, if later approved, should be a derived edition with two visibly separate panels and a reconciliation table. The land and aquatic source records remain independently citable; a combined display must show both ranges, the formula, the conversion assumptions, and the fact that uncertainty is not additive in a simple precise way. If conversion assumptions are too broad, present parallel land and aquatic stories rather than a combined number.

## Publication gate

`validated-private` means the object passed machine validation and source review in private staging. It does not mean project-approved or project-published. Before public copy, an authorized reviewer must record a scoped approval for the named story edition, confirm the source terms, verify the exact selected rows and checksum, review the exclusions and uncertainty wording, and attach a correction/version-history path. A later source revision must never silently rewrite an earlier edition.
