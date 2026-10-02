# FSS Scotland approved-establishments source assessment

Assessment date: 2026-09-13
Scope: read-only readiness review; no artifact was downloaded.

## One-time E2E supplement — 2026-10-02

The bounded acquisition and restricted private E2E authorized for this
project were completed against the current FSS open-data CSV edition published
2026-09-29. The live catalog identifies Scotland coverage, monthly publication,
and Open Government Licence v3. The capture was 247,291 bytes
(SHA-256 `621a94b0d7ccba7741fab0bc9c5644b9d74b588a518b8f9b46d7b6f7e44587e3`).
The source adapter accepted 595 of 728 rows and quarantined 133; all accepted
records were imported into a disposable private PostGIS database, queried
through the private list/search/detail/map API, and replayed idempotently.
The disposable database was removed after certification. No coordinates were
provided: all 595 candidates are listable, zero are map-visible, and zero
public rows/projections were created. Full row-free counts and artifact hashes
are in the [E2E manifest](../../../data/manifests/fss-approved-establishments-e2e-20261002.json);
row-bearing capture, normalized, and database evidence remains outside git in
the manifest's `D:\UntilEveryCage-backups\source-evidence` archive.

The original 2026-09-13 review below remains accurate for its date. This later
single run verifies one published edition and a conservative private workflow;
it does **not** authorize a schedule, establish source completeness, constitute
privacy/legal clearance, or permit release. Scotland remains distinct from the
FSA England/Wales feed and any Northern Ireland source. The archive's row-level
privacy-risk flags and blocked publication gate must be respected.

## Direct official evidence

- FSS publishes an approved-establishments register for Scotland. The register page is dated 9 September 2026 and links an XLSX resource. It says an approval number without a two-letter prefix is approved by FSS rather than a local authority: [FSS register](https://www.foodstandards.gov.scot/business-guidance/running-a-food-business/publications/approved-establishments-register).
- FSS's open-data metadata identifies the resource as `Approved Establishments in Scotland`, coverage Scotland, site ID FS0010, OGL v3, monthly updates, and publication date 11 August 2026. The linked CSV URL is [Approved Establishments in Scotland.csv](https://www.foodstandards.gov.scot/sites/default/files/2026-08/Approved%20Establishments%20in%20Scotland.csv): [FSS open-data metadata](https://www.foodstandards.gov.scot/open-data-portal/approved-establishments-in-scotland).
- FSS says it maintains and publishes the list based on information supplied by competent authorities, and distinguishes FSS approvals from local-authority approvals: [FSS approved establishments guidance](https://www.foodstandards.gov.scot/business-guidance/industry-specific-advice/meat/meat-and-meat-establishments/fss-approved-establishments).
- FSS's privacy notice for food-law enforcement says it holds business trading name/address and operator name, obtains information from local authorities, uses it for statutory food-law enforcement, and retains name/address information while approved and up to six complete financial years after closure: [FSS privacy notices](https://www.foodstandards.gov.scot/privacy-notices).
- The OGL v3 terms require attribution and state that the licence does not cover personal data: [National Archives OGL v3](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/). FSS's open-data plan describes its intention to publish information under OGL v3: [FSS Open Data Publication Plan](https://www.foodstandards.gov.scot/about-us/how-we-work/governance/open-data-publication-plan).

## Readiness decision

**Conditional GO for restricted staging of the published CSV only**, after recording the exact URL, retrieval timestamp, byte hash/size, source metadata, and a privacy-screened restricted copy. This is an operational recommendation, not legal clearance. Keep the raw artifact access-controlled and do not add it to repository fixtures.

**NO-GO for automated recurring retrieval or public release at this time.** The reviewed FSS pages do not state rate limits, robots/API expectations, automated-retrieval permission, a machine-readable schema contract, or a project-specific retention/removal instruction. These must be confirmed or conservatively bounded before scheduling retrieval. OGL permission also cannot be treated as permission to publish personal data.

## Field and publication constraints

Approval number, trading name, competent authority and activity information appear in the published-list context, but the current CSV contents were not inspected. Preserve all source cells as strings and do not infer a schema until the artifact is lawfully acquired and reviewed. Treat address lines, operator names, telephone/contact data, and precise coordinates (if present) as privacy-sensitive. Do not geocode or publish precise locations by default. FSS's published guidance also shows that approval responsibility can be split between FSS and local authorities, so authority provenance must remain explicit.

The public derivative gate requires: verified schema and field-level publication status; explicit OGL attribution including FSS/source/date and licence link; personal-data and residential/private-location screening; suppression propagation; documented correction/removal handling; human terms/privacy review; and release-specific project approval. Until those gates pass, retain only restricted staging and quarantine, with no public API, export, map, or release.

## Unresolved evidence to obtain before acquisition automation

1. FSS confirmation of acceptable request frequency, caching, conditional requests, and whether automated retrieval is welcomed or constrained.
2. The live CSV/XLSX schema, effective/update-date semantics, encoding, and whether the two formats are equivalent.
3. Dataset-specific attribution wording, third-party rights exclusions, correction/removal process, and any source terms beyond the OGL metadata.
4. A project retention schedule aligned with source corrections/removals; the FSS six-year historical practice is evidence about FSS's own records, not authorization for this project's indefinite retention.
