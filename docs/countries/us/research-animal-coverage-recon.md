# United States research-animal coverage reconnaissance

Scope/date: documentation-first reconnaissance of public, authoritative United States sources beyond the existing USDA APHIS Animal Welfare Act (AWA) annual-report lane, observed 2026-09-18 UTC. This document records source topology, not a facility census, animal-use estimate, publication approval, or a claim that any source is complete.

## Bottom line

The United States does not expose one public, national laboratory/research-animal register that can safely stand in for a facility master or a national animal-use total.

The evidence has to stay in separate lanes:

| Evidence lane | Strongest public source found | What it can establish | What it cannot establish |
| --- | --- | --- | --- |
| Institutional identity | OLAW assured-institutions lookup, AAALAC directory, agency/state pages | A named institution, unit, assurance/accreditation or agency relationship as stated by that source | Current operation, every research site, animal use, or factual approval of every project |
| Funding/project evidence | NIH RePORTER API and ExPORTER; NSF Award Search API; NASA NSPIRES | An award/project, recipient organization, dates, funding agency, and selected project text/identifiers | That animals were used, where the work physically occurred, or how many animals were used |
| Regulatory registration | APHIS public search; California CDPH laboratory-animal approval as a state example | A source-native registration/certificate or state approval observation | A complete national register, current activity, or actual use |
| Inspection/oversight evidence | APHIS inspection reports; DoD ACURO and VA ORO program pages; FDA GLP authority | A dated inspection, site-visit, oversight, or program statement when the source publishes one | A clean bill of health, complete inspection history, or animal counts |
| Actual animal-use counts | APHIS Form 7023 annual reports and fiscal-year summaries; some state forms may request prior-year counts | Counts for the reporting population, period, columns, species and exclusions stated by the source | Purpose-bred rat/mouse/bird use, all agricultural research, unreported use, or a national all-species total |

The existing [US recovery packet](README.md) remains the implementation boundary for FSIS and APHIS. This reconnaissance adds research-specific source contracts and candidate integrations; it does not merge them into the FSIS facility layer.

## Source matrix

### NIH funding and assurance

