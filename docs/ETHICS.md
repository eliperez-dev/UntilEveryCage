# Until Every Cage: data ethics and credibility principles

Start with the [plain-language summary](ETHICS-SUMMARY.md). This full document remains authoritative. [Implementation tasks](governance/policy-implementation-todo.md) track unfinished protections; [policy history](governance/ethics-changelog.md) records amendments.

This project exists to create a trustworthy, open, and inspectable view of animal agriculture locations. The value of the project depends on people being able to understand where a record came from, what was done to it, what remains uncertain, and why it is visible.

These principles are binding for acquisition, processing, storage, review, and publication.

## Repository and test-data boundary

Real raw datasets and real derived records are local research inputs, not repository fixtures. Raw files, extracted addresses, coordinates, facility names, geocoder responses, and restricted or removed records must remain in ignored local storage unless a documented review establishes that committing them is necessary, lawful, safe, and consistent with this policy. The repository should contain methods, schemas, migration history, source URLs, retrieval timestamps, checksums, sanitized aggregate reports, and synthetic test fixtures. A public source does not by itself authorize committing extracted records.

Suppression must be demonstrable through safe aggregate counts and redacted audit metadata without publishing the suppressed payload. Repository history, generated reports, logs, fixtures, API responses, and exports must not become alternate disclosure paths for restricted or removed records.

They define the project's publication requirements and maintainer responsibilities, not a claim that every existing implementation already meets them. A known gap must be documented and the affected publication restricted until it is addressed. This policy takes precedence over conflicting unconditional retention instructions in repository guidance and pipeline documents.

## 1. Evidence before interpretation

Preserve the original source artifact, source URL, retrieval timestamp, checksum, publication date when available, and the code and configuration used to process it, subject to the restricted-retention and removal rules below. Normalized fields and classifications are interpretations; they must remain linked to the original source values and must never be presented as if they were original facts.

## 2. Non-destructive history

Retained research evidence is append-only by default. Corrections, later source snapshots, and review decisions create new versions linked to earlier evidence. Ordinary cleaning and imports must not silently overwrite or delete history.

This default does not require retaining personal information, harmful submissions, accidentally collected secrets, or material whose retention is not justified or permitted. A designated maintainer may authorize restriction, redaction, or deletion through a documented exceptional-removal process. Urgent public suppression may happen before that review is complete. No append-only implementation rule may prevent necessary removal.

Record the case ID, affected internal record IDs, reason category, decision, authorized actor, timing, and affected systems in a minimal audit event. Do not copy the removed address, coordinates, sensitive text, or identifying payload into that event. Retain an original privately only where there is a documented, proportionate and permitted need, with limited access and a review/expiry date. Preservation for audit is not an automatic justification for indefinite retention. Redacted derivatives must be labeled as such, not represented as unchanged originals.

Any restricted backup copy must remain unavailable for normal use and follow a documented expiry or removal plan. Restores must reapply current suppression and removal decisions before data can be served. Auditability includes explaining why evidence is no longer retained; it does not require reconstructing a removed sensitive payload.

## 3. Reproducibility and open methods

The project should publish its schemas, transformation rules, source registry, adapter code, dependency versions, sanitized validation reports, and release definitions. A developer should be able to reproduce a result from retained artifacts and documented code/configuration. Where privacy, removal, or source restrictions prevent public reproduction, disclose that limitation and provide a safe account of the method. “Open” describes our methods and evidence trail; it does not grant permission to redistribute data whose source license prohibits redistribution or to expose protected information.

## 4. Honest uncertainty

Unknown, unavailable, approximate, unresolved, ambiguous, and failed values must be represented explicitly. We do not guess coordinates, infer closure from disappearance, or silently repair suspicious source values. A geocoded point must include its provider, query, timestamp, precision, result, and review state.

## 5. Source and claim separation

