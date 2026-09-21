import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

test('public ethics page contains safety disclosures and reporting link', () => {
    const html = readFileSync(resolve(process.cwd(), 'static/ethics.html'), 'utf8');
    expect(html).toContain('Candidate, staged, quarantined, and raw evidence are not public data.');
    expect(html).toContain('Privacy%2Flocation%20removal');
    expect(html).toContain('id="reporting"');
    expect(html).toContain('Data ethics, provenance, and limitations');
    expect(html).toContain('does not claim legal immunity');
});
