# Germany BLtU source assessment

This document owns source research and field interpretation. Current counts and
readiness live only in [source-status.json](source-status.json). Private retrieval
and processing have a scoped [terms record](../pipeline/sources/germany/terms-review.json);
public redistribution rights remain unresolved.

## Source identity and scope

The BVL’s official cross-border-trade page identifies the BLtU database as the list
of establishments approved under Regulation (EC) 853/2004 and says the lists include
company address, approval number, and approved activities/species. It also says the
lists are continuously updated. See the [BVL scope page](https://www.bvl.bund.de/DE/Arbeitsbereiche/01_Lebensmittel/01_Aufgaben/05_GrenzueberschreitenderHandel/lm_grenzueberschrHandel_basepage.html).

The [BVL data portal](https://gis.bvl.bund.de/datenportal/) describes the data as
authority-provided material, says tabular data can be exported as CSV or Excel, and
identifies BVL/BKG attribution notices for portal geodata. The portal’s export
capability supports a reproducible acquisition design, but it does not by itself
establish permission to redistribute the exported establishment records.

The stable entry route is [BVL BLtU](https://www.bvl.bund.de/bltu); the BVL portal supports selecting and exporting the current general or category list. Session-bound export URLs must be captured as run-specific provenance, not checked in as a source URL.

The existing V1 Germany adapter is [`static_data/de/migrate_data.py`](../static_data/de/migrate_data.py),
which references the BLtU publication endpoint and expects downloaded/merged CSVs.
Its current behavior also performs external geocoding and emits a wide source-shaped
CSV; V2 must not reuse those behaviors without a reviewed, deterministic replacement.

## Terms and risk decision

The official pages located for this assessment document public access and export, but
do not present a clear license or redistribution grant for the establishment-record
export. The private acquisition authorization does not settle source permissions
or public redistribution. Establish:

1. whether automated retrieval is permitted, including rate/frequency limits;
2. whether local research retention of the raw export is permitted;
3. whether transformed establishment records may be redistributed in a public
   non-commercial project under the project’s data license/attribution model; and
4. required attribution, notices, update/deletion obligations, and any restrictions
   on address, approval-number, or activity/species fields.

This is a terms uncertainty, not a claim that the source prohibits use. Retain the
stable landing route, session navigation, exact private export URL, response
metadata, bytes and checksum. Acquisition is not publication authorization.
Privacy/safety review is separately required because facility addresses can overlap
with residences or identify individuals; source origin does not resolve that risk.

## 2026-10-25 public export verification

The public BLtU workflow was exercised through its ordinary session navigation:
the landing page's “Weiter ohne JavaScript” action opened the start page, and the
“Generalliste” action opened the table. Its CSV export control returned HTTP 200
(`application/csv`); the private capture is retained at
`D:\\UntilEveryCage-Operations\\source-captures\\de-launch-20261025` with SHA-256
`6dfb981a0927cebf5de5b0bd7de5debb180b1df2d633bb9becfd12c5439ab0d2` (2,065,432
bytes). The page displays “BVL Betriebslisten Version 1.0.35 [10/2023]”; this is
the application/list version string, not evidence of the export's effective date,
which remains unknown.

The first parser pass matched the captured 50-column schema but quarantined rows
for activity flags outside its narrow SH/CP mapping. An aggregate audit found
otherwise valid rows among those exclusions. The adapter now retains all flags with their source
column positions and values, carries the native street field privately, and
marks unknown taxonomy as unresolved rather than
discarding structurally valid observations. Column-count anomalies and malformed
CSV rows remain quarantined. SH and CP are the only mapped broad categories; other source
flags remain native/unresolved. Coordinates are unknown and geocoding is disabled.
The shared private importer and authenticated list/detail routes retain the
normalized evidence. Authenticated detail can return the source business address;
collection/map routes and public releases do not gain address access from this work.
The source inventory distinguishes import acceptance from actual map readiness.

The shared refresh runner has also completed this live acquisition into a private
candidate handoff. Local provider-neutral address staging is distinct from public
release review: the source's `pending-review` privacy label is retained unchanged
and does not alone withhold a business address from the local queue. Only explicit
source address restrictions/withheld or known-residential evidence is excluded.
An address-queue entry requires a nonempty source street address; city/country-only
queries are counted separately rather than treated as street addresses.
No source coordinates were supplied. Germany has no enabled private Geoapify
source profile, so queue entries remain pending provider configuration; no durable
provider jobs or external provider calls were created. This is not a claim that
addresses were privacy-screened, publicly releasable, or map-ready.

## Metadata evidence boundary

Any user-supplied JSON describing this source must be treated as a lead until tied to
the actual BLtU resource. In particular, `http://dcat-ap.de` identifies a metadata
profile/specification, not a dataset license, and `https://bund.de` is a placeholder,
not the BLtU resource URI. A DL-DE record for another BVL dataset cannot be inherited
by BLtU without dataset-specific evidence.

## Private/test-only implementation

[`pipeline/sources/germany/`](../pipeline/sources/germany/) provides the bounded
public-session downloader, typed BLtU adapter and shared private import bridge:

```text
python scripts/real_preview.py refresh --source de.locations
```

Use the assigned disposable database and existing runtime configuration, not a
serving or frozen database. Preserved captures can also be parsed with the
source-owned `--raw` and `--acquisition-metadata` arguments. The adapter preserves
repeated activity columns, current/legacy approval-number provenance and malformed
rows. Unknown classifications are retained, not silently discarded. Queue artifacts
are private; an external provider and durable provider jobs are separate stages.

## Repeated acquisition

The source-owned scoped terms record permits the private runner to retrieve a
current export into ignored raw storage and record URL, retrieval
timestamp, HTTP/content metadata, effective/publication date, byte size, SHA-256,
adapter/config versions, and source snapshot identity. It must then run only through
private parse/normalize/validate/quarantine staging. Unknown classifications,
unresolved coordinates, suspicious identity changes, and source disappearance must
remain explicit review outcomes. The shared command can import private candidates;
geocoding, release promotion and publication are not implied by acquisition approval.

## Unresolved inquiry questions

The retired inquiry document was an unsent draft, not permission received.
For BLtU specifically, establish the exact dataset licence/metadata URL,
permitted periodic export route/rate, artifact retention and redistribution
conditions, attribution, treatment of addresses/activity fields and publisher
correction/withdrawal obligations. Do not borrow licence metadata from another
BVL product or mistake the pesticide API for an animal-facility register.
