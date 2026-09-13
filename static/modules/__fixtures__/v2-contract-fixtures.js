export const exactOfficialLocation = {
    facility_id: '00000000-0000-0000-0000-000000000001',
    canonical_name: 'Synthetic facility — not a real location',
    country_code: 'DK', city: 'Testby', category: 'slaughter',
    publication_profile: 'official', factual_review_status: 'reviewed',
    privacy_screening_status: 'passed', project_approval: 'approved', reviewer_role: 'maintainer', publication_warning: null,
    display_precision: 'exact', latitude: 55, longitude: 10,
    first_observed_at: '2026-09-13T00:00:00Z', last_observed_at: '2026-09-13T00:00:00Z', observation_count: 1,
    lifecycle_status: 'active_observed', source_type: 'official', provenance_source: 'Synthetic source',
    release_id: 'fixture-release', release_ruleset_version: 'fixture-v1', provenance_source_id: 'fixture.source',
    provenance_source_name: 'Synthetic source', provenance_source_url: 'https://example.invalid/source',
    provenance_retrieved_at: '2026-09-13T00:00:00Z'
};

export const noPromotedRelease = {
    data: [], api_version: 'v2',
    meta: { release_id: null, profile: 'official', coverage_note: 'No promoted release is currently available.' }
};

export const restrictedLocation = {
    ...exactOfficialLocation,
    canonical_name: 'Synthetic restricted record — must never be rendered',
    privacy_screening_status: 'failed'
};
