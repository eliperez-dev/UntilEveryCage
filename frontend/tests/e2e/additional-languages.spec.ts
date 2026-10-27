import { expect, test, type Page } from '@playwright/test';
import { join } from 'node:path';
import { installEmptyPublicMap } from '../fixtures/empty-public-map';
const choices = [
  { code: 'en', name: 'English', map: 'Map', bug: 'Report a bug' },
  { code: 'es', name: 'Español', map: 'Mapa', bug: 'Informar de un error' },
  { code: 'fr', name: 'Français', map: 'Carte', bug: 'Signaler un bug' },
  { code: 'de', name: 'Deutsch', map: 'Karte', bug: 'Fehler melden' },
  { code: 'nl', name: 'Nederlands', map: 'Kaart', bug: 'Een bug melden' },
  { code: 'da', name: 'Dansk', map: 'Kort', bug: 'Rapportér en fejl' },
];
async function choose(page: Page, name: string) {
  await page.locator('.language-action').click();
  await page.locator('#shared-language-menu').getByRole('button', { name, exact: true }).click();
  await expect(page.locator('#shared-language-menu')).toHaveCount(0);
}

test('language popover preserves selected map state through Escape, tools and locale changes', async ({ page }) => {
  await installEmptyPublicMap(page, 'synthetic-release');
  await page.goto('./#/map?list=open&lat=38&lon=-96&z=4&pitch=40&bearing=20&release_id=synthetic-release&selected=synthetic-record-1&source_filter=us.fsis');
  await expect(page.locator('.dossier')).toBeVisible(); const before = page.url().split('#')[1];
  await page.locator('.language-action').click();
  await expect(page.locator('#shared-language-menu [aria-pressed=true]')).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(page.locator('#shared-language-menu')).toHaveCount(0);
  await expect(page.locator('.language-action')).toBeFocused();
  await expect(page.locator('.dossier')).toBeVisible(); expect(page.url().split('#')[1]).toBe(before);
  await page.locator('.tools-action').click(); await page.locator('.language-action').click();
  await expect(page.locator('#shared-tools-menu')).toHaveCount(0);
  await page.locator('.tools-action').click(); await expect(page.locator('#shared-language-menu')).toHaveCount(0);
  await page.keyboard.press('Escape'); await expect(page.locator('.dossier')).toBeVisible();
  for (const choice of choices) {
    await choose(page, choice.name); await expect(page.locator('html')).toHaveAttribute('lang', choice.code);
    await expect(page.locator('.masthead nav').getByRole('link', { name: choice.map, exact: true })).toBeVisible();
    await expect(page.locator('.dossier')).toBeVisible(); expect(page.url().split('#')[1]).toBe(before);
  }
  await page.reload(); await expect(page.locator('html')).toHaveAttribute('lang', 'da');
  await expect(page.locator('.dossier')).toBeVisible(); expect(page.url().split('#')[1]).toBe(before);
  await page.locator('.dossier-header button').first().click();
  await page.locator('#field-search').fill('Synthetic private query');
  const searchRoute = page.url().split('#')[1];
  for (const choice of choices.slice(2)) {
    await choose(page, choice.name);
    await expect(page.locator('#field-search')).toHaveValue('Synthetic private query');
    expect(page.url().split('#')[1]).toBe(searchRoute);
  }
});

test('six languages fit phone headers and contribution controls in both themes', async ({ page }) => {
  test.setTimeout(90_000);
  await page.route('**/api/**', route => {
    if (!new URL(route.request().url()).pathname.startsWith('/api/')) return route.fallback();
    return route.fulfill({ status: 404, json: {} });
  });
  await page.goto('./#/contribute?type=bug');
  for (const width of [320, 390]) for (const theme of ['dark', 'light']) {
    await page.setViewportSize({ width, height: 844 });
    if (await page.locator('html').getAttribute('data-theme') !== theme) await page.locator('.theme-toggle').click();
    for (const choice of choices) {
      await choose(page, choice.name);
      await expect(page.locator('html')).toHaveAttribute('lang', choice.code);
      await expect(page.locator('.intake h2')).toHaveText(choice.bug);
      await expect(page.locator('input[name=page_url]')).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      const geometry = await page.evaluate(() => {
        const box = (selector: string) => document.querySelector(selector)!.getBoundingClientRect();
        const brand = box('.wordmark'), theme = box('.theme-toggle'), language = box('.language-action'), tools = box('.tools-action');
        return { ordered: brand.right <= theme.left && theme.right <= language.left && language.right <= tools.left, fits: tools.right <= innerWidth, target: language.width >= 44 && language.height >= 44 };
      });
      expect(geometry).toEqual({ ordered: true, fits: true, target: true });
      await page.locator('.language-action').click();
      const menu = await page.locator('#shared-language-menu').boundingBox();
      expect(menu!.x).toBeGreaterThanOrEqual(0); expect(menu!.x + menu!.width).toBeLessThanOrEqual(width);
      await expect(page.locator('#shared-language-menu').getByRole('button', { name: choice.name, exact: true })).toHaveAttribute('aria-pressed', 'true');
      if (process.env.UEC_LANGUAGE_SCREENSHOT_DIR && width === 320 && theme === 'dark' && choice.code === 'fr') await page.screenshot({ path: join(process.env.UEC_LANGUAGE_SCREENSHOT_DIR, 'language-mobile-french.png') });
      await page.mouse.click(4, 200); await expect(page.locator('#shared-language-menu')).toHaveCount(0);
    }
  }
});

