# Switzerland source reconnaissance

Status: row-free reconnaissance only; no names, addresses, coordinates, exports, or private artifacts are retained. Last checked 2026-09-16.

## FSVO approved food-business list

The authoritative route is the Swiss Federal Food Safety and Veterinary Office (FSVO/BLV) page [Listen bewilligter Schweizer Betriebe](https://www.blv.admin.ch/de/listen-bewilligter-schweizer-betriebe), with German, French, and Italian equivalents. The search/list route observed at [kwk.blv.admin.ch](https://kwk.blv.admin.ch/bewilligungsliste-de/) exposes approval number, facility/operator naming, address/contact material, status/permission date, and activity/type fields. The FSVO explains that food businesses are reported or approved by cantonal enforcement authorities; animal-origin businesses generally require approval, and slaughter/game-processing businesses are governed separately. This is therefore a federated authority view, not proof of a single uniform national register.

The source broadens adapter requirements beyond a simple CSV: multilingual labels must be preserved beside normalized values; approval numbers and dates are observations with lifecycle semantics; list versions and source-language URLs must be retained; and records must not be deduplicated across activity or export-list views without an explicit identity rule. The page exposes precise business addresses and contacts, so raw evidence remains private and public coordinates/addresses require a separate privacy decision. Government origin is not project review or publication approval.

## Readiness and future integration plan

| Area | Finding | Next bounded step |
| --- | --- | --- |
| Access/format | Public search/list route observed; no stable bulk/API contract verified | Authorized operator captures one list export/page response and records URL, UTC time, hash, bytes, and visible version/date |
| Coverage/cadence | Federal page links multiple establishment families; canton-fed scope and refresh cadence are unclear | Inventory list families and compare two dated snapshots; disappearance means “not observed” |
| Provenance/rights | FSVO is authoritative source origin; reuse/attribution and list-specific terms are not pinned | Obtain terms decision and preserve source-language page/list URLs |
| Privacy | Addresses, phone/email, and coordinates may be present; mixed-use/residential risk is unresolved | Keep contacts restricted; define field-level release profile and coordinate precision policy |
| Adapter | Requires multilingual raw labels, list-family identity, approval lifecycle, and one-to-many activity observations | Implement deterministic private adapter with schema fingerprint, raw-label preservation, quarantine on drift, and source-version linkage |

Difficulty estimate: high (about 4/5). The hard parts are authorization for reproducible capture, federated coverage, multilingual code/label mapping, and privacy-safe release—not parsing.

No adapter, runtime-health claim, or publication authorization is created by this reconnaissance.