Do not use “official” as a standalone source, quality, or review label. **Government-sourced**, **project-approved**, **project-published**, **community-reviewed**, and **community-unreviewed** describe different properties, not interchangeable credibility tiers.

| Term | Precise meaning | Does not establish |
| --- | --- | --- |
| Government-sourced | The cited evidence originates with a government or competent authority. Name that source. | Project approval, current accuracy, completeness, or independent verification. |
| Community-submitted | A person or community contributor supplied the claim. Preserve this origin even after review. | Factual review or permission to publish. |
| Community-reviewed | Community reviewers assessed specified evidence; record reviewer role, date, scope, outcome, and limitations. | Review by Until Every Cage maintainers, project approval, or a finding that the claim is true. |
| Community-unreviewed | A community claim has not completed recorded factual review. Privacy screening is a separate step. | Factual verification; it can still be explicitly queryable when privacy-eligible. |
| Project-reviewed | Authorized project reviewers assessed specified evidence and recorded a scoped outcome. | Government origin, guaranteed truth, or automatic release approval. |
| Project-approved | Authorized project maintainers approved a record/version for a named curated release/profile under documented checks. | Actual publication, government origin, or certification of every fact. |
| Project-published | Until Every Cage actually made a record/version available in an identified release/profile. | Project factual approval: an explicitly labeled unreviewed-community profile is also project-published. |

Represent source origin, factual review events, privacy/moderation eligibility, project approval, and publication independently. Review events identify whether the actor is a community reviewer or project reviewer, and preserve outcomes such as corroborated, disputed, inconclusive, or rejected. “Reviewed” alone does not mean accepted. Community and project reviews may coexist; a new review does not erase earlier outcomes.

The default curated project dataset contains records approved for that named release and eligible for public access. Its initial acquisition focus is government sources, but secondary or community-origin evidence can qualify through the documented project approval process. A community review alone never grants project approval. Publishing a privacy-eligible claim in the opt-in community profile is authorization to display a labeled claim, not approval of its factual content or admission to the default dataset. Approval is scoped to a record/version and release/profile; future changes do not automatically inherit it.

Example labels: **“Government-sourced · Project-approved · Published in release X”**, **“Community-submitted · Community-reviewed (inconclusive) · Not project-approved”**, and **“Community-submitted · Community-unreviewed · Published in the opt-in community profile · Not project-approved.”** Label the scope/outcome of any project review too. Source origin remains unchanged when evidence is reviewed, approved, or published.

### Explicit access to factually unreviewed community claims

Factually unreviewed user submissions may be publicly queried after passing privacy and abuse screening. Screening establishes publication eligibility, not factual verification or endorsement. Keep source origin, factual review events and reviewer roles, privacy/moderation eligibility, project approval, and publication distinct. Raw unscreened submissions, restricted personal information, and rejected material are not publicly queryable.

Access requires an explicit community-unreviewed selection, such as a dedicated page/profile or API parameter; ordinary map, search, API, and export defaults exclude these claims. Use the prominent label, for example: **“Unreviewed community claim — not verified by Until Every Cage.”** Show it before access and on each record, with persistent context on result lists and maps. Do not rely on color, a tooltip, or a one-time notice alone. Keep opt-in community results/counts separate from the default curated project dataset; never silently add unapproved claims to its facility totals.

Direct links to eligible claims must open with the same prominent context rather than look like project-approved facility pages. API responses and every exported row must carry source origin, factual review status and reviewer role, project approval, and publication/profile context; downloads also identify the selected profile and its limitations. Public source previews and historical views follow the same labeling and active privacy restrictions. Link related government-sourced or project-approved records as separate evidence without changing the claim's origin or approval. An explicit query never overrides address/coordinate removal or other safety restrictions.

### What the project can and cannot promise

