# Italy private review packet

As of 2026-09-15, `it.853-2004` has catalog-linked private acquisition and candidate lifecycle support. `it.1069-2009` remains a separate, unimplemented candidate. Publication is blocked.

- Terms/licensing: the Ministry catalogue indicates Italian Open Data Licence v2.0; attribution and project redistribution review remain open.
- Privacy: addresses, tax identifiers, and precise source coordinates remain in restricted evidence; normalized/API-shaped rows suppress them pending review.
- Completeness: the 853/2004 CSV is only one Ministry scope; by-products, omitted fields, and row-level effective dates are not silently included or inferred.
- Classification: recognition number plus activity code is provisional source identity; repeated pairs quarantine. Source establishment/activity categories and codes are emitted as coverage diagnostics without collapsing them.
- Coverage/lifecycle: invalid dates, missing geography, unknown status, and coordinate precision remain explicit. Source disappearance is not closure; candidate import/API checks are private and test-only.

Evidence: `pipeline/sources/italy/`, `docs/country-recon-it.md`, and `pipeline/tests/e2e/test_italy_candidate_import.py`.
