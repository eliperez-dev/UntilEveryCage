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
