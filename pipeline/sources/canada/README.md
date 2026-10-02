# Canada source adapters

The Ontario adapter consumes delimited text. The CFIA adapter consumes the
current workbook export and supports XLSX directly, plus HTML-table exports
served with an `.xls` filename. Native cell text is retained in
`source_values`. The normalized private handoff preserves facility address
fields for shared later enrichment, excludes phone/contact fields from
geocoding queries, and keeps Ontario's validated source points with
`source-provided` precision. Coordinates are used before address enrichment;
records without a usable point enter the provider-neutral queue. No adapter
calls an external geocoder. Federal/provincial merging and publication remain
separate decisions.

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
candidate handoff plus the shared provider-neutral geocode queue. Queue
generation is synchronous staging only and makes no provider calls. A candidate
is not approval or publication.
