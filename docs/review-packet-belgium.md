# Belgium private review packet

As of 2026-09-17, Belgium has a private two-artifact FASFC operator/codebook lifecycle validated against a current official pair. No real operator rows are retained in Git and publication is blocked.

- Terms/licensing: CC BY 4.0 is indicated by data.gov.be; FASFC attribution, last-update labeling, non-misleading use, and project publication review remain required.
- Privacy: address, postal, enterprise, and coordinate values stay in restricted source evidence; normalized rows suppress them and geocoding is disabled.
- Completeness: the operator feed represents current FASFC registrations/approvals/authorizations, not every animal-agriculture facility or every slaughterhouse.
- Classification: the LAP/PAP codebook join is exact; slaughter, cutting, processing, storage, animal-by-products, and export remain distinct source categories. Ambiguous/repeated codes quarantine.
- Coverage/lifecycle: operator and activity-code artifacts were captured together. The live operator feed is cp1252 CSV with an identifier/activity-only schema and repeated source observations; exact duplicates quarantine, while distinct rows sharing an establishment/activity key remain separate. Missing rows are `not-observed`, never closure.

Current row-free run evidence: `data/manifests/de-be-private-candidates-2026-09-17.json` and the private lifecycle sidecars under ignored `data/staging/be.fasfc/20260917T000000Z-v3/`. Adapter/sidecar tests are in `pipeline/sources/belgium/`; the existing candidate-import E2E remains synthetic/test-only.
