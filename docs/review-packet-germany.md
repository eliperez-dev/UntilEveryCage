# Germany private review packet

As of 2026-09-17, Germany uses the typed BLtU adapter and assisted/private refresh against a current public general-list CSV export. No release, geocode, or public API exposure is allowed.

- Terms/licensing: BVL documents public access/export, but dataset-specific reuse and redistribution terms require named human confirmation.
- Privacy: facility addresses may overlap residences or identify people; addresses and coordinates stay private and geocoding is disabled.
- Completeness: BLtU covers the approved 853/2004 list, not all animal-agriculture facilities. Export effective date and currentness are run-specific.
- Classification: only pinned SH/CP mappings are accepted; unmapped activities, missing identity, duplicate approval IDs, and physical schema drift quarantine.
- Coverage/lifecycle: the ordinary public form flow and session/request-specific export URL are recorded per run. The current run reconciles 15,788 input rows into 2,691 normalized and 13,097 quarantined rows. Missing rows are `not-observed`, never closure.

Current row-free run evidence: `data/manifests/de-be-private-candidates-2026-09-17.json` and the private lifecycle sidecars under ignored `data/staging/de.bltu/20260917T000000Z-v3/`. Adapter/sidecar tests are in `pipeline/sources/germany/`; the existing candidate-import E2E remains synthetic/test-only.
