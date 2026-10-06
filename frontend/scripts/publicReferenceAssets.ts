import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import type { Plugin } from 'vite';

// These files have one checked-in owner. Vite serves them in development and
// emits their bytes into dist for the existing staging script to copy.
const root = new URL('../../', import.meta.url);
const files: Record<string, URL> = {
  'public-openapi.json': new URL('docs/api/public-openapi.json', root),
  'v2-location.schema.json': new URL('docs/api/v2-location.schema.json', root),
  'swagger-ui-bundle.js': new URL('frontend/node_modules/swagger-ui-dist/swagger-ui-bundle.js', root),
  'swagger-ui.css': new URL('frontend/node_modules/swagger-ui-dist/swagger-ui.css', root),
  'swagger-ui-LICENSE': new URL('frontend/node_modules/swagger-ui-dist/LICENSE', root),
  'swagger-ui-NOTICE': new URL('frontend/node_modules/swagger-ui-dist/NOTICE', root),
  'swagger-ui-bundle.js.LICENSE.txt': new URL('frontend/node_modules/swagger-ui-dist/swagger-ui-bundle.js.LICENSE.txt', root),
};
export function publicReferenceAssets(): Plugin {
  return {
    name: 'uec-public-reference-assets',
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        const path = (request.url ?? '').split('?')[0] ?? '';
        const prefix = [server.config.base + 'reference/', '/reference/'].find(candidate => path.startsWith(candidate));
        const name = prefix ? path.slice(prefix.length) : '';
        const source = files[name];
        if (!source) { next(); return; }
        if (request.method !== 'GET' && request.method !== 'HEAD') { response.statusCode = 405; response.end(); return; }
        try {
          const bytes = readFileSync(source);
          response.setHeader('Content-Type', name.endsWith('.json') ? 'application/json' : name.endsWith('.js') ? 'text/javascript' : name.endsWith('.css') ? 'text/css' : 'text/plain');
          response.setHeader('Cache-Control', 'no-cache');
          response.end(request.method === 'HEAD' ? undefined : bytes);
        } catch { response.statusCode = 503; response.end('The local reference asset is unavailable.'); }
      });
    },
    generateBundle() {
      for (const [name, source] of Object.entries(files)) {
        this.emitFile({ type: 'asset', fileName: `reference/${name}`, source: readFileSync(fileURLToPath(source)) });
      }
    },
  };
}
