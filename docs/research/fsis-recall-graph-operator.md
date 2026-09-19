# FSIS recall graph operator slice

This private adapter stages the FSIS Recall API as government-sourced evidence. A recall is represented as a dated public-health action, not as proof of wrongdoing, ownership, or current operation. Raw and parsed records stay in the private run directory; the row-free aggregate manifest is safe for operator metrics only.

The only automatic facility candidate is an explicit establishment number supplied by the source record (or an unambiguous establishment-number token in source text). Firm, address, and name-only matches are quarantined. Candidates remain `review_required`, `private`, and `not_eligible`; there is no public graph projection or release path in this slice.

## Bounded operator query

For a local run, inspect only the aggregate manifest:

```powershell
python -c "import json,sys; m=json.load(open(sys.argv[1])); print({'source_id':m['source_id'],'input_rows':m['input_rows'],'accepted_rows':m['accepted_rows'],'quarantined_rows':m['quarantined_rows'],'candidate_count':m['candidate_count'],'publication_status':m['publication_status']})" .\aggregate-manifest.json
```

This query answers “how many source rows produced private review candidates?” without printing recall firms, products, addresses, or graph payloads. Human review must assess privacy, source terms, contradictory evidence, and the meaning of the recall before any approval or publication work.
