import { expect, test, type Page } from '@playwright/test';
import { englishStoryMessages, type StoryMessages } from '../../src/app/scale-story/messages';
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

test('since-open totals share document time across navigation and reset on refresh', async ({page}) => {
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.addInitScript(() => {
    let milliseconds = 0;
    Object.defineProperty(performance,'now',{configurable:true,value:()=>milliseconds});
    (window as any).__counterTime = (value:number) => milliseconds=value;
  });
  await page.goto('./');
  const total = (population:string) => page.locator(`[data-counter="${population}"]`);
  for(const population of ['human','chicken','land','fish']) await expect(total(population)).toHaveAttribute('data-total','0');
  await page.evaluate(() => (window as any).__counterTime(1000));
  for(const [population,count] of [['human','2'],['chicken','2'],['land','2779'],['fish','65671']]) await expect(total(population!)).toHaveAttribute('data-total',count!);
  await page.getByRole('navigation',{name:'Primary'}).getByRole('link',{name:'About',exact:true}).click();
  await page.evaluate(() => (window as any).__counterTime(5000));
  await page.getByRole('link',{name:'Until Every Cage home',exact:true}).click();
  await expect(total('land')).toHaveAttribute('data-total','13895');
  await expect(total('fish')).toHaveAttribute('data-total','328355');
  await expect(total('land')).toHaveText('≈ 13,895 killed since you opened this page');
  await expect(total('fish')).toHaveText('≈ 328,355 caught or slaughtered since you opened this page');
  await page.reload();
  for(const population of ['human','chicken','land','fish']) await expect(total(population)).toHaveAttribute('data-total','0');
});

test('physics is the default outflow and preserves complete emission after reload', async ({page}) => {
  await page.setViewportSize({width:390,height:844}); await page.goto('./');
  for(const population of ['land','fish']) {
    const section=page.locator(`.throughput[data-population="${population}"]`),canvas=section.locator('canvas');
    await expect(section.getByRole('checkbox')).toHaveCount(0);
    await canvas.scrollIntoViewIfNeeded();
    await expect(canvas).toHaveAttribute('data-physics','enabled');
    await expect.poll(()=>canvas.evaluate(node=>Number(node.dataset.physicsAlive))).toBeGreaterThan(0);
    await expect.poll(()=>canvas.evaluate(node=>Number(node.dataset.physicsEmitted)===Number(node.dataset.emitted))).toBe(true);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  }
  await page.reload();
  for(const canvas of await page.locator('.throughput canvas').all()) await expect(canvas).toHaveAttribute('data-physics','enabled');
});

function comparisonStatements(text: StoryMessages) {
  return [[text.humanLandText, text.humanLandValue], [text.oneSecondText, text.oneSecondValue], [text.dripCondition, text.waterLandValue]]
    .map(([template, emphasis]) => { expect(template!.split('{emphasis}')).toHaveLength(2); return template!.replace('{emphasis}', emphasis!); });
}

