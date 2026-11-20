import { test, expect } from '@playwright/test';
import { installEmptyPublicMap } from '../fixtures/empty-public-map';

test('Spanish map labels persist across reload without changing the shared map view', async ({ page }) => {
  await installEmptyPublicMap(page, 'synthetic-release');
  await page.goto('./#/map?lat=38&lon=-96&z=4&release_id=synthetic-release&country=US&list=closed');
  await expect(page.getByRole('combobox', { name: 'Search across public release records' })).toBeVisible();
  await page.getByRole('button', { name: 'Language', exact: true }).click();
  await page.getByRole('button', { name: 'Español', exact: true }).click();
  await expect(page.getByRole('combobox', { name: 'Buscar en los registros de la versión pública' })).toBeVisible();
  const mapView = new URLSearchParams(new URL(page.url()).hash.split('?')[1]);
  for (const [key, value] of Object.entries({ lat: '38', lon: '-96', z: '4', release_id: 'synthetic-release', country: 'US' })) {
    expect(mapView.get(key)).toBe(value);
  }
  await page.reload();
  await expect(page.getByRole('navigation', { name: 'Navegación principal' }).getByRole('link', { name: 'Mapa', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Idioma', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Español', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await page.goto('./#/contribute?type=bug');
  await expect(page.getByLabel('¿Qué ocurrió?')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Enviar informe' })).toBeVisible();
});

test('Spanish renders the localized FAQ while retaining the English manifest when English is selected', async ({ page }) => {
  await page.goto('./#/faq');
  await page.getByRole('button', { name: 'Language', exact: true }).click();
  await page.getByRole('button', { name: 'Español', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Preguntas frecuentes' })).toBeVisible();
  await page.getByRole('navigation', { name: 'Navegación principal' }).getByRole('link', { name: 'Acerca de' }).click();
  await page.getByRole('button', { name: 'Idioma', exact: true }).click();
  await page.getByRole('button', { name: 'English', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'About Until Every Cage is Empty' })).toBeVisible();
  await expect(page.locator('.manifesto')).toContainText('The violence inflicted on these animals is not accidental');
});
