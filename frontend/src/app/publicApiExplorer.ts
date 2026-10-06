export type ExplorerRequest = { url: string; method?: string; headers?: Record<string, string>; credentials?: RequestCredentials };
const publicGetPath = /^\/api\/v2\/(?:locations(?:\/[0-9a-f-]{36})?|locations\.csv|map\/feed|releases\/manifest|releases\/[A-Za-z0-9._-]+\/map\/tiles\/\d+\/\d+\/\d+\.mvt|discovery\/(?:filters|facets)|graph\/(?:connections|entities(?:\/[0-9a-f-]{36}\/neighborhood)?))$/i;
export function guardExplorerRequest(request: ExplorerRequest, origin: string, assetBase: string): ExplorerRequest {
  const url = new URL(request.url, origin);
  const referenceFiles = ['public-openapi.json', 'v2-location.schema.json'].map(name => new URL(`${assetBase}reference/${name}`, origin).pathname);
  if ((request.method ?? 'GET').toUpperCase() !== 'GET' || url.origin !== origin || url.username || url.password || (!publicGetPath.test(url.pathname) && !referenceFiles.includes(url.pathname))) throw new Error('The explorer supports public GET requests on this website only.');
  const safeHeaders: Record<string, string> = { Accept: 'application/json' };
  for (const [name, value] of Object.entries(request.headers ?? {})) {
    if (name.toLowerCase() === 'accept') safeHeaders.Accept = value;
    else if (name.toLowerCase() === 'if-none-match') safeHeaders['If-None-Match'] = value;
  }
  return { ...request, url: url.toString(), method: 'GET', credentials: 'omit', headers: safeHeaders };
}
export const explorerOptions = Object.freeze({
  supportedSubmitMethods: ['get'], validatorUrl: null, queryConfigEnabled: false,
  persistAuthorization: false, withCredentials: false, deepLinking: false,
  docExpansion: 'list', defaultModelsExpandDepth: -1, displayOperationId: false,
  showExtensions: false, tryItOutEnabled: false,
});
