# UK approved-establishments country composition

This layer consumes restricted normalized outputs from the distinct FSS
Scotland and FSA England/Wales/Northern Ireland adapters. It keeps the source
record and its complete source run manifest nested under each composed row;
source IDs, nation, authority, source-specific lifecycle, terms state and
review state are never flattened or overwritten.

No records are automatically merged across FSS/FSA or across nations. A
possible-match review signal is emitted only for an exact normalized trading
name and postcode match across different sources and nations, and carries
references to both records rather than combining them. Suppression is keyed
by `(source_id, source_record_id)` and therefore survives reimport without
silently suppressing a similarly numbered record from another jurisdiction.

The composition manifest is always `release_state: not-created` and
`candidate_created: false`. Unconfirmed terms or incomplete project review
block any candidate/release state. Missing or failed source outputs and
incompatible adapter schema versions fail closed before replacing a prior
view. This is restricted review infrastructure only: no downloads, farms,
geocoding, public API/export, promotion, or release is performed.
