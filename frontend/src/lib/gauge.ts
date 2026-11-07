// Speedometer scale: labels increase left to right, 20 sits at the top centre and
// the 150 tok/s maximum at the far-right end. Between ticks the scale is linear.

export const GAUGE_TICKS = [0, 10, 20, 30, 60, 90, 120, 150] as const;
export const GAUGE_POSITIONS = [0, 0.25, 0.5, 0.6, 0.7, 0.8, 0.9, 1] as const;

/** Total arc in degrees; centred on straight up, so 0.5 is always the top. */
export const GAUGE_SWEEP = 220;

export function valueToFraction(value: number): number {
  if (!Number.isFinite(value) || value <= 0) return 0;
  const last = GAUGE_TICKS.length - 1;
  if (value >= GAUGE_TICKS[last]) return 1;
  for (let i = 1; i <= last; i++) {
    if (value <= GAUGE_TICKS[i]) {
      const span = (value - GAUGE_TICKS[i - 1]) / (GAUGE_TICKS[i] - GAUGE_TICKS[i - 1]);
      return GAUGE_POSITIONS[i - 1] + span * (GAUGE_POSITIONS[i] - GAUGE_POSITIONS[i - 1]);
    }
  }
  return 1;
}

/** Rotation in degrees from straight up (negative = left, positive = right). */
export function fractionToRotation(fraction: number): number {
  return (fraction - 0.5) * GAUGE_SWEEP;
}

/** Point on a circle for a fraction of the arc, in SVG coordinates (y down). */
export function pointOnArc(cx: number, cy: number, radius: number, fraction: number): { x: number; y: number } {
  const radians = (fractionToRotation(fraction) * Math.PI) / 180;
  return { x: cx + radius * Math.sin(radians), y: cy - radius * Math.cos(radians) };
}
