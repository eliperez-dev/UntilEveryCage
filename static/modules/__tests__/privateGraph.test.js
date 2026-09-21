import { jest } from '@jest/globals';

test('private graph surface is explicitly bounded and not a public projection', async () => {
  const fs = await import('fs/promises');
  const html = await fs.readFile(new URL('../../private-graph.html', import.meta.url), 'utf8');
  expect(html).toContain('Private evidence only');
  expect(html).toContain('does not establish ownership');
  const js = await fs.readFile(new URL('../../private-graph.js', import.meta.url), 'utf8');
  expect(js).toContain('/api/private/graph/search');
  expect(js).toContain('/api/private/graph/traverse');
  expect(js).toContain('replace');
  const css = await fs.readFile(new URL('../../private-graph.css', import.meta.url), 'utf8');
  expect(css).toContain('.workspace');
  expect(css).toContain('.notice');
  expect(html).toContain('class="workspace"');
});
