import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.route('https://**/*', route => route.abort());
  // Keep the interaction suite independent of the several-thousand-row density
  // corpus, which is covered by the dedicated map renderer tests.
  const records = Array.from({ length: 20 }, (_, index) => ({ id:`syn-${String(index + 1).padStart(3, '0')}`, name:`Synthetic processing record ${index + 1}`, category:'processing_and_preparation', taxonomy:{ displayCategory:'processing_and_preparation', primaryCategories:['processing_and_preparation'], leafActivities:[{key:'meat_cutting',label:'Meat cutting'}], assignments:[], taxonomyVersion:'synthetic-test' }, locality:'Sample town', country:'Denmark', precision:index === 2 ? 'unmapped' : 'exact', latitude:index === 2 ? null : 56.1629 + index * .002, longitude:index === 2 ? null : 10.2039 + index * .002 }));
  await page.route('**/src/design-lab/fixtures.ts*', route => route.fulfill({ contentType:'text/javascript', body:`export const LAB_SENTINEL='F1A_SYNTHETIC_REVIEW_ONLY';export const labRecords=${JSON.stringify(records)};` }));
});
async function openFixture(page: import('@playwright/test').Page, list = 'closed') {
  await page.goto(`./#/map?f1a=field&list=${list}&lat=56.1629&lon=10.2039&z=10`);
  await expect(page.locator('.lab')).toHaveAttribute('data-data-mode', 'synthetic');
}
test('mobile sheet collapses to a handle, opens by keyboard and snaps during handle drags', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openFixture(page);
  const handle = page.getByRole('button', { name: 'Search map', exact: true });
  await expect(handle).toHaveAttribute('data-sheet-state', 'collapsed');
  await expect(page.locator('#field-search')).toBeHidden();
  const collapsed = await page.locator('.map-stage').boundingBox();
  await handle.click();
  await expect(handle).toHaveAttribute('data-sheet-state', 'middle');
  await expect(page.locator('#field-search')).toBeVisible();
  const middle = await page.locator('.map-stage').boundingBox();
  expect(middle).toEqual(collapsed);
  await handle.focus(); await page.keyboard.press('End');
  await expect(handle).toHaveAttribute('data-sheet-state', 'expanded');
  await page.keyboard.press('Home');
  await expect(handle).toHaveAttribute('data-sheet-state', 'collapsed');
  let box = await handle.boundingBox();
  await page.mouse.move(box!.x + 100, box!.y + 20); await page.mouse.down();
  await page.mouse.move(box!.x + 100, box!.y - 300, { steps: 6 }); await page.mouse.up();
  await expect(handle).toHaveAttribute('data-sheet-state', 'middle');
  box = await handle.boundingBox();
  await page.mouse.move(box!.x + 100, box!.y + 20); await page.mouse.down();
  await page.mouse.move(box!.x + 100, 820, { steps: 6 }); await page.mouse.up();
  await expect(handle).toHaveAttribute('data-sheet-state', 'collapsed');
  await handle.focus(); await page.keyboard.press('ArrowUp');
  await expect(handle).toHaveAttribute('data-sheet-state', 'middle');
  await page.keyboard.press('ArrowDown');
  await expect(handle).toHaveAttribute('data-sheet-state', 'collapsed');
});

