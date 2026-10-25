# Source status

[`source-status.json`](source-status.json) is the sole authoritative record of
source readiness, evidence links, and source-specific next-action notes. This
page is a navigation aid; it intentionally contains no copied status table,
counts, or current-state narrative.

Each source entry records its metadata-evidence state, acquisition state,
runtime-health state, publication eligibility, supporting evidence, and next
action. `runtime_health: healthy` means the latest measured live refresh,
private import, and map-feed check succeeded; it is a snapshot only and does
not imply recurring reliability, a freshness SLA, or a scheduler. Read the
linked country/source record for source facts and the linked manifest for
row-free run evidence. Those records explain evidence; they do not override
the readiness fields in the JSON.

The JSON is not a runtime monitor, release approval, or publication
authorization. `runtime_health` and `publication_eligibility` remain separate
from metadata and acquisition evidence. See [ETHICS.md](ETHICS.md), the
[product readiness tracker](PRODUCT-READINESS.md), and the
[historical archive index](archive/README.md) for their respective authorities.

Read the run date and scope. Historical rehearsal blocks and private-source
`publication_eligibility: blocked` entries are not a claim that an already
approved public release is unpublished. Current release membership comes from
its manifest/serving projection; private acquisition evidence is a different
cohort. Do not add private-run totals to public totals or call a refreshed
regional source new national coverage. Update an existing source entry rather
than creating another inventory or copying status into a country README.