test('direct dot comparison leads into both funnels while preserving the route, header and discovery', async ({ page }) => {
  await page.goto('./#/?release_id=synthetic-story'); const route = page.url();
  await expect(page.getByRole('navigation', { name: 'Primary' }).getByRole('link')).toHaveText(['Map', 'Data', 'Contribute', 'About']);
  await expect(page.getByRole('button', { name: 'Find locations near me', exact: true })).toBeVisible();
  expect((await page.locator('.hero').boundingBox())!.height).toBeLessThan(600);
  await expect(page.getByRole('button', { name: 'See the scale', exact: true })).toHaveCount(0);
  const story = page.locator('.scale-story'); await story.scrollIntoViewIfNeeded(); expect(page.url()).toBe(route);
  await expect(story.locator('.story-intro')).toHaveCount(0);
  await expect(story.locator('.line-chapter > h3')).toHaveText(englishStoryMessages.lineClaim);
  await expect(story.getByText(englishStoryMessages.humans, { exact: true })).toBeVisible();
  await expect(story.getByText(englishStoryMessages.chickens, { exact: true })).toBeVisible();
  await expect(story.locator('.story-chapter > h3')).toHaveText([englishStoryMessages.landSentence, englishStoryMessages.fishSentence]);
  await expect(story.locator('.introductions')).toHaveCount(0);
  await expect(story.locator('canvas')).toHaveCount(3);
  await expect(story.getByRole('button', { name: 'Grid', exact: true })).toHaveCount(0);
  await expect(story.getByRole('button', { name: 'Funnel', exact: true })).toHaveCount(0);
  await expect(story.getByRole('button', { name: 'Fish', exact: true })).toHaveCount(0);
  await expect(story.locator('.mortality-comparison .unit')).toHaveText(englishStoryMessages.introExplanation);
  for (const selector of ['.mortality-comparison', '.land-chapter .throughput', '.fish-chapter .throughput']) {
    const chapter = story.locator(selector), canvas = chapter.locator('canvas');
    await canvas.scrollIntoViewIfNeeded(); await expect(canvas).toHaveAttribute('data-state', 'running');
    await expect.poll(async () => Number(await canvas.getAttribute('data-emitted'))).toBeGreaterThan(0);
    await expect(chapter.getByRole('button', { name: /^(Pause|Resume)$/ })).toHaveCount(0);
    if (selector !== '.mortality-comparison') await expect(chapter.locator('.canvas-wrap')).toHaveAttribute('data-mode', 'funnel');
    await expect(chapter.locator('.map-link')).toHaveAttribute('href', '#/map?release_id=synthetic-story');
  }
  await expect(story.locator('.fish-chapter .date')).toContainText('2019');
  await expect(story.locator('.fish-chapter .flow-caption')).toContainText('upper estimate');
  await expect(story.locator('.comparison-question')).toHaveCount(0);
  await expect(story.locator('.comparison-statement')).toHaveText(comparisonStatements(englishStoryMessages));
  await expect(story.locator('.comparison-emphasis')).toHaveText([englishStoryMessages.humanLandValue, englishStoryMessages.oneSecondValue, englishStoryMessages.waterLandValue]);
  await expect(story.locator('.land-chapter .comparison-statement')).toHaveText(comparisonStatements(englishStoryMessages)[0]!);
  await expect(story.locator('.comparison-statement:visible')).toHaveCount(1);
  await expect(story.locator('.methods .comparison-statement')).toHaveCount(2);
  expect(await story.locator('.land-chapter .comparison').evaluate(node => Boolean(node.compareDocumentPosition(document.querySelector('.fish-chapter')!) & Node.DOCUMENT_POSITION_FOLLOWING))).toBe(true);
  await expect(story.locator('.methods')).not.toHaveAttribute('open'); await story.locator('summary').click();
  await expect(story.locator('.methods')).toContainText('140/60'); await expect(story.locator('.methods')).toContainText('0.25 mL');
  await expect(page.locator('.release-totals')).toContainText('4'); await expect(page.locator('.maplibregl-map')).toHaveCount(0);
});

