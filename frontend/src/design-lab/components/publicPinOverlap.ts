import { PUBLIC_PIN_ID } from '../publicPinSummaries';
import type { JsonMapCollection, JsonMapFeature } from './jsonMapFallback';

export type OverlapMember = Readonly<{ id: string; coordinates: [number, number]; feature: JsonMapFeature }>;
export type ScreenPoint = Readonly<{ x: number; y: number }>;
export type OverlapBounds = Readonly<{ left: number; top: number; right: number; bottom: number }>;
export const OVERLAP_BADGE_SOURCE = 'public-pin-stacks';
export const OVERLAP_BADGE_LAYER = 'public-pin-stack-count';
export const SHARED_POINT_PIN_IMAGE_PREFIX = 'v1-pin-shared-point-';
export const SHARED_POINT_PIN_SCALE = .4;

// MapLibre paints symbol text above every icon in its layer. Put the count
// in the icon so a pin in front can cover both the rear pin and its count.
export function sharedPointPinImage(image: HTMLImageElement | ImageBitmap, count: number): ImageData {
  const canvas = document.createElement('canvas');
  canvas.width = image.width;
  canvas.height = image.height;
  const context = canvas.getContext('2d')!;
  context.drawImage(image, 0, 0);
  const fontSize = count < 100 ? 10 : count < 1000 ? 8 : 7;
  context.font = `700 ${fontSize / SHARED_POINT_PIN_SCALE}px Arial, sans-serif`;
  context.fillStyle = '#fff';
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  context.fillText(String(count), canvas.width / 2, canvas.height - 22 / SHARED_POINT_PIN_SCALE);
  return context.getImageData(0, 0, canvas.width, canvas.height);
}

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
