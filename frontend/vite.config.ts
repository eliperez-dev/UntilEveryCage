import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import type { ProxyOptions } from 'vite';

export default defineConfig(({ command }) => {
  // The secret exists only in this local dev-server process. It is never placed
  // in import.meta.env, the generated bundle, browser storage, URLs, or logs.
  const previewToken = command === 'serve' ? process.env.UEC_DEV_PREVIEW_TOKEN : undefined;
  const localRealPreview = Boolean(previewToken) && process.env.VITE_LOCAL_DATA_MODE === 'real-preview';
  const realPreviewMapSource = localRealPreview
    ? process.env.VITE_REAL_PREVIEW_MAP_SOURCE ?? 'mvt'
    : undefined;
  const realPreviewProxy: Record<string, string | ProxyOptions> = {};
  if (previewToken && process.env.VITE_LOCAL_DATA_MODE === 'real-preview') {
    realPreviewProxy['/dev/real-preview'] = {
      target: process.env.VITE_API_ORIGIN ?? 'http://127.0.0.1:38001',
      changeOrigin: false,
      configure(proxy) {
        proxy.on('proxyReq', request => request.setHeader('x-uec-dev-preview-token', previewToken));
      },
    };
  }
  const localApiProxy = { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false }, ...realPreviewProxy };
  const previewModeMeta = {
    name: 'uec-local-data-mode',
    transformIndexHtml(html: string) {
      return localRealPreview ? html.replace('<head>', '<head><meta name="uec-local-data-mode" content="real-preview">') : html;
    },
  };

  return {
    base: localRealPreview ? '/' : '/v2-preview/',
    publicDir: 'public',
    plugins: [svelte(), previewModeMeta],
    define: realPreviewMapSource
      ? { 'import.meta.env.VITE_REAL_PREVIEW_MAP_SOURCE': JSON.stringify(realPreviewMapSource) }
      : {},
    server: { proxy: localApiProxy },
    preview: { proxy: localApiProxy },
    build: { outDir: 'dist', emptyOutDir: true },
  };
});
