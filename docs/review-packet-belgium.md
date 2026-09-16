# Belgium private review packet

As of 2026-09-15, Belgium has a private two-artifact FASFC operator/codebook lifecycle with synthetic schema fixtures. No real operator rows are retained in Git and publication is blocked.

- Terms/licensing: CC BY 4.0 is indicated by data.gov.be; FASFC attribution, last-update labeling, non-misleading use, and project publication review remain required.
- Privacy: address, postal, enterprise, and coordinate values stay in restricted source evidence; normalized rows suppress them and geocoding is disabled.
- Completeness: the operator feed represents current FASFC registrations/approvals/authorizations, not every animal-agriculture facility or every slaughterhouse.
- Classification: the LAP/PAP codebook join is exact; slaughter, cutting, processing, storage, animal-by-products, and export remain distinct source categories. Ambiguous/repeated codes quarantine.
- Coverage/lifecycle: operator and activity-code artifacts must be captured together; the live operator header was not available in this environment. Missing rows are `not-observed`, never closure.

Evidence: `pipeline/sources/belgium/`, `docs/country-recon-be.md`, and `pipeline/tests/e2e/test_germany_belgium_candidate_import.py`.
