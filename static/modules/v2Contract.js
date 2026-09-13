/**
 * Runtime boundary for the V2 public API.
 * Keep this deliberately independent from DOM/map code so the future
 * TypeScript frontend can replace it with generated types without changing
 * publication semantics.
 */
export const V2_PROFILES = Object.freeze(['official', 'secondary', 'community']);
export const V2_SOURCE_TYPES = Object.freeze(['official', 'secondary', 'user_submitted']);
export const V2_DISPLAY_PRECISIONS = Object.freeze(['exact', 'city', 'unmapped']);
export const V2_LIFECYCLE_STATUSES = Object.freeze([
    'active_observed',
    'explicitly_closed',
    'not_seen_recently',
    'status_unknown'
]);

const isObject = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const hasString = (record, field) => typeof record[field] === 'string' && record[field].length > 0;
const hasNullableString = (record, field) => record[field] === null || typeof record[field] === 'string';

export function validateV2Location(record) {
    if (!isObject(record)) throw new TypeError('V2 location must be an object');
    for (const field of ['facility_id', 'country_code', 'category', 'publication_profile', 'factual_review_status',
        'privacy_screening_status', 'project_approval', 'display_precision', 'lifecycle_status', 'source_type',
        'release_id', 'release_ruleset_version', 'provenance_source_id', 'provenance_source_name',
        'provenance_source_url', 'provenance_retrieved_at']) {
        if (!hasString(record, field)) throw new TypeError(`V2 location missing ${field}`);
    }
    for (const field of ['canonical_name', 'city', 'reviewer_role']) {
        if (!hasNullableString(record, field)) throw new TypeError(`V2 location has invalid ${field}`);
    }
    if (!hasNullableString(record, 'publication_warning')) throw new TypeError('V2 location has invalid publication_warning');
    if (!V2_PROFILES.includes(record.publication_profile)) throw new TypeError('V2 location has invalid publication_profile');
    if (!V2_SOURCE_TYPES.includes(record.source_type)) throw new TypeError('V2 location has invalid source_type');
    if (!V2_DISPLAY_PRECISIONS.includes(record.display_precision)) throw new TypeError('V2 location has invalid display_precision');
    if (!V2_LIFECYCLE_STATUSES.includes(record.lifecycle_status)) throw new TypeError('V2 location has invalid lifecycle_status');
    if (record.privacy_screening_status !== 'passed') throw new TypeError('V2 location is not privacy eligible');
    if (record.project_approval !== 'approved' && record.publication_profile !== 'community') {
        throw new TypeError('V2 curated location is not project approved');
    }
    if (record.factual_review_status === 'unreviewed' && record.publication_profile === 'community' &&
        record.publication_warning !== 'Unreviewed community claim — not verified by Until Every Cage') {
        throw new TypeError('unreviewed community location is missing its publication warning');
    }
    return record;
}

export function validateV2Envelope(body) {
    if (!isObject(body) || body.api_version !== 'v2' || !isObject(body.meta)) {
        throw new TypeError('V2 response envelope is invalid');
    }
    if (!Array.isArray(body.data) && !isObject(body.data)) throw new TypeError('V2 response data is invalid');
    if (Array.isArray(body.data)) body.data.forEach(validateV2Location);
    else validateV2Location(body.data);
    return body;
}
