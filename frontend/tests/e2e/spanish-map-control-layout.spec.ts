import { expect, test, type Page } from '@playwright/test';

const contrastRatio = (foreground: string, background: string) => {
  const luminance = (color: string) => {
    const channels = color.match(/[\d.]+/g)?.slice(0, 3).map(Number) ?? [];
    const linear = channels.map(value => {
      const channel = value / 255;
      return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * linear[0]! + 0.7152 * linear[1]! + 0.0722 * linear[2]!;
  };
  const [lighter, darker] = [luminance(foreground), luminance(background)].sort((left, right) => right - left);
  return (lighter + 0.05) / (darker! + 0.05);
};

async function setSpanishAndTheme(page: Page, theme: 'Claro' | 'Oscuro') {
  const tools = page.getByRole('button', { name: 'Herramientas', exact: true });
  if (await tools.getAttribute('aria-expanded') !== 'true') await tools.click();
  await page.getByLabel('Idioma', { exact: true }).selectOption('es');
  await page.getByRole('button', { name: theme, exact: true }).click();
  await expect(page.locator('html')).toHaveAttribute('lang', 'es');
  await expect(page.locator('html')).toHaveAttribute('data-theme', theme === 'Claro' ? 'light' : 'dark');
}

test('Spanish map controls do not overlap at 390px or 375px in either theme', async ({ page }, testInfo) => {
  test.skip(!process.env.UEC_REAL_PREVIEW_URL, 'Requires the running local v0 preview supplied by integration.');
  await page.addInitScript(() => localStorage.setItem('uec-language', 'es'));
  await page.goto('/#/map');
  await expect(page.getByRole('button', { name: 'Buscar en el mapa' })).toBeVisible();
  await expect(page.locator('.map-controls')).toBeVisible();

  for (const width of [390, 375]) {
    await page.setViewportSize({ width, height: 844 });
    for (const theme of ['Claro', 'Oscuro'] as const) {
      await setSpanishAndTheme(page, theme);
      const geometry = await page.evaluate(() => {
        const search = document.querySelector('.search-toggle')!.getBoundingClientRect();
        const toolbar = document.querySelector('.map-controls-wrap')!.getBoundingClientRect();
        const hint = document.querySelector('.gesture-hint')!;
        const toolbarSurface = document.querySelector('.map-controls')!;
        const style = getComputedStyle(hint);
        const background = getComputedStyle(toolbarSurface).backgroundColor;
        return {
          overlaps: search.left < toolbar.right && toolbar.left < search.right && search.top < toolbar.bottom && toolbar.top < search.bottom,
          overflow: toolbarSurface.scrollWidth > toolbarSurface.clientWidth,
          hintColor: style.color,
          hintFontSize: parseFloat(style.fontSize),
          toolbarBackground: background,
          labelClipped: (() => {
            const label = document.querySelector('.map-controls-label')!;
            const labelBox = label.getBoundingClientRect();
            const toolbarBox = toolbarSurface.getBoundingClientRect();
            return labelBox.left < toolbarBox.left || labelBox.right > toolbarBox.right;
          })(),
        };
      });
      expect(geometry.overlaps, `${width}px ${theme}: search and map controls overlap`).toBe(false);
      expect(geometry.overflow, `${width}px ${theme}: map controls overflow their toolbar`).toBe(false);
      expect(geometry.labelClipped, `${width}px ${theme}: translated toolbar label is clipped`).toBe(false);
      expect(geometry.hintFontSize, `${width}px ${theme}: hint size`).toBeGreaterThanOrEqual(10);
      expect(contrastRatio(geometry.hintColor, geometry.toolbarBackground), `${width}px ${theme}: hint contrast`).toBeGreaterThanOrEqual(4.5);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${width}px ${theme}: page overflow`).toBe(true);

      await page.screenshot({ path: testInfo.outputPath(`spanish-map-${width}-${theme.toLowerCase()}.png`) });
      if (width === 390) {
        const tools = page.getByRole('button', { name: 'Herramientas', exact: true });
        if (await tools.getAttribute('aria-expanded') !== 'true') await tools.click();
        await expect(page.getByLabel('Idioma', { exact: true })).toHaveValue('es');
        await expect(page.getByRole('group', { name: 'Tema de color' })).toBeVisible();
        await expect(page.getByRole('button', { name: theme, exact: true })).toHaveAttribute('aria-pressed', 'true');
        await page.screenshot({ path: testInfo.outputPath(`spanish-tools-390-${theme.toLowerCase()}.png`) });
        await page.getByRole('button', { name: 'Cerrar herramientas', exact: true }).click();
      }
    }
  }
});
