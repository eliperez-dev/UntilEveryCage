import type { Profile } from '../domain/publication';

export type SessionState = Readonly<{
  profile: Profile;
  release: string | null;
  generation: number;
  status: 'idle' | 'loading' | 'ready' | 'error';
  locations: readonly string[];
  selectedId: string | null;
  error: string | null;
}>;

export type SnapshotResponse = Readonly<{ generation: number; profile: Profile; release: string; locationIds: readonly string[] }>;
export type SessionEvent =
  | Readonly<{ type: 'query/start'; profile: Profile }>
  | Readonly<{ type: 'query/success'; response: SnapshotResponse }>
  | Readonly<{ type: 'query/failure'; generation: number; message: string }>;

export const initialSession = (profile: Profile = 'curated'): SessionState => ({ profile, release: null, generation: 0, status: 'idle', locations: [], selectedId: null, error: null });

export function reduceSession(state: SessionState, event: SessionEvent): SessionState {
  if (event.type === 'query/start') {
    return { ...state, profile: event.profile, generation: state.generation + 1, status: 'loading', locations: [], selectedId: null, error: null };
  }
  const generation = event.type === 'query/success' ? event.response.generation : event.generation;
  if (generation !== state.generation) return state;
  if (event.type === 'query/failure') return { ...state, status: 'error', locations: [], selectedId: null, error: event.message };
  if (event.response.profile !== state.profile) return state;
  if (state.release !== null && event.response.release !== state.release) {
    return { ...state, release: event.response.release, status: 'loading', locations: [], selectedId: null, error: 'Release changed; refreshing this profile.' };
  }
  return { ...state, release: event.response.release, status: 'ready', locations: event.response.locationIds, selectedId: null, error: null };
}

export function acceptResponse(state: SessionState, response: SnapshotResponse): SessionState {
  return reduceSession(state, { type: 'query/success', response });
}
