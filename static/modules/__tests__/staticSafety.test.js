import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

test('map and public ethics page declare a restrictive referrer policy', () => {
    for (const file of ['static/index.html', 'static/ethics.html']) {
        const html = readFileSync(resolve(process.cwd(), file), 'utf8');
        expect(html).toContain('<meta name="referrer" content="strict-origin-when-cross-origin">');
    }
});

test('browser-facing external links opened in new tabs protect the opener', () => {
    const html = readFileSync(resolve(process.cwd(), 'static/howtouse.html'), 'utf8');
    expect(html).not.toMatch(/target="_blank"\s+rel="noopener"(?:\s|>)/);
});

test('service worker never caches API responses that could outlive suppression', () => {
    const worker = readFileSync(resolve(process.cwd(), 'static/sw.js'), 'utf8');
    expect(worker).toContain('must not be cached client-side');
    expect(worker).not.toContain('cache.put(');
    expect(worker).not.toContain('caches.match(');
});
