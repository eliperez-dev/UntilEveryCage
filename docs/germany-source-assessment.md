# Germany BLtU source assessment

This document owns source research and field interpretation. Current counts and
readiness live only in [source-status.json](source-status.json). Private retrieval
and processing have a scoped [terms record](../pipeline/sources/germany/terms-review.json).
The federal open-data catalogue lists a source-specific reuse licence for BLtU;
that evidence is separate from the project's artifact- and release-scoped decision.

## Source identity and scope

The BVL’s official cross-border-trade page identifies the BLtU database as the list
of establishments approved under Regulation (EC) 853/2004 and says the lists include
company address, approval number, and approved activities/species. It also says the
lists are continuously updated. See the [BVL scope page](https://www.bvl.bund.de/DE/Arbeitsbereiche/01_Lebensmittel/01_Aufgaben/05_GrenzueberschreitenderHandel/lm_grenzueberschrHandel_basepage.html).

The [BVL data portal](https://gis.bvl.bund.de/datenportal/) describes the data as
authority-provided material, says tabular data can be exported as CSV or Excel, and
identifies BVL/BKG attribution notices for portal geodata. The export capability
supports reproducible acquisition, but does not itself state reuse terms for
establishment records; the separate BLtU-specific catalogue licence is described
below.

The stable entry route is [BVL BLtU](https://www.bvl.bund.de/bltu); the BVL portal supports selecting and exporting the current general or category list. Session-bound export URLs must be captured as run-specific provenance, not checked in as a source URL.

The existing V1 Germany adapter is [`static_data/de/migrate_data.py`](../static_data/de/migrate_data.py),
which references the BLtU publication endpoint and expects downloaded/merged CSVs.
Its current behavior also performs external geocoding and emits a wide source-shaped
CSV; V2 must not reuse those behaviors without a reviewed, deterministic replacement.

## Terms and risk decision

The federal BLE/BMELH open-data catalogue entry [“Zugelassene
Lebensmittelbetriebe”](https://www.landwirtschaftsdaten.de/detailansicht.html?cHash=228583357d36cd394966d7398546ee2b&tx_epadpsearch_showdetails%5Baction%5D=show&tx_epadpsearch_showdetails%5Bcontroller%5D=Search&tx_epadpsearch_showdetails%5Bgeodata%5D=187)
links the [BLtU database](http://www.bvl.bund.de/bltu), names BVL, Ref. 115 as
publisher, and lists [Datenlizenz Deutschland Namensnennung 2.0
(DL-DE BY 2.0)](https://www.govdata.de/dl-de/by-2-0). The catalogue record reports
its last change as 2021-06-07. The licence permits commercial and non-commercial
reuse, including copying, editing, distribution, and combining data. Where supplied
by the data provider, the attribution includes the provider name, the licence name
and link, and the dataset URI; changes must be identified. See the [GovData
attribution FAQ](https://www.govdata.de/informationen/faq). This BLtU-specific
catalogue entry is distinct from the BVL portal's separate BVL/BKG geodata credits.

The catalogue detail URL was fetched over HTTPS on 2026-10-25, but currently serves
a generic BMELH open-data landing page; the saved HTML does not contain the BLtU
record. The catalogue search result still exposes the record and its BLtU resource
link. The row-free capture hashes and this limitation are recorded in the private
evidence receipt at
`D:\\UntilEveryCage-Operations\\source-captures\\bltu-terms-catalogue-20261025\\bltu-catalogue-terms-evidence.json`.

The scoped private [terms record](../pipeline/sources/germany/terms-review.json)
authorizes bounded retrieval and private staging only; it is not itself the source
licence or a public-release decision. The catalogue licence does not establish the
export's effective date, resolve facility-address privacy, or approve any project
release. Record the exact source-artifact/release decision and attribution before
promotion; assess addresses separately because they can overlap residences or
identify individuals. Keep the stable BLtU route, session navigation, per-run export
URL, response metadata, bytes, and checksum as acquisition provenance.

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
CSV rows remain quarantined. The pinned BLtU taxonomy crosswalk maps supported
activity flags while retaining every native flag; unsupported flags stay unresolved.
BLtU supplies no coordinates; later private provider
enrichment is separate from source acquisition and is summarized below.
The shared private importer and authenticated list/detail routes retain the
normalized evidence. Authenticated detail can return the source business address;
collection/map routes and public releases do not gain address access from this work.
The source inventory distinguishes import acceptance from actual map readiness.

The shared refresh runner also staged the live acquisition privately. A separate,
bounded Geoapify enrichment path has since been exercised under a private Germany
source profile. The [canonical source inventory](source-status.json) owns its current
request, acceptance, display, and unmapped counts. Migration 095 aligns German
address normalization and requires matching postcode, locality and available state
context. An append-only audit excludes older provider points that fail those checks.
Provider results
and remaining address work are private evidence, not evidence that addresses were
privacy-screened, publicly releasable, or map-ready. No source coordinates were
supplied.

## Metadata evidence boundary

The DL-DE BY 2.0 evidence above is the federal catalogue's BLtU-specific entry and
resource link; do not substitute a licence record for another BVL dataset. Direct
retrieval of the catalogue detail page now returns generic landing-page HTML, so the
private capture is not a copy of the catalogue record itself. Preserve this evidence
limitation along with the indexed entry and its listed 2021-06-07 catalogue-change
date. The BLtU export's displayed application/list version `1.0.35 [10/2023]` is not
an effective date for the captured rows.

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

## Remaining source questions

The export's effective date remains unknown, and the catalogue entry's last-change
date predates the observed 2026 capture. BVL describes the lists as continuously
updated, but the exact effective date for a particular download must not be inferred
from the application version. Preserve each run's retrieval time, response metadata,
and checksum. Privacy, source-field interpretation, and the project's release-scoped
decision remain separate from the catalogue licence. Do not mistake the pesticide
API or another BVL product's terms for the BLtU resource.
