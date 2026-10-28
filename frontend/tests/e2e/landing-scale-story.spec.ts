import { expect, test, type Page } from '@playwright/test';
import { englishStoryMessages } from '../../src/app/scale-story/messages';
import { storyTranslations } from '../../src/app/scale-story/translations';

async function installAggregates(page: Page) {
  await page.route('**/api/v2/**', route => {
    const url = new URL(route.request().url()), precision = url.searchParams.get('display_precision');
    if (url.pathname.endsWith('/releases/manifest')) return route.fulfill({ json: { api_version: 'v2', data: { profile: 'official', release_id: 'synthetic-story', manifest: {}, manifest_sha256: 'a'.repeat(64), suppression_generation: 1 } } });
    if (url.pathname.endsWith('/discovery/facets')) return route.fulfill({ json: { api_version: 'v2', meta: { profile: 'official', release_id: 'synthetic-story', ruleset_version: 'synthetic-rules', coverage_scope: 'Synthetic records', count_semantics: 'Synthetic records', release_created_at: '2026-01-01T00:00:00Z', filters: precision ? { display_precision: precision } : {} }, dimensions: precision ? { display_precision: [{ value: precision, count: 2 }], country_code: [{ value: 'DK', count: 2 }] } : { display_precision: [{ value: 'source_reported', count: 2 }, { value: 'approximate', count: 2 }], source_id: [{ value: 'synthetic-source', count: 4 }] } } });
    return route.fulfill({ status: 404, json: {} });
  });
}
test.beforeEach(async ({ page }) => installAggregates(page));

test('the actual landing keeps its route and discovery while the funnel and snake operate', async ({ page }) => {
  await page.goto('./#/?release_id=synthetic-story');
  const route = page.url();
  await expect(page.getByRole('navigation', { name: 'Primary' }).getByRole('link')).toHaveText(['Map', 'Data', 'Contribute', 'About']);
  await expect(page.getByRole('button', { name: 'Find locations near me', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'See the scale', exact: true }).click();
  expect(page.url()).toBe(route);
  const story = page.locator('.scale-story'), canvas = story.locator('canvas');
  await expect(story).toBeFocused();
  await expect(story.getByRole('button', { name: 'Funnel', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await canvas.scrollIntoViewIfNeeded(); await expect(canvas).toHaveAttribute('data-state', 'running');
  await expect.poll(async () => Number(await canvas.getAttribute('data-emitted'))).toBeGreaterThan(50);
  await story.getByRole('button', { name: 'Pause', exact: true }).click();
  await expect(canvas).toHaveAttribute('data-state', 'paused');
  const pixels = await canvas.evaluate(node => node.toDataURL());
  await page.waitForTimeout(120); expect(await canvas.evaluate(node => node.toDataURL())).toBe(pixels);
  await story.getByRole('button', { name: 'Grid', exact: true }).click();
  await expect(story.locator('.canvas-wrap')).toHaveAttribute('data-mode', 'grid');
  await story.getByRole('button', { name: 'Fish', exact: true }).click();
  await expect(story.locator('.rate-date')).toContainText('2019');
  await expect(story.locator('.annual')).toContainText('upper estimate');
  await expect(story.locator('.methods')).not.toHaveAttribute('open');
  await story.locator('summary').click(); await expect(story.locator('.methods')).toContainText('0.25 mL');
  await expect(page.locator('.release-totals')).toContainText('4');
  await expect(page.locator('.maplibregl-map')).toHaveCount(0);
  await expect(story.locator('.map-link')).toHaveAttribute('href', '#/map?release_id=synthetic-story');
});

test('mobile reduced motion remains static, readable and navigable in both themes', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 320, height: 760 });
  await page.goto('./');
  const story = page.locator('.scale-story'), canvas = story.locator('canvas');
  await story.scrollIntoViewIfNeeded(); await expect(canvas).toHaveAttribute('data-state', 'static');
  await expect(story.getByRole('button', { name: 'Pause', exact: true })).toHaveCount(0);
  for (const theme of ['dark', 'light']) {
    if (theme === 'light') await page.locator('.masthead .theme-toggle').click();
    for (const population of ['Land animals', 'Fish']) {
      await story.getByRole('button', { name: population, exact: true }).click();
      for (const mode of ['Funnel', 'Grid']) {
        await story.getByRole('button', { name: mode, exact: true }).click();
        await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        const targets = await story.locator('button,.map-link').evaluateAll(elements => elements.map(e => e.getBoundingClientRect().height));
        expect(targets.every(height => height >= 44)).toBe(true);
      }
    }
  }
  const before = await canvas.evaluate(node => node.toDataURL()); await page.waitForTimeout(100);
  expect(await canvas.evaluate(node => node.toDataURL())).toBe(before);
});

test('offscreen and route departure stop the particle loop; returning starts a clean instance', async ({ page }) => {
  await page.addInitScript(() => {
    const request = window.requestAnimationFrame.bind(window);
    (window as unknown as { storyRaf: number }).storyRaf = 0;
    window.requestAnimationFrame = callback => request(time => { (window as unknown as { storyRaf: number }).storyRaf++; callback(time); });
  });
  await page.goto('./');
  const canvas = page.locator('.scale-story canvas');
  await canvas.scrollIntoViewIfNeeded(); await expect(canvas).toHaveAttribute('data-state', 'running');
  await page.locator('.landing-footer').scrollIntoViewIfNeeded(); await expect(canvas).toHaveAttribute('data-state', 'offscreen');
  await page.waitForTimeout(50);
  const before = await page.evaluate(() => (window as unknown as { storyRaf: number }).storyRaf);
  await page.waitForTimeout(100); expect(await page.evaluate(() => (window as unknown as { storyRaf: number }).storyRaf)).toBe(before);
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'About', exact: true }).click();
  await expect(canvas).toHaveCount(0); await page.waitForTimeout(50);
  const left = await page.evaluate(() => (window as unknown as { storyRaf: number }).storyRaf);
  await page.waitForTimeout(100); expect(await page.evaluate(() => (window as unknown as { storyRaf: number }).storyRaf)).toBe(left);
  await page.goBack(); await expect(page.locator('.scale-story')).toBeVisible();
});

