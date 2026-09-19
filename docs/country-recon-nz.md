# New Zealand source reconnaissance

Status: reconnaissance only; no row-level records, names, addresses, coordinates, or private artifacts are retained here. This is not publication approval or a healthy live-pipeline claim. Last checked 2026-09-13.

## MPI approved premises and country listings

Primary routes:

- Register index: <https://www.mpi.govt.nz/food-business/meat-game-processing-requirements/meat-industry-registers-and-lists>
- Country-listing search example: <https://www.mpi.govt.nz/export/export-requirements/country-listing-requirements-for-animal-products/search-for-country-listings/country-listings-page?List=87>

The portal exposes market/product-specific lists of approved or listed premises. Depending on the list, fields may include an MPI identifier, premises name, address, operation/type, product, species, and expiry or audit date. Relevant categories include slaughterhouse, boning/cutting, processing, cold store, and related animal-product operations.

No stable public API or bulk URL was verified. MPI pages returned HTTP 403 during automated retrieval. Lists have market-specific scope, overlapping records, and regular updates. Treat disappearance as “not observed,” not closure. Rights and attribution must be confirmed for the specific download/page. Rural/RD and mixed residential/business addresses require privacy and safety review. Do not infer ownership, residence, welfare status, current operation, or activity beyond the source statement.

## Stats NZ Agricultural Production Statistics

Primary metadata: <https://datainfoplus.stats.govt.nz/item/nz.govt.stats/a9908d00-4827-46b2-a38a-310c0c75b029>.

The observed latest metadata described **Agricultural Production Statistics: June 2025 (Final)**, identifier `a9908d00-4827-46b2-a38a-310c0c75b029`, version 2, DDI 3.3, version date `2026-04-08T02:42:33.9384122Z`. This is regional aggregate context, not a named-farm or facility-point source. Coverage includes livestock and farm practices; releases distinguish provisional/final results, census years, sample surveys, confidentiality protections, perturbation, suppression, and imputation.

The metadata states CC BY 4.0 with attribution to Statistics New Zealand and restrictions on misuse of government emblems. A stable statistical table API or bulk endpoint was not verified. A bounded metadata JSON fetch failed with connection refusal; no artifact, bytes, or hash are claimed.

## Readiness block

| Source | Source verification | Private acquisition | Adapter / validation | Terms, privacy, publication | Blocker | Next action |
|---|---|---|---|---|---|---|
| MPI listings | Official routes identified; download/API not verified | Blocked by HTTP 403; no artifact or rows | No adapter or validation | Confirm list-specific terms; screen rural/mixed-use addresses; preserve source origin separately | Portal access, endpoint, licensing, and schema variation | Authorized maintainer confirms permitted route/terms, then stage one bounded artifact with URL, UTC timestamp, hash, size, and version |
| Stats NZ aggregates | Official metadata route and release metadata observed | Local fetch failed; no artifact or hash | No adapter; aggregate data must not become facility points | CC BY 4.0 attribution; protect confidentiality and preserve suppression/perturbation/imputation limits | No verified table/bulk endpoint or reproducible artifact | Confirm official table/API route, privately capture one aggregate artifact, and validate release/version/schema |

## Safety boundary

Neither source is ready for public facility publication. MPI lists may contain precise premises information and require current terms/privacy review. Stats NZ is a contextual aggregate source and must not be transformed into named farms or facility coordinates. Government origin does not establish project review, approval, or current operation.
