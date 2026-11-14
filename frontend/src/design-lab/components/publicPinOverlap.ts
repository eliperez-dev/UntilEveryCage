import { PUBLIC_PIN_ID } from '../publicPinSummaries';
import type { JsonMapCollection, JsonMapFeature } from './jsonMapFallback';

export type OverlapMember = Readonly<{ id: string; coordinates: [number, number]; feature: JsonMapFeature }>;
export type ScreenPoint = Readonly<{ x: number; y: number }>;
export type OverlapBounds = Readonly<{ left: number; top: number; right: number; bottom: number }>;
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

/** Neutral pin art shared by groups of the same size. */
export function createOverlapBadgeImage(count: number): ImageData | null {
  const canvas = document.createElement('canvas');
  canvas.width = 88;
  canvas.height = 96;
  const context = canvas.getContext('2d');
  if (!context) return null;
  context.scale(2, 2);
  context.beginPath();
  context.moveTo(22, 47);
  context.bezierCurveTo(16, 37, 5, 29, 5, 19);
  context.arc(22, 19, 17, Math.PI, 0);
  context.bezierCurveTo(39, 29, 28, 37, 22, 47);
  context.closePath();
  context.fillStyle = '#302e2b';
  context.fill();
  context.strokeStyle = '#fff8e9';
  context.lineWidth = 2;
  context.lineJoin = 'round';
  context.stroke();
  context.fillStyle = '#fff8e9';
  context.font = `700 ${count < 1000 ? 13 : 10}px system-ui, sans-serif`;
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  context.fillText(String(count), 22, 19, 28);
  return context.getImageData(0, 0, canvas.width, canvas.height);
}

export function overlapPanelFrame(bounds: OverlapBounds, anchor: ScreenPoint, count: number) {
  const width = Math.max(0, Math.min(304, bounds.right - bounds.left));
  const height = Math.max(0, Math.min(382, bounds.bottom - bounds.top));
  const visibleHeight = Math.min(height, 52 + 48 * count);
  const right = anchor.x + 25;
  const preferred = right + width <= bounds.right ? right : anchor.x - 25 - width;
  return {
    left: Math.max(bounds.left, Math.min(preferred, bounds.right - width)),
    top: Math.max(bounds.top, Math.min(anchor.y - 47, bounds.bottom - visibleHeight)),
    width,
    maxHeight: height,
  };
}
