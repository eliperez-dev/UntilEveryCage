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
    const unmapped = mapRealPreviewCandidate(parseRealPreviewCandidate(record({ location_class: 'unmapped_private_observation', display_precision: 'city_postal_coarse', latitude: null, longitude: null, coordinate_precision: null })));
    expect([exact.precision, approximate.precision, coarse.precision, unmapped.precision]).toEqual(['exact', 'approximate', 'coarse', 'unmapped']);
    expect(coarse.latitude).toBeNull();
    expect(unmapped.latitude).toBeNull();
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
    expect(mapRealPreviewCandidate(absent).name).toBe('Name unavailable');
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
    const searchPage = await repository.list({ query: 'Lyon', limit: 200 });
    const viewportPage = await repository.viewport({ west: 1, south: 44, east: 6, north: 47 }, { cursor: candidateId, limit: 500 });
    expect(searchPage.records[0]?.candidateId).toBe(candidateId);
    expect(searchPage.nextCursor).toBe(candidateId);
    expect(new URL(`http://localhost${calls[0]!.url}`).searchParams.get('q')).toBe('Lyon');
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
