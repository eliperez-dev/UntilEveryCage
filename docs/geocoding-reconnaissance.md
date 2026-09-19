# Country/source geocoding reconnaissance

Status: public-documentation reconnaissance and contract work only. Checked
2026-09-18 under [`docs/ETHICS.md`](ETHICS.md). No private facility record,
address, coordinate, geocoder query, or raw provider response is committed;
no provider was called with a project record. This report does not approve a
source, a geocoder, a coordinate, a release, or publication.

## Result

`pipeline/geocoding/profiles.json` is the machine-readable profile registry.
`pipeline/contracts/geocoding-profile.schema.json` documents its external
shape, while `pipeline/contracts/geocoding_profile.py` validates the stronger
privacy, fallback, provenance, terms-review, and publication boundaries.
`pipeline/geocoding/recon.py` joins the profiles to the checked-in source and
status registries and produces a deterministic row-free JSON report:

```powershell
python -m pipeline.geocoding.recon --output data/reports/geocoding-recon.json
```

The report currently ranks 254 registered sources across 45 country/scope
prefixes. Its score uses only checked-in status signals: acquisition (0–50),
metadata (0–15), adapter implementation (0–14), runtime health (0–5), a
blocked-acquisition penalty, and a small assessed-profile tie-break bonus.
Ties sort by `source_id`. It ranks source readiness, not factual quality or
publication eligibility.

## Deep tranche and order

The first tranche is deliberately bounded. It covers the highest-readiness
source lanes that have private artifacts or implemented source adapters, plus
the UK lane whose FSA/FSS child feeds have materially stronger private staging
than the aggregate legacy registry row indicates.

1. Denmark — `dk.smiley`: source `Geo_Lat`/`Geo_Lng` may be present, but point
   semantics and privacy remain review questions. Prefer the official DAWA
   address service; its current documentation warns that DAWA is closing, so
   replacement planning is part of this lane.
2. Belgium — `be.locations`: FASFC operator and activity-code artifacts are
   privately validated, but the live operator schema does not establish a
   stable coordinate contract. Prefer BeSt-Address and its regional registers;
   preserve Dutch/French/German variants and regional position metadata.
3. Italy — `it.853-2004`: the catalog supplies optional coordinate fields and
   a location-status value, with some coordinates attributed to OSM. Prefer
   ANNCSU for civic-number/access validation; never treat an OSM-derived
   catalog point as automatically publishable.
4. Brazil — `br.sif.registered`, `br.sif.export`: SIF registered and export
   evidence are separate source families; the assessed SIF CSVs supplied no
   source coordinates. Prefer CEP/municipality validation, then a reviewed
   exact provider. e-SISBI GIS and Trase coordinates remain separate future or
   secondary evidence, not silent repairs.
5. Germany — `de.locations`: the normalized adapter deliberately withholds
   coordinates pending review. Prefer BKG/AdV structured geocoding and use its
   score, result type, and hit class together; a high score alone is not
   acceptance.
6. United Kingdom — `uk.locations`: FSA England/Wales, FSS Scotland and
   Northern Ireland are separate feed boundaries. Prefer licensed OS Places /
   AddressBase where a project-specific contract permits it; use UPRN and ONS
   postcode data only for reviewed linking or coarse display.

The implementation order is a recommendation for private contract and test
work. Every profile remains `publication: blocked` and `no_private_records_queried:
true`.

## Reusable global backups

The default global candidate is `global.nominatim-self-hosted`, with
`global.pelias-self-hosted` as the second architecture candidate. Both require
project-controlled deployment, source-index review, update/capacity
benchmarks, attribution, suppression-aware caching, and a documented data
residency decision. They are not enabled by this change.

The public `nominatim.openstreetmap.org` service is intentionally not the
default. Its policy sets an absolute maximum of one request per second,
discourages recurring bulk work, requires a valid identifying User-Agent or
Referer and attribution, requires caching for permitted bulk work, and says
not to submit personal or confidential data. It also prohibits systematic
queries and reselling geocoding results. See the [Nominatim usage
policy](https://operations.osmfoundation.org/policies/nominatim/).

The OSM wiki's [alternatives / third-party providers
catalog](https://wiki.openstreetmap.org/wiki/Nominatim#Alternatives_.2F_Third-party_providers)
is recorded as a discovery source only. OpenCage, Stadia Maps, LocationIQ and
Geoapify are listed in `global_fallback_policy.provider_discovery_catalog` as
unreviewed candidates. Their current privacy, retention, residency, licensing,
rate, bulk and cost terms must be reviewed separately before any one becomes
an approved provider. A hosted global provider is never a reason to transmit a
private candidate address by default.

## Common fallback and acceptance policy

Every profile carries the same explicit state chain:

`exact → coarse → restricted → unmapped`

An exact result requires a unique address-level match, country/locality
agreement, provider-specific confidence evidence, a privacy decision, and a
human acceptance path. A coarse result is a separately labeled locality or
postcode reference; it is never an invented facility point. Restricted values
stay out of provider queries and public projections. Unmapped means only that
no eligible result was observed; it does not mean closure or absence.

Provider responses are append-only evidence. Source coordinates are preserved
as source evidence and are never overwritten by a geocoder result. Provider
disagreement, moved points, stale/retired addresses and outages create new
events or review states; they do not silently update a current point. Failed
acquisitions must leave the previous validated release available, subject to
current suppression.

## Backlog

The full deterministic backlog is generated from the 254-source registry and
retains explicit unknowns and next actions from `docs/source-status.json`.
Sources with private or verified acquisition but no deep profile are the next
tranche; metadata-only and not-run sources remain reconnaissance or unstarted
backlog. The report is source-level and aggregate-only: it contains no
facility rows, address strings, coordinates, provider responses, or release
approval decisions.

The current profile validator and tests cover:

- profile schema and registry/source-ID integration;
- deterministic score and tie ordering;
- explicit unknown/not-observed coordinate states;
- exact/coarse/restricted/unmapped fallback ordering;
- privacy-minimized query construction and no-private-record network boundary;
- provider terms/rate/logging/residency review fields;
- source-coordinate preservation and disagreement/moved-point handling; and
- separation of geocoding evidence from approval and publication.
