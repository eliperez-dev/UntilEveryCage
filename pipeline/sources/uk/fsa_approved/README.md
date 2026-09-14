# FSA England, Wales and Northern Ireland approved establishments

This adapter is synthetic-fixture-only. Its CSV columns and authority/nation
mapping are explicit test assumptions, not an inferred live FSA artifact
schema. FSS Scotland remains a separate source and adapter; no FSS records or
configuration are merged into this capability.

The adapter preserves every source cell and identifier string, including
leading zeroes, and emits no guessed coordinates. Establishment IDs are
unique only within a nation, allowing authority datasets to be isolated even
when identifiers repeat across nations. Authority/nation mismatches, schema
drift, duplicate or missing IDs, unknown activities/statuses, malformed rows,
remarks and privacy-risk addresses are quarantined or fail closed.

## FSA-specific acquisition gates

Before any acquisition, a maintainer must verify separately for England,
Wales and Northern Ireland: the current artifact URL and format, publication
and effective dates, FSA/department ownership, terms/licence, attribution
requirements, update automation/rate limits, raw-artifact retention and
removal rules, and whether the source permits redistribution. No live schema,
download, automation, geocoding, release, public API/export, or external
contact is authorized by this fixture contract. Privacy/suppression review,
human factual review, project approval and publication remain independent
gates.
