export type ClusterPaintFrame = { time: number; hidden: string[]; visible: string[] };

/** A hidden merge parent is covered while its previously painted children
 * remain visible. Judge each recorded frame against the actual native lineage,
 * including replies that arrived after that frame; do not mistake a hold for
 * an empty map, or count offscreen draw attempts as painted replacements.
 */
export function maxUnpaintedBranchMs(frames: ClusterPaintFrame[], lineage: [string, string][]): number {
  const children = new Map<string, Set<string>>();
  for (const [parent, child] of lineage) {
    if (!children.has(parent)) children.set(parent, new Set());
    children.get(parent)!.add(child);
  }
  const missingSince = new Map<string, number>();
  let maximum = 0;
  for (const frame of frames) {
    const visible = new Set(frame.visible), missing = new Set<string>();
    for (const key of frame.hidden) {
      const queue = [key], visited = new Set<string>();
      let covered = false;
      while (queue.length) {
        const next = queue.pop()!;
        if (visited.has(next)) continue;
        visited.add(next);
        if (visible.has(next)) { covered = true; break; }
        for (const child of children.get(next) ?? []) queue.push(child);
      }
      if (covered) continue;
      missing.add(key);
      if (!missingSince.has(key)) missingSince.set(key, frame.time);
      maximum = Math.max(maximum, frame.time - missingSince.get(key)!);
    }
    for (const key of missingSince.keys()) if (!missing.has(key)) missingSince.delete(key);
  }
  return maximum;
}
