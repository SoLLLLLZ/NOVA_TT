// Small pixel icons drawn on a grid so they stay crisp at any size.

type IconProps = { size?: number; className?: string };

function Pixels({ rows, size = 16, className, fill = "currentColor" }: IconProps & { rows: string[]; fill?: string }) {
  const height = rows.length;
  const width = rows[0].length;
  return (
    <svg
      className={className}
      width={size}
      height={(size * height) / width}
      viewBox={`0 0 ${width} ${height}`}
      shapeRendering="crispEdges"
      aria-hidden="true"
    >
      {rows.flatMap((row, y) =>
        [...row].map((cell, x) => (cell === "#" ? <rect key={`${x}-${y}`} x={x} y={y} width={1} height={1} fill={fill} /> : null)),
      )}
    </svg>
  );
}

export function BoltIcon(props: IconProps) {
  return (
    <Pixels
      {...props}
      rows={[
        "......####",
        ".....####.",
        "....####..",
        "...####...",
        "..####....",
        ".########.",
        "########..",
        "....####..",
        "...####...",
        "..####....",
        ".###......",
        "##........",
      ]}
    />
  );
}

export function ChipIcon(props: IconProps) {
  return (
    <Pixels
      {...props}
      rows={[
        "..#.#.#.#.#..",
        "..#.#.#.#.#..",
        "#############",
        "..#.......#..",
        "###.#####.###",
        "..#.#...#.#..",
        "###.#...#.###",
        "..#.#####.#..",
        "#############",
        "..#.#.#.#.#..",
        "..#.#.#.#.#..",
      ]}
    />
  );
}

export function FlagIcon(props: IconProps) {
  return (
    <Pixels
      {...props}
      rows={[
        "#.............",
        "##..##..##....",
        "#.##..##..##..",
        "##..##..##....",
        "#.##..##..##..",
        "##..##..##....",
        "#.##..##..##..",
        "#.............",
        "#.............",
        "#.............",
      ]}
    />
  );
}

export function GearIcon(props: IconProps) {
  return (
    <Pixels
      {...props}
      rows={[
        ".....##.....",
        "..#.####.#..",
        ".##########.",
        "..###..###..",
        "####....####",
        "####....####",
        "..###..###..",
        ".##########.",
        "..#.####.#..",
        ".....##.....",
      ]}
    />
  );
}

export function RefreshIcon(props: IconProps) {
  return (
    <Pixels
      {...props}
      rows={[
        "....#####...",
        "..##.....#.#",
        ".#........##",
        "#.......####",
        "#...........",
        "...........#",
        "####.......#",
        "##........#.",
        "#.#.....##..",
        "...#####....",
      ]}
    />
  );
}

export function CheckIcon(props: IconProps) {
  return (
    <Pixels
      {...props}
      rows={[
        ".........##",
        "........##.",
        ".......##..",
        "##....##...",
        ".##..##....",
        "..####.....",
        "...##......",
      ]}
    />
  );
}

export function CrossIcon(props: IconProps) {
  return (
    <Pixels
      {...props}
      rows={["##...##", ".##.##.", "..###..", ".##.##.", "##...##"]}
    />
  );
}

export function CaretIcon(props: IconProps) {
  return <Pixels {...props} rows={["#########", ".#######.", "..#####..", "...###...", "....#...."]} />;
}
