# Private graph persistence boundary

`graph_persistence.py` is the D4 adapter-to-graph boundary. It accepts only a
validated private handoff and only a loopback disposable database carrying the
exact `uec-e2e-disposable-v1` marker. It returns aggregate counts and never
prints or returns row payloads.

Facility graph candidates and evidence-event handoffs use separate entrypoints:

```python
from pipeline.common.graph_persistence import import_graph_candidates
import_graph_candidates(url, candidate_handoff, disposable_db=True)
```

```python
from pipeline.common.graph_persistence import import_evidence_events
import_evidence_events(url, evidence_handoff, disposable_db=True)
```

The facility sink materializes source-qualified facility/organization
projections, source identifiers, claims, relationships, and source-scoped
crosswalk candidates. It never creates a universal identity. The evidence sink
stores event payloads and source-scoped linkage candidates separately; it never
creates a facility. All imported rows default to private, review-required,
privacy-pending, and not eligible for publication.

Each handoff is content-addressed. Batches commit independently, so an
interrupted run can be retried without duplicating rows. The public graph views
remain empty until a separate human-gated release process creates a promoted
release; this importer cannot do that.

For explicitly configured private working targets, use
`pipeline/scripts/maintenance/materialize-private-graph.py` with
`UEC_GRAPH_DATABASE_URL`, `UEC_GRAPH_DATABASE_NAME`, and
`UEC_GRAPH_DATABASE_PURPOSE=private-graph-materialization-v1`. The command is
limited to a loopback database whose exact name matches the configured
private target. Its database role must have the graph table grants required by
the shared importer and no write privileges on other `uec` tables. The
original disposable importer and its marker guard remain unchanged. This
command persists private evidence only; it does not alter release membership,
privacy, factual review, approval, or public projections.

Where a source record has exactly one match in the latest promoted official
public-discovery projection, its private graph facility endpoint is bound to
that canonical facility UUID and approved source-record ID. The Italy 853/2004
adapter's current candidate key differs from the approved snapshot's historical
key, so its bounded append-only binding phase requires the same source ID and
raw artifact plus a one-to-one native recognition-number/activity-code pair
on both the candidate and selected release sides. It copies existing private
identifier assertion state unchanged and never modifies review, privacy,
rights, release, or publication state. Repeated candidate pairs, missing
matches, and ambiguous release mappings remain private and are reported as
aggregate counts; they are not guessed into a public endpoint. The API still
rechecks the selected release and live suppression gates on every request.

Public edge projection also requires versioned support references: each
supporting reference carries its exact `source_record_id` and must resolve to
a direct selected-release record or to an exact row in
`uec.graph_record_release_bindings`. The binding table is projection metadata,
not an approval decision; it is insert-only for the graph writer and read-only
for the API role. The API rechecks source/artifact congruence and current
canonical-record eligibility. An entity identifier shared across records is
not sufficient evidence for publishing an edge.

Compact matcher candidates may use the normalized field key
`establishment_id` for blocking. Before persistence, facility endpoints for
sources in `graph_source_mapping.FACILITY_IDENTIFIERS` are typed with that
source's declared native identifier type. The source ID and identifier value
are preserved exactly; organization endpoints, already-native types, and
unmapped sources are unchanged. This is a source-local field mapping, not a
cross-source identifier equivalence. Corrected endpoint representations use
new edge keys, leaving earlier private rows intact as history.

For already-retained inferred edges created before that boundary normalization,
`_repair_generic_facility_endpoint_types` appends the corrected typed
representation without rerunning matching. It requires both ordered support
references to resolve exactly by source, native record key, and artifact SHA
through either the direct selected-release record/facility map or an exact
private-to-canonical release binding; each support must resolve to one
canonical facility. Each generic endpoint must also match exactly one mapped
native identifier on that same canonical facility. It
does not change endpoint values, support references, relationship semantics,
or prior edge rows. Unmapped, ambiguous, stale-artifact, and non-current
release cases remain unchanged.

The Italy D6 matcher normalizes identifiers for comparison, but persisted
facility endpoint keys must retain the adapter's native identifier spelling.
The materializer therefore stores native endpoint values while keeping
normalized values confined to matching signals. Its bounded repair mode
appends a deterministic native-key representation only when both ordered
support refs resolve through the current release binding and each exact
canonical record has one same-facility native assertion matching under the
documented D6 normalization. It retains the old malformed private edge as
history; repaired rows are replacement representations of existing candidates,
not new discoveries. Repeated repair is idempotent. In the controlled Italy
snapshot, 148 of 273 inferred rows have complete versioned support for this
repair; the remaining 125 are unbound and are left unchanged and ineligible.
