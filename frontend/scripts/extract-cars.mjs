// Splits design/cars-source.png into one transparent PNG per demo model.
// The sheet has a flat light background; we flood-fill it from the crop edges
// so light pixels inside a car (the Flash car's pearl body) are kept.
import sharp from "sharp";

const SRC = new URL("../assets/design/cars-source.png", import.meta.url).pathname;
const OUT = new URL("../src/assets/cars/", import.meta.url).pathname;
const MODELS = ["qwen3.8-27b", "qwen3.8-flash-next", "muse-glimmer"]; // left → right
const TOLERANCE = 30; // summed RGB distance from the sampled background
const PAD = 4;
const EXACT = 4; // distance for seeding enclosed background holes
const MIN_HOLE = 12;

const { data, info } = await sharp(SRC).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
const { width, height } = info;
const at = (x, y) => (y * width + x) * 4;
const bg = [data[0], data[1], data[2]];
const bgSum = bg[0] + bg[1] + bg[2];
const isBgColor = (i) =>
  Math.abs(data[i] - bg[0]) + Math.abs(data[i + 1] - bg[1]) + Math.abs(data[i + 2] - bg[2]) <= TOLERANCE;

// Find horizontal runs of columns that contain non-background pixels.
const occupied = [];
for (let x = 0; x < width; x++) {
  let hit = false;
  for (let y = 0; y < height && !hit; y++) hit = !isBgColor(at(x, y));
  occupied.push(hit);
}
const runs = [];
for (let x = 0, start = -1; x <= width; x++) {
  const on = x < width && occupied[x];
  if (on && start < 0) start = x;
  if (!on && start >= 0) {
    if (x - start > 20) runs.push([start, x - 1]);
    start = -1;
  }
}
if (runs.length !== MODELS.length) throw new Error(`expected ${MODELS.length} cars, found ${runs.length}`);

for (const [index, [x0, x1]] of runs.entries()) {
  let y0 = height, y1 = 0;
  for (let y = 0; y < height; y++)
    for (let x = x0; x <= x1; x++)
      if (!isBgColor(at(x, y))) { y0 = Math.min(y0, y); y1 = Math.max(y1, y); }

  const left = Math.max(0, x0 - PAD), top = Math.max(0, y0 - PAD);
  const w = Math.min(width - 1, x1 + PAD) - left + 1;
  const h = Math.min(height - 1, y1 + PAD) - top + 1;
  const out = Buffer.alloc(w * h * 4);
  for (let y = 0; y < h; y++) data.copy(out, y * w * 4, at(left, top + y), at(left, top + y) + w * 4);

  const distance = (k) => {
    const i = k * 4;
    return Math.abs(out[i] - bg[0]) + Math.abs(out[i + 1] - bg[1]) + Math.abs(out[i + 2] - bg[2]);
  };
  // Never clear pixels brighter than the background: the Flash car's pearl body is ~254.
  const brighter = (k) => out[k * 4] + out[k * 4 + 1] + out[k * 4 + 2] > bgSum + 3;
  const seen = new Uint8Array(w * h);
  const fill = (seeds) => {
    const stack = [...seeds];
    while (stack.length) {
      const y = stack.pop(), x = stack.pop();
      if (x < 0 || y < 0 || x >= w || y >= h) continue;
      const k = y * w + x;
      if (seen[k]) continue;
      seen[k] = 1;
      if (distance(k) > TOLERANCE || brighter(k)) continue;
      out[k * 4 + 3] = 0;
      stack.push(x + 1, y, x - 1, y, x, y + 1, x, y - 1);
    }
  };

  // 1. Background connected to the crop edges.
  const edges = [];
  for (let x = 0; x < w; x++) edges.push(x, 0, x, h - 1);
  for (let y = 0; y < h; y++) edges.push(0, y, w - 1, y);
  fill(edges);

  // 2. Background showing through enclosed gaps (between wings and body):
  //    clusters of near-exact background colour, at least MIN_HOLE pixels big.
  const probe = new Uint8Array(w * h);
  for (let start = 0; start < w * h; start++) {
    if (probe[start] || seen[start] || distance(start) > EXACT) continue;
    const cluster = [];
    const stack = [start];
    probe[start] = 1;
    while (stack.length) {
      const k = stack.pop();
      cluster.push(k);
      const x = k % w, y = (k - x) / w;
      for (const [nx, ny] of [[x + 1, y], [x - 1, y], [x, y + 1], [x, y - 1]]) {
        if (nx < 0 || ny < 0 || nx >= w || ny >= h) continue;
        const n = ny * w + nx;
        if (!probe[n] && !seen[n] && distance(n) <= EXACT) { probe[n] = 1; stack.push(n); }
      }
    }
    if (cluster.length >= MIN_HOLE) fill(cluster.flatMap((k) => [k % w, Math.floor(k / w)]));
  }

  const file = `${OUT}${MODELS[index]}.png`;
  await sharp(out, { raw: { width: w, height: h, channels: 4 } }).png().toFile(file);
  console.log(`${file} ${w}x${h}`);
}
