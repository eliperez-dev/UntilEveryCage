# FSS Scotland approved establishments

This source-first adapter is synthetic-fixture-only. It accepts caller-supplied
CSV bytes and never downloads, geocodes, promotes, publishes, exports, or
contacts FSS/FSA. It preserves source cells and approval IDs as strings,
including leading zeroes, while representing absent coordinates as `null`.

Rows with duplicate or missing approval IDs, missing/unknown activities,
unknown statuses, malformed cells, remarks, or privacy-risk address tokens are
quarantined. Header and row-shape drift fails closed. Every run records a
checksum, byte size, source metadata, adapter/schema versions, counts, and
the explicit human-gated/non-release state.

Before acquisition, a maintainer must verify the current FSS artifact URL,
schema, publication/effective date, licence and attribution terms in an
approved environment. England/Wales FSA and Northern Ireland sources require
separate evidence and adapters. Privacy/suppression review, human factual
review, project approval, release authorization, and any legal/terms decision
remain gates; no real artifact or facility record belongs in this repository.
