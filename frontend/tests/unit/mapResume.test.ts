import { describe, expect, it } from 'vitest';
import { createMapResumeGuard, releaseIdentityKey } from '../../src/design-lab/mapResume';

describe('public map resume validation', () => {
  it('distinguishes release, manifest and current restriction generation', () => {
    const initial = { releaseId: 'synthetic-release', manifestSha256: 'a'.repeat(64), suppressionGeneration: 1 };
    expect(releaseIdentityKey({ ...initial })).toBe(releaseIdentityKey(initial));
    for (const identity of [{ ...initial, releaseId: 'other-release' }, { ...initial, manifestSha256: 'b'.repeat(64) }, { ...initial, suppressionGeneration: 2 }]) expect(releaseIdentityKey(identity)).not.toBe(releaseIdentityKey(initial));
    expect(releaseIdentityKey(null)).toBeNull();
  });

  it('accepts only a fresh active validation and rejects failures', async () => {
    const guard = createMapResumeGuard(); const accepted: string[] = []; let failures = 0;
    let finish: ((value: string) => void) | undefined;
    const first = guard.verify(() => new Promise<string>(resolve => finish = resolve), value => accepted.push(value), () => failures++);
    guard.pause(); finish?.('stale'); await first;
    expect(accepted).toEqual([]);
    await guard.verify(async () => 'fresh', value => accepted.push(value), () => failures++);
    expect(accepted).toEqual(['fresh']);
    await guard.verify(async () => { throw new Error('unavailable'); }, value => accepted.push(value), () => failures++);
    expect(failures).toBe(1);
  });

  it('prevents an older activation from replacing a newer validation', async () => {
    const guard = createMapResumeGuard(); const accepted: string[] = [];
    let finish: ((value: string) => void) | undefined;
    const older = guard.verify(() => new Promise<string>(resolve => finish = resolve), value => accepted.push(value), () => {});
    await guard.verify(async () => 'new', value => accepted.push(value), () => {});
    finish?.('old'); await older;
    expect(accepted).toEqual(['new']);
  });
});
