# D5 real-corpus graph connection analysis

`pipeline.common.d5_connection_analysis` is the row-free analysis boundary for
the D5 real-corpus rehearsal. It can inspect checked-in aggregate manifests and
restricted local JSONL handoffs, but only aggregate metrics and hashed review
tokens may be written to a report.

It does not create a release, import a database, merge identities, transfer
claims, geocode, or publish. Exact source-native identifiers create
review-required deterministic evidence. Multi-signal matches create
review-required probabilistic candidates. Neither result is a canonical
identity or a publication decision.

## Run against aggregate manifests

```powershell
python -m pipeline.common.d5_connection_analysis `
  --manifest data/manifests/current-reacquisition-2026-09-16.json `
  --manifest data/manifests/current-canada-private-2026-09-17.json `
  --output data/manifests/d5-real-graph-analysis-20260921.json
```

Checked-in manifests contain counts and provenance metadata only. They cannot
prove row-level graph connections, so the resulting report explicitly shows
that no private rows were supplied.

## Run with restricted handoffs

The operator may supply one or more private normalized or graph-candidate
JSONL paths. Paths must remain outside Git and should normally live on the
private evidence volume:

```powershell
python -m pipeline.common.d5_connection_analysis `
  --manifest D:\UEC-private\d5\aggregate-manifest.json `
  --rows dk.smiley=D:\UEC-private\d5\dk\normalized\records.jsonl `
  --rows it.853-2004=D:\UEC-private\d5\it\normalized\records.jsonl `
  --rows ca.cfia.federal-meat=D:\UEC-private\d5\ca\graph-candidates.jsonl `
  --output D:\UEC-private\d5\reports\graph-analysis.json
```

The current handoff reader accepts normalized adapter rows and graph-candidate
rows. It retains source IDs, compact identifiers, signal presence, dates, and
relationship counts in memory only. It never copies `source_values`, names,
addresses, coordinates, phones, or emails into the report.

## Connection rules

The analyzer records these real-data checks when the corresponding handoff
fields exist:

- repeated source-native facility and organization identifiers;
- FSIS observation-to-establishment exact-ID evidence;
- APHIS certificate/customer exact-ID evidence, kept as evidence events;
- Italy VAT/fiscal-code organization candidates;
- Denmark CVR facility-to-organization candidates;
- explicit CFIA operator/regulator relationships emitted by the adapter;
- duplicate/collision, orphan, quarantine, suppression, provenance, and date
  inconsistency counts.

Probabilistic candidates require at least two compatible normalized signals,
such as name+postal, name+city, or name+address. Their report entry contains
only a digest, source pair, method, confidence band, contributing feature
names, ruleset, and disclaimer. The candidate remains `review_required`, with
`automatic_merge=false` and `transfers_claims=false`.

APHIS and FSIS remain separate source kinds. The analyzer reports both
`aphis_fsis_automatic_links=0` and `aphis_fsis_review_candidates=0`; no
evidence-only APHIS observation is treated as a facility or cross-source
identity.

## Review packet and limitations

The row-free `review_packet` section deterministically samples candidate
digests using:

```text
sha256(source_id|source_record_key|d5-multi-signal-candidates-v1)
```

An authorized reviewer can use those digests against the restricted handoff
without exposing rows in Git or in an aggregate report. Until that review
occurs, precision and recall are explicitly `unmeasured`; synthetic controls
must not be used as real-data accuracy estimates.
