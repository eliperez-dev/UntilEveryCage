import type { PublicReleaseIdentity } from '../api/PublicReleaseRepository';

export function releaseIdentityKey(identity: PublicReleaseIdentity | null): string | null {
  return identity ? `${identity.releaseId}:${identity.manifestSha256}:${identity.suppressionGeneration}` : null;
}

/** One transient validation lease. A paused or superseded check cannot reveal a map. */
export function createMapResumeGuard() {
  let generation = 0;
  let controller: AbortController | undefined;
  return {
    pause() { generation++; controller?.abort(); controller = undefined; },
    async verify<T>(read: (signal: AbortSignal) => Promise<T>, accept: (value: T) => void, reject: () => void) {
      controller?.abort();
      controller = new AbortController();
      const pending = controller;
      const ticket = ++generation;
      try {
        const value = await read(pending.signal);
        if (ticket === generation && !pending.signal.aborted) accept(value);
      } catch {
        if (ticket === generation && !pending.signal.aborted) reject();
      }
    },
  };
}
