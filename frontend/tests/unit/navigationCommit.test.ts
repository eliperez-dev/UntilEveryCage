import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createNavigationCommitGuard } from '../../src/app/navigationCommit';

describe('cold header navigation during lazy workspace loading', () => {
  let guard: ReturnType<typeof createNavigationCommitGuard>;
  beforeEach(() => {
    vi.useFakeTimers();
    document.body.innerHTML = '<div class="masthead"><a href="#/about"><span>About</span></a></div><button>Other</button>';
    guard = createNavigationCommitGuard(window);
  });
  afterEach(() => { guard.dispose(); document.body.innerHTML = ''; vi.useRealTimers(); });
  const press = () => document.querySelector('a span')!.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true, button: 0 }));
  it('commits immediately outside a header link gesture', () => {
    const commit = vi.fn();
    document.querySelector('button')!.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }));
    guard.commit(commit); expect(commit).toHaveBeenCalledOnce();
  });
  it('retains the link through release and the native click task', async () => {
    const commit = vi.fn(); press(); guard.commit(commit);
    window.dispatchEvent(new MouseEvent('pointerup'));
    await Promise.resolve(); expect(commit).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(0); expect(commit).toHaveBeenCalledOnce();
  });
  for (const event of ['pointercancel', 'blur']) it(`releases a deferred workspace after ${event}`, async () => {
    const commit = vi.fn(); press(); guard.commit(commit);
    window.dispatchEvent(new MouseEvent(event));
    await vi.advanceTimersByTimeAsync(0); expect(commit).toHaveBeenCalledOnce();
  });
  it('drops deferred commits and listeners when the app is disposed', async () => {
    const commit = vi.fn(); press(); guard.commit(commit);
    window.dispatchEvent(new MouseEvent('pointerup')); guard.dispose();
    await vi.advanceTimersByTimeAsync(0); guard.commit(commit);
    expect(commit).not.toHaveBeenCalled();
  });
});
