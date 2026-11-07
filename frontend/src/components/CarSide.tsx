import type { CarPalette } from "../models";

// Side-view open-wheel car on a 48×18 pixel grid, coloured per model.
type Part = [x: number, y: number, w: number, h: number, color: keyof CarPalette | "tire" | "shine"];

const TIRE_ROWS = [2, 3, 4, 5, 5, 5, 5, 5, 4, 3, 2]; // half-widths, top to bottom
const RIM_ROWS = [1, 2, 3, 3, 3, 2, 1];
const HUB_ROWS = [1, 1, 1];

function disc(cx: number, cy: number, rows: number[], color: Part[4]): Part[] {
  const top = cy - Math.floor(rows.length / 2);
  return rows.map((half, i) => [cx - half, top + i, half * 2 + 1, 1, color]);
}

function wheel(cx: number, cy: number): Part[] {
  return [...disc(cx, cy, TIRE_ROWS, "tire"), ...disc(cx, cy, RIM_ROWS, "rim"), ...disc(cx, cy, HUB_ROWS, "tire")];
}

const PARTS: Part[] = [
  // rear wing
  [1, 2, 9, 2, "body"],
  [1, 4, 2, 4, "dark"],
  [4, 4, 2, 4, "dark"],
  // engine cover, airbox, sidepod
  [5, 7, 12, 4, "body"],
  [15, 3, 4, 5, "dark"],
  [16, 2, 3, 1, "accent"],
  [12, 6, 16, 1, "body"],
  // main body and nose
  [8, 7, 30, 4, "body"],
  [38, 8, 5, 3, "body"],
  [43, 9, 3, 2, "body"],
  [12, 9, 26, 1, "stripe"],
  [10, 7, 6, 1, "shine"],
  // cockpit and halo
  [21, 4, 7, 1, "dark"],
  [21, 5, 2, 2, "dark"],
  [23, 5, 5, 2, "accent"],
  // floor
  [5, 11, 36, 1, "dark"],
  ...wheel(8, 12),
  ...wheel(36, 12),
  // front wing
  [39, 13, 9, 2, "body"],
  [46, 10, 2, 5, "dark"],
];

export function CarSide({ palette, scale = 4 }: { palette: CarPalette; scale?: number }) {
  const colors: Record<Part[4], string> = { ...palette, tire: "#14181E", shine: "rgba(255,255,255,0.55)" };
  return (
    <svg
      className="car-side"
      width={48 * scale}
      height={18 * scale}
      viewBox="0 0 48 18"
      shapeRendering="crispEdges"
      aria-hidden="true"
    >
      {PARTS.map(([x, y, w, h, color], i) => (
        <rect key={i} x={x} y={y} width={w} height={h} fill={colors[color]} />
      ))}
    </svg>
  );
}
