import { expect, test } from '@playwright/test';

test('panning keeps the native cluster index and startup overlay stable', async ({ page }) => {
  test.skip(!process.env.UEC_REAL_PREVIEW_URL, 'Requires the populated local preview');
  await page.goto('/#/map?f1a=field&list=closed&lat=36.3&lon=-89.9&z=4.3');
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.getSource('locations') && map.isSourceLoaded('locations');
  }, undefined, { timeout: 90_000 });

  const result = await page.evaluate(async () => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const source = map.getSource('locations');
    const original = source.setData;
    let rebuilds = 0;
    let startupShown = false;
    source.setData = function (...args: unknown[]) {
      rebuilds++;
      return original.apply(this, args);
    };
    const observer = new MutationObserver(() => {
      if (document.querySelector('.startup-status')) startupShown = true;
    });
    observer.observe(document.body, { childList: true, subtree: true });
    try {
      await new Promise<void>(resolve => {
        map.once('moveend', resolve);
        map.panBy([250, 0], { duration: 300 });
      });
      await new Promise(resolve => setTimeout(resolve, 250));
      return { rebuilds, startupShown };
    } finally {
      source.setData = original;
      observer.disconnect();
    }
  });

  expect(result).toEqual({ rebuilds: 0, startupShown: false });
});
