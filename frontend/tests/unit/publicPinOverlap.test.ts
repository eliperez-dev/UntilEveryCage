import { describe, expect, it } from 'vitest';
import { collectPublicOverlap, coordinateKey, createConcentricRingLayout, createPublicOverlapIndex, projectRingPoint, publicOverlapMember, ringViewport } from '../../src/design-lab/components/publicPinOverlap';
import type { JsonMapCollection, JsonMapFeature } from '../../src/design-lab/components/jsonMapFallback';

const point = (n: number, coordinates: [number, number] = [12, 34], precision = 'source_reported'): JsonMapFeature => ({
  type: 'Feature', id: `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`,
  geometry: { type: 'Point', coordinates },
  properties: { key: `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`, weight: 1, precision, kind: precision === 'approximate' ? 'reference' : 'source-coordinate' },
});
const collection = (...features: JsonMapFeature[]): JsonMapCollection => ({ type: 'FeatureCollection', features });

describe('public pin overlaps', () => {
  it('finds the complete shared-point group from a single rendered member and preserves individual precision', () => {
    const features = Array.from({ length: 81 }, (_, i) => point(i, [12, 34], i % 2 ? 'approximate' : 'source_reported'));
    const index = createPublicOverlapIndex(collection(...features));
    const result = collectPublicOverlap(index, [features[75]], { x: 100, y: 100 }, () => ({ x: 100, y: 100 }));
    expect(result).toHaveLength(81);
    expect(new Set(result.map(member => member.feature.properties.precision)).size).toBe(2);
    expect(result[0]!.feature).toBe(features[0]);
  });
  it('does not carry old release/filter membership into a replacement collection', () => {
    const first = point(1), second = point(2);
    const previous = createPublicOverlapIndex(collection(first, second));
    const filtered = createPublicOverlapIndex(collection(second));
    expect(previous.group(String(second.id))).toHaveLength(2);
    expect(filtered.group(String(second.id))).toHaveLength(1);
    expect(collectPublicOverlap(filtered, [first], { x: 0, y: 0 }, () => ({ x: 0, y: 0 }))).toEqual([]);
  });
  it('has stable deduplicated IDs and excludes clusters, private reference keys, weighted aggregates and invalid coordinates', () => {
    const first = point(1), second = point(2);
    const invalid = [
      { ...point(3), properties: { key: 'a'.repeat(32), weight: 1 } },
      { ...point(4), properties: { ...point(4).properties, cluster_id: 12 } },
      { ...point(5), properties: { ...point(5).properties, kind: 'aggregate' } },
      { ...point(6), properties: { ...point(6).properties, weight: 81 } },
      point(7, [0, 91]), point(8, [181, 0]), point(9, [NaN, 0]),
    ];
    const index = createPublicOverlapIndex(collection(second, ...invalid, first, second));
    expect([...index.byId.keys()]).toHaveLength(2);
    expect(index.group(String(first.id)).map(member => member.id)).toEqual([String(first.id), String(second.id)]);
    for (const feature of invalid) expect(publicOverlapMember(feature)).toBeNull();
  });
  it('supports wrapped world copies without changing real member geometry', () => {
    const feature = point(1, [180, 0]);
    const other = point(2, [-180, 0]);
    const index = createPublicOverlapIndex(collection(feature, other));
    expect(coordinateKey([180, 0])).toBe(coordinateKey([-180, 0]));
    expect(index.group(String(feature.id))).toHaveLength(2);
    const wrapped = { ...feature, geometry: { type: 'Point', coordinates: [540, 0] } };
    const matches = collectPublicOverlap(index, [wrapped], { x: 50, y: 50 }, () => ({ x: 50, y: 50 }));
    expect(matches).toHaveLength(2);
    expect(matches.find(member => member.id === feature.id)?.coordinates).toEqual([180, 0]);
  });
  it('expands visible nearby overlaps but excludes unrelated marks and unfiltered rendered leftovers', () => {
    const first = point(1, [1, 1]), second = point(2, [2, 2]), far = point(3, [100, 100]);
    const stale = point(4, [1, 1]);
    const index = createPublicOverlapIndex(collection(first, second, far));
    const result = collectPublicOverlap(index, [first, second, far, stale], { x: 0, y: 0 }, coordinates => ({ x: coordinates[0] * 10, y: coordinates[1] * 10 }), 30);
    expect(result.map(member => member.id)).toEqual([String(first.id), String(second.id)]);
    expect(result.map(member => member.coordinates)).toEqual([[1, 1], [2, 2]]);
  });
});

