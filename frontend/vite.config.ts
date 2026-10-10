import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import type { ProxyOptions } from 'vite';
import { publicReferenceAssets } from './scripts/publicReferenceAssets';

export default defineConfig(({ command }) => {
  // The secret exists only in this local dev-server process. It is never placed
  // in import.meta.env, the generated bundle, browser storage, URLs, or logs.
  const previewToken = command === 'serve' ? process.env.UEC_DEV_PREVIEW_TOKEN : undefined;
  const localRealPreview = Boolean(previewToken) && process.env.VITE_LOCAL_DATA_MODE === 'real-preview';
  const localCandidatePreview = Boolean(previewToken) && process.env.VITE_LOCAL_DATA_MODE === 'candidate-preview';
  const realPreviewMapSource = localRealPreview
    ? process.env.VITE_REAL_PREVIEW_MAP_SOURCE ?? 'mvt'
    : undefined;
  const apiOrigin = process.env.VITE_API_ORIGIN ?? 'http://127.0.0.1:8000';
  const realPreviewProxy: Record<string, string | ProxyOptions> = {};
  if (previewToken && process.env.VITE_LOCAL_DATA_MODE === 'real-preview') {
    realPreviewProxy['/dev/real-preview'] = {
      target: process.env.UEC_REAL_PREVIEW_API_ORIGIN ?? process.env.VITE_API_ORIGIN ?? 'http://127.0.0.1:38001',
      changeOrigin: false,
      configure(proxy) {
        proxy.on('proxyReq', request => request.setHeader('x-uec-dev-preview-token', previewToken));
      },
    };
  }
  const candidatePreviewProxy: Record<string, string | ProxyOptions> = {};
  if (localCandidatePreview && previewToken) {
    candidatePreviewProxy['/api/dev/preview/test-release'] = {
      target: process.env.UEC_CANDIDATE_PREVIEW_API_ORIGIN ?? apiOrigin,
      changeOrigin: false,
      configure(proxy) {
        proxy.on('proxyReq', request => request.setHeader('x-uec-dev-preview-token', previewToken));
      },
    };
  }
  // Vite resolves proxy contexts in declaration order. Keep the authenticated
  // candidate route ahead of the generic API route so its token is injected.
  const localApiProxy = { ...candidatePreviewProxy, ...realPreviewProxy, '/api': { target: apiOrigin, changeOrigin: false } };
  const previewModeMeta = {
    name: 'uec-local-data-mode',
    transformIndexHtml(html: string) {
      const mode = localRealPreview ? 'real-preview' : localCandidatePreview ? 'candidate-preview' : null;
      return mode ? html.replace('<head>', `<head><meta name="uec-local-data-mode" content="${mode}">`) : html;
    },
  };

  return {
    base: process.env.UEC_COMBINED_PREVIEW === 'true' ? '/v2-preview/' : (localRealPreview || localCandidatePreview) ? '/' : '/v2-preview/',
    publicDir: 'public',
    plugins: [svelte(), previewModeMeta, publicReferenceAssets()],
    define: realPreviewMapSource
      ? { 'import.meta.env.VITE_REAL_PREVIEW_MAP_SOURCE': JSON.stringify(realPreviewMapSource) }
      : {},
    server: { proxy: localApiProxy },
    preview: { proxy: localApiProxy },
    build: { outDir: 'dist', emptyOutDir: true },
  };
});