test('lazy locale failure keeps the current language and does not fetch other dictionaries on English startup', async ({ page }) => {
  const loaded: string[] = [];
  page.on('request', request => { if (/\/(?:fr|de|nl|da)(?:-[^/]+)?\.json(?:\?|$)/.test(request.url())) loaded.push(request.url()); });
  await page.goto('./#/about'); await expect(page.locator('.manifesto')).toBeVisible(); expect(loaded).toEqual([]);
  let blocked = true;
  await page.route(url => /\/fr(?:-[^/]+)?\.json$/.test(url.pathname), route => blocked ? route.abort() : route.fallback());
  await page.locator('.language-action').click(); await page.getByRole('button', { name: 'Français', exact: true }).click();
  await expect(page.locator('#shared-language-menu [role=alert]')).toContainText('Language could not be loaded.');
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  blocked = false; await page.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(page.locator('html')).toHaveAttribute('lang', 'fr');
  await expect(page.locator('#shared-language-menu')).toHaveCount(0);
});

test('phone language options and Retry own their entire hit area above map controls', async ({ page }) => {
  await installEmptyPublicMap(page, 'synthetic-release');
  let blocked = true;
  await page.route(url => /\/fr(?:-[^/]+)?\.json$/.test(url.pathname), route => blocked ? route.abort() : route.fallback());
  await page.goto('./#/map?list=open&lat=38&lon=-96&z=4&release_id=synthetic-release&selected=synthetic-record-1');
  await expect(page.locator('.dossier')).toBeVisible();
  await expect(page.locator('.map-navigation')).toBeVisible();
  const selectedRoute = page.url().split('#')[1];
  async function assertForeground(selector: string) {
    await expect(page.locator('#shared-language-menu .language-options button')).toHaveCount(6);
    expect(await page.locator(selector).evaluateAll(buttons => buttons.every(button => {
      const box = button.getBoundingClientRect();
      return [box.left + 4, box.left + box.width / 2, box.right - 4].every(x => {
        const hit = document.elementFromPoint(x, box.top + box.height / 2);
        return hit === button || Boolean(hit && button.contains(hit));
      });
    }))).toBe(true);
  }
  for (const width of [320, 375, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.locator('.language-action').click();
    await assertForeground('#shared-language-menu .language-options button');
    await page.getByRole('button', { name: 'Français', exact: true }).click();
    await expect(page.locator('#shared-language-menu [role=alert]')).toBeVisible();
    await assertForeground('#shared-language-menu .language-options button, #shared-language-menu .language-error button');
    if (process.env.UEC_LANGUAGE_SCREENSHOT_DIR && width === 390) await page.screenshot({ path: join(process.env.UEC_LANGUAGE_SCREENSHOT_DIR, 'language-map-foreground-retry.png') });
    await page.keyboard.press('Escape'); await expect(page.locator('.language-action')).toBeFocused();
    await expect(page.locator('.dossier')).toBeVisible(); expect(page.url().split('#')[1]).toBe(selectedRoute);
  }
  blocked = false;
  await page.locator('.language-action').click();
  const retry = page.locator('#shared-language-menu .language-error button');
  const box = await retry.boundingBox();
  await page.mouse.click(box!.x + box!.width - 4, box!.y + box!.height / 2);
  await expect(page.locator('html')).toHaveAttribute('lang', 'fr');
  await expect(page.locator('#shared-language-menu')).toHaveCount(0);
  await expect(page.locator('.dossier')).toBeVisible(); expect(page.url().split('#')[1]).toBe(selectedRoute);
});
