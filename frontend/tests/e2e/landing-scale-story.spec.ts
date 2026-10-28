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

test('natural scrolling introduces four chapters while preserving the route, header and discovery', async ({ page }) => {
  await page.goto('./#/?release_id=synthetic-story'); const route = page.url();
  await expect(page.getByRole('navigation', { name: 'Primary' }).getByRole('link')).toHaveText(['Map', 'Data', 'Contribute', 'About']);
  await expect(page.getByRole('button', { name: 'Find locations near me', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'See the scale', exact: true }).click(); expect(page.url()).toBe(route);
  const story = page.locator('.scale-story'); await expect(story).toBeFocused();
  await expect(story.locator('h2')).toHaveText(englishStoryMessages.introTitle);
  await expect(story.locator('h3')).toHaveText([englishStoryMessages.humansSentence, englishStoryMessages.landSentence, englishStoryMessages.fishSentence]);
  await expect(story.locator('canvas')).toHaveCount(3);
  await expect(story.getByRole('button', { name: 'Fish', exact: true })).toHaveCount(0);
  await expect(story.locator('.intro-dot')).toHaveCSS('background-color', 'rgb(242, 240, 232)');
  for (const selector of ['.mortality-comparison', '.land-chapter .throughput', '.fish-chapter .throughput']) {
    const chapter = story.locator(selector), canvas = chapter.locator('canvas');
    await canvas.scrollIntoViewIfNeeded(); await expect(canvas).toHaveAttribute('data-state', 'running');
    await expect.poll(async () => Number(await canvas.getAttribute('data-emitted'))).toBeGreaterThan(0);
    await chapter.getByRole('button', { name: 'Pause', exact: true }).click(); await expect(canvas).toHaveAttribute('data-state', 'paused');
    const pixels = await canvas.evaluate(node => node.toDataURL()); await page.waitForTimeout(100); expect(await canvas.evaluate(node => node.toDataURL())).toBe(pixels);
    if (selector !== '.mortality-comparison') { await chapter.getByRole('button', { name: 'Grid', exact: true }).click(); await expect(chapter.locator('.canvas-wrap')).toHaveAttribute('data-mode', 'grid'); }
    await chapter.getByRole('button', { name: 'Resume', exact: true }).click();
    await expect(chapter.locator('.map-link')).toHaveAttribute('href', '#/map?release_id=synthetic-story');
  }
  await expect(story.locator('.fish-chapter .date')).toContainText('2019');
  await expect(story.locator('.fish-chapter .flow-caption')).toContainText('upper estimate');
  await expect(story.locator('.methods')).not.toHaveAttribute('open'); await story.locator('summary').click();
  await expect(story.locator('.methods')).toContainText('140/60'); await expect(story.locator('.methods')).toContainText('0.25 mL');
  await expect(page.locator('.release-totals')).toContainText('4'); await expect(page.locator('.maplibregl-map')).toHaveCount(0);
});

test('all chapters have static reduced-motion equivalents and mobile controls in both themes', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' }); await page.setViewportSize({ width: 320, height: 760 }); await page.goto('./');
  const story = page.locator('.scale-story'); await story.scrollIntoViewIfNeeded();
  for (const canvas of await story.locator('canvas').all()) await expect(canvas).toHaveAttribute('data-state', 'static');
  const labels = await story.locator('.line-labels').boundingBox(), field = await story.locator('.line-field').boundingBox();
  expect(labels!.y + labels!.height).toBeLessThanOrEqual(field!.y);
  await expect(story.getByRole('button', { name: 'Pause', exact: true })).toHaveCount(0);
  for (const theme of ['dark', 'light']) {
    if (theme === 'light') await page.locator('.masthead .theme-toggle').click();
    for (const chapter of await story.locator('.throughput').all()) {
      await chapter.getByRole('button', { name: 'Grid', exact: true }).click();
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    }
    const targets = await story.locator('button,.map-link').evaluateAll(elements => elements.map(e => e.getBoundingClientRect().height)); expect(targets.every(height => height >= 44)).toBe(true);
  }
  const canvas = story.locator('.fish-chapter canvas'), before = await canvas.evaluate(node => node.toDataURL()); await page.waitForTimeout(100); expect(await canvas.evaluate(node => node.toDataURL())).toBe(before);
});

