# France DGAL Sections I and II private preview

Sections I (`fr.dgal.section-i`, domestic ungulates) and II
(`fr.dgal.section-ii`, poultry and lagomorphs) are separate source identities.
The Ministry's current 853/2004 page links each TXT file and says the lists are
updated daily. Each run downloads the selected section directly, retains the
original restricted artifact and acquisition metadata, validates the current
schema, quarantines malformed or unclassified rows, normalizes accepted
observations, and atomically imports the exact handoff into the local private
preview database.

One scheduler-safe command refreshes one source and updates the map's database
in one run:

```text
python scripts/real_preview.py refresh --source fr.dgal.section-i
python scripts/real_preview.py refresh --source fr.dgal.section-ii
```

The Ministry source page states daily updates, so source operations schedule a
daily check. The source lock, bounded retries, run ledger, schema checks, and
atomic importer apply to both commands. A failed fetch or schema change stops
the run without a stale or fixture replacement. Re-running an identical source
snapshot is an idempotent database import.

## Terms and attribution evidence

The current [Ministry DGAL page](https://agriculture.gouv.fr/liste-des-etablissements-agrees-ce-conformement-au-reglement-ce-ndeg8532004-lists-ue-approved)
links the two [Section I](https://fichiers-publics.agriculture.gouv.fr/dgal/ListesOfficielles/SSA1_VIAN_ONG_DOM.txt)
and [Section II](https://fichiers-publics.agriculture.gouv.fr/dgal/ListesOfficielles/SSA1_VIAN_COL_LAGO.txt)
files and states that the lists are updated daily. The Ministry's
[legal notice](https://agriculture.gouv.fr/mentions-legales) permits reuse of
information or data not covered by copyright for non-commercial purposes,
subject to preserving the integrity of reproduced material and citing the
Ministry; commercial or advertising reuse requires prior permission. Neither
the linked TXT files nor the 853/2004 page currently states a separate
file-specific licence. Per-source evidence is retained in
`data/terms-reviews/fr.dgal.section-i.json` and
`data/terms-reviews/fr.dgal.section-ii.json`. The evidence authorizes bounded
non-commercial acquisition and private preview under the Ministry notice; it
does not claim legal certainty or approve a public release. Attribution names
the Ministry/DGAL, section, source URL, and retrieval/update timestamp.

## Geography and privacy

The source handoff supplies commune, postal code, and department, not facility
coordinates. For display only, the importer acquires commune centre points from
[geo.api.gouv.fr's administrative divisions API](https://geo.api.gouv.fr/decoupage-administratif/communes).
The endpoint response, retrieval metadata, source and derived hashes, API
version, and current reference fingerprint are retained privately. Its
underlying IGN Admin Express COG dataset is published with the
[Licence Ouverte 2.0](https://www.data.gouv.fr/datasets/admin-express-admin-express-cog-admin-express-cog-carto-admin-express-cog-carto-plus-pe).
Resolution uses exact normalized commune name plus the source department code;
homonyms and unresolved names remain unmapped and counted. Display geometry is
always `city_reference_approximate`, an approximate commune centre, never a
facility point.

Addresses and SIRET values remain only in restricted evidence. Name, duplicate,
category, and cross-approval identity reviews remain open; a listed observation
does not prove that a facility is operating. No public rows or release membership
are created by this preview pipeline.