test('the complete story translates in all six languages without mobile overflow', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 320, height: 760 });
  for (const language of ['en', 'es', 'fr', 'de', 'nl', 'da'] as const) {
    await page.goto('./');
    await page.evaluate(value => localStorage.setItem('uec-language', value), language);
    await page.reload();
    const text = language === 'en' ? englishStoryMessages : storyTranslations[language];
    await expect(page.locator('.scale-story h2')).toHaveText(text.startWithOne);
    await expect(page.locator('.scale-story .human-context')).toContainText(text.humanActivity);
    await page.locator('.scale-story').getByRole('button', { name: text.fish, exact: true }).click();
    await expect(page.locator('.scale-story .annual')).toHaveText(text.fishFlowCaption);
    await page.locator('.scale-story').getByRole('button', { name: text.grid, exact: true }).click();
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});

test('hidden-tab time freezes both individual-rate lanes and does not catch up on return', async ({ page }) => {
  await page.addInitScript(() => {
    let hidden = false;
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => hidden });
    (window as unknown as { storyVisibility: (value: boolean) => void }).storyVisibility = value => { hidden = value; document.dispatchEvent(new Event('visibilitychange')); };
  });
  await page.goto('./'); const canvas = page.locator('.scale-story canvas');
  await canvas.scrollIntoViewIfNeeded(); await expect(canvas).toHaveAttribute('data-state', 'running');
  await expect.poll(async () => Number(await canvas.getAttribute('data-emitted'))).toBeGreaterThan(100);
  await page.evaluate(() => (window as unknown as { storyVisibility: (value: boolean) => void }).storyVisibility(true));
  await expect(canvas).toHaveAttribute('data-state', 'offscreen');
  const pixels = await canvas.evaluate(node => node.toDataURL());
  await page.waitForTimeout(350); expect(await canvas.evaluate(node => node.toDataURL())).toBe(pixels);
  const before = Number(await canvas.getAttribute('data-emitted'));
  const humanBefore = Number(await canvas.getAttribute('data-human-emitted'));
  const resumed = await page.evaluate(() => {
    (window as unknown as { storyVisibility: (value: boolean) => void }).storyVisibility(false);
    const node = document.querySelector<HTMLCanvasElement>('.scale-story canvas')!;
    return { animals: Number(node.dataset.emitted), humans: Number(node.dataset.humanEmitted) };
  });
  expect(resumed).toEqual({ animals: before, humans: humanBefore });
  await expect(canvas).toHaveAttribute('data-state', 'running');
  await expect.poll(async () => Number(await canvas.getAttribute('data-emitted'))).toBeGreaterThan(before);
});
