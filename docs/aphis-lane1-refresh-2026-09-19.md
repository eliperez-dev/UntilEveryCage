# APHIS lane 1 refresh — 2026-09-19

This lane captured current APHIS Animal Care Public Search Tool exports through the documented `Export To CSV` control in an authorized browser session. Raw source and derived artifacts remain in the restricted APHIS handoff and are excluded from Git; exact storage locations and hashes remain in the private evidence manifest.

No public release, database import, facility merge, geocoding, or approval claim was made.

## Annual reports

- Route: `https://efile.aphis.usda.gov/PublicSearchTool/s/annual-reports`
- Query: year `2025`; selected `View Annual Reports`; provider display `995`; 100 rows per page.
- Capture: 10 original page CSV artifacts retained privately; 9 pages of 100 and a final page of 95; 995 rows reconciled to the provider total.
- Lineage input is private and built with `pipeline.sources.us.aphis.capture.build_lineage_csv`; the original-page row sequence is preserved and all 995 rows carry page hash, page ordinal, page row, byte size, and source URL lineage in restricted evidence.
- Adapter result: 995 normalized, 0 quarantined; the authoritative lineage handoff is private and recorded in the restricted evidence manifest.
- Combined-input and normalized hashes are recorded in the private handoff manifest.
- Lineage and normalized hashes are recorded in the private handoff manifest.

The earlier FY2025 `View Registrants` export was not treated as annual-report evidence. It is preserved separately in restricted evidence for provenance and is not the annual-report processing input.

## Current research-facility registrations

- Route: `https://efile.aphis.usda.gov/PublicSearchTool/s/inspection-reports`
- Direct all-states attempt: 21 original page CSV artifacts were retained before the official UI stopped returning the next partition. Pages 22–26 remain recorded as failed/missing in the private capture manifest; this attempt is preserved as incomplete and is not the recovery input.
- Recovery route: the supported `State` filter was selected separately for each of the 52 observed state/territory options, with `View Registrants` and `Export To CSV`. The retained originals and state/filter/page/global-capture metadata remain in restricted evidence.
- Recovery reconciliation: 59 original CSVs, 2,552 rows, 2,552 unique `(Customer Number, Certificate Number)` keys, one consistent header, and zero duplicate keys. The state-filter union totals exactly match the provider display of 2,552, and all 2,100 rows from the preserved direct attempt overlap the recovered union by source-native key.
- Lineage input is private and built with `pipeline.sources.us.aphis.capture.build_lineage_csv`; the 59 original pages remain mapped by global capture ordinal, while state and within-state page metadata remain in the restricted capture manifest.
- Adapter result: 2,552 normalized, 0 quarantined; the authoritative lineage handoff is private and carries lineage on all 2,552 rows.
- Combined-input and normalized hashes are recorded in the private handoff manifest.
- Lineage and normalized hashes are recorded in the private handoff manifest.

The recovered union is a complete reconciliation of the observed official APHIS state-filter result sets, not a facility-master, factual-review, privacy-eligibility, approval, or publication claim.

The FY2025 `View Registrants` snapshot accidentally captured from the annual-reports route is preserved in restricted evidence, but its derived combined file is invalid: one page has a different inspection-report schema, producing a 995-source-row/984-derived-row mismatch. It is documented in the private disposition record and excluded from processing.

All other browser downloads, including delayed and cross-profile exports, remain in restricted evidence and were not silently discarded or assigned to a page.

## Governance and limitations

The handoffs remain `private-candidate`, `review_required`, and publication-blocked. APHIS public-search origin does not establish factual review, privacy eligibility, project approval, or publication permission. Names, business addresses, status dates, and animal-use values remain restricted source evidence pending the project’s review and rights checks. Missing years or records are not interpreted as closure or non-use.
