# Germany private review packet

As of 2026-09-15, Germany uses the typed BLtU adapter and assisted/private refresh. No release, geocode, or public API exposure is allowed.

- Terms/licensing: BVL documents public access/export, but dataset-specific reuse and redistribution terms require named human confirmation.
- Privacy: facility addresses may overlap residences or identify people; addresses and coordinates stay private and geocoding is disabled.
- Completeness: BLtU covers the approved 853/2004 list, not all animal-agriculture facilities. Export effective date and currentness are run-specific.
- Classification: only pinned SH/CP mappings are accepted; unmapped activities, missing identity, duplicate approval IDs, and physical schema drift quarantine.
- Coverage/lifecycle: the portal export URL is session/request-specific and must be recorded per run. Missing rows are `not-observed`, never closure.

Evidence: `pipeline/sources/germany/`, `pipeline/germany/bltu_adapter.py`, and `docs/germany-source-assessment.md`.
