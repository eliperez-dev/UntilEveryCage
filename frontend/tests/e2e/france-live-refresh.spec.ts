import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';

test('completed France DGAL CLI run is API-readable and selectable at approximate commune locations', async ({ page }) => {
  test.setTimeout(180_000);
  const sourceId = process.env.UEC_E2E_FR_SOURCE_ID;
  const runId = process.env.UEC_E2E_FR_RUN_ID;
  const ledgerPath = process.env.UEC_E2E_FR_LEDGER_PATH;
  test.skip(!sourceId || !runId || !ledgerPath, 'Requires a completed France DGAL CLI run and its private runtime ledger.');
  expect(['fr.dgal.section-i', 'fr.dgal.section-ii']).toContain(sourceId);

  const ledger = JSON.parse(await readFile(ledgerPath!, 'utf8'));
  expect(ledger.status).toBe('imported');
  expect(ledger.source_id).toBe(sourceId);
  expect(ledger.run_id).toBe(runId);
  expect(ledger.public_rows).toBe(0);
  expect(ledger.preview_import.status).toBe('imported');
  expect(ledger.preview_import.public_release_count).toBe(0);
  expect(ledger.preview_import.public_projection_count).toBe(0);
  expect(ledger.acquisition.source_id).toBe(sourceId);
  expect(ledger.acquisition.run_id).toBe(runId);
  expect(ledger.acquisition.sha256).toMatch(/^[a-f0-9]{64}$/i);
  expect(ledger.acquisition.adapter_version).toBe('fr-dgal-853-v2');
  expect(ledger.acquisition.config_version).toBe('fr-dgal-853-txt-v2');
  expect(ledger.acquisition.rights_caveat).toContain('non-commercial reuse');
  expect(ledger.schema_fingerprint).toMatch(/^[a-f0-9]{64}$/i);
  expect(ledger.normalized_sha256).toMatch(/^[a-f0-9]{64}$/i);
  expect(ledger.candidate_handoff_sha256).toMatch(/^[a-f0-9]{64}$/i);
  expect(ledger.coordinate_precision_breakdown.exact).toBe(0);
  expect(ledger.coordinate_precision_breakdown.approximate_city_display).toBeGreaterThan(0);

  const requests: string[] = [];
  page.on('request', request => requests.push(request.url()));
  await page.goto(`/#/map?f1a=field&source=${encodeURIComponent(sourceId!)}&lat=46.6&lon=2.2&z=5`);
  await expect(page.locator('[data-data-mode="real-preview"]')).toBeVisible();

  const api = await page.evaluate(async (source) => {
    const countsResponse = await fetch('/dev/real-preview/counts', { cache: 'no-store' });
    const counts = await countsResponse.json();
    const listResponse = await fetch(`/dev/real-preview/locations?source_id=${encodeURIComponent(source)}&limit=1`, { cache: 'no-store' });
    const list = await listResponse.json();
    const item = list.data[0];
    const search = await fetch(`/dev/real-preview/locations?source_id=${encodeURIComponent(source)}&q=${encodeURIComponent(item.city)}&limit=20`, { cache: 'no-store' }).then(response => response.json());
    const detail = await fetch(`/dev/real-preview/locations/${item.candidate_id}`, { cache: 'no-store' }).then(response => response.json());
    const viewport = await fetch(`/dev/real-preview/viewport?source_id=${encodeURIComponent(source)}&west=-6&south=41&east=11&north=52&limit=20`, { cache: 'no-store' }).then(response => response.json());
    return { counts, list, search, detail, viewport, item };
  }, sourceId!);
  expect(api.counts.meta.runtime_ledger.some((entry: any) => entry.source_id === sourceId && entry.run_id === runId)).toBe(true);
  expect(api.list.data).toHaveLength(1);
  expect(api.item.display_precision).toBe('city_reference_approximate');
  expect(api.search.data.some((item: any) => item.candidate_id === api.item.candidate_id)).toBe(true);
  expect(api.detail.data.candidate_id).toBe(api.item.candidate_id);
  expect(api.viewport.data.some((item: any) => item.source_id === sourceId && item.display_precision === 'city_reference_approximate')).toBe(true);
  expect(api.item.project_approval).toBe(false);

  await expect(page.locator('.maplibregl-canvas')).toBeVisible();
  await expect(page.getByRole('button', { name: /Open approximate city location/ }).first()).toBeVisible({ timeout: 90_000 });
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.isStyleLoaded() && map.querySourceFeatures('locations').some((feature: any) => feature.properties.kind === 'aggregate' && feature.properties.precision === 'city');
  }, undefined, { timeout: 90_000 });
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.queryRenderedFeatures({ layers: ['aggregate-outer', 'cluster-outer'] }).length ?? 0), { timeout: 30_000 }).toBeGreaterThan(0);

  await page.getByRole('button', { name: /Open approximate city location/ }).first().click();
  const member = page.locator('#field-record-list ol li button').first();
  await expect(member).toBeVisible();
  await expect(member).toContainText('Approximate city location · not a facility point');
  await member.click();
  const detail = page.locator('.reading-sheet');
  await expect(detail.getByText('Approximate city location · not a facility point')).toBeVisible();
  await expect(detail.getByText(/Approximate city location — not a facility point; private preview only/)).toBeVisible();
  expect(requests.some(url => new URL(url).pathname === '/dev/real-preview/refresh')).toBe(false);
  expect(requests.join('\n')).not.toMatch(/postgresql:|password|secret|uec-dev-preview-token/i);
  expect(await page.locator('body').innerText()).not.toMatch(/x-uec-dev-preview-token|postgresql:|uec-dev-preview-token/i);
  expect(JSON.stringify(await page.evaluate(() => ({ local: localStorage, session: sessionStorage }))).toLowerCase()).not.toMatch(/uec-dev-preview-token|postgresql:|password|secret/i);
});
