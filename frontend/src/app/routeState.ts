export type RouteState =
  | Readonly<{ kind: 'map' }>
  | Readonly<{ kind: 'database' }>
  | Readonly<{ kind: 'methodology' }>
  | Readonly<{ kind: 'record'; facilityId: string }>
  | Readonly<{ kind: 'not-found'; fragment: string }>;

type RoutableState = Exclude<RouteState, { kind: 'not-found' }>;

export function parseRoute(hash: string): RouteState {
  const raw = hash.startsWith('#') ? hash.slice(1) : hash;
  const [pathPart] = raw.split('?');
  const path = pathPart || '/map';

  if (path === '/' || path === '/map') return { kind: 'map' };
  if (path === '/database') return { kind: 'database' };
  if (path === '/methodology') return { kind: 'methodology' };

  // Keep old shared links working while the public route changes to /records/:id.
  const recordMatch = /^\/(?:records|locations)\/([a-z0-9-]+)$/.exec(path);
  if (recordMatch?.[1]) return { kind: 'record', facilityId: recordMatch[1] };

  return { kind: 'not-found', fragment: raw };
}

export function serializeRoute(route: RoutableState): string {
  if (route.kind === 'map') return '#/map';
  if (route.kind === 'database') return '#/database';
  if (route.kind === 'methodology') return '#/methodology';
  return `#/records/${encodeURIComponent(route.facilityId)}`;
}
