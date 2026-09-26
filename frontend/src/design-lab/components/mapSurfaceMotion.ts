/**
 * Canvas-only primitives for map cluster motion.
 *
 * These helpers deliberately do not know about MapLibre sources or Svelte state.
 * Keeping the drawing contract here makes the controller in MapSurface readable
 * and prevents a visual transition from accidentally becoming a data source.
 */

export type MotionDot = Readonly<{
  x: number;
  y: number;
  longitude?: number;
  latitude?: number;
  count: number;
  color: string;
  featureKey?: string;
  parentKey?: string;
}>;

export type ClusterMotion = Readonly<{
  startedAt: number;
  duration: number;
  origin: MotionDot;
  children: readonly MotionDot[];
  direction?: "split" | "join";
}>;

export function mvtClusterColor(count: number): string {
  if (count >= 100) return "#f18017b8";
  if (count >= 10) return "#f0c20cb8";
  return "#6ecc39b8";
}

export function resizeMotionCanvas(
  canvas: HTMLCanvasElement,
  width: number,
  height: number,
  pixelRatio: number,
): CanvasRenderingContext2D | undefined {
  const deviceWidth = Math.round(width * pixelRatio);
  const deviceHeight = Math.round(height * pixelRatio);

  if (canvas.width !== deviceWidth || canvas.height !== deviceHeight) {
    canvas.width = deviceWidth;
    canvas.height = deviceHeight;
  }

  const context = canvas.getContext("2d") ?? undefined;
  context?.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  return context;
}

/** Draw the disc and count together so an animation never leaves orphaned text. */
export function drawMotionDot(
  context: CanvasRenderingContext2D,
  value: MotionDot,
  opacity: number,
  scale: number,
): void {
  context.save();
  context.globalAlpha = opacity;
  context.translate(value.x, value.y);
  context.scale(scale, scale);
  context.beginPath();
  context.arc(0, 0, 20, 0, Math.PI * 2);
  context.fillStyle = "#f1efe899";
  context.fill();
  context.beginPath();
  context.arc(0, 0, 15, 0, Math.PI * 2);
  context.fillStyle = value.color;
  context.fill();
  context.fillStyle = "#172019";
  context.font = "700 12px system-ui";
  context.textAlign = "center";
  context.textBaseline = "middle";
  context.fillText(String(value.count), 0, 0);
  context.restore();
}
