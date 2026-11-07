// Renders the pixel lightning-bolt mark into the extension's toolbar icons.
import sharp from "sharp";

const OUT = new URL("../public/icons/", import.meta.url).pathname;
// 16x16 pixel grid; each string is one row, "#" = bolt pixel.
const BOLT = [
  "................",
  ".........####...",
  "........####....",
  ".......####.....",
  "......####......",
  ".....####.......",
  "....#########...",
  "...#########....",
  ".......####.....",
  "......####......",
  ".....####.......",
  "....####........",
  "...###..........",
  "..##............",
  "................",
  "................",
];

const rects = BOLT.flatMap((row, y) =>
  [...row].map((c, x) => (c === "#" ? `<rect x="${x}" y="${y}" width="1" height="1"/>` : "")),
).join("");
const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" shape-rendering="crispEdges">
<rect width="16" height="16" rx="2" fill="#07111F"/><g fill="#C6F432">${rects}</g></svg>`;

for (const size of [16, 32, 48, 128]) {
  await sharp(Buffer.from(svg), { density: 72 * (size / 16) })
    .resize(size, size, { kernel: "nearest" })
    .png()
    .toFile(`${OUT}icon-${size}.png`);
}
console.log("icons written");
