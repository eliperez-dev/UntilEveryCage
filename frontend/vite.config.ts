import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import type { ProxyOptions } from 'vite';
import { publicReferenceAssets } from './scripts/publicReferenceAssets';

export default defineConfig(({ command }) => {
  // The public container serves this build from the Rust service's origin.
  // Keep preview/dev under their existing /v2-preview/ contract unless the
  // explicit production build marker is present.
  const publicBuild = process.env.UEC_PUBLIC_BUILD === 'true';
  // The secret exists only in this local dev-server process. It is never placed
  // in import.meta.env, the generated bundle, browser storage, URLs, or logs.
  const previewToken = command === 'serve' ? process.env.UEC_DEV_PREVIEW_TOKEN : undefined;
  const localRealPreview = Boolean(previewToken) && process.env.VITE_LOCAL_DATA_MODE === 'real-preview';
  const localCandidatePreview = Boolean(previewToken) && process.env.VITE_LOCAL_DATA_MODE === 'candidate-preview';
  const realPreviewMapSource = localRealPreview
    ? process.env.VITE_REAL_PREVIEW_MAP_SOURCE ?? 'mvt'
    : undefined;
  const apiOrigin = process.env.VITE_API_ORIGIN ?? 'http://127.0.0.1:8000';
  // Optional split-origin contribution service, including its private queue.
  // This unprefixed environment variable
  // belongs to the Vite process only and is never defined in browser code.
  const communityApiOrigin = process.env.UEC_COMMUNITY_API_ORIGIN?.trim();
  const secureApiOrigin = command === 'serve' && process.env.VITE_SECURE_INBOX_EXPERIMENT === 'true'
    ? process.env.UEC_SECURE_COMMUNITY_API_ORIGIN?.trim() : undefined;
  const secureProxy: Record<string, string | ProxyOptions> = {};
  if (secureApiOrigin) {
    const origin = new URL(secureApiOrigin);
    if (origin.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(origin.hostname)
      || origin.username || origin.password || origin.pathname !== '/' || origin.search || origin.hash) throw new Error('The local encrypted inbox requires a loopback API origin.');
    secureProxy['/api/community/secure'] = { target: origin.origin, changeOrigin: false };
    secureProxy['/api/private/community/secure'] = { target: origin.origin, changeOrigin: false };
  }
  const communityProxy: Record<string, string | ProxyOptions> = communityApiOrigin
    ? {
      '/api/community': { target: communityApiOrigin, changeOrigin: new URL(communityApiOrigin).protocol === 'https:' },
      '/api/private/community': { target: communityApiOrigin, changeOrigin: new URL(communityApiOrigin).protocol === 'https:' },
    }
    : {};
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
  // candidate route and optional community override ahead of the generic API.
  // Hosted HTTPS APIs need their own Host header; loopback API behavior stays the same.
  const apiChangeOrigin = new URL(apiOrigin).protocol === 'https:';
  const localApiProxy = { ...secureProxy, ...candidatePreviewProxy, ...realPreviewProxy, ...communityProxy, '/api': { target: apiOrigin, changeOrigin: apiChangeOrigin }, '/health': { target: apiOrigin, changeOrigin: apiChangeOrigin } };
  const previewModeMeta = {
    name: 'uec-local-data-mode',
    transformIndexHtml(html: string) {
      const mode = localRealPreview ? 'real-preview' : localCandidatePreview ? 'candidate-preview' : null;
      return mode ? html.replace('<head>', `<head><meta name="uec-local-data-mode" content="${mode}">`) : html;
    },
  };

  return {
    base: publicBuild || (localRealPreview || localCandidatePreview)
      ? '/'
      : '/v2-preview/',
    publicDir: 'public',
    plugins: [svelte(), previewModeMeta, publicReferenceAssets()],
    // This lazy worker dependency must be optimized before the first map visit;
    // discovering it later forces a full page reload and discards UI state.
    optimizeDeps: { include: ['maplibre-gl/dist/maplibre-gl-worker.mjs'] },
    define: realPreviewMapSource
      ? { 'import.meta.env.VITE_REAL_PREVIEW_MAP_SOURCE': JSON.stringify(realPreviewMapSource) }
      : {},
    server: { proxy: localApiProxy },
    preview: { proxy: localApiProxy },
    build: { outDir: 'dist', emptyOutDir: true },
  };
});
