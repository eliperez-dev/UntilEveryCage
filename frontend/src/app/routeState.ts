import type { Profile } from '../domain/publication';
export type RouteState = Readonly<{kind:'home';profile:Profile}> | Readonly<{kind:'location';facilityId:string;profile:Profile}> | Readonly<{kind:'not-found';fragment:string}>;
const profiles: readonly Profile[]=['curated','official','secondary','community'];
const profileOf=(value:string|null):Profile=>profiles.includes(value as Profile)?value as Profile:'curated';
export function parseRoute(hash:string):RouteState { const raw=hash.startsWith('#')?hash.slice(1):hash; const [pathPart,query='']=raw.split('?'); const path=pathPart ?? ''; const profile=profileOf(new URLSearchParams(query).get('profile')); if(path===''||path==='/') return {kind:'home',profile}; const match=/^\/locations\/([a-z0-9-]+)$/.exec(path); if(match?.[1]) return {kind:'location',facilityId:match[1],profile}; return {kind:'not-found',fragment:raw}; }
export function serializeRoute(route:Exclude<RouteState,{kind:'not-found'}>):string { const path=route.kind==='home'?'/':`/locations/${encodeURIComponent(route.facilityId)}`; return `#${path}?profile=${route.profile}`; }
