import { expect, test, type Page } from '@playwright/test';
import { installEmptyPublicMap } from '../fixtures/empty-public-map';

async function install(page: Page) {
  await installEmptyPublicMap(page, 'synthetic-display-settings');
  await page.route('https://**/*', route => route.abort());
  await page.goto('./#/map?release_id=synthetic-display-settings&lat=45&lon=5&z=8&bearing=20');
  await page.waitForFunction(() => { const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__; return map?.isStyleLoaded() && map.getSource('locations') && !map.isMoving(); });
  await page.getByRole('button', { name: 'More tools', exact: true }).click();
  await expect(page.getByLabel('Clustering', { exact: true })).toBeEnabled();
}

test('More tools controls update the live renderer and stay in sync with debug and reset', async ({ page }, testInfo) => {
  await install(page);
  const menu = page.locator('#shared-tools-menu');
  await expect(menu.getByRole('group', { name: 'Map display' })).toBeVisible();
  await expect(menu.getByRole('group', { name: 'Map view' })).toHaveCount(0);
  await expect(menu.getByRole('group', { name: 'Map style' })).toHaveCount(0);
  await expect(menu.getByLabel('Clustering', { exact: true })).toHaveValue('auto');
  const icons = menu.getByRole('slider', { name: 'Icon size', exact: true });
  await expect(icons).toHaveValue('0.8');
  await expect(icons).toHaveAttribute('aria-valuetext', '80%');
  await expect(menu.getByLabel('Use optimized pins')).not.toBeChecked();
  await page.evaluate(() => {
    const w = window as any, map = w.__UEC_LOCAL_PREVIEW_MAP__;
    w.__displayOriginalSource = map.getSource('locations');
    w.__displayOriginalCamera = [map.getCenter().toArray(), map.getZoom(), map.getPitch(), map.getBearing()];
  });
  await icons.fill('1.1');
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getLayoutProperty('v1-source-pins', 'icon-size'))).toBe(.55);
  await menu.getByLabel('Use optimized pins').check();
  const dots = menu.getByRole('slider', { name: 'Dot size', exact: true });
  await expect(dots).toHaveValue('6.5');
  await dots.fill('9');
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getPaintProperty('source-coordinate-points', 'circle-radius'))).toBe(9);
  expect(await page.evaluate(() => {
    const w = window as any, map = w.__UEC_LOCAL_PREVIEW_MAP__;
    return { source: map.getSource('locations') === w.__displayOriginalSource, camera: JSON.stringify([map.getCenter().toArray(), map.getZoom(), map.getPitch(), map.getBearing()]) === JSON.stringify(w.__displayOriginalCamera) };
  })).toEqual({ source: true, camera: true });
  for (const mode of ['off', 'on', 'auto']) {
    await menu.getByLabel('Clustering', { exact: true }).selectOption(mode);
    await expect(menu.getByLabel('Clustering', { exact: true })).toHaveValue(mode);
  }
  await menu.getByLabel('Enable debug menu', { exact: true }).check();
  await page.getByRole('button', { name: 'Close more tools', exact: true }).click();
  await page.getByRole('button', { name: 'Debug menu', exact: true }).click();
  const debug = page.getByRole('complementary', { name: 'Debug menu', exact: true });
  await debug.getByText('Map tuning', { exact: true }).click();
  await expect(debug.locator('#cluster-mode')).toHaveValue('auto');
  await expect(debug.locator('#v1-pin-mode')).not.toBeChecked();
  await expect(debug.locator('#coordinate-radius')).toHaveValue('9');
  await debug.locator('#coordinate-radius').fill('5');
  await page.getByRole('button', { name: 'More tools', exact: true }).click();
  await expect(dots).toHaveValue('5');
  await page.screenshot({ path: testInfo.outputPath('more-tools-display-desktop.png') });
  await page.getByRole('button', { name: 'Close more tools', exact: true }).click();
  await debug.getByRole('button', { name: 'Reset temporary settings', exact: true }).click();
  await page.getByRole('button', { name: 'More tools', exact: true }).click();
  await expect(menu.getByLabel('Clustering', { exact: true })).toHaveValue('auto');
  await expect(menu.getByLabel('Use optimized pins')).not.toBeChecked();
  await expect(icons).toHaveValue('0.8');
});

test('More tools display controls fit a 320px phone in all six languages', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 320, height: 760 });
  await install(page);
  for (const [code, name, tools] of [
    ['en', 'English', 'More tools'], ['es', 'Español', 'Más herramientas'],
    ['fr', 'Français', 'Plus d’outils'], ['de', 'Deutsch', 'Weitere Werkzeuge'],
    ['nl', 'Nederlands', 'Meer hulpmiddelen'], ['da', 'Dansk', 'Flere værktøjer'],
  ]) {
    await page.locator('.language-action').click();
    await page.locator('#shared-language-menu').getByRole('button', { name, exact: true }).click();
    await expect(page.locator('html')).toHaveAttribute('lang', code);
    await page.getByRole('button', { name: tools, exact: true }).click();
    const geometry = await page.locator('#shared-tools-menu').evaluate(menu => {
      const bounds = menu.getBoundingClientRect();
      return { fits: bounds.left >= 0 && bounds.right <= innerWidth && menu.scrollWidth <= menu.clientWidth,
        targets: [...menu.querySelectorAll('select,input[type=range],label.toggle')].every(control => control.getBoundingClientRect().height >= 44),
        pageFits: document.documentElement.scrollWidth <= innerWidth };
    });
    expect(geometry).toEqual({ fits: true, targets: true, pageFits: true });
    if (code === 'de') await page.screenshot({ path: testInfo.outputPath('more-tools-display-mobile-german.png') });
    await page.keyboard.press('Escape');
    await expect(page.getByRole('button', { name: tools, exact: true })).toBeFocused();
  }
});

test('map display controls are absent away from the map', async ({ page }) => {
  await page.goto('./#/about');
  await page.getByRole('button', { name: 'More tools', exact: true }).click();
  await expect(page.locator('#shared-tools-menu .map-display-tools')).toHaveCount(0);
  await expect(page.getByLabel('Current release', { exact: true })).toBeVisible();
});
