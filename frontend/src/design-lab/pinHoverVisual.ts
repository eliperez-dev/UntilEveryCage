import { DEFAULT_FACILITY_PIN_SCALE } from './components/facilityPinScale';

export type PinHoverVisual = Readonly<{
  kind: 'pin' | 'dot';
  width: number;
  height: number;
  /** Bottom-anchored pins follow the artwork; dots are centered on coordinates. */
  transform: 'translate(-50%, -100%)' | 'translate(-50%, -50%)';
  maskUrl: string | null;
}>;

/** Geometry matches the actual 50×82 V1 raster at the renderer's half size.
 * The grey pin has the same alpha silhouette as the other category artwork.
 * Use this as an alpha mask with a stronger white glow, never a round pin halo. */
export function pinHoverVisual(
  pins: boolean, pinScale: number, coordinateRadius: number, baseUrl = '/',
): PinHoverVisual {
  if (!pins) {
    const radius = Number.isFinite(coordinateRadius) ? Math.max(3, Math.min(12, coordinateRadius)) : 6.5;
    return { kind: 'dot', width: radius * 2 + 8, height: radius * 2 + 8, transform: 'translate(-50%, -50%)', maskUrl: null };
  }
  const scale = Number.isFinite(pinScale) ? Math.max(0.6, Math.min(1.6, pinScale)) : DEFAULT_FACILITY_PIN_SCALE;
  // BASE_URL is a local build path. Reject arbitrary CSS/remote inputs rather
  // than embedding a feature property into a mask declaration.
  const prefix = /^\/(?:[A-Za-z0-9._~-]+\/)*$/.test(baseUrl) ? baseUrl : '/';
  return { kind: 'pin', width: 25 * scale, height: 41 * scale, transform: 'translate(-50%, -100%)',
    maskUrl: `${prefix}v1-pins/marker-icon-2x-grey.png` };
}
