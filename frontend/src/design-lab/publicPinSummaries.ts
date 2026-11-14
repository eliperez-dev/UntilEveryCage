import type { PublicPinSummary } from './contract';
import { isTaxonomyPrimaryKey } from '../domain/taxonomy';

export const PUBLIC_PIN_ID = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;

function displayLabel(value: PublicPinSummary | null): PublicPinSummary | null {
  if (!value || typeof value.name !== 'string' || !value.name.trim()
    || value.name.length > 512 || !isTaxonomyPrimaryKey(value.categoryKey)) return null;
  // Keep text as text. Svelte's normal text interpolation performs escaping;
  // this helper never creates HTML or carries source/detail fields into a label.
  return Object.freeze({ name: value.name.trim(), categoryKey: value.categoryKey,
    ...(typeof value.nameProvided === 'boolean' ? { nameProvided: value.nameProvided } : {}),
    ...(typeof value.locality === 'string' && value.locality.trim() && value.locality.length <= 512 ? { locality: value.locality.trim() } : {}),
    ...(typeof value.country === 'string' && /^[A-Z]{2}$/.test(value.country) ? { country: value.country } : {}),
  });
}

/** Only tiny public display labels live here, never detail payloads or disk data. */
export function createPublicPinSummaries(
  read: (id: string, signal: AbortSignal) => Promise<PublicPinSummary | null>,
  now: () => number = Date.now,
  capacity = 48,
  ttlMs = 30_000,
) {
  let context: string | null = null;
  let generation = 0;
  const limit = Number.isFinite(capacity) ? Math.max(0, Math.floor(capacity)) : 48;
  const labels = new Map<string, { label: PublicPinSummary; expires: number }>();
  const pending = new Set<AbortController>();
  const usable = (id: string) => !!context && PUBLIC_PIN_ID.test(id);
  function remember(id: string, value: PublicPinSummary | null): PublicPinSummary | null {
    if (!usable(id)) return null;
    const label = displayLabel(value);
    if (!label) { labels.delete(id); return null; }
    labels.delete(id);
    labels.set(id, { label, expires: now() + ttlMs });
    while (labels.size > limit) labels.delete(labels.keys().next().value!);
    return label;
  }
  function peek(id: string): PublicPinSummary | null {
    if (!usable(id)) return null;
    const cached = labels.get(id);
    if (!cached || cached.expires <= now()) { labels.delete(id); return null; }
    labels.delete(id); labels.set(id, cached);
    return cached.label;
  }
  return {
    setContext(value: string | null) {
      if (value === context) return;
      context = value; generation++;
      for (const controller of pending) controller.abort();
      pending.clear(); labels.clear();
    },
    /** Synchronous fast path after setContext; never starts a request. */
    peek,
    contextToken: () => context ? generation : null,
    /** Seed only from an already verified public list/detail in this generation. */
    remember(id: string, value: PublicPinSummary | null, token: number | null) {
      return token !== null && token === generation ? remember(id, value) : null;
    },
    async resolve(id: string, signal: AbortSignal): Promise<PublicPinSummary | null> {
      if (!usable(id) || signal.aborted) return null;
      const cached = peek(id);
      if (cached) return cached;
      const ticket = generation;
      const controller = new AbortController();
      const abort = () => controller.abort();
      signal.addEventListener('abort', abort, { once: true });
      pending.add(controller);
      try {
        const value = await read(id, controller.signal);
        if (controller.signal.aborted || signal.aborted || generation !== ticket || !context) return null;
        return remember(id, value);
      } catch {
        if (generation === ticket) labels.delete(id);
        return null;
      } finally {
        pending.delete(controller);
        signal.removeEventListener('abort', abort);
      }
    },
  };
}
