import { test, expect } from '@playwright/test';

test('landing stays separate from the map and its media can be paused', async ({ page }) => {
  const apiRequests: string[] = [];
  page.on('request', request => { if (new URL(request.url()).pathname.startsWith('/api/')) apiRequests.push(request.url()); });
  await page.goto('./');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('HIDDEN INPLAIN SIGHT.');
  await expect(page.getByRole('navigation', { name: 'Primary' }).getByRole('link')).toHaveText(['Map', 'Data', 'Contribute', 'About']);
  await expect(page.locator('.masthead nav [aria-current]')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Dark theme', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'More tools', exact: true })).toBeVisible();
  await expect(page.locator('.hero-photo')).toHaveCount(2);
  await expect.poll(() => page.locator('.hero-photo').evaluateAll(images => images.every(image => (image as HTMLImageElement).complete && (image as HTMLImageElement).naturalWidth > 0))).toBe(true);
  await expect(page.locator('.maplibregl-map')).toHaveCount(0);
  expect(apiRequests).toEqual([]);
  await page.getByRole('button', { name: 'Pause background animation' }).click();
  await expect.poll(() => page.locator('.cow').evaluate(image => image.getAnimations().map(animation => animation.playState))).toEqual(['paused', 'paused']);
  await page.getByRole('button', { name: 'Resume background animation' }).click();
  await expect.poll(() => page.locator('.cow').evaluate(image => image.getAnimations().map(animation => animation.playState))).toEqual(['running', 'running']);
  await page.getByRole('link', { name: 'Open the map', exact: true }).first().click();
  await expect.poll(() => new URL(page.url()).hash.split('?')[0]).toBe('#/map');
  await expect(page.locator('.landing-page')).toHaveCount(0);
  await page.goBack();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('HIDDEN INPLAIN SIGHT.');
});

test('landing supports narrow screens, keyboard entry and reduced motion', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 320, height: 760 });
  await page.goto('./');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect(page.locator('.pig')).toHaveCSS('animation-name', 'none');
  await expect(page.locator('.cow')).toBeHidden();
  await expect(page.locator('.motion-toggle')).toHaveCount(0);
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('main')).toBeFocused();
  expect(new URL(page.url()).hash).toBe('');
  for (const link of ['Map', 'Data', 'Contribute', 'About']) await expect(page.getByRole('navigation').getByRole('link', { name: link, exact: true })).toBeVisible();
});

test('saved Spanish choice applies to the landing and shared header in both themes', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('uec-language', 'es'));
  await page.setViewportSize({ width: 320, height: 760 });
  await page.goto('./#/');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('OCULTO APLENA VISTA.');
  await expect(page.getByRole('link', { name: 'Abrir el mapa', exact: true }).first()).toBeVisible();
  const nav = page.getByRole('navigation', { name: 'Navegación principal' });
  await expect(nav.getByRole('link')).toHaveText(['Mapa', 'Datos', 'Contribuir', 'Acerca de']);
  for (const theme of ['dark', 'light'] as const) {
    if (theme === 'light') await page.locator('.masthead .theme-toggle').click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    for (const link of await nav.getByRole('link').all()) {
      await expect(link).toBeVisible();
      const box = await link.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.height).toBeGreaterThanOrEqual(44);
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(320);
    }
    await page.getByRole('button', { name: 'Más herramientas', exact: true }).click();
    await expect(page.getByRole('combobox', { name: 'Idioma', exact: true })).toBeVisible();
    await expect(page.getByRole('combobox', { name: 'Versión actual', exact: true })).toBeDisabled();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('button', { name: 'Más herramientas', exact: true })).toBeFocused();
  }
});

test('landing shared navigation preserves map context without loading map data', async ({ page }) => {
  const apiRequests: string[] = [];
  page.on('request', request => { if (new URL(request.url()).pathname.startsWith('/api/')) apiRequests.push(request.url()); });
  await page.goto('./#/?lat=52&lon=5&z=6&release_id=synthetic-landing-context');
  const mapHref = '#/map?lat=52&lon=5&z=6&release_id=synthetic-landing-context';
  const nav = page.getByRole('navigation', { name: 'Primary' });
  await expect(nav.getByRole('link', { name: 'Map', exact: true })).toHaveAttribute('href', mapHref);
  await expect(nav.getByRole('link', { name: 'Data', exact: true })).toHaveAttribute('href', `#/database/api?map=${encodeURIComponent(mapHref)}`);
  await expect(nav.getByRole('link', { name: 'Contribute', exact: true })).toHaveAttribute('href', `#/contribute?map=${encodeURIComponent(mapHref)}`);
  await expect(page.getByRole('link', { name: 'Open the map', exact: true }).first()).toHaveAttribute('href', mapHref);
  await expect(page.locator('.maplibregl-map')).toHaveCount(0);
  expect(apiRequests).toEqual([]);
});
