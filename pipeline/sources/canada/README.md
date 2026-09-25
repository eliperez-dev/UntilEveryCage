# Canada source adapters

The Ontario adapter consumes delimited text. The CFIA adapter consumes the
current workbook export and supports XLSX directly, plus HTML-table exports
served with an `.xls` filename. Native cell text is retained in
`source_values`; numeric inference, address publication, geocoding, and
federal/provincial merging are intentionally disabled.

For CFIA's current legacy workbook, numbered `CODES_1` through `CODES_10`
columns are interpreted using the official key on the CFIA results page.
Function suffixes are validated per numbered column; export markets and
detained/imported-product inspection remain distinct from production
activities. See the Canada pipeline page for the complete crosswalk and the
documented download/result-page count discrepancy.

Workbook schema is checked against explicit aliases and a header fingerprint.
Missing required columns, duplicate headers, malformed rows, unsupported binary
BIFF `.xls`, and unknown CFIA function codes fail closed or quarantine rows.
Every run preserves the acquired artifact metadata and emits only a private
candidate handoff. A candidate is not approval or publication.