describe('growing concentric ring geometry', () => {
  it('uses one evenly spaced ring for eight records and caps every ring at twelve', () => {
    expect(createConcentricRingLayout(0)).toEqual({ positions: [], ringCounts: [], ringRadii: [], radius: 0 });
    expect(createConcentricRingLayout(8).ringCounts).toEqual([8]);
    expect(createConcentricRingLayout(12).ringCounts).toEqual([12]);
    expect(createConcentricRingLayout(13).ringCounts).toEqual([7,6]);
    expect(createConcentricRingLayout(25).ringCounts).toEqual([9,8,8]);
    const layout = createConcentricRingLayout(64);
    expect(layout.ringCounts).toEqual([11,11,11,11,10,10]);
    for (let ring = 0; ring < layout.ringCounts.length; ring++) {
      const members = layout.positions.filter(position => position.ring === ring + 1);
      const radius = layout.ringRadii[ring]!;
      const chord = 2 * radius * Math.sin(Math.PI / members.length);
      for (const member of members) expect(Math.hypot(member.x, member.y)).toBeCloseTo(radius);
      for (let i = 0; i < members.length; i++) {
        const first = members[i]!, second = members[(i + 1) % members.length]!;
        expect(Math.hypot(first.x - second.x, first.y - second.y)).toBeCloseTo(chord);
      }
      if (ring > 0) expect(radius - layout.ringRadii[ring - 1]!).toBe(44);
    }
  });
  for (const total of [6,8,12,13,18,25,36,214,614]) it('lays out all '+total+' records once with disjoint44px targets', () => {
    const layout=createConcentricRingLayout(total);
    expect(Math.max(...layout.ringCounts)).toBeLessThanOrEqual(12);
    expect(Math.max(...layout.ringCounts)-Math.min(...layout.ringCounts)).toBeLessThanOrEqual(1);
    expect(layout.positions.map(p=>p.index)).toEqual(Array.from({length:total},(_,i)=>i));
    for (const p of layout.positions) {
      expect(Math.hypot(p.x,p.y)).toBeCloseTo(layout.ringRadii[p.ring-1]!);
      for (const q of layout.positions.slice(p.index+1)) expect(Math.hypot(p.x-q.x,p.y-q.y)).toBeGreaterThanOrEqual(44);
    }
  });
  for (const width of [375,390,768]) for (const total of [214,614]) {
    it('uses a bounded member list instead of clipped rings at width '+width+' for '+total+' records', () => {
      const layout = createConcentricRingLayout(total);
      const viewport = ringViewport({left:12,right:width-12,top:70,bottom:640},{x:width/2,y:280},layout.radius);
      expect(viewport.usable).toBe(true);
      expect(viewport.overflow).toBe(true);
      expect(viewport.width).toBeLessThanOrEqual(width-24);
      expect(viewport.height).toBeLessThanOrEqual(420);
      expect(layout.positions).toHaveLength(total);
      expect(viewport.bounds.top).toBeGreaterThanOrEqual(122);
      expect(viewport.bounds.bottom).toBeLessThanOrEqual(640);
    });
  }
  it('fits thirty-six compact records into a fixed surface under450px', () => {
    const layout = createConcentricRingLayout(36);
    const viewport = ringViewport({left:12,right:1428,top:120,bottom:820},{x:700,y:450},layout.radius);
    expect(layout.ringRadii).toEqual([86,130,174]);
    expect(viewport.overflow).toBe(false);
    expect(viewport.width).toBe(436);
    expect(viewport.height).toBe(436);
    for (const position of layout.positions) {
      const point = projectRingPoint(position,viewport.center);
      expect(point.x-22).toBeGreaterThanOrEqual(viewport.bounds.left);
      expect(point.x+22).toBeLessThanOrEqual(viewport.bounds.right);
      expect(point.y-42).toBeGreaterThanOrEqual(viewport.bounds.top);
      expect(point.y+22).toBeLessThanOrEqual(viewport.bounds.bottom);
    }
  });
  it('centers a ring on the source anchor when there is room and clamps only at viewport edges', () => {
    const layout = createConcentricRingLayout(8);
    const bounds = { left: 12, right: 1100, top: 80, bottom: 800 };
    const anchor = { x: 550, y: 400 };
    const centered = ringViewport(bounds, anchor, layout.radius);
    expect(centered.center).toEqual(anchor);
    const edged = ringViewport(bounds, { x: 20, y: 90 }, layout.radius);
    expect(edged.bounds.left).toBeGreaterThanOrEqual(bounds.left);
    expect(edged.bounds.top).toBeGreaterThanOrEqual(bounds.top + 52);
    expect(edged.bounds.right).toBeLessThanOrEqual(bounds.right);
    expect(edged.bounds.bottom).toBeLessThanOrEqual(bounds.bottom);
  });
  it('does not place the group viewport over a short or fully expanded sheet',()=>{
    for(const bottom of [100,250]) expect(ringViewport({left:12,right:360,top:80,bottom},{x:100,y:100},createConcentricRingLayout(81).radius).usable).toBe(false);
  });
});
