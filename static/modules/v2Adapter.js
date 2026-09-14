export function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

/** Convert a V2 public API record into the legacy map shape. */
export function normalizeV2Location(record, meta = {}) {
    const provenance = record.provenance || {
        source_id: record.provenance_source_id,
        source_name: record.provenance_source_name || record.provenance_source,
        source_url: record.provenance_source_url,
        retrieved_at: record.provenance_retrieved_at
    };
    return {
        ...record,
        establishment_name: record.canonical_name || 'Unnamed facility',
        country: (record.country_code || '').toLowerCase(),
        latitude: record.latitude,
        longitude: record.longitude,
        city: record.city || '',
        type: record.category || record.classification_category || 'unknown',
        v2: {
            facilityId: record.facility_id,
            category: record.category,
            sourceType: record.source_type,
            profile: record.publication_profile,
            displayPrecision: record.display_precision,
            lifecycleStatus: record.lifecycle_status,
            firstObservedAt: record.first_observed_at,
            lastObservedAt: record.last_observed_at,
            observationCount: record.observation_count,
            releaseId: record.release_id,
            rulesetVersion: record.release_ruleset_version,
            provenance,
            releaseCreatedAt: meta.release_created_at,
            coverageNote: meta.coverage_note
        }
    };
}

export async function fetchV2Locations(url, options = {}) {
    const response = await fetch(url, {
        headers: { Accept: 'application/json' },
        ...options
    });
    if (!response.ok) throw new Error(`V2 location request failed: HTTP ${response.status}`);
    const body = await response.json();
    if (body.api_version !== 'v2' || !Array.isArray(body.data)) {
        throw new Error('V2 location response did not match the public contract');
    }
    return {
        locations: body.data.map(record => normalizeV2Location(record, body.meta || {})),
        meta: body.meta || {}
    };
}
