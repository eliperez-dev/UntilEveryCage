import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';

test('one local operator action acquires, imports, maps, and opens newly acquired Belgium detail', async ({ page }) => {
  test.setTimeout(900_000);
  const refreshCalls: string[] = [];
  const apiResponses: Array<{ url: string; status: number }> = [];
  page.on('request', request => {
    if (new URL(request.url()).pathname === '/dev/real-preview/refresh') refreshCalls.push(request.method());
  });
  page.on('response', response => {
    if (new URL(response.url()).pathname.startsWith('/dev/real-preview/')) apiResponses.push({ url: response.url(), status: response.status() });
  });

  await page.goto('/#/map?f1a=field&lat=50.7&lon=4.6&z=8&list=closed');
  await expect(page.locator('[data-data-mode="real-preview"]')).toBeVisible();
  const existingRunId = process.env.UEC_E2E_EXISTING_RUN_ID;
  let completedRunId: string;
  if (existingRunId) {
    completedRunId = existingRunId;
    const ledgerPath = process.env.UEC_E2E_EXISTING_LEDGER_PATH;
    if (!ledgerPath) throw new Error('UEC_E2E_EXISTING_LEDGER_PATH is required in completed-run mode.');
    const completedLedger = JSON.parse(await readFile(ledgerPath, 'utf8'));
    expect(completedLedger.status).toBe('imported');
    expect(completedLedger.run_id).toBe(existingRunId);
    expect(completedLedger.preview_import.status).toBe('imported');
    expect(completedLedger.preview_import.normalized_sha256).toMatch(/^[a-f0-9]{64}$/i);
    expect(completedLedger.preview_import.idempotent).toBe(true);
    expect(completedLedger.preview_import.public_release_count).toBe(0);
    expect(completedLedger.preview_import.public_projection_count).toBe(0);
    expect(completedLedger.public_rows).toBe(0);
    const readiness = await page.evaluate(async () => await (await fetch('/dev/real-preview/counts', { cache: 'no-store' })).json());
    expect(readiness.api_version).toBe('real-preview-v1');
    expect(readiness.meta.runtime_ledger.some((entry: { source_id?: string; run_id?: string }) => entry.source_id === 'be.locations' && entry.run_id === existingRunId)).toBe(true);
    expect(readiness.data.facility_candidate_count).toBe(completedLedger.preview_import.facility_candidate_count);
    expect(readiness.data.map_visible_count).toBe(completedLedger.map_visible_count);
    expect(readiness.data.map_visible_count).toBe(completedLedger.preview_import.map_visible_count);
    expect(readiness.data.map_visible_count).toBeLessThanOrEqual(readiness.data.facility_candidate_count);
  } else {
    const refreshResponsePromise = page.waitForResponse(response => new URL(response.url()).pathname === '/dev/real-preview/refresh');
    await page.getByRole('button', { name: 'Refresh Belgium data' }).click();
    const refreshResponse = await refreshResponsePromise;
    await expect(page.getByRole('button', { name: 'Acquiring…' })).toBeDisabled({ timeout: 10_000 });
    const completion = page.getByRole('status').filter({ hasText: /observations.*facilities.*map locations.*run preview-be-locations-/ });
    const failure = page.getByRole('alert');
    const terminal = await Promise.race([
      completion.waitFor({ state: 'visible', timeout: 840_000 }).then(() => 'succeeded' as const),
      failure.waitFor({ state: 'visible', timeout: 840_000 }).then(() => 'failed' as const),
    ]);
    if (terminal === 'failed') {
      const message = await failure.innerText();
      throw new Error(`button-created source job reached terminal failure: ${message}`);
    }
    expect(refreshCalls).toEqual(['POST']);
    expect(refreshResponse.status()).toBe(200);
    const refreshEnvelope = await refreshResponse.json();
    expect(refreshEnvelope.api_version).toBe('real-preview-v1');
    const refreshed = refreshEnvelope.data;
    expect(refreshed.status).toBe('imported');
    expect(refreshed.observations).toBeGreaterThan(0);
    expect(refreshed.facility_candidates).toBeGreaterThan(0);
    expect(refreshed.map_visible_count).toBeGreaterThan(0);
    expect(refreshed.map_visible_count).toBeLessThanOrEqual(refreshed.facility_candidates);
    const completionText = await completion.innerText();
    completedRunId = completionText.match(/run (preview-be-locations-[0-9a-f-]{36})/i)?.[1] ?? '';
    expect(refreshed.run_id).toBe(completedRunId);
    const readiness = await page.evaluate(async () => await (await fetch('/dev/real-preview/counts', { cache: 'no-store' })).json());
    expect(readiness.data.facility_candidate_count).toBe(refreshed.facility_candidates);
    expect(readiness.data.map_visible_count).toBe(refreshed.map_visible_count);
    expect(readiness.meta.runtime_ledger.some((entry: { run_id?: string }) => entry.run_id === completedRunId)).toBe(true);
  }

  const bodyText = await page.locator('body').innerText();
  expect(bodyText).toMatch(/Approximate city location/);
  expect(bodyText).toContain('not a facility point');
  await expect(page.locator('.maplibregl-canvas')).toBeVisible();
  await expect(page.getByRole('button', { name: /Results [1-9][0-9]*/ })).toBeVisible();
  await expect(page.getByText('Loading map records…')).toHaveCount(0, { timeout: 90_000 });
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.isStyleLoaded() && map.querySourceFeatures('locations').some((feature: any) => feature.properties.kind === 'aggregate' && feature.properties.precision === 'city');
  }, undefined, { timeout: 90_000 });
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.queryRenderedFeatures({ layers: ['aggregate-outer', 'cluster-outer'] }).length ?? 0), { timeout: 15_000 }).toBeGreaterThan(0);

  // The accessible feature control is generated from the exact aggregate features
  // supplied to MapLibre, giving keyboard and pointer users a deterministic map interaction.
  const aggregateMembers = page.locator('#field-record-list ol li button');
  await page.getByRole('button', { name: /Open approximate city location/ }).first().click();
  await expect(aggregateMembers.first()).toBeVisible();
  const aggregateLabels = await aggregateMembers.allInnerTexts();
  expect(aggregateLabels.length).toBeGreaterThan(0);
  expect(aggregateLabels.every(label => label.includes('be.locations') && label.includes('Approximate city location · not a facility point'))).toBe(true);
  await aggregateMembers.first().click();
  await expect(page.getByRole('heading', { level: 2 })).toBeVisible();
  await expect(page.locator('.reading-sheet').getByRole('heading', { level: 2, name: /be\.locations/ })).toBeVisible();
  await expect(page.locator('.reading-sheet').getByText('Approximate city location · not a facility point')).toBeVisible();
  await expect(page.locator('.reading-sheet').getByText(/Approximate city location — not a facility point; private preview only/)).toBeVisible();

  const storage = await page.evaluate(() => ({ local: JSON.stringify(localStorage), session: JSON.stringify(sessionStorage) }));
  expect(JSON.stringify(storage)).not.toMatch(/uec-dev-preview-token|postgresql:|preview-[a-z0-9-]{20,}/i);
  expect(page.url()).not.toMatch(/token|password|secret/i);
  expect(bodyText).not.toMatch(/uec-dev-preview-token|postgresql:|x-uec-dev-preview-token/i);
  expect(apiResponses.some(item => item.url.includes('token'))).toBe(false);
  expect(apiResponses.some(item => item.url.includes('/locations?'))).toBe(true);
  expect(apiResponses.some(item => item.url.includes('/viewport?'))).toBe(true);
  expect(apiResponses.some(item => item.url.includes('/counts'))).toBe(true);
  expect(apiResponses.some(item => item.url.includes('/locations/') && item.status === 200)).toBe(true);
  expect(apiResponses.every(item => item.status >= 200 && item.status < 300)).toBe(true);
});