“Government-sourced” identifies evidence origin; “project-approved” identifies a scoped release decision; “project-published” identifies availability. None certifies the underlying claim. Government records can be inaccurate, outdated, incomplete, or ambiguous. Inclusion does not independently establish that a facility is operating, that its address is an operating site, or that a particular practice, animal count, violation, or wrongdoing occurred there. A successful source check does not mean the source itself has been updated. Legacy data must retain its legacy label and known or unknown source dates.

For records presented as meeting the project publication standard, the project commits to:

- identifying the source and retrieval/observation dates that are actually known;
- recording acquisition integrity, versioned transformations, classification rules, and validation results;
- separating source statements from project interpretation, geocoding, and submitted claims;
- documenting uncertainty, coverage limitations, and review status;
- applying publication restrictions and maintaining a correction/removal process with accountable decisions.

These are verifiable process commitments, not guarantees of factual truth, completeness, exact location, uninterrupted availability, or real-time accuracy. Do not claim a guarantee that a release's retained evidence and checks cannot demonstrate. Discovered failures must be disclosed and corrected. The same traceability, privacy, and honest-presentation requirements apply to any published submission; corroboration does not change its source origin. Source origin, review events, privacy eligibility, project approval, and publication remain separate fields.

## 6. Proportionate publication

Separate three access states: public-eligible information, restricted information available only to authorized reviewers for a documented purpose, and information that must not be retained. A retail business from a broad source such as Denmark's food register may be outside the main map's scope yet eligible for a labeled public filter; sensitive personal information must not become public by enabling a filter, searching an API, or requesting an old release. Factually unreviewed submissions are eligible for explicit, prominently labeled public queries once privacy/abuse screening permits publication, as defined in section 5. Unscreened submissions remain restricted.

Publication restrictions apply to pages, maps, API responses, search results, bulk downloads, embeds, raw-artifact previews, public logs, and historical releases. Suppression must cover both explicit fields and equivalent disclosures in source text, identifiers, links, geocoding queries, or attachments. Public access and raw-evidence retention are separate decisions governed by this policy.

## 7. Respect for people and communities

Use only data that can be collected and published responsibly. Follow source terms, attribution requirements, rate limits, and applicable privacy and safety obligations. Do not publish personal information merely because it is technically obtainable. Escalate safety-sensitive cases for human review.

## 8. Protect individuals from exposure and targeting

The project documents organizations, facilities, and high-level industry activity—not private individuals. Factory workers, farm workers, contractors, drivers, residents, family members, neighbors, activists, and anyone else who is not a high-level executive or public figure in the relevant animal-agriculture or advocacy space must not be named, mapped, profiled, or made targetable by this website.

Organizations and facilities are the default subjects. Names or public statements from high-level executives and relevant public figures may be included exceptionally when directly relevant to their public professional role, supported by public sources, and approved through documented maintainer review explaining that relevance. This exception never permits publishing private contact details, home addresses, personal routines, family information, or other information that could facilitate harassment or targeting.

User submissions must be screened for doxxing, personal addresses, worker-identifying details, threats, harassment, and targeting intent. A facility address must not be treated as permission to expose the people who work or live there. When a source conflates a facility with an individual, redact or exclude individual-level details from public outputs and separately assess whether restricted retention is justified under section 2.

### Residential, private, harmful, or incorrectly located records

Anyone may request removal or correction of an address and its associated coordinates when the record identifies a residence or private personal location, maps the wrong property, exposes individuals, or contains materially incorrect or harmful identifying information. Affected residents do not need to obtain an upstream government correction before this project acts.

Confirmed residential or private personal addresses and associated precise coordinates must be removed from public outputs. Mixed residential/business sites and locations whose status is unclear require review; suppress precise address and coordinate fields while a credible privacy or safety concern remains unresolved. A registered office, mailing address, or geocoder match is not sufficient evidence of an operating facility. Private ownership of a commercial facility alone is not a reason for removal: the distinction is between relevant facility evidence and exposure of private life.