test('all offscreen chapters and route departure stop animation callbacks', async ({ page }) => {
  await page.addInitScript(() => { const request = window.requestAnimationFrame.bind(window); (window as unknown as { storyRaf: number }).storyRaf = 0; window.requestAnimationFrame = callback => request(time => { (window as unknown as { storyRaf: number }).storyRaf++; callback(time); }); });
  await page.goto('./'); const canvases = page.locator('.scale-story canvas');
  await canvases.nth(1).scrollIntoViewIfNeeded(); await expect(canvases.nth(1)).toHaveAttribute('data-state', 'running');
  await page.locator('.landing-footer').scrollIntoViewIfNeeded(); for (const canvas of await canvases.all()) await expect(canvas).toHaveAttribute('data-state', 'offscreen');
  await page.waitForTimeout(50); const before = await page.evaluate(() => (window as unknown as { storyRaf: number }).storyRaf); await page.waitForTimeout(100); expect(await page.evaluate(() => (window as unknown as { storyRaf: number }).storyRaf)).toBe(before);
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'About', exact: true }).click(); await expect(canvases).toHaveCount(0); await page.waitForTimeout(50);
  const left = await page.evaluate(() => (window as unknown as { storyRaf: number }).storyRaf); await page.waitForTimeout(100); expect(await page.evaluate(() => (window as unknown as { storyRaf: number }).storyRaf)).toBe(left);
  await page.goBack(); await expect(page.locator('.scale-story')).toBeVisible();
});

test('all four conversational chapters translate in every supported language at 320px', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' }); await page.setViewportSize({ width: 320, height: 760 });
  await page.goto('./', { waitUntil: 'commit' });
  await page.locator('.scale-story').waitFor();
  for (const language of ['en', 'es', 'fr', 'de', 'nl', 'da'] as const) {
    if (language !== 'en') { await page.locator('.masthead .language-action').click(); await page.locator(`#shared-language-menu button[lang="${language}"]`).click(); await expect(page.locator('#shared-language-menu')).toHaveCount(0); }
    const text = language === 'en' ? englishStoryMessages : storyTranslations[language];
    await expect(page.locator('.scale-story h2')).toHaveText(text.introTitle);
    await expect(page.locator('.scale-story h3')).toHaveText([text.humansSentence, text.landSentence, text.fishSentence]);
    await expect(page.locator('.mortality-comparison')).toContainText(text.chickenRate);
    await expect(page.locator('.mortality-comparison .lane-headings>div').nth(1).locator('span')).toHaveText(`≈ ${(140 / 60).toLocaleString(language, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} / s`);
    const labels = await page.locator('.line-labels').boundingBox(), field = await page.locator('.line-field').boundingBox(); expect(labels!.y + labels!.height).toBeLessThanOrEqual(field!.y);
    await expect(page.locator('.fish-chapter .flow-caption')).toHaveText(text.fishFlowCaption);
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});

test('hidden-tab time freezes both comparison lanes and resumes without catchup', async ({ page }) => {
  await page.addInitScript(() => { let hidden = false; Object.defineProperty(document, 'hidden', { configurable: true, get: () => hidden }); (window as unknown as { storyVisibility: (value: boolean) => void }).storyVisibility = value => { hidden = value; document.dispatchEvent(new Event('visibilitychange')); }; });
  await page.goto('./'); const canvas = page.locator('.mortality-comparison canvas'); await canvas.scrollIntoViewIfNeeded(); await expect(canvas).toHaveAttribute('data-state', 'running');
  await expect.poll(async () => Number(await canvas.getAttribute('data-emitted'))).toBeGreaterThan(0);
  await page.evaluate(() => (window as unknown as { storyVisibility: (value: boolean) => void }).storyVisibility(true)); await expect(canvas).toHaveAttribute('data-state', 'offscreen');
  const pixels = await canvas.evaluate(node => node.toDataURL()); await page.waitForTimeout(350); expect(await canvas.evaluate(node => node.toDataURL())).toBe(pixels);
  const before = { chickens: Number(await canvas.getAttribute('data-emitted')), humans: Number(await canvas.getAttribute('data-human-emitted')) };
  const resumed = await page.evaluate(() => { (window as unknown as { storyVisibility: (value: boolean) => void }).storyVisibility(false); const node = document.querySelector<HTMLCanvasElement>('.mortality-comparison canvas')!; return { chickens: Number(node.dataset.emitted), humans: Number(node.dataset.humanEmitted) }; });
  expect(resumed).toEqual(before); await expect(canvas).toHaveAttribute('data-state', 'running');
});
