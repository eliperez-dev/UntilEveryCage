import type { Page } from '@playwright/test';

/** A valid, entirely synthetic empty release for navigation-only checks. */
export async function installEmptyPublicMap(page: Page, releaseId: string) {
  const identity = { profile: 'official', release_id: releaseId, manifest_sha256: 'a'.repeat(64), suppression_generation: 1 };
  await page.route('**/api/v2/**', route => {
    const path = new URL(route.request().url()).pathname;
    const envelope = (data: unknown, meta: unknown) => route.fulfill({ status: 200, json: { api_version: 'v2', data, meta } });
    if (path === '/api/v2/releases/manifest') return route.fulfill({ status: 200, json: { api_version: 'v2', data: { ...identity, manifest: {} } } });
    if (path === '/api/v2/map/feed') return envelope({ type: 'FeatureCollection', features: [] }, {
      ...identity, feature_count: 0, public_record_count: 0, unmapped_count: 0, release_label: 'Synthetic release', dataset_version: 'synthetic',
    });
    if (path === '/api/v2/map/matches') return envelope({ facility_ids: [] }, { ...identity, total_count: 0, mapped_count: 0 });
    if (path === '/api/v2/locations') return envelope([], { profile: 'official', release_id: releaseId, ruleset_version: 'synthetic-rules', coverage_note: 'Synthetic navigation fixture.', next_cursor: null, total_count: 0 });
    return route.fulfill({ status: 404, json: {} });
  });
}
