import { PUBLIC_PIN_ID } from '../pinHoverLabels';
import type { JsonMapCollection, JsonMapFeature } from './jsonMapFallback';

export type OverlapMember = Readonly<{ id: string; coordinates: [number, number]; feature: JsonMapFeature }>;
export type ScreenPoint = Readonly<{ x: number; y: number }>;
export type RingBounds = Readonly<{ left: number; top: number; right: number; bottom: number }>;
export const OVERLAP_LAYERS = ['v1-source-pins', 'source-coordinate-points', 'approx-reference-pins', 'approx-reference-points', 'approx-reference-circles'];
export const OVERLAP_BADGE_SOURCE = 'public-pin-stacks';
export const OVERLAP_BADGE_LAYER = 'public-pin-stack-count';

export function publicOverlapMember(feature: any, allowWrapped = false): OverlapMember | null {
  const properties = feature?.properties;
  const id = properties?.facility_id ?? properties?.key ?? properties?.id;
  const coordinates = feature?.geometry?.coordinates;
  if (properties?.cluster || properties?.cluster_id !== undefined || properties?.kind === 'aggregate'
    || properties?.kind === 'cluster' || Number(properties?.weight ?? 1) !== 1
    || typeof id !== 'string' || !PUBLIC_PIN_ID.test(id) || feature?.geometry?.type !== 'Point'
    || !Array.isArray(coordinates) || !Number.isFinite(coordinates[0]) || !Number.isFinite(coordinates[1])
    || Math.abs(coordinates[1]) > 90 || (!allowWrapped && Math.abs(coordinates[0]) > 180)) return null;
  return { id: id.toLowerCase(), coordinates: [normalizeLongitude(coordinates[0]), coordinates[1]], feature };
}

export function normalizeLongitude(value: number): number {
  return ((value + 180) % 360 + 360) % 360 - 180;
}
// Avoid rounding ordinary coordinates: nearby sites are not the same point.
export function coordinateKey(coordinates: readonly [number, number]): string {
  const longitude = coordinates[0];
  return `${longitude >= -180 && longitude < 180 ? longitude : normalizeLongitude(longitude)},${coordinates[1]}`;
}

/** One lazy index for the current immutable, already filtered public collection.
 * No detail data, persisted coordinates, or second spatial hierarchy is created. */
export function createPublicOverlapIndex(collection: JsonMapCollection) {
  const byId = new Map<string, OverlapMember>();
  const byCoordinate = new Map<string, OverlapMember[]>();
  for (const feature of collection.features) {
    const member = publicOverlapMember(feature);
    if (!member || byId.has(member.id)) continue;
    // Keep the original validated coordinate for geometry and precision selection.
    const coordinates = feature.geometry.coordinates;
    const original = { ...member, coordinates };
    byId.set(member.id, original);
    const key = coordinateKey(coordinates);
    const group = byCoordinate.get(key);
    if (group) group.push(original); else byCoordinate.set(key, [original]);
  }
  for (const group of byCoordinate.values()) group.sort((a, b) => a.id.localeCompare(b.id));
  return {
    byId,
    sharedGroups: () => [...byCoordinate.values()].filter(group => group.length > 1),
    group(id: string): readonly OverlapMember[] {
      const member = byId.get(id.toLowerCase());
      return member ? byCoordinate.get(coordinateKey(member.coordinates))! : [];
    },
  };
}
export type PublicOverlapIndex = ReturnType<typeof createPublicOverlapIndex>;

/** Only public members in the current collection enter a visual overlap.
 * Expand exact-coordinate groups even when native placement returns one mark. */
export function collectPublicOverlap(index: PublicOverlapIndex, rendered: readonly any[], clicked: ScreenPoint,
  project: (coordinates: [number, number]) => ScreenPoint, radius = 26): readonly OverlapMember[] {
  const result = new Map<string, OverlapMember>();
  for (const feature of rendered) {
    const candidate = publicOverlapMember(feature, true);
    const member = candidate && index.byId.get(candidate.id);
    if (!member) continue;
    const projected = project(member.coordinates);
    if (Math.hypot(projected.x - clicked.x, projected.y - clicked.y) > radius) continue;
    for (const sibling of index.group(member.id)) result.set(sibling.id, sibling);
  }
  return [...result.values()].sort((a, b) => a.id.localeCompare(b.id));
}

export type RingPosition = ScreenPoint & Readonly<{ index: number; ring: number }>;
export type ConcentricRingLayout = Readonly<{ positions: readonly RingPosition[]; ringCounts: readonly number[]; ringRadii: readonly number[]; radius: number }>;
export type RingViewport = Readonly<{ bounds: RingBounds; center: ScreenPoint; usable: boolean; overflow: boolean; width: number; height: number }>;
export const MAX_PINS_PER_RING = 12;
const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));

/** Display coordinates only. At most twelve evenly spaced pins per ring.
 * Balance populations so a sparse final ring never becomes a lone outer pin. */
export function createConcentricRingLayout(total: number, step = 44): ConcentricRingLayout {
  const positions: RingPosition[] = [];
  const ringCounts: number[] = [];
  const ringRadii: number[] = [];
  const spacing = Math.max(44, step);
  const rings = Math.max(1, Math.ceil(total / MAX_PINS_PER_RING));
  const baseCount = Math.floor(total / rings);
  const remainder = total % rings;
  // Keep a 44px target without a separate group zoom budget.
  const firstCount = baseCount + (remainder > 0 ? 1 : 0);
  const firstRadius = Math.max(spacing, Math.ceil(44 / (2 * Math.sin(Math.PI / Math.max(2, firstCount)))));
  let index = 0, ring = 0;
  while (index < total) {
    ring++;
    const count = baseCount + (ring <= remainder ? 1 : 0);
    const radius = firstRadius + spacing * (ring - 1);
    ringCounts.push(count);
    ringRadii.push(radius);
    const phase = ring % 2 === 0 ? Math.PI / count : 0;
    for (let i = 0; i < count; i++) {
      const angle = -Math.PI / 2 + i * Math.PI * 2 / count + phase;
      positions.push({ index: index++, ring, x: Math.cos(angle) * radius, y: Math.sin(angle) * radius });
    }
  }
  return { positions, ringCounts, ringRadii, radius: ringRadii.at(-1) ?? 0 };
}

/** Fixed rings fit completely; oversized groups use a bounded member list.
 * The caller has already excluded map controls, sheets and attribution. */
export function ringViewport(bounds: RingBounds, anchor: ScreenPoint, radius: number): RingViewport {
  const availableWidth = Math.max(0, bounds.right - bounds.left);
  const availableHeight = Math.max(0, bounds.bottom - bounds.top - 52);
  const diameter = Math.max(192, radius * 2 + 88);
  const overflow = diameter > Math.min(760, availableWidth, 600, availableHeight);
  const width = Math.max(0, Math.min(overflow ? 360 : diameter, availableWidth));
  const height = Math.max(0, Math.min(overflow ? 420 : diameter, availableHeight));
  const usable = width >= 188 && height >= (overflow ? 128 : 172);
  const center = {
    x: clamp(anchor.x, bounds.left + width / 2, bounds.right - width / 2),
    y: clamp(anchor.y, bounds.top + 52 + height / 2, bounds.bottom - height / 2),
  };
  return { center, bounds: { left: center.x - width / 2, right: center.x + width / 2, top: center.y - height / 2, bottom: center.y + height / 2 }, usable, overflow, width, height };
}

export function projectRingPoint(position: ScreenPoint, center: ScreenPoint): ScreenPoint {
  return { x: center.x + position.x, y: center.y + position.y };
}
