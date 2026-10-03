import { describe, expect, it, vi } from 'vitest';
import {
  createRealPreviewRepository,
  mapRealPreviewCandidate,
  parseRealPreviewCandidate,
  RealPreviewError,
  type FetchLike,
} from '../../src/api/RealPreviewRepository';
import { selectDesignLabDataMode } from '../../src/design-lab/dataMode';

const candidateId = 'a0000000-0000-4000-8000-000000000001';
const record = (overrides: Record<string, unknown> = {}) => ({
  candidate_id: candidateId,
  source_id: 'fr.dgal.section-i',
  location_class: 'numeric_source_coordinate',
  display_precision: 'source_numeric_pending_review',
  country_code: 'FR',
  city: null,
  postal_code: null,
  latitude: 48.8566,
  longitude: 2.3522,
  coordinate_precision: 'numeric',
  coordinate_review_status: 'pending_human_privacy_review',
  factual_review_status: 'not_reviewed',
  privacy_screening_status: 'pending',
  project_approval: false,
  publication_status: 'not_published',
  preview_label: 'Private real V2 candidate — not project-approved or published',
  ...overrides,
});
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

describe('private real-preview repository', () => {
  it('selects real data only in the explicitly enabled development server mode', () => {
    expect(selectDesignLabDataMode(true, 'real-preview')).toBe('real-preview');
    expect(selectDesignLabDataMode(true, null)).toBe('synthetic');
    expect(selectDesignLabDataMode(false, 'real-preview')).toBe('synthetic');
  });

  it('maps numeric, approximate, coarse, and unmapped records to distinct placement classes', () => {
    const exact = mapRealPreviewCandidate(parseRealPreviewCandidate(record()));
    const approximate = mapRealPreviewCandidate(parseRealPreviewCandidate(record({ display_precision: 'approximate_source_precision_unknown_pending_review' })));
    const coarse = mapRealPreviewCandidate(parseRealPreviewCandidate(record({ location_class: 'city_postal', display_precision: 'city_postal_coarse', latitude: null, longitude: null, coordinate_precision: null, city: 'Lyon' })));
    const localityCandidate = parseRealPreviewCandidate(record({ location_class: 'city_postal', display_precision: 'locality_reference_coarse', latitude: 41.39, longitude: 2.17, coordinate_precision: 'municipality_capital_locality', default_map_scope: false, city: 'Barcelona' }));
    const localityReference = mapRealPreviewCandidate(localityCandidate);
    const unmapped = mapRealPreviewCandidate(parseRealPreviewCandidate(record({ location_class: 'unmapped_private_observation', display_precision: 'city_postal_coarse', latitude: null, longitude: null, coordinate_precision: null })));
    expect([exact.precision, approximate.precision, coarse.precision, localityReference.precision, unmapped.precision]).toEqual(['exact', 'approximate', 'coarse', 'coarse', 'unmapped']);
    expect(coarse.latitude).toBeNull();
    expect(localityCandidate.displayPrecision).toBe('locality_reference_coarse');
    expect(localityCandidate.defaultMapScope).toBe(false);
    expect(localityReference.precision).toBe('coarse');
    expect(unmapped.latitude).toBeNull();
  });

  it('keeps FSIS source-provided coordinates in the visibly unverified private category', () => {
    const fsis = mapRealPreviewCandidate(parseRealPreviewCandidate(record({
      source_id: 'us.fsis',
      display_precision: 'source_provided_unverified',
      coordinate_precision: 'source-provided',
    })));
    expect(fsis).toMatchObject({
      sourceId: 'us.fsis',
      precision: 'approximate',
      coordinatePrecision: 'source-provided',
    });
  });

  it('parses Geoapify display points as provider evidence without changing source-coordinate semantics', () => {
    const providerAddress = parseRealPreviewCandidate(record({
      source_id: 'au.npi.facilities', location_class: 'city_postal', display_precision: 'provider_address_point_high_confidence',
      country_code: 'AU', latitude: -37.8, longitude: 144.9, coordinate_precision: 'provider_address_point_high_confidence',
      coordinate_provider: 'Geoapify', coordinate_method: 'geoapify_forward', coordinate_confidence: 0.97,
      coordinate_confidence_band: 'high', coordinate_review_status: 'automated_high_confidence_private_display',
    }));
    expect(mapRealPreviewCandidate(providerAddress)).toMatchObject({
      precision: 'approximate', coordinateProvider: 'Geoapify', coordinateConfidence: 0.97,
      coordinateMethod: 'geoapify_forward', latitude: -37.8,
    });
    expect(() => parseRealPreviewCandidate(record({
      location_class: 'city_postal', display_precision: 'provider_address_point_high_confidence',
      coordinate_provider: 'Other', coordinate_method: 'other',
    }))).toThrow(RealPreviewError);
  });

  it('rejects zero-zero, out-of-range, non-finite, and incomplete coordinate pairs', () => {
    for (const bad of [
      record({ latitude: 0, longitude: 0 }),
      record({ latitude: 91 }),
      record({ latitude: Number.NaN }),
      record({ longitude: null }),
    ]) expect(() => parseRealPreviewCandidate(bad)).toThrow(RealPreviewError);
    expect(parseRealPreviewCandidate(record({ latitude: 0, longitude: -30 })).latitude).toBe(0);
  });

  it('accepts nullable future allowlisted fields and renders a missing name honestly', () => {
    const parsed = parseRealPreviewCandidate(record({
      display_name: 'Example facility',
      activity_label: null,
      activity_source: 'source classification',
      source_name: 'Example authority',
      source_record_id: 'safe-row-17',
      source_url: 'https://example.test/source',
      source_record_url: null,
      retrieved_at: '2026-01-02T03:04:05Z',
      observed_at: null,
      evidence_summary: 'Summary supplied by the allowlisted API.',
      coordinate_provenance: 'municipality_admin_centre',
      default_map_scope: false,
      map_scope_reason: 'outside_default_map_scope',
    }));
    expect(parsed).toMatchObject({
      displayName: 'Example facility', activityLabel: null, activitySource: 'source classification',
      sourceName: 'Example authority', sourceRecordId: 'safe-row-17',
      sourceUrl: 'https://example.test/source', sourceRecordUrl: null,
      retrievedAt: '2026-01-02T03:04:05Z', observedAt: null,
      evidenceSummary: 'Summary supplied by the allowlisted API.',
      coordinateProvenance: 'municipality_admin_centre',
      defaultMapScope: false,
      mapScopeReason: 'outside_default_map_scope',
    });
    const absent = parseRealPreviewCandidate(record());
    expect(absent.displayName).toBeNull();
    expect(absent.evidenceSummary).toBeNull();
    expect(mapRealPreviewCandidate(absent).name).toBe('Facility candidate');
    expect(mapRealPreviewCandidate(parsed).name).toBe('Example facility');
  });

  it('parses additive taxonomy with safe leaf attribution and falls back on unknown primary keys', () => {
    const candidate = parseRealPreviewCandidate(record({
      taxonomy_display_category: 'research_and_animal_use',
      taxonomy_primary_categories: ['research_and_animal_use'],
      taxonomy_leaf_activities: [{ key: 'animal-use', label: 'Animal use in research' }],
      taxonomy_assignments: [{
        primary_key: 'research_and_animal_use', leaf_key: 'animal-use', leaf_label: 'Animal use in research',
        source_code_reference: 'column activity', source_label_reference: 'activity text', source_code: null,
        source_label: 'Research establishment', method: 'derived', status: 'mapped', taxonomy_version: 'uec-taxonomy-v1',
        crosswalk_version: 'fr-section-i-v1', ruleset_version: 'rules-v1', observation_id: 'obs-1', source_record_id: 'row-1', artifact_id: 'artifact-1',
      }],
    }));
    expect(mapRealPreviewCandidate(candidate)).toMatchObject({ taxonomy: {
      displayCategory: 'research_and_animal_use', leafActivities: [{ label: 'Animal use in research' }],
      assignments: [{ sourceLabel: 'Research establishment', method: 'derived', status: 'mapped' }],
    } });
    const unknown = parseRealPreviewCandidate(record({ taxonomy_display_category: 'future-key', taxonomy_primary_categories: ['future-key'] }));
    expect(mapRealPreviewCandidate(unknown).taxonomy).toMatchObject({ displayCategory: 'unclassified', primaryCategories: ['unclassified'] });
  });

  it('rejects unsafe URLs in future source-link fields', () => {
    expect(() => parseRealPreviewCandidate(record({ source_url: 'javascript:alert(1)' }))).toThrow(RealPreviewError);
    expect(() => parseRealPreviewCandidate(record({ source_record_url: 'http://example.test/record' }))).toThrow(RealPreviewError);
  });

  it('maps the bounded global city/postal cursor and viewport cursor contracts without sending credentials from the browser', async () => {
    const calls: Array<{ url: string; init: RequestInit | undefined }> = [];
    const fetcher: FetchLike = vi.fn(async (input, init) => {
      calls.push({ url: String(input), init });
      return response({ api_version: 'real-preview-v1', data: [record()], meta: { private_preview: true, next_cursor: candidateId } });
    });
    const repository = createRealPreviewRepository(fetcher);
    const searchPage = await repository.list({ query: 'Lyon', sourceId: 'fr.dgal.section-i', categoryKeys: ['slaughter', 'processing_and_preparation'], limit: 200 });
    const viewportPage = await repository.viewport({ west: 1, south: 44, east: 6, north: 47 }, { cursor: candidateId, limit: 500 });
    expect(searchPage.records[0]?.candidateId).toBe(candidateId);
    expect(searchPage.nextCursor).toBe(candidateId);
    expect(new URL(`http://localhost${calls[0]!.url}`).searchParams.get('q')).toBe('Lyon');
    expect(new URL(`http://localhost${calls[0]!.url}`).searchParams.get('source_id')).toBe('fr.dgal.section-i');
    expect(new URL(`http://localhost${calls[0]!.url}`).searchParams.get('category_keys')).toBe('slaughter,processing_and_preparation');
    expect(new URL(`http://localhost${calls[1]!.url}`).searchParams.get('cursor')).toBe(candidateId);
    expect(calls.every(call => !call.url.includes('token') && !JSON.stringify(call.init?.headers).toLowerCase().includes('token'))).toBe(true);
    expect(calls[0]?.init?.cache).toBe('no-store');
  });

  it('returns explicit authentication failures and never substitutes a fixture response', async () => {
    const repository = createRealPreviewRepository(async () => response({}, 401));
    await expect(repository.list()).rejects.toMatchObject({ kind: 'unauthorized' });
  });

  it('maps detail, aggregate counts, and source facets from the API envelopes', async () => {
    const fetcher: FetchLike = async input => {
      if (String(input).endsWith('/counts')) return response({ api_version: 'real-preview-v1', data: { facility_candidate_count: 35073, numeric_coordinate_count: 31504, city_postal_count: 3569, unmapped_candidate_count: 20, default_map_scope_candidate_count: 35000, out_of_default_map_scope_candidate_count: 73 } });
      if (String(input).endsWith('/facets')) return response({ api_version: 'real-preview-v1', data: [{ source_id: 'fr.dgal.section-i', location_class: 'numeric_source_coordinate', default_map_scope: true, count: 100 }] });
      return response({ api_version: 'real-preview-v1', data: record() });
    };
    const repository = createRealPreviewRepository(fetcher);
    expect((await repository.detail(candidateId)).sourceId).toBe('fr.dgal.section-i');
    expect(await repository.counts()).toEqual({ facilityCandidateCount: 35073, numericCoordinateCount: 31504, cityPostalCount: 3569, mapVisibleCount: 31504, unmappedCandidateCount: 20, defaultMapScopeCandidateCount: 35000, outOfDefaultMapScopeCandidateCount: 73 });
    expect(await repository.facets()).toEqual([{ sourceId: 'fr.dgal.section-i', locationClass: 'numeric_source_coordinate', defaultMapScope: true, count: 100 }]);
  });
});
