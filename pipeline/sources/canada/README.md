# Canada source adapters

The Ontario adapter consumes delimited text. The CFIA adapter consumes the
current workbook export and supports XLSX directly, plus HTML-table exports
served with an `.xls` filename. Native cell text is retained in
`source_values`; numeric inference, address publication, provider selection,
and federal/provincial merging are intentionally disabled. Accepted Canadian
records without source coordinates get a private provider-neutral geocode
queue. It stores only the address query and source reference, excludes names
and phone fields, and remains pending until geocoder terms and privacy review;
the adapter never calls a geocoder.

For CFIA's current legacy workbook, numbered `CODES_1` through `CODES_10`
columns are interpreted using the official key on the CFIA results page.
Function suffixes are validated per numbered column; export markets and
detained/imported-product inspection remain distinct from production
activities. See the Canada pipeline page for the complete crosswalk and the
documented download/result-page count discrepancy.

Workbook schema is checked against explicit aliases and a header fingerprint.
Missing required columns, duplicate headers, malformed rows, unsupported binary
BIFF `.xls`, and unknown CFIA function codes fail closed or quarantine rows.
Every run preserves the acquired artifact metadata and emits a private
candidate handoff plus a restricted geocode queue. Queue generation is
synchronous staging only; asynchronous provider work remains separate and
blocked pending provider review. A candidate is not approval or publication.