test('mobile selection preserves query and sheet state, and map preview retains the selected record', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openFixture(page, 'open');
  const handle = page.getByRole('button', { name: 'Search map', exact: true });
  await handle.focus(); await page.keyboard.press('End');
  await page.locator('#field-search').fill('Synthetic');
  await expect(page.locator('.record-list .activity-summary').first()).not.toHaveText('');
  await page.locator('[data-record-id="syn-001"]').click();
  await expect(page.locator('.dossier')).toBeVisible();
  const detailHandle = page.getByRole('button', { name:'View facility details', exact:true });
  await expect(detailHandle).toHaveAttribute('data-sheet-state','expanded');
  await detailHandle.focus(); await page.keyboard.press('ArrowDown');
  const view=page.getByRole('navigation',{name:'Map navigation',exact:true}).getByRole('button',{name:'View',exact:true});
  await expect(view).toBeEnabled();
  await view.click();
  await expect(page.locator('#map-navigation-view')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.locator('#map-navigation-view')).toHaveCount(0);
  await expect(page.locator('.dossier')).toBeVisible();
  expect(new URL(page.url()).hash).toContain('selected=syn-001');
  await expect(detailHandle).toHaveAttribute('data-sheet-state','middle');
  await detailHandle.focus(); await page.keyboard.press('End');
  await expect(detailHandle).toHaveAttribute('data-sheet-state','expanded');
  await page.keyboard.press('Home');
  await expect(detailHandle).toHaveAttribute('data-sheet-state','collapsed');
  expect(new URL(page.url()).hash).toContain('selected=syn-001');
  await detailHandle.click();
  await expect(detailHandle).toHaveAttribute('data-sheet-state','middle');
  await expect(page.locator('.search-tools')).toBeHidden();
  await expect(page.locator('.csv-download')).toBeHidden();
  await expect(page.locator('.result-status')).toBeHidden();
  const selectedUrl = page.url();
  await page.getByRole('button', { name: 'Show on map', exact: true }).click();
  await expect(page.locator('.dossier')).toBeHidden();
  await expect(page.getByRole('button', { name: 'View facility details', exact: true })).toBeVisible();
  expect(new URL(page.url()).hash).toContain('selected=syn-001');
  await page.getByRole('button', { name: 'View facility details', exact: true }).click();
  await expect(page.locator('.dossier')).toBeVisible();
  await page.getByRole('button', { name: /Back to results/ }).click();
  await expect(page.locator('#field-search')).toHaveValue('Synthetic');
  await expect(handle).toHaveAttribute('data-sheet-state', 'expanded');
  expect(selectedUrl).toContain('selected=syn-001');
});

test('selected deep links start at middle and the detail handle drags through all three states without remounting the map', async ({ page }) => {
  await page.setViewportSize({ width:390,height:844 });
  await page.goto('./#/map?f1a=field&selected=syn-001&lat=56.1629&lon=10.2039&z=10');
  const handle=page.getByRole('button',{name:'View facility details',exact:true});
  await expect(handle).toHaveAttribute('data-sheet-state','middle');
  await expect(page.locator('.dossier')).toBeVisible();
  await expect(page.locator('.maplibregl-canvas')).toHaveCount(1);
  await page.locator('.maplibregl-canvas').evaluate(canvas=>{(window as any).__sheetOriginalCanvas=canvas});
  let box=(await handle.boundingBox())!;
  await page.mouse.move(box.x+100,box.y+20);await page.mouse.down();await page.mouse.move(box.x+100,140,{steps:6});await page.mouse.up();
  await expect(handle).toHaveAttribute('data-sheet-state','expanded');
  box=(await handle.boundingBox())!;
  await page.mouse.move(box.x+100,box.y+20);await page.mouse.down();await page.mouse.move(box.x+100,825,{steps:8});await page.mouse.up();
  await expect(handle).toHaveAttribute('data-sheet-state','collapsed');
  await expect(page.locator('.dossier')).toBeHidden();
  expect(new URL(page.url()).hash).toContain('selected=syn-001');
  await handle.click();
  await expect(handle).toHaveAttribute('data-sheet-state','middle');
  expect(await page.locator('.maplibregl-canvas').evaluate(canvas=>canvas===(window as any).__sheetOriginalCanvas)).toBe(true);
});

test('new and repeated pin selections preserve expanded detail and reopen collapsed detail at middle', async ({ page }) => {
  await page.setViewportSize({width:390,height:844});
  await openFixture(page,'open');
  const canvas = await page.locator('.map-stage').boundingBox();
  await page.locator('[data-record-id="syn-001"]').click();
  const handle=page.getByRole('button',{name:'View facility details',exact:true});
  await handle.focus();await page.keyboard.press('End');
  async function selectPin(id:string) {
    await page.waitForFunction(()=>{const map=(window as any).__UEC_LOCAL_PREVIEW_MAP__;return map?.getLayer('exact-pins')&&!map.isMoving()});
    await page.evaluate(id=>{
      const map=(window as any).__UEC_LOCAL_PREVIEW_MAP__, original=map.queryRenderedFeatures;
      const feature={type:'Feature',geometry:{type:'Point',coordinates:[10.2059,56.1649]},properties:{id},layer:{id:'exact-pins'}};
      map.queryRenderedFeatures=(_point:unknown,options:{layers?:string[]}={})=>options.layers?.includes('exact-pins')?[feature]:[];
      map.fire('click',{point:{x:20,y:20},lngLat:{lng:10.2059,lat:56.1649},originalEvent:new MouseEvent('click')});
      map.queryRenderedFeatures=original;
    },id);
  }
  await selectPin('syn-002');
  await expect(page.locator('.dossier h1')).toContainText('Synthetic processing record 2');
  await expect(handle).toHaveAttribute('data-sheet-state','expanded');
  await selectPin('syn-002');
  await expect(handle).toHaveAttribute('data-sheet-state','expanded');
  await handle.focus();await page.keyboard.press('Home');
  await selectPin('syn-002');
  await expect(handle).toHaveAttribute('data-sheet-state','middle');
  expect(await page.locator('.map-stage').boundingBox()).toEqual(canvas);
});