Where an address or point is confirmed incorrect, remove the incorrect location from current public outputs and publish a replacement only when supported by evidence and eligible under this policy. Suppress harmful identifying details; withdraw the public record if field-level removal cannot adequately address the issue. A coarse regional description may remain only if it does not re-identify the protected location. Do not publish a substitute guessed point.

Public-source availability does not override these protections. Public removal and deletion from retained storage must both be considered; retaining the original is not the default outcome of a removal request. Reimports and new geocoding runs must honor active restrictions, using the minimum necessary protected record references to prevent re-exposure. Only an explicit documented review may lift a restriction.

## 9. Accountable correction

When an error is found, document the correction, its evidence where safe to retain, who or what made the decision, and when it took effect. Preserve non-sensitive history and clearly mark superseded findings. Previous releases are not an exception to privacy restrictions; withdraw or replace affected public artifacts with labeled sanitized versions and preserve a safe correction notice.

### Requests and response workflow

Send a correction, privacy, or address/coordinate removal request to **untileverycageproject@protonmail.com**. Include the public record link or ID, the concern, the requested action, and optional supporting evidence. Put “Privacy/location removal” in the subject for a location-exposure concern. Do not post sensitive evidence in a public issue. Do not request identity documents, additional private addresses, or other sensitive material unless necessary for the particular review; use the least intrusive verification that is sufficient.

1. Log a restricted case and assign a responsible maintainer. Prioritize credible ongoing exposure or safety concerns, suppressing affected public details promptly pending review. This is not an emergency-response service.
2. Assess source evidence, relevance, accuracy, residential overlap, publication risk, and any need for continued restricted retention. Do not reject a concern solely because the information came from government data.
3. Record and implement the decision: correction, removal, restriction, or a reasoned refusal. Set a next review date for unresolved cases and communicate status and the outcome through the requester's provided contact route. Observe applicable response deadlines; do not promise an unstaffed response SLA.
4. Propagate accepted changes through all project-controlled public outputs and caches. Mark affected releases and notify known downstream recipients where appropriate. The project cannot guarantee recall of independent third-party copies; disclose that limit and take feasible steps to request correction or removal.
5. Verify the result and ensure future releases and restores do not republish suppressed details. Record any incomplete propagation work. Permit reconsideration with new evidence and a second reviewer where available.

Requester contact information and supporting private evidence are restricted, collected minimally, and assigned a documented retention/review period. Public correction notices must not reveal the removed information or the requester's identity.

## 10. Accessible explanation

Every public record should have a clear path to its source, observation date, confidence or review state, and relevant limitations. Technical complexity is not a reason to hide uncertainty from users.

## 11. Visitor privacy

Visitor interest in a facility, region, or campaign can itself be sensitive. The requirements below are intended controls, not a statement that current hosting or provider behavior has already been audited.

- Do not introduce advertising trackers, cross-site behavioral tracking, fingerprinting, or visitor profiles. Optional audience measurement must be justified, minimize collection, and avoid precise locations, raw search queries, or per-person browsing histories.
- Collect application and infrastructure logs only for documented operational/security purposes. Minimize identifiers and request payloads, restrict access, and set explicit short retention periods justified by purpose. Record the actual periods and deletion behavior after auditing the application, hosting/CDN, proxy, and error-reporting configurations; do not invent a duration or promise no logging without verification.
- Make location entry optional; town/postcode search must work without device geolocation. Do not persist a visitor's home address or precise device location by default, include it in analytics, or place it in shared links. Explain when a requested search sends location information to a provider.
- Inventory external tile, geocoding, asset, analytics, and hosting services. Document what each receives, why it is needed, and any known retention or control limits. Prefer reduced disclosure where feasible. No analytics script does not imply that no third party receives network or location-related information.
- Publish a plain-language account of verified visitor-data practices and known limitations before launching affected v2 features. Reassess it when providers or configurations change. Do not claim anonymity, absence of logs, or protections outside the project's demonstrated control.

