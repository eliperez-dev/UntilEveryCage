# Germany BLtU source assessment

Status: automated reacquisition and publication paused pending a human terms decision. This document records
source evidence and risks; it is not legal advice, legal clearance, project approval,
or publication authorization.

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

The existing V1 Germany adapter is [`static_data/de/migrate_data.py`](../static_data/de/migrate_data.py),
which references the BLtU publication endpoint and expects downloaded/merged CSVs.
Its current behavior also performs external geocoding and emits a wide source-shaped
CSV; V2 must not reuse those behaviors without a reviewed, deterministic replacement.

## Terms and risk decision

The official pages located for this assessment document public access and export, but
do not present a clear license or redistribution grant for the establishment-record
export. Therefore acquisition is **blocked pending human confirmation** of:

1. whether automated retrieval is permitted, including rate/frequency limits;
2. whether local research retention of the raw export is permitted;
3. whether transformed establishment records may be redistributed in a public
   non-commercial project under the project’s data license/attribution model; and
4. required attribution, notices, update/deletion obligations, and any restrictions
   on address, approval-number, or activity/species fields.

This is a terms uncertainty, not a claim that the source prohibits use. A single
real BLtU export was downloaded earlier at the user's direction as a restricted
local research artifact and staged privately (15,797 input rows; 6,346 normalized;
9,451 quarantined). It is not a repository fixture, release candidate, API source,
map layer, export, or publication. That retrieval does not establish permission for
recurring acquisition, retention, or redistribution; those decisions remain open.
Privacy/safety review is separately required because facility addresses can overlap
with residences or identify individuals; source origin does not resolve that risk.

## Metadata evidence boundary

Any user-supplied JSON describing this source must be treated as a lead until tied to
the actual BLtU resource. In particular, `http://dcat-ap.de` identifies a metadata
profile/specification, not a dataset license, and `https://bund.de` is a placeholder,
not the BLtU resource URI. A DL-DE record for another BVL dataset cannot be inherited
by BLtU without dataset-specific evidence.

## Planned recurring acquisition after approval

Once the named human reviewer records a positive terms decision, an automated runner
may retrieve a current export into ignored raw storage and record URL, retrieval
timestamp, HTTP/content metadata, effective/publication date, byte size, SHA-256,
adapter/config versions, and source snapshot identity. It must then run only through
private parse/normalize/validate/quarantine staging. Unknown classifications,
unresolved coordinates, suspicious identity changes, and source disappearance must
remain explicit review outcomes. No geocoding, release promotion, API ingestion, or
publication is implied by acquisition approval.
