import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

test('CLI-acquired Italy run is visible and selectable in the read-only preview', async ({ page }) => {
  test.setTimeout(180_000);
  const sourceId = process.env.UEC_E2E_SOURCE_ID ?? 'it.853-2004';
  const runId = process.env.UEC_E2E_EXISTING_RUN_ID;
  const ledgerPath = process.env.UEC_E2E_EXISTING_LEDGER_PATH;
  if (!['it.853-2004', 'it.1069-2009'].includes(sourceId) || !runId || !ledgerPath) throw new Error('Provide an Italy source ID, completed CLI run ID, and runtime ledger path.');
  const ledger = JSON.parse(readFileSync(resolve(ledgerPath), 'utf8'));
  expect(ledger.status).toBe('imported');
  expect(ledger.source_id).toBe(sourceId);
  expect(ledger.run_id).toBe(runId);
  expect(ledger.public_rows).toBe(0);
  expect(ledger.preview_import.status).toBe('imported');
  expect(ledger.preview_import.idempotent).toBe(true);
  expect(ledger.preview_import.public_release_count).toBe(0);
  expect(ledger.preview_import.public_projection_count).toBe(0);
  expect(ledger.normalized_sha256).toMatch(/^[a-f0-9]{64}$/i);
  expect(ledger.schema_fingerprint).toMatch(/^[a-f0-9]{64}$/i);
  const precision = ledger.coordinate_precision_breakdown;
  expect(precision.exact).toBe(0);
  expect(precision.source_precision_unknown).toBe(ledger.preview_import.numeric_coordinate_count);
  expect(precision.city_or_postal_only).toBe(ledger.preview_import.city_postal_count);
  expect(precision.unmapped).toBe(ledger.preview_import.unmapped_map_candidate_count);
  expect(ledger.acquisition.run_id).toBe(runId);

  const requestUrls: string[] = [];
  page.on('request', request => requestUrls.push(request.url()));
  await page.goto(`/#/map?f1a=field&source=${encodeURIComponent(sourceId)}&lat=42.5&lon=12.5&z=5`);
  await expect(page.locator('[data-data-mode="real-preview"]')).toBeVisible();
  const readiness = await page.evaluate(async () => {
    const response = await fetch('/dev/real-preview/counts', { cache: 'no-store' });
    return { status: response.status, body: await response.json() };
  });
  expect(readiness.status).toBe(200);
  expect(readiness.body.meta.runtime_ledger.some((entry: any) => entry.source_id === sourceId && entry.run_id === runId)).toBe(true);
  expect(readiness.body.data.facility_candidate_count).toBe(ledger.preview_import.facility_candidate_count);
  expect(readiness.body.data.map_visible_count).toBe(ledger.map_visible_count);

  const feature = page.getByRole('button', { name: `Open approximate source location for ${sourceId}` }).first();
  await expect(feature).toBeVisible({ timeout: 90_000 });
  const featureLabel = await feature.innerText();
  const locality = featureLabel.split(' · ').slice(1).join(' · ').trim();
  expect(locality).not.toBe('');
  await page.getByRole('searchbox').fill(locality);
  await expect(page.getByText(sourceId, { exact: false }).first()).toBeVisible();
  await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.flyTo({ center: [13, 42], zoom: 8, duration: 0 }));
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.isStyleLoaded() && map.querySourceFeatures('locations').some((feature: any) => feature.properties.kind === 'approximate');
  }, undefined, { timeout: 90_000 });
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.queryRenderedFeatures({ layers: ['approximate-points'] }).length ?? 0), { timeout: 60_000 }).toBeGreaterThan(0);
  await feature.click();
  const detail = page.locator('.reading-sheet');
  await expect(detail.getByText('Approximate source coordinate · precision unknown', { exact: true })).toBeVisible();
  await expect(detail.getByText(/precision unknown; private preview only.*not approved or published/i)).toBeVisible();
  await expect(detail.getByText('pending_human_privacy_review')).toBeVisible();
  const apiRequests = requestUrls.map(url => new URL(url)).filter(url => url.pathname.startsWith('/dev/real-preview/'));
  expect(apiRequests.some(url => url.pathname.endsWith('/locations') && url.searchParams.get('source_id') === sourceId && url.searchParams.has('q'))).toBe(true);
  expect(apiRequests.some(url => url.pathname.endsWith('/viewport') && url.searchParams.get('source_id') === sourceId)).toBe(true);
  expect(apiRequests.some(url => /^\/dev\/real-preview\/locations\/[0-9a-f-]+$/i.test(url.pathname))).toBe(true);
  expect(requestUrls.some(url => new URL(url).pathname === '/dev/real-preview/refresh')).toBe(false);
  expect(requestUrls.join('\n')).not.toMatch(/postgresql:|password|secret|uec-dev-preview-token/i);
  expect(await page.locator('body').innerText()).not.toMatch(/x-uec-dev-preview-token|postgresql:|uec-dev-preview-token/i);
  expect(JSON.stringify(await page.evaluate(() => ({ local: localStorage, session: sessionStorage }))).toLowerCase()).not.toMatch(/uec-dev-preview-token|postgresql:|password|secret/i);
});
