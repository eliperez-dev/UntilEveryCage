import { jest } from '@jest/globals';

test('private graph surface is explicitly bounded and not a public projection', async () => {
  const html = await (await import('fs/promises')).readFile(new URL('../../../../static/private-graph.html', import.meta.url), 'utf8');
  expect(html).toContain('Private evidence only');
  expect(html).toContain('does not establish ownership');
  const js = await (await import('fs/promises')).readFile(new URL('../../private-graph.js', import.meta.url), 'utf8');
  expect(js).toContain('/api/private/graph/search');
  expect(js).toContain('/api/private/graph/traverse');
  expect(js).toContain('replace');
});
