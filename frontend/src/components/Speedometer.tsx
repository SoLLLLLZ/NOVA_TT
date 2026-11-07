import { useEffect, useRef, useState } from "react";
import { GAUGE_POSITIONS, GAUGE_TICKS, fractionToRotation, pointOnArc, valueToFraction } from "../lib/gauge";
import { formatRate } from "../lib/format";
import { usePrefersReducedMotion } from "../lib/motion";

const CX = 150;
const CY = 140;
const R = 112;
const SEGMENTS = 72;
/** Arc turns amber from the fourth tick (30 tok/s) upward, as in the mockup. */
const WARM_FROM = GAUGE_POSITIONS[3];

/** Tweens a number toward `target`: count-up on first value, short glide after. */
function useTweened(target: number | null, reduced: boolean): number | null {
  const [shown, setShown] = useState<number | null>(target);
  const shownRef = useRef<number | null>(null);
  useEffect(() => {
    if (target === null) {
      shownRef.current = null;
      setShown(null);
      return;
    }
    if (reduced) {
      shownRef.current = target;
      setShown(target);
      return;
    }
    const from = shownRef.current ?? 0;
    const duration = shownRef.current === null ? 600 : 260;
    const start = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      const value = from + (target - from) * eased;
      shownRef.current = value;
      setShown(value);
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, reduced]);
  return shown;
}

export function Speedometer({ decode, prefill }: { decode: number | null; prefill: number | null }) {
  const reduced = usePrefersReducedMotion();
  const shown = useTweened(decode, reduced);
  const fraction = decode === null ? 0 : valueToFraction(decode);
  const [pulse, setPulse] = useState(0);
  const firstValue = useRef(true);

  useEffect(() => {
    if (decode !== null && firstValue.current) {
      firstValue.current = false;
      setPulse((n) => n + 1);
    }
  }, [decode]);

  return (
    <div className="gauge">
      <svg className="gauge__svg" viewBox="0 0 300 230" shapeRendering="crispEdges" aria-hidden="true">
        {Array.from({ length: SEGMENTS }, (_, i) => {
          const f = i / (SEGMENTS - 1);
          const p = pointOnArc(CX, CY, R, f);
          const warm = f >= WARM_FROM;
          const lit = decode !== null && f <= fraction;
          return (
            <rect
              key={i}
              x={p.x - 3}
              y={p.y - 5}
              width={6}
              height={10}
              transform={`rotate(${fractionToRotation(f)} ${p.x} ${p.y})`}
              className={`gauge__seg${warm ? " is-warm" : ""}${lit ? " is-lit" : ""}`}
            />
          );
        })}
        {GAUGE_TICKS.map((tick, i) => {
          const f = GAUGE_POSITIONS[i];
          const inner = pointOnArc(CX, CY, R - 16, f);
          const label = pointOnArc(CX, CY, R - 32, f);
          return (
            <g key={tick}>
              <rect
                x={inner.x - 1}
                y={inner.y - 4}
                width={2}
                height={8}
                transform={`rotate(${fractionToRotation(f)} ${inner.x} ${inner.y})`}
                className="gauge__tick"
              />
              <text x={label.x} y={label.y + 4} textAnchor="middle" className={`gauge__label${f >= WARM_FROM ? " is-warm" : ""}`}>
                {tick}
              </text>
            </g>
          );
        })}
        <g
          className={`gauge__needle${reduced ? " no-motion" : ""}`}
          style={{ transform: `rotate(${fractionToRotation(fraction)}deg)`, transformOrigin: `${CX}px ${CY}px` }}
        >
          <rect x={CX - 2} y={CY - R + 30} width={4} height={R - 38} />
        </g>
        <circle cx={CX} cy={CY} r={9} className="gauge__hub" />
      </svg>
      <div className="gauge__readout" key={pulse}>
        <span className="gauge__value">{shown === null ? "—" : Math.round(shown).toLocaleString("en-US")}</span>
        <span className="gauge__unit">tok/s</span>
      </div>
      <p className="gauge__caption">Decode speed</p>
      <p className="gauge__prefill">
        Prompt speed <strong>{formatRate(prefill)}</strong> tok/s
      </p>
      <p className="sr-only" aria-live="polite">
        {decode === null ? "Waiting for speed" : `Decode speed ${Math.round(decode)} tokens per second`}
      </p>
    </div>
  );
}
