# FSS Scotland approved-establishments source assessment

Assessment date: 2026-09-13
Scope: read-only readiness review; no artifact was downloaded.

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