test('all chapters have static reduced-motion equivalents and mobile controls in both themes', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' }); await page.setViewportSize({ width: 320, height: 760 }); await page.goto('./');
  const story = page.locator('.scale-story'); await story.scrollIntoViewIfNeeded();
  expect((await page.locator('.hero').boundingBox())!.height).toBeLessThan(650);
  for (const canvas of await story.locator('canvas').all()) await expect(canvas).toHaveAttribute('data-state', 'static');
  const labels = await story.locator('.line-labels').boundingBox(), field = await story.locator('.line-field').boundingBox();
  expect(labels!.y + labels!.height).toBeLessThanOrEqual(field!.y);
  await expect(story.getByRole('button', { name: 'Pause', exact: true })).toHaveCount(0);
  for (const canvas of await story.locator('.throughput canvas').all()) {
    // Both populations retain a visible source grid and red outflow in the static equivalent.
    await expect.poll(() => canvas.evaluate(node => {
      const image = (node as HTMLCanvasElement).getContext('2d')!.getImageData(0, 0, (node as HTMLCanvasElement).width, (node as HTMLCanvasElement).height);
      let white = 0, red = 0;
      for (let i = 0; i < image.data.length; i += 4) {
        if (!image.data[i + 3]) continue;
        if (image.data[i]! > 210 && image.data[i + 1]! > 210 && image.data[i + 2]! > 200) white++;
        if (image.data[i]! > 150 && image.data[i + 1]! < 100 && image.data[i + 2]! < 100) red++;
      }
      return white > 20 && red > 20;
    })).toBe(true);
  }
  for (const theme of ['dark', 'light']) {
    if (theme === 'light') await page.locator('.masthead .theme-toggle').click();
    for (const chapter of await story.locator('.throughput').all()) {
      await expect(chapter.locator('.canvas-wrap')).toHaveAttribute('data-mode', 'funnel');
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

test('direct opening and funnel chapters translate in every supported language at 320px', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' }); await page.setViewportSize({ width: 320, height: 760 });
  await page.goto('./', { waitUntil: 'commit' });
  await page.locator('.scale-story').waitFor();
  for (const language of ['en', 'es', 'fr', 'de', 'nl', 'da', 'zh-Hans'] as const) {
    if (language !== 'en') { await page.locator('.masthead .language-action').click(); await page.locator(`#shared-language-menu button[lang="${language}"]`).click(); await expect(page.locator('#shared-language-menu')).toHaveCount(0); }
    const text = language === 'en' ? englishStoryMessages : storyTranslations[language];
    await expect(page.locator('.story-intro')).toHaveCount(0);
    await expect(page.locator('.line-chapter > h3')).toHaveText(text.lineClaim);
    await expect(page.locator('.scale-story').getByText(text.humans, { exact: true })).toBeVisible();
    await expect(page.locator('.scale-story').getByText(text.chickens, { exact: true })).toBeVisible();
    await expect(page.locator('.scale-story .story-chapter > h3')).toHaveText([text.landSentence, text.fishSentence]);
    await expect(page.locator('.mortality-comparison .unit')).toHaveText(text.introExplanation);
    await expect(page.locator('.mortality-comparison')).toContainText(text.chickenRate);
    const chickenRate = page.locator('.mortality-comparison .lane-headings>div').nth(1).locator('.lane-rate');
    await expect(chickenRate).toContainText((140 / 60).toLocaleString(language, { minimumFractionDigits: 1, maximumFractionDigits: 1 }));
    const rates = await page.locator('.lane-rate').evaluateAll(elements => elements.map(element => {
      const unit = element.querySelector('small')!;
      return { top: element.getBoundingClientRect().top, unitTop: unit.getBoundingClientRect().top,
        numberSize: parseFloat(getComputedStyle(element).fontSize), unitSize: parseFloat(getComputedStyle(unit).fontSize), unitText: unit.textContent!.trim() };
    }));
    expect(Math.abs(rates[0]!.top - rates[1]!.top)).toBeLessThanOrEqual(1);
    expect(Math.abs(rates[0]!.unitTop - rates[1]!.unitTop)).toBeLessThanOrEqual(1);
    for (const rate of rates) {
      expect(rate.unitSize).toBeGreaterThanOrEqual(16);
      expect(rate.numberSize / rate.unitSize).toBeLessThanOrEqual(2.5);
      expect(rate.unitText).not.toMatch(/^\/?\s*s$/);
    }
    const funnelRates = await page.locator('.throughput .rate').evaluateAll(elements => elements.map(element => ({
      number: parseFloat(getComputedStyle(element).fontSize), unit: parseFloat(getComputedStyle(element.querySelector('span')!).fontSize),
    })));
    expect(funnelRates[0]!.number).toBe(funnelRates[1]!.number);
    for (const rate of funnelRates) { expect(rate.unit).toBeGreaterThanOrEqual(16); expect(rate.number / rate.unit).toBeLessThanOrEqual(2.5); }
    await expect(page.locator('.land-chapter .comparison-statement')).toHaveText(comparisonStatements(text)[0]!);
    await expect(page.locator('.comparison-statement:visible')).toHaveCount(1);
    await expect(page.locator('.comparison-statement')).toHaveText(comparisonStatements(text));
    await expect(page.locator('.comparison-emphasis')).toHaveText([text.humanLandValue, text.oneSecondValue, text.waterLandValue]);
    const emphases = await page.locator('.comparison-emphasis').evaluateAll(elements => elements.map(element => ({
      tag: element.tagName, weight: Number(getComputedStyle(element).fontWeight), transform: getComputedStyle(element).textTransform,
    })));
    expect(emphases.every(item => item.tag === 'STRONG' && item.weight >= 700 && item.transform === 'none')).toBe(true);
    expect((await page.locator('.comparison-statement').allTextContents()).every(statement => !/[?？¿]/.test(statement))).toBe(true);
    const heroActionsFit = await page.locator('.hero').evaluate(hero => {
      const frame = hero.getBoundingClientRect();
      return Array.from(hero.querySelectorAll('.hero-actions > *')).every(action => {
        const rect = action.getBoundingClientRect();
        return rect.width > 0 && rect.height >= 44 && rect.left >= frame.left && rect.right <= frame.right && rect.top >= frame.top && rect.bottom <= frame.bottom;
      });
    });
    expect(heroActionsFit).toBe(true);
    const labels = await page.locator('.line-labels').boundingBox(), field = await page.locator('.line-field').boundingBox(); expect(labels!.y + labels!.height).toBeLessThanOrEqual(field!.y);
    await expect(page.locator('.fish-chapter .flow-caption')).toHaveText(text.fishFlowCaption);
    for (const chapter of await page.locator('.throughput').all()) {
      const unit = chapter.locator('.unit');
      await expect(unit).toHaveCount(1);
      const explanation = await unit.boundingBox(), visualization = await chapter.locator('.canvas-wrap').boundingBox();
      expect(explanation!.y + explanation!.height).toBeLessThanOrEqual(visualization!.y);
      await expect(chapter.locator('.controls .unit')).toHaveCount(0);
    }
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