test('cancelled mobile handle gestures settle without stranding a drag', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 740 });
  await openFixture(page);
  const handle = page.getByRole('button', { name: 'Search map', exact: true });
  await handle.click();
  const box = await handle.boundingBox();
  await page.mouse.move(box!.x + 80, box!.y + 20); await page.mouse.down();
  await page.mouse.move(box!.x + 80, box!.y - 90, { steps: 4 });
  await handle.dispatchEvent('pointercancel', { pointerId: 1, pointerType: 'mouse', clientY: box!.y - 90 });
  await page.mouse.up();
  await expect(handle).not.toHaveClass(/dragging/);
  await handle.focus(); await page.keyboard.press('Home');
  await expect(handle).toHaveAttribute('data-sheet-state', 'collapsed');
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
});

test('desktop overlays a one-third rail on the unchanged map and mobile handle stays out of keyboard navigation', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 960 });
  await openFixture(page, 'open');
  const rail = await page.locator('.results').boundingBox();
  const map = await page.locator('.map-stage').boundingBox();
  expect(rail!.width).toBeCloseTo(480, -1);
  expect(map!.width).toBeCloseTo(1440, -1);
  await expect(page.locator('.mobile-sheet-handle')).toBeHidden();
  await page.locator('[data-record-id="syn-001"]').click();
  await expect(page.locator('.search-tools')).toBeHidden();
  await page.getByRole('button', { name: /Back to results/ }).click();
  await expect(page.locator('.search-tools')).toBeVisible();
});

for (const width of [320,390]) test(`mobile filters keep their final option and clear action reachable at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height:844 });
  await openFixture(page, 'open');
  const handle = page.getByRole('button', { name:'Search map', exact:true });
  await expect(handle).toHaveAttribute('data-sheet-state','middle');
  await page.locator('.filters > summary').click();
  const popup = page.locator('.filter-sheet');
  await expect.poll(async () => (await popup.boundingBox())!.y + (await popup.boundingBox())!.height).toBeLessThanOrEqual(844);
  await expect.poll(async () => (await popup.boundingBox())!.y + (await popup.boundingBox())!.height).toBeGreaterThan(830);
  await popup.evaluate(node => { node.scrollTop = node.scrollHeight; });
  const last = popup.getByRole('checkbox').last();
  await expect(last).toBeInViewport();
  await last.check();
  await popup.evaluate(node => { node.scrollTop = node.scrollHeight; });
  const clear = popup.getByRole('button', { name:'Clear all filters',exact:true });
  await expect(clear).toBeInViewport();
  await clear.click();
  await expect(last).not.toBeChecked();
  await handle.focus(); await page.keyboard.press('End');
  await expect(handle).toHaveAttribute('data-sheet-state','expanded');
  await expect.poll(async () => (await popup.boundingBox())!.y + (await popup.boundingBox())!.height).toBeLessThanOrEqual(844);
  await popup.evaluate(node => { node.scrollTop = node.scrollHeight; });
  await last.focus(); await page.keyboard.press('Space');
  await expect(last).toBeChecked();
  await expect(last).toBeInViewport();
  await page.keyboard.press('Escape');
  await expect(popup).toBeHidden();
  await expect(page.locator('.filters > summary')).toBeFocused();
  await expect(handle).toHaveAttribute('data-sheet-state','expanded');
});

test('desktop filters extend to the available viewport bottom and retain the clear action', async ({page})=>{
  await page.setViewportSize({width:1440,height:960});await openFixture(page,'open');
  await page.locator('.filters > summary').click();
  const popup=page.locator('.filter-sheet');
  await expect.poll(async()=>{const r=(await popup.boundingBox())!;return r.y+r.height}).toBeGreaterThan(946);
  await expect.poll(async()=>{const r=(await popup.boundingBox())!;return r.y+r.height}).toBeLessThanOrEqual(960);
  await popup.getByRole('checkbox').last().check();
  await popup.getByRole('button',{name:'Clear all filters',exact:true}).click();
  await expect(popup.getByRole('checkbox').last()).not.toBeChecked();
});
