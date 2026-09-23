# Belgium private review packet

## Operator terms decision

The human operator explicitly approved restricted private processing of the
FASFC operator list and its LAP/PAP activity-code catalogue, with these
conditions: only carefully selected animal-related categories may ever feed a
public map; attribute FASFC and the source's latest-update date; avoid
misleading presentation and any implication of FASFC endorsement; minimize
possible natural-person fields; and report source activity observations
separately from deduplicated facility candidates. This is recorded in the
canonical approved terms-review record at
`data/terms-reviews/be.locations.json`. This is project authorization, not
legal advice or a legal determination about all third-party rights.

Official routes are the [FASFC Open Data page](https://www.foodweb.favv-afsca.be/professionelen/praktisch/opendata/),
the [operator dataset catalogue](https://data.gov.be/en/datasets/favv-afsca-operators),
the [activity-code catalogue](https://data.gov.be/en/datasets/fasfc-activity-codes),
and the direct files `inter_actieve_actoren_EN.csv` and
`inter_PAP_omschrijving_EN.csv` on the official static FASFC host. The
catalogue indicates CC Attribution 4.0. That indication and the operator's
project decision do not guarantee privacy, personality, database, or other
third-party rights beyond the stated reuse terms.

## Implemented pipeline boundary

The canonical command in `pipeline/sources/belgium/README.md` acquires the two
official artifacts together, stores each immutably with hash/provenance and
HTTP update metadata, validates the pinned header fingerprints, parses the
CSV (including CP1252), quarantines invalid/duplicate/unresolved rows, joins
the official codebook, normalizes privately, and can insert source-scoped
candidate observations into a marked loopback disposable database. Repeated
identical candidate evidence is idempotent in the shared graph-import layer.

Animal scope uses explicit official PAP IDs and their exact place/activity/
product code signatures allowlisted from the official codebook; descriptions
are not used to infer scope. This is a
narrow project classification, not an official FASFC animal-facility category
and not a completeness claim. Unknown labels do not count as in-scope.
Activity observations, out-of-scope rows, quarantines, and unique
source-scoped establishment identifiers remain separate measures.

Names, operator/approval numbers, addresses, postcodes, and coordinates are
excluded from normalized and candidate-handoff records. Raw source bytes are
retained only under ignored restricted private storage. Municipality is kept
as coarse context; no geocoding is performed. A natural person's establishment
record may still be identifiable by the source-native establishment ID in the
private database, so private access and retention review remain necessary.

## Readiness and limits

This adapter's public-surface state remains blocked. FASFC's operator list
covers operators with current FASFC registration/approval/authorization and
their LAP/PAP observations; it is not a census of animal facilities or
slaughterhouses. Source update metadata and artifact hashes are row-free
readiness evidence, not source-validity or publication claims. The public map
must not expose operator identifiers or source rows. Any release needs separate
review of codebook coverage, category selection, privacy/safety, attribution
and latest-update rendering, factual interpretation, and a release decision.
