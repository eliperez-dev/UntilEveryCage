import { test, expect } from '@playwright/test';
import { installEmptyPublicMap } from '../fixtures/empty-public-map';

test('Spanish selection changes primary and map controls without changing route state and persists after reload', async ({ page }) => {
  await installEmptyPublicMap(page, 'synthetic-release');
  await page.goto('./#/map?scenario=default&lat=38&lon=-96&z=4&release_id=synthetic-release&source=us.fsis&category=Processing&precision=exact&country=US&source_filter=us.fsis&activity=slaughter&selected=synthetic-record-1&focus=selected');
  await expect(page.getByText('Search records', { exact: true })).toBeVisible();
  const stateBeforeSwitch = page.url().split('#')[1];
  const languageControl = async () => {
    // The shell header can appear before the lazy map module is mounted.
    await expect(page.getByRole('navigation', { name: /^(Map navigation|Navegación del mapa)$/ })).toBeVisible();
    await page.getByRole('button', { name: /^(Tools|Herramientas)$/ }).click();
    return page.getByLabel(/^(Language|Idioma)$/);
  };
  const control = await languageControl();
  await control.selectOption('es');
  await expect(page.getByRole('navigation', { name: 'Navegación principal' }).getByRole('link', { name: 'Mapa', exact: true })).toBeVisible();
  await expect(page.getByText('Buscar registros', { exact: true })).toBeVisible();
  await expect(page.getByText('Filtros 6', { exact: true })).toBeVisible();
  expect(page.url().split('#')[1]).toBe(stateBeforeSwitch);
  const mapParams = new URLSearchParams(page.url().split('?')[1] ?? '');
  expect(mapParams.get('release_id')).toBe('synthetic-release');
  expect(mapParams.get('lat')).toBe('38');
  expect(mapParams.get('lon')).toBe('-96');
  expect(mapParams.get('z')).toBe('4');
  expect(mapParams.get('selected')).toBe('synthetic-record-1');
  expect(mapParams.get('category')).toBe('Processing');
  expect(mapParams.get('precision')).toBe('exact');
  expect(mapParams.get('country')).toBe('US');
  await page.reload();
  await expect(page.getByRole('navigation', { name: 'Navegación principal' }).getByRole('link', { name: 'Mapa', exact: true })).toBeVisible();
  const restoredControl = await languageControl();
  await expect(restoredControl).toHaveValue('es');
});

test('Spanish renders the localized FAQ while retaining the English manifest when English is selected', async ({ page }) => {
  await page.goto('./#/faq');
  await page.getByRole('button', { name: 'Tools' }).click();
  await page.getByLabel('Language').selectOption('es');
  await expect(page.getByRole('heading', { name: 'Preguntas frecuentes' })).toBeVisible();
  await page.getByRole('button', { name: 'Cerrar herramientas' }).click();
  await page.getByRole('navigation', { name: 'Navegación principal' }).getByRole('link', { name: 'Acerca de' }).click();
  await page.getByRole('button', { name: 'Herramientas', exact: true }).click();
  await page.getByLabel('Idioma').selectOption('en');
  await expect(page.getByRole('heading', { name: 'About Until Every Cage is Empty' })).toBeVisible();
  await expect(page.locator('.manifesto')).toContainText('The violence inflicted on these animals is not accidental');
});

test('map search and the bug contribution form expose Spanish controls', async ({ page }) => {
  await installEmptyPublicMap(page, 'synthetic-release');
  await page.goto('./#/map?list=open');
  await expect(page.getByRole('combobox', { name: 'Search across public release records' })).toBeVisible();
  await page.getByRole('button', { name: 'Tools' }).click();
  await page.getByLabel('Language').selectOption('es');
  await expect(page.getByRole('combobox', { name: 'Buscar en los registros de la versión pública' })).toBeVisible();
  await expect(page.getByRole('button', { name:'Cerrar el panel' })).toBeVisible();
  await page.goto('./#/contribute?type=bug');
  await expect(page.getByLabel('¿Qué ocurrió?')).toBeVisible();
  await expect(page.getByLabel('Pasos para reproducirlo')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Enviar informe' })).toBeVisible();
});
