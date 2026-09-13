# Denmark classification and validation scope

Governed by [ETHICS.md](../../ETHICS.md). Classification inclusion means relevant to scope, not verified truth or permission to publish. Privacy eligibility and review status are separate checks. Preservation/queryability below is limited to authorized access and permitted retention; restricted records are not accessible through optional map filters. See the [policy checklist](../../governance/policy-implementation-todo.md) for enforcement tasks.

## Objective

Determine which Find Smiley businesses are relevant to Until Every Cage’s animal-agriculture map without using classification as destructive cleanup. Classification is a versioned interpretation layer after parsing and normalization. Exceptional privacy redaction/deletion remains a separate process under ETHICS.md.

## Required outputs

1. `category-catalog.json`: every distinct `Smileybranche`, `FVST_branchenummer`, and `FVST_branche` observed in the current artifact, with counts and examples.
2. `classification-rules.yml`: explicit rule IDs, source values/codes, decision (`include`, `exclude`, `review`), mapped activity, species, and rationale.
3. `classified-records.jsonl`: one row per normalized record with rule ID, decision, activity, and classification notes.
4. `classification-report.json`: totals by decision, category, rule, coordinate status, and unmapped/unknown values.
5. `review-queue.jsonl`: records or categories requiring human judgment, with source URLs and preserved source fields.

## Decision model

Use three decisions rather than a boolean:

- `include`: evidence supports relevance to the current map scope.
- `exclude`: the business is outside the current scope, such as ordinary restaurants or general retail without a qualifying activity.
- `review`: the category or record cannot be classified safely from the available evidence.

Classification must be based on official activity codes and labels first, with name text used only as a review signal. Never infer slaughter, farming, or processing solely from a business name. A general food register is not evidence that every business handles animals.

## Initial category review

Generate the complete category catalog from the fresh XML and review categories in descending record count. Start with likely relevant categories such as slaughterers, meat products, fish and shellfish, dairy products, egg products, animal by-products, and aquaculture. Keep adjacent categories—restaurants, general grocery, transport, packaging, and cold storage—separate until their relevance and intended map scope are explicitly decided.

For each category, record:

- exact source code and labels
- record count
- representative source URLs
- likely activity mapping
- whether it is a physical facility or a business/service category
- inclusion decision and rationale
- reviewer and decision date

## Validation rules before classification release

- Required source key must be present and unique within the artifact.
- Country is Denmark by source context; do not invent a region value.
- Postal codes remain strings to preserve leading zeroes.
- Dates are parsed to ISO only when unambiguous; original values remain available.
- Coordinates are currently absent in this source and must remain unresolved.
- Every classified record links to the source artifact hash and source URL when available.
- Unknown or newly introduced categories fail review rather than defaulting to inclusion or exclusion.
- Record-count changes between source runs produce a diff report before classification rules are applied.

## Implementation sequence

1. Build the category catalog from the current normalized staging file.
2. Review and approve the category decision table before classifying all records.
3. Implement deterministic rules with rule IDs and a ruleset version.
4. Generate classified output and review totals.
5. Sample records from every included category and every review category.
6. Freeze the first classification ruleset and preserve it with the release metadata.

## Acceptance criteria

The classification stage is complete when every observed category has an explicit decision, every included record has a rule ID and activity mapping, every excluded/reviewed record remains queryable, the result is deterministic on rerun, and a reviewer can move from any decision to the normalized record, source URL, raw artifact checksum, and rule rationale.

Classification does not imply geospatial accuracy. Coordinate enrichment remains a later stage and must preserve unresolved locations until a separately documented geocoding process succeeds.
