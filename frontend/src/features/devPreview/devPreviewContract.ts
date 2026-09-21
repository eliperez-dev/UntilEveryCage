/**
 * Shape agreed for the private candidate-preview boundary. The client never
 * supplies credentials in a URL and never treats these rows as publication.
 */
export type DevPreviewState = 'disabled' | 'unavailable' | 'loading' | 'ready' | 'error';

export const DEV_PREVIEW_PATH = '/api/dev/preview/candidates';
export const DEV_PREVIEW_QUERY = 'dev-candidates';
export const DEV_PREVIEW_TOKEN_HEADER = 'X-UEC-Dev-Preview-Token';
export const TEST_RELEASE_PATH = '/api/dev/preview/test-release';
export const TEST_RELEASE_API_VERSION = 'dev-test-v1';
export const TEST_RELEASE_LABEL = 'Disposable test release — not project-approved or published';
export const testReleasePath = (resource: 'locations' | 'filters' | 'facets' | 'csv', id?: string): string =>
  `${TEST_RELEASE_PATH}/${resource}${id ? `/${encodeURIComponent(id)}` : ''}`;

/** Keep a manually typed preview URL inert in production builds. */
export const canOpenDevPreview = (isDevelopment: boolean, requestedMode: string | null): boolean =>
  isDevelopment && requestedMode === DEV_PREVIEW_QUERY;

/** Persistent copy used on every private-preview surface. */
export const DEV_PREVIEW_LABEL = 'PRIVATE TEST DATA — NOT REVIEWED OR PUBLISHED';
export const devPreviewExportLabel = (isPreview: boolean): string | null => isPreview ? 'Private test preview — export unavailable.' : null;
export const canMountPublicExport = (isPreview: boolean): boolean => !isPreview;
