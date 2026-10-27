export type SheetSnap = 'collapsed' | 'middle' | 'expanded';
export type SheetTuning = Readonly<{ middlePercent?: number; expandedPercent?: number }>;
export const COLLAPSED_SHEET_HEIGHT = 56;
export function filterViewportHeight(top: number, viewportBottom: number, safeArea = 0): number {
  return Math.max(0, Math.floor(viewportBottom - top - Math.max(0, safeArea) - 8));
}
export function sheetHeights(available: number, tuning: SheetTuning = {}, safeArea = 0) {
  const workspace = Math.max(0, Number.isFinite(available) ? available : 0);
  const collapsed = Math.min(workspace, COLLAPSED_SHEET_HEIGHT + Math.max(0, safeArea));
  const middlePercent = Math.max(35, Math.min(65, tuning.middlePercent ?? 48));
  const expandedPercent = Math.max(75, Math.min(95, tuning.expandedPercent ?? 90));
  return { collapsed, middle: Math.max(collapsed, workspace * middlePercent / 100), expanded: Math.max(collapsed, workspace * expandedPercent / 100) };
}
export function nearestSheetSnap(height: number, heights: ReturnType<typeof sheetHeights>): SheetSnap {
  return (Object.keys(heights) as SheetSnap[]).reduce((closest, key) => Math.abs(heights[key] - height) < Math.abs(heights[closest] - height) ? key : closest, 'collapsed');
}
export function sheetKeyboardSnap(key: string, current: SheetSnap): SheetSnap | null {
  const order: SheetSnap[] = ['collapsed', 'middle', 'expanded'];
  if (key === 'Home') return 'collapsed';
  if (key === 'End') return 'expanded';
  if (key === 'ArrowUp') return order[Math.min(2, order.indexOf(current) + 1)]!;
  if (key === 'ArrowDown') return order[Math.max(0, order.indexOf(current) - 1)]!;
  return null;
}
