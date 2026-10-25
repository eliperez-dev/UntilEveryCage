import { test, expect } from '@playwright/test';

test('Spanish selection changes primary and map controls without changing route state and persists after reload', async ({ page }) => {
  await page.goto('./#/map?scenario=default&lat=38&lon=-96&z=4&release_id=synthetic-release&source=us.fsis&cat=Processing&selected=synthetic-record-1&focus=selected');
  await expect(page.getByRole('button', { name: 'Search map' })).toBeVisible();
  const stateBeforeSwitch = page.url().split('#')[1];
  const languageControl = async () => {
    await page.getByRole('button', { name: 'Tools' }).click();
    return page.getByLabel('Language');
  };
  const control = await languageControl();
  await control.selectOption('es');
  await expect(page.getByRole('navigation', { name: 'Navegación principal' }).getByRole('link', { name: 'Mapa', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: /Buscar en el mapa/ })).toBeVisible();
  await expect(page.getByRole('group', { name: 'Vista del mapa' })).toContainText('Calles');
  expect(page.url().split('#')[1]).toBe(stateBeforeSwitch);
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
  await page.getByRole('button', { name: 'Herramientas' }).click();
  await page.getByLabel('Idioma').selectOption('en');
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'About' }).click();
  await expect(page.getByRole('heading', { name: 'About Until Every Cage is Empty' })).toBeVisible();
  await expect(page.locator('.manifesto')).toContainText('The violence inflicted on these animals is not accidental');
});

test('public database filters and the bug contribution form expose Spanish controls', async ({ page }) => {
  await page.goto('./#/database');
  await page.getByRole('button', { name: 'Tools' }).click();
  await page.getByLabel('Language').selectOption('es');
  await expect(page.getByRole('heading', { name: 'Consultar registros' })).toBeVisible();
  await expect(page.getByLabel('Buscar registros')).toBeVisible();
  await expect(page.getByLabel('País')).toBeVisible();
  await page.goto('./#/contribute?type=bug');
  await expect(page.getByLabel('¿Qué ocurrió?')).toBeVisible();
  await expect(page.getByLabel('Pasos para reproducirlo')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Enviar informe' })).toBeVisible();
});
