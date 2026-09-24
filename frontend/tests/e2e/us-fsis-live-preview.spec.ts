import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';

test('fresh FSIS CLI run is reconciled and selectable in the read-only preview', async ({ page }) => {
  test.setTimeout(180_000);
  const sourceId = 'us.fsis';
  const runId = process.env.UEC_E2E_FSIS_RUN_ID;
  const ledgerPath = process.env.UEC_E2E_FSIS_LEDGER_PATH;
  if (!runId || !ledgerPath) throw new Error('Provide the completed FSIS CLI run ID and private runtime ledger path.');
  const ledger = JSON.parse(await readFile(ledgerPath, 'utf8'));
  expect(ledger.status).toBe('imported');
  expect(ledger.source_id).toBe(sourceId);
  expect(ledger.run_id).toBe(runId);
  expect(ledger.public_rows).toBe(0);
  expect(ledger.preview_import.idempotent).toBe(true);
  expect(ledger.preview_import.public_release_count).toBe(0);
  expect(ledger.preview_import.public_projection_count).toBe(0);
  expect(ledger.acquisition.directory.publication_date).toBe(ledger.acquisition.demographics.publication_date);
  expect(ledger.acquisition.directory.publication_date).toMatch(/^2026-/);
  expect(ledger.acquisition.directory.sha256).toMatch(/^[a-f0-9]{64}$/i);
  expect(ledger.acquisition.demographics.sha256).toMatch(/^[a-f0-9]{64}$/i);
  expect(ledger.quarantine.accepted_rows).toBe(ledger.preview_import.observation_count);
  expect(ledger.quarantine.quarantined_rows).toBe(0);
  expect(ledger.coordinate_precision_breakdown.exact).toBe(0);
  expect(ledger.coordinate_precision_breakdown.source_provided_unspecified).toBe(ledger.map_visible_count);

  const requestUrls: string[] = [];
  page.on('request', request => requestUrls.push(request.url()));
  await page.goto('/#/map?f1a=field&source=us.fsis&lat=39&lon=-98&z=4');
  await expect(page.locator('[data-data-mode="real-preview"]')).toBeVisible();

  const api = await page.evaluate(async (source) => {
    const countsResponse = await fetch('/dev/real-preview/counts', { cache: 'no-store' });
    const counts = await countsResponse.json();
    const list = await fetch(`/dev/real-preview/locations?source_id=${encodeURIComponent(source)}&limit=1`, { cache: 'no-store' }).then(response => response.json());
    const item = list.data[0];
    const search = await fetch(`/dev/real-preview/locations?source_id=${encodeURIComponent(source)}&q=${encodeURIComponent(item.city)}&limit=50`, { cache: 'no-store' }).then(response => response.json());
    const detail = await fetch(`/dev/real-preview/locations/${item.candidate_id}`, { cache: 'no-store' }).then(response => response.json());
    const viewport = await fetch(`/dev/real-preview/viewport?source_id=${encodeURIComponent(source)}&west=-126&south=23&east=-65&north=50&limit=500`, { cache: 'no-store' }).then(response => response.json());
    return { counts, list, search, detail, viewport, item };
  }, sourceId);
  expect(api.counts.meta.runtime_ledger.some((entry: any) => entry.source_id === sourceId && entry.run_id === runId)).toBe(true);
  expect(api.counts.data.facility_candidate_count).toBe(ledger.preview_import.facility_candidate_count);
  expect(api.counts.data.map_visible_count).toBe(ledger.map_visible_count);
  expect(api.list.data).toHaveLength(1);
  expect(api.search.data.some((entry: any) => entry.candidate_id === api.item.candidate_id)).toBe(true);
  expect(api.detail.data.candidate_id).toBe(api.item.candidate_id);
  expect(api.item.source_id).toBe(sourceId);
  expect(api.item.display_precision).toBe('approximate_source_provided_pending_review');
  expect(api.viewport.data.some((entry: any) => entry.source_id === sourceId)).toBe(true);

  const feature = page.getByRole('button', { name: /^Open approximate source location for us\.fsis$/ }).first();
  await expect(feature).toBeVisible({ timeout: 90_000 });
  const locality = (await feature.innerText()).split(' · ').slice(1).join(' · ').trim();
  expect(locality).not.toBe('');
  await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.flyTo({ center: [-98, 39], zoom: 4, duration: 0 }));
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.isStyleLoaded() && map.querySourceFeatures('locations').some((entry: any) => entry.properties.kind === 'approximate');
  }, undefined, { timeout: 90_000 });
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.queryRenderedFeatures({ layers: ['approximate-points'] }).length ?? 0), { timeout: 60_000 }).toBeGreaterThan(0);
  await feature.click();
  const detail = page.locator('.reading-sheet');
  await expect(detail.getByText('Approximate source coordinate · pending review', { exact: true })).toBeVisible();
  await expect(detail.getByText(/Private real V2 candidate — not project-approved or published/i)).toBeVisible();
  expect(requestUrls.some(url => new URL(url).pathname === '/dev/real-preview/refresh')).toBe(false);
  expect(requestUrls.join('\n')).not.toMatch(/postgresql:|password|secret|uec-dev-preview-token/i);
  expect(await page.locator('body').innerText()).not.toMatch(/x-uec-dev-preview-token|postgresql:|uec-dev-preview-token/i);
  expect(JSON.stringify(await page.evaluate(() => ({ local: localStorage, session: sessionStorage }))).toLowerCase()).not.toMatch(/uec-dev-preview-token|postgresql:|password|secret/i);
});
