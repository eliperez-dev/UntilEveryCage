import type { PinHoverLabel } from './contract';
import { isTaxonomyPrimaryKey } from '../domain/taxonomy';

export const PUBLIC_PIN_ID = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;

/** Only tiny public display labels live here, never detail payloads or disk data. */
export function createPinHoverLabels(
  read: (id: string, signal: AbortSignal) => Promise<PinHoverLabel | null>,
  now: () => number = Date.now,
  capacity = 48,
  ttlMs = 30_000,
) {
  let context: string | null = null;
  let generation = 0;
  const labels = new Map<string, { label: PinHoverLabel; expires: number }>();
  const pending = new Set<AbortController>();
  return {
    setContext(value: string | null) {
      if (value === context) return;
      context = value; generation++;
      for (const controller of pending) controller.abort();
      pending.clear(); labels.clear();
    },
    async resolve(id: string, signal: AbortSignal): Promise<PinHoverLabel | null> {
      if (!context || signal.aborted || !PUBLIC_PIN_ID.test(id)) return null;
      const cached = labels.get(id);
      if (cached && cached.expires > now()) {
        labels.delete(id); labels.set(id, cached);
        return cached.label;
      }
      labels.delete(id);
      const ticket = generation;
      const controller = new AbortController();
      const abort = () => controller.abort();
      signal.addEventListener('abort', abort, { once: true });
      pending.add(controller);
      try {
        const value = await read(id, controller.signal);
        if (controller.signal.aborted || signal.aborted || generation !== ticket || !context
          || !value || typeof value.name !== 'string' || !value.name.trim()
          || value.name.length > 512 || !isTaxonomyPrimaryKey(value.categoryKey)) return null;
        const label = Object.freeze({ name: value.name.trim(), categoryKey: value.categoryKey });
        labels.set(id, { label, expires: now() + ttlMs });
        while (labels.size > capacity) labels.delete(labels.keys().next().value!);
        return label;
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

/** Aggregate references and cluster centres never enter the detail route. */
export function individualHoverPin(feature: any): { id: string; coordinates: [number, number] } | null {
  const props = feature?.properties;
  const id = props?.facility_id ?? props?.key ?? props?.id;
  const coordinates = feature?.geometry?.coordinates;
  if (props?.cluster || props?.cluster_id !== undefined || props?.kind === 'cluster' || props?.kind === 'aggregate'
    || Number(props?.weight ?? 1) !== 1 || typeof id !== 'string' || !PUBLIC_PIN_ID.test(id)
    || feature?.geometry?.type !== 'Point' || !Array.isArray(coordinates)
    || !Number.isFinite(coordinates[0]) || !Number.isFinite(coordinates[1])
    || Math.abs(coordinates[0]) > 180 || Math.abs(coordinates[1]) > 90) return null;
  return { id, coordinates: [coordinates[0], coordinates[1]] };
}
