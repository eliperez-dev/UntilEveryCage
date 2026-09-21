import { describe, expect, it } from 'vitest';
import { dimensionsFromFacets, dimensionsFromLocations, displayValue } from '../../src/features/coverage/coverageModel';

describe('coverage model', () => {
  it('keeps dimensions separate and preserves facet counts', () => {
    const result = dimensionsFromFacets({ display_precision: [{ value: 'exact', count: 4 }], source_type: [{ value: 'official', count: 4 }], lifecycle_status: [{ value: 'active_observed', count: 3 }] });
    expect(result.map(dimension => dimension.key)).toEqual(['display_precision', 'source_type', 'lifecycle_status']);
    expect(result[0]?.values[0]?.count).toBe(4);
  });

  it('derives explicitly synthetic fixture dimensions from evidence fields', () => {
    const result = dimensionsFromLocations([{ id: 'one', name: 'One', region: 'DK', category: 'dairy', lat: null, lon: null, observed: '2026', source: 'Test', evidence: { sourceType: 'official', factualReviewStatus: 'recorded', reviewerRole: null, privacyScreeningStatus: 'passed', projectApproval: 'approved', publicationProfile: 'official', publicationWarning: null, sourceId: 'one', sourceUrl: 'https://example.test/one', provenanceSource: 'Test', sourceRightsStatus: 'cleared', retrievedAt: '2026', displayPrecision: 'unmapped', lifecycleStatus: 'status_unknown', observationCount: null } }]);
    expect(result.find(dimension => dimension.key === 'display_precision')?.values).toEqual([{ value: 'unmapped', count: 1 }]);
  });

  it('uses human labels for public vocabulary values', () => expect(displayValue('user_submitted')).toBe('Community-submitted'));
});
