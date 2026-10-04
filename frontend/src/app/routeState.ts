export type RouteState =
  | Readonly<{ kind: 'map' }>
  | Readonly<{ kind: 'database' }>
  | Readonly<{ kind: 'methodology' }>
  | Readonly<{ kind: 'record'; facilityId: string }>
  | Readonly<{ kind: 'community'; page: 'contribute' | 'status' | 'claims' | 'claim-detail' | 'review'; claimId?: string; targetRecordId?: string; releaseId?: string }>
  | Readonly<{ kind: 'not-found'; fragment: string }>;

type RoutableState = Exclude<RouteState, { kind: 'not-found' }>;

export function parseRoute(hash: string): RouteState {
  const raw = hash.startsWith('#') ? hash.slice(1) : hash;
  const [pathPart] = raw.split('?');
  const path = pathPart || '/map';

  if (path === '/' || path === '/map') return { kind: 'map' };
  if (path === '/database') return { kind: 'database' };
  if (path === '/methodology') return { kind: 'methodology' };
  if (path === '/contribute') {
    const targetRecordId = new URLSearchParams(raw.split('?')[1] ?? '').get('target');
    return { kind: 'community', page: 'contribute', ...(targetRecordId ? { targetRecordId } : {}) };
  }
  if (path === '/contribution-status') return { kind: 'community', page: 'status' };
  if (path === '/community') return { kind: 'community', page: 'claims' };
  if (path === '/community/claim') {
    const claimId = new URLSearchParams(raw.split('?')[1] ?? '').get('id');
    const releaseId = new URLSearchParams(raw.split('?')[1] ?? '').get('release_id');
    if (claimId && /^[a-zA-Z0-9-]{1,80}$/.test(claimId)) return { kind: 'community', page: 'claim-detail', claimId, ...(releaseId ? { releaseId } : {}) };
  }
  if (path === '/contribution-review') return { kind: 'community', page: 'review' };

  // Keep old shared links working while the public route changes to /records/:id.
  const recordMatch = /^\/(?:records|locations)\/([a-z0-9-]+)$/.exec(path);
  if (recordMatch?.[1]) return { kind: 'record', facilityId: recordMatch[1] };

  return { kind: 'not-found', fragment: raw };
}

export function serializeRoute(route: RoutableState): string {
  if (route.kind === 'map') return '#/map';
  if (route.kind === 'database') return '#/database';
  if (route.kind === 'methodology') return '#/methodology';
  if (route.kind === 'community') {
    if (route.page === 'contribute') return `#/contribute${route.targetRecordId ? `?target=${encodeURIComponent(route.targetRecordId)}` : ''}`;
    if (route.page === 'status') return '#/contribution-status';
    if (route.page === 'claims') return '#/community';
    if (route.page === 'claim-detail') return `#/community/claim?id=${encodeURIComponent(route.claimId ?? '')}${route.releaseId ? `&release_id=${encodeURIComponent(route.releaseId)}` : ''}`;
    return '#/contribution-review';
  }
  return `#/records/${encodeURIComponent(route.facilityId)}`;
}