## 12. Maintainer availability and publication authority

Keep a restricted operational record of the responsible maintainer, publication authority, and any backup who has explicitly agreed to serve and has suitable access. Do not imply a second reviewer or standing legal relationship exists when none is established. Contributors may escalate uncertainty without making novel privacy or legal decisions themselves.

When no authorized reviewer is available, new publication requiring human approval pauses. Existing releases may remain available only while eligible under current restrictions; compliant acquisition and private staging may continue. An authorized operator may still urgently suppress affected public details under the removal procedure. If a known exposure cannot be safely isolated, restrict the affected public capability rather than allowing the publication pause to block protective action. Record pending cases, deadlines, and a handover plan; absence does not suspend applicable obligations.

Implement this through actual release permissions and deployment controls. A written pause rule alone does not prevent a compromised account from publishing. Use least privilege, protected approval paths, and a tested ability to restrict publication; outstanding controls belong in the implementation checklist.

## 13. Legal demands and preservation

Route legal demands to the responsible maintainer through the private contact in section 9. Record receipt, deadlines, sender, requested scope, and relevant case references in restricted storage. Seek qualified legal advice promptly to assess authenticity, authority, scope, disclosure restrictions, and any preservation or response obligations. Do not assume a demand is valid or invalid because of who sent it, and do not ignore deadlines while seeking advice.

Do not disclose private material merely because a demand letter requests it. Make any disclosure through an authorized, documented process after assessing applicable requirements, and limit it to what is appropriately required or otherwise lawfully justified. Do not promise blanket refusal or automatic compliance. Ordinary correction and privacy requests remain eligible for prompt action even when submitted through counsel.

Before deleting potentially relevant material, assess preservation obligations and obtain qualified guidance where needed. Restrict access while that assessment occurs. Any necessary preservation must be narrowly scoped, documented, and periodically reviewed; it does not authorize continued public exposure or indefinite retention of unrelated information.

Consider notifying affected people and publishing a sanitized account or aggregate transparency information only where lawful and appropriate, after considering confidentiality, safety, and advice. Do not publish the private demand or requester details by default. Record the decision and any limits on disclosure. [EFF's guidance for online service providers](https://www.eff.org/wp/osp) is background, not a determination of the project's obligations or a claim of legal representation.

## 14. Amendments and presentation

Version policy changes and record their date, substance, rationale, and approval reference in the policy changelog. Keep prior policy versions available through repository history. Update the summary and supporting guidance when their meaning changes. Announce material changes through the repository changelog and, once available, the public policy page; do not imply announcements were made through channels that do not exist.

The full policy governs. The short summary and eventual public page explain it without weakening its requirements or asserting unfinished controls are operational. Public-facing claims must describe verified behavior and disclose relevant gaps.

## Developer rule

Use a new event, version, or review decision for ordinary corrections. For exposure, privacy, or harmful-retention cases, restrict public access first and follow the exceptional-removal procedure; history preservation must not prevent that response. Restrict or pause affected publication when policy compliance is uncertain. Escalate unresolved matters to the responsible maintainer and document the decision without spreading sensitive data.

Contributors must not be expected to make novel privacy, publication, or legal judgments alone. Maintainers own release approval and exceptional retention/removal decisions. Reviewers should disclose relevant conflicts, seek a second reviewer where practical, and use recorded identifiers rather than publishing personal reviewer details. Changes affecting privacy or publication require documented review; automated acquisition is not publication authorization.

This policy sets standards and responsibilities; it does not confer legal immunity on the project or contributors or replace applicable obligations. Jurisdiction-specific questions and any public terms or liability language require qualified legal review. General privacy guidance, such as the [ICO's guide to individual rights](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/individual-rights/individual-rights/), is a reference rather than a determination of which laws apply to this project.

Version: 1.0  
Status: governing project policy; not yet publicly published  
Last reviewed: 2026-09-12
