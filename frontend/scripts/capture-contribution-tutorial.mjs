import { chromium } from '@playwright/test';
import { mkdir, copyFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { URL } from 'node:url';

// Record only blank UI. Never submit a form or request records, receipts,
// coordinates, private previews, operator screens, or external services.
const root = resolve(import.meta.dirname, '..', '..');
const preview = new URL(process.argv[2] ?? 'http://127.0.0.1:4179/v2-preview/');
if (!['127.0.0.1', 'localhost'].includes(preview.hostname)) throw new Error('Tutorial recording requires a loopback preview.');
const captures = resolve(root, 'target', 'tutorial-capture');
const destination = resolve(root, 'frontend', 'public', 'tutorials');
await mkdir(captures, { recursive: true });
await mkdir(destination, { recursive: true });
const browser = await chromium.launch({ headless: true });
try {
  const context = await browser.newContext({ viewport: { width: 960, height: 720 }, recordVideo: { dir: captures, size: { width: 960, height: 720 } } });
  const page = await context.newPage();
  await page.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.origin !== preview.origin || url.pathname.startsWith('/api/') || url.pathname.startsWith('/dev/')) return route.abort();
    return route.continue();
  });
  const video = page.video();
  preview.hash = '/contribute?type=bug';
  await page.goto(preview.toString());
  const tasks = page.getByRole('navigation', { name: 'Contribution tasks' });
  await tasks.waitFor();
  await page.waitForTimeout(1500);
  await tasks.getByRole('link', { name: 'Evidence', exact: true }).focus();
  await page.waitForTimeout(900);
  await tasks.getByRole('link', { name: 'Evidence', exact: true }).click();
  await page.getByLabel('Record link or ID', { exact: true }).waitFor();
  await page.waitForTimeout(2200);
  await tasks.getByRole('link', { name: 'Correction', exact: true }).click();
  await page.waitForTimeout(1500);
  await tasks.getByRole('link', { name: 'Evidence', exact: true }).click();
  await page.getByLabel('Record link or ID', { exact: true }).focus();
  await page.waitForTimeout(2200);
  await context.close();
  if (!video) throw new Error('Playwright video recording was unavailable.');
  await copyFile(await video.path(), resolve(destination, 'contribution-types.webm'));
  console.log('Recorded blank contribution-type tutorial to frontend/public/tutorials/contribution-types.webm');
} finally { await browser.close(); }