**NIH RePORTER / ExPORTER — funding and project evidence.** The [RePORTER API](https://api.reporter.nih.gov/) exposes project and publication search APIs. Its documented project fields include application/project identifiers, core project number, fiscal year, project dates, agency, funded organization name, organization IPF, UEI, DUNS, FIPS and ZIP, funding amounts and mechanism, and project title/terms/abstract fields. The [ExPORTER bulk page](https://reporter.nih.gov/exporter/publications) provides public CSV-oriented bulk administrative files and says the consolidated annual project file is normally released annually, with later updates after the President’s budget and RCDC integration.

This is the best first automation candidate for funding/project evidence. Use exact `appl_id`, `core_project_num`/project number, fiscal year and organization identifiers as source keys. Preserve the recipient organization separately from any explicitly stated performance site. A project title or abstract mentioning an animal model is a project claim, not a count and not proof that the recipient operates a laboratory at its mailing address. RePORTER’s one-request-per-second recommendation and large-job time window belong in the adapter contract; API responses, release dates, pagination and schema fingerprints must be versioned.

**OLAW assured institutions — assurance/identity evidence.** The [Assured Institutions Look Up Tool](https://grants.nih.gov/policy-and-compliance/policy-topics/animal-welfare/assurance/assured-institutions) exposes organization name, Assurance ID (and legacy ID), type, state/territory and country for institutions with a current approved Domestic or Foreign Assurance. The [assurance page](https://grants.nih.gov/policy-and-compliance/policy-topics/animal-welfare/assurance) states that a Domestic Assurance is required for U.S. institutions conducting live vertebrate animal work onsite for PHS, NSF or NASA-supported activities, and describes interinstitutional assurances when work is performed at another named site.

OLAW is therefore useful for a dated assurance observation and for distinguishing award recipient from performance-site assurance. It is not a project register, an IACUC protocol register, a facility inspection database, or an animal-use count source. The [annual-report requirement](https://grants.nih.gov/policy-and-compliance/policy-topics/animal-welfare/assurance/domestic-annual-report) concerns changes in the program/facilities, Institutional Official, IACUC membership, semiannual evaluation dates, minority views and accreditation status. It does not publish a national annual table of animals used. Annual reports are submitted as signed PDFs by email, so no public bulk endpoint was identified.

### Federal agencies and federal laboratories

**FDA.** FDA’s [laboratory-animal MOU with USDA and NIH](https://www.fda.gov/about-fda/domestic-mous/mou-225-16-010) describes three distinct programs: USDA registration/licensing and inspections, FDA Good Laboratory Practice (GLP) standards under 21 CFR Part 58 with FDA inspections and possible laboratory disqualification, and NIH/OLAW assurance/compliance. The MOU also says that each agency maintains registries or inventories within its own authority and that nonpublic shared information is access-controlled. The public [NCTR animal-facilities page](https://www.fda.gov/about-fda/nctr-location-facilities-services/nctr-animal-facilities-and-services) is useful institutional evidence for an FDA program and its IACUC/AAALAC statements, but it is not a national FDA research-facility export.

The public [openFDA Animal & Veterinary API](https://open.fda.gov/apis/animalandveterinary/) is an adverse-event dataset, not an animal-research-facility or experimental-use register. Its records can contain numbers of animals affected/treated, but those numbers describe adverse-event reports and must never be relabeled as research use.

**VA.** The [VA Animal Research Program](https://www.research.va.gov/programs/animal_research/default.cfm) and [VA research overview](https://www.research.va.gov/programs/animal_research/overview.cfm) document that VA animal-care programs operate under VA policy, PHS Policy, the AWA where applicable, IACUC oversight and AAALAC accreditation. VA’s [Office of Research Oversight](https://department.va.gov/vha/research-oversight/what-oro-does/) describes proactive evaluations, investigations and remediation oversight for laboratory animal welfare. These pages are authoritative program/oversight evidence, but no public machine-readable national VA facility or animal-use dataset was identified. VA facility pages may prove a local program; they do not provide national counts.

**DoD / DHA ACURO.** The [Animal Care and Use Review Office](https://mrdc.health.mil/index.cfm/resources/research_protections/acuro) states that ACURO oversees DHA, USAMRDC and Department of War research, development, testing, evaluation and training involving animals, including extramural contracts and grants; its functions include protocol review and site visits/compliance inspections. The page publishes policies and reporting resources, not a national facility list or animal-use table. Model ACURO as oversight evidence linked to an award/protocol/site only when the source explicitly supplies those identifiers. Do not infer a facility from a DoD awardee address.

**NSF and NASA.** NSF’s [developer page](https://www.nsf.gov/digital/developer) documents an Award Search API for research spending and results. NASA states that [NSPIRES](https://www.nasa.gov/hrp/for-prospective-researchers/) supports the lifecycle of solicitations and awards and that organizations need SAM registration to participate. Both are funding/project evidence only. OLAW expressly includes NSF- and NASA-supported onsite live vertebrate work in its Assurance rules, but the funding record still does not establish animal use, facility location, or count. These are lower-priority adjuncts after NIH RePORTER because animal-related classification and performance-site semantics need more review.

### Accreditation and state records

**AAALAC International.** The [public directory](https://www.aaalac.org/accreditation/directory/directory-of-accredited-organizations-search-result/) is maintained by the private nonprofit accreditor and says the list is updated on an ongoing basis. It identifies accredited organizations/units and locations, including government, academic and commercial programs. Accreditation is voluntary and unit-scoped. It is not an APHIS registration, OLAW assurance, inspection result, animal-use count or proof that every listed campus currently uses animals. Retain the directory’s organization/unit distinction and the observation date; do not flatten a parent organization into all listed facilities.

**California as a state-record pilot.** California’s [Laboratory Animal Use Approval Program](https://www.cdph.ca.gov/Programs/cls/operations/Pages/LaboratoryAnimalUseApprovalProgram.aspx) says California requires approval to keep/use live warm-blooded animals for education, research, testing or diagnostic purposes, but exempts laboratories subject to USDA-APHIS or NIH-OLAW and does not conduct routine inspections. The [LAB 139 form](https://www.cdph.ca.gov/CDPH%20Document%20Library/ControlledForms/lab139.pdf) asks for institution/location, responsible program person, use types, and animals kept or used during the previous calendar year, including laboratory mice, laboratory rats and other species. This is a valuable state-level example of a potential count/approval contract and also a warning: a state record may target precisely the animals or laboratories excluded from federal coverage, while federally regulated facilities may be absent. No public statewide bulk registry or export was verified in this reconnaissance.

State sources should be added jurisdiction by jurisdiction. A state approval, permit or public-record response is a source-local observation, not a national denominator. Public-records requests must be narrowly scoped and privacy-reviewed; they must not be used to assemble personal addresses, names or sensitive operational details into a new public register.

## APHIS boundaries and exclusions

APHIS remains the only source located in this reconnaissance that publishes both a public national-ish research-facility search surface and annual animal-use summaries. It is still not a complete laboratory/research-animal census.

The [AWA and regulations Blue Book](https://www.aphis.usda.gov/sites/default/files/ac_bluebook_awa_508_comp_version.pdf) defines “animal” to include dogs, cats, nonhuman primates, guinea pigs, hamsters, rabbits and other warm-blooded animals designated for research/testing/exhibition, while excluding:

- birds, rats of genus *Rattus*, and mice of genus *Mus* bred for use in research;
- horses not used for research; and
- farm animals such as livestock or poultry used or intended for food/fiber, or to improve nutrition, breeding, management, production efficiency or food/fiber quality.

These exclusions are semantic, not a license to estimate the missing population. In particular, “rat” or “mouse” alone does not prove the purpose-bred exclusion, and species alone does not resolve agricultural versus non-agricultural purpose. APHIS separately says that captive-bred birds used in research are exempt, while farm-type poultry used solely for agricultural purposes are exempt and can be covered when used for non-agricultural purposes. Preserve the source’s stated purpose and coverage category rather than normalizing all birds, rats, mice or farm animals into one bucket.

The [Research Facility Annual Usage Summary](https://www.aphis.usda.gov/awa/research-facility-report/annual-summary) says each USDA-registered and Federal research facility submits Form 7023. The summary includes R, F and V certificate populations and AWA-covered animals reported by USDA Agricultural Research Service G-certificate facilities. APHIS says ARS reports all animals used for research, including farm animals and noncovered species, but excludes the ARS-reported farm and other noncovered species from the summary so that the summary represents AWA-covered animals. Annual reports may be amended after generation. The linked FY2025 PDF is a concrete source-reported count: 751,355 across its summary table as of 2026-05-28; it is not an estimate of all animals used in U.S. research.

Consequently:

- APHIS annual-report counts are **actual reported counts for a defined fiscal-year/reporting population**, not projections.
- APHIS counts do not include purpose-bred research mice/rats/birds and do not by themselves cover all agricultural research.
- APHIS registrations establish a regulatory relationship; they do not establish current operation, site ownership, or the number of animals actually used in a particular study.
- APHIS inspections establish dated inspection evidence; they do not establish a complete inspection history or that no unobserved use occurred.
- APHIS annual reports, inspections and registrations remain separate source-local evidence types. An annual-report row is not a facility master row and must not be silently joined to NIH, VA, DoD, FDA, AAALAC or state rows.

## Reusable source contract

All new US research-animal adapters should use the repository’s ordinary provenance fields and add the following source-specific semantics:

1. **Evidence identity:** `source_id`, official URL/final download URL, retrieval timestamp, publisher-supplied publication/effective/reporting period, content type, byte size, SHA-256, adapter/config version, schema fingerprint and terms/attribution review.
2. **Source-native keys:** preserve every supplied identifier without coercion: APHIS certificate/customer/report identifiers; RePORTER application, core project and organization identifiers; OLAW Assurance ID; AAALAC organization/unit; state approval/certificate; FDA/DoD/VA report or site identifiers when public.
3. **Observation type:** one of `institution_identity`, `funding_project`, `assurance`, `accreditation`, `registration`, `inspection`, `oversight`, `reported_animal_use`, `aggregate_animal_use`, or `policy_only`.
4. **Subject and location:** distinguish legal entity, institution, campus/unit, facility, mailing address, performance site, inspection site and source-reported study site. Store location precision and review state; never geocode a private/person-linked address merely because a source has an address.
5. **Count contract:** store fiscal/calendar period, species label exactly as supplied, reporting column/measure, unit, amendment status, covered/excluded populations, and whether the value is a source-reported count, aggregate, or unavailable. Never sum across APHIS, OLAW, funding, state or adverse-event observations.
6. **Review and release:** source origin, factual review, privacy/safety eligibility, project approval and publication remain separate. Current absence means `not_observed`, not closure, non-use or no assurance.

## Conservative graph semantics

Only create a relationship when the source states it or a reviewed exact-key crosswalk records it:

| Relationship | Safe meaning | Do not infer |
| --- | --- | --- |
| `project_funded_by → organization` | Award recipient named by the funder | That the organization used animals or owns the performance site |
| `project_performed_at → site` | The award/protocol explicitly names the site | Recipient mailing address as the site |
| `institution_has_assurance → OLAW assurance` | Assurance observation for the institution/type/date | Approval of every protocol or a count of animals |
| `unit_accredited_by → AAALAC` | Voluntary accreditation for the named unit/location | Regulatory registration or current animal use |
| `institution_registered_with → regulator` | Source-native registration/certificate observation | Operation, ownership, or use quantity |
| `site_inspected_by → authority` | Dated inspection/site-visit evidence | Complete inspection history or compliance certification |
| `reported_use_at → site/reporting unit` | The source report states a count for the period and scope | Unreported species, purpose-bred animals, or national totals |
| `state_approval_for → activity/site` | State approval/form observation with stated scope | Federal coverage or national comparability |

Names, addresses, DUNS/UEI, assurance IDs, certificate numbers and PI names are matching aids with different privacy and lifecycle properties. Institutional legal names can be shared by multiple campuses; one assurance can cover branches or an affiliate arrangement; AAALAC units can be narrower than the parent; an award recipient can differ from the performance site; and a state approval can deliberately cover only federally excluded laboratories. Fuzzy matching, name/address proximity and geocoded proximity are not identity proof. Ambiguous or conflicting links belong in quarantine or a reviewed link ledger.

## Prioritized next integrations

1. **NIH RePORTER API + ExPORTER:** implement a rate-limited funding/project adapter with exact award, organization and fiscal-year keys; classify animal relevance as a project-text signal only and keep it out of facility/use counts.
2. **APHIS annual summary/public-search profiles:** extend the existing profile-explicit adapter for registrations, annual reports and inspections; add a separate annual aggregate-count artifact and amendment/version handling; preserve R/F/V/G scope and exclusions.
3. **OLAW assured-institutions lookup:** add an assisted capture or carefully bounded browser adapter for current assurance observations, including Assurance ID, type, state/country and observation date; never treat it as an animal-use table.
4. **AAALAC directory:** add a voluntary accreditation observation only after terms, unit identity, refresh behavior and contact/address minimization are reviewed.
5. **California CDPH pilot:** obtain an authorized current approval/renewal extract or public-record response, test the form’s prior-year count fields with synthetic fixtures, and model federal-exemption semantics explicitly. Do not generalize California to other states.
6. **NSF and NASA funding adjuncts:** integrate only after the NIH contract is stable; use for award/project coverage and link to OLAW assurances where explicitly supported, never as animal-use evidence.
7. **VA, DoD ACURO and FDA:** retain as policy/oversight/manual evidence until a public, reproducible, terms-permitted facility or count route is verified. Do not build a national facility layer from agency program pages or FOIA fragments.

## Current limitations and blockers

No new row-level artifact, raw report, assurance file, state application, or private contact data was acquired or committed during this reconnaissance. Current public routes were documented from official pages and current linked documents only. The remaining blockers are source-specific terms and redistribution review, durable export/API contracts for the UI-mediated tools, exact effective-date and amendment semantics, privacy treatment for addresses and people, and an authorized maintainer review before any candidate release. These blockers do not mean that the sources failed or that no additional facilities/counts exist.

## Official sources consulted

- [NIH RePORTER API](https://api.reporter.nih.gov/) and [RePORTER ExPORTER](https://reporter.nih.gov/exporter/publications)
- [OLAW Animal Welfare](https://grants.nih.gov/policy-and-compliance/policy-topics/animal-welfare), [Assured Institutions](https://grants.nih.gov/policy-and-compliance/policy-topics/animal-welfare/assurance/assured-institutions), and [Annual Report](https://grants.nih.gov/policy-and-compliance/policy-topics/animal-welfare/assurance/domestic-annual-report)
- [APHIS Research Facility Annual Usage Summary](https://www.aphis.usda.gov/awa/research-facility-report/annual-summary), [FY2025 PDF](https://direct.aphis.usda.gov/sites/default/files/fy2025-research-animal-use-summary.pdf), [AWA Blue Book](https://www.aphis.usda.gov/sites/default/files/ac_bluebook_awa_508_comp_version.pdf), and [bird standards](https://www.aphis.usda.gov/awa/bird-standards)
- [FDA/USDA/NIH laboratory-animal MOU](https://www.fda.gov/about-fda/domestic-mous/mou-225-16-010), [FDA NCTR animal facilities](https://www.fda.gov/about-fda/nctr-location-facilities-services/nctr-animal-facilities-and-services), and [openFDA Animal & Veterinary](https://open.fda.gov/apis/animalandveterinary/)
- [VA Animal Research Program](https://www.research.va.gov/programs/animal_research/default.cfm), [VA animal-research overview](https://www.research.va.gov/programs/animal_research/overview.cfm), and [VA Office of Research Oversight](https://department.va.gov/vha/research-oversight/what-oro-does/)
- [DoD/DHA ACURO](https://mrdc.health.mil/index.cfm/resources/research_protections/acuro)
- [NSF Developer Resources](https://www.nsf.gov/digital/developer) and [NASA NSPIRES overview](https://www.nasa.gov/hrp/for-prospective-researchers/)
- [AAALAC accredited-organization directory](https://www.aaalac.org/accreditation/directory/directory-of-accredited-organizations-search-result/)
- [California CDPH Laboratory Animal Use Approval Program](https://www.cdph.ca.gov/Programs/cls/operations/Pages/LaboratoryAnimalUseApprovalProgram.aspx) and [LAB 139](https://www.cdph.ca.gov/CDPH%20Document%20Library/ControlledForms/lab139.pdf)
