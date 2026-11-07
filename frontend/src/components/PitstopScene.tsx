import type { ModelLook } from "../models";
import { CarSide } from "./CarSide";

export type PitPhase = "spin" | "drive" | "service";

/** Spin → drive → service sequence. Timing lives in CSS; App advances `phase`. */
export function PitstopScene({ look, phase }: { look: ModelLook; phase: PitPhase }) {
  return (
    <div className={`pit pit--${phase}`} aria-hidden="true">
      <svg className="pit__bay" viewBox="0 0 340 170" shapeRendering="crispEdges">
        <defs>
          <linearGradient id="pit-cone" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#7FE8FF" stopOpacity="0.32" />
            <stop offset="1" stopColor="#7FE8FF" stopOpacity="0" />
          </linearGradient>
          <pattern id="pit-checker" width="6" height="6" patternUnits="userSpaceOnUse">
            <rect width="6" height="6" fill="#1B3556" />
            <rect width="3" height="3" fill="#3C6E9F" />
            <rect x="3" y="3" width="3" height="3" fill="#3C6E9F" />
          </pattern>
        </defs>
        {/* gantry */}
        <rect x="14" y="8" width="312" height="8" fill="#2E5A86" />
        <rect x="14" y="16" width="312" height="2" fill="#16304F" />
        <rect x="18" y="18" width="16" height="140" fill="url(#pit-checker)" />
        <rect x="306" y="18" width="16" height="140" fill="url(#pit-checker)" />
        <rect x="34" y="18" width="4" height="140" fill="#16304F" />
        <rect x="302" y="18" width="4" height="140" fill="#16304F" />
        {/* light bar and cone */}
        <polygon className="pit__cone" points="122,30 218,30 262,156 78,156" fill="url(#pit-cone)" />
        <rect className="pit__light" x="122" y="24" width="96" height="6" fill="#9DF2FF" />
        {/* left arm */}
        <g className="pit__arm pit__arm--l">
          <rect x="64" y="104" width="12" height="52" fill="#2F6496" />
          <rect x="66" y="96" width="8" height="8" fill="#7FB8E6" />
          <g className="pit__arm-upper">
            <rect x="68" y="58" width="6" height="44" fill="#4B8AC4" transform="rotate(38 71 100)" />
            <rect x="96" y="56" width="8" height="8" fill="#7FB8E6" />
            <g className="pit__arm-tool">
              <rect x="98" y="62" width="4" height="22" fill="#4B8AC4" />
              <rect x="94" y="84" width="12" height="6" fill="#C9F0FF" />
            </g>
          </g>
        </g>
        {/* right arm */}
        <g className="pit__arm pit__arm--r">
          <rect x="264" y="104" width="12" height="52" fill="#2F6496" />
          <rect x="266" y="96" width="8" height="8" fill="#7FB8E6" />
          <g className="pit__arm-upper">
            <rect x="266" y="58" width="6" height="44" fill="#4B8AC4" transform="rotate(-38 269 100)" />
            <rect x="236" y="56" width="8" height="8" fill="#7FB8E6" />
            <g className="pit__arm-tool">
              <rect x="238" y="62" width="4" height="22" fill="#4B8AC4" />
              <rect x="232" y="84" width="4" height="8" fill="#C9F0FF" />
              <rect x="244" y="84" width="4" height="8" fill="#C9F0FF" />
            </g>
          </g>
        </g>
        {/* tyre stack */}
        <rect x="40" y="124" width="22" height="10" fill="#1A2130" />
        <rect x="40" y="136" width="22" height="10" fill="#1A2130" />
        <rect x="40" y="148" width="22" height="10" fill="#1A2130" />
        <rect x="44" y="127" width="14" height="4" fill="#2A3346" />
        <rect x="44" y="139" width="14" height="4" fill="#2A3346" />
        <rect x="44" y="151" width="14" height="4" fill="#2A3346" />
        {/* monitor */}
        <rect x="280" y="118" width="22" height="18" fill="#10233B" stroke="#4B8AC4" strokeWidth="2" />
        <rect className="pit__bar1" x="285" y="128" width="3" height="5" fill="#5CE1FF" />
        <rect className="pit__bar2" x="290" y="125" width="3" height="8" fill="#5CE1FF" />
        <rect className="pit__bar3" x="295" y="122" width="3" height="11" fill="#5CE1FF" />
        <rect x="282" y="140" width="18" height="18" fill="#10233B" stroke="#2F6496" strokeWidth="2" />
      </svg>
      <div className="pit__ring" />
      <div className="pit__floor" />
      <div className="pit__lines">
        <span />
        <span />
        <span />
      </div>
      <div className="pit__car">
        <img className="pit__car-front" src={look.car} alt="" draggable={false} />
        <div className="pit__car-side">
          <CarSide palette={look.side} />
        </div>
      </div>
    </div>
  );
}

export function PhaseTiles({ phase, look }: { phase: PitPhase; look: ModelLook }) {
  const order: PitPhase[] = ["spin", "drive", "service"];
  const current = order.indexOf(phase);
  return (
    <ol className="tiles" aria-label="Pitstop phase">
      {order.map((name, index) => (
        <li
          key={name}
          className={`tile${index === current ? " is-current" : ""}${index < current ? " is-done" : ""}`}
          aria-current={index === current ? "step" : undefined}
        >
          <div className="tile__box">
            <span className="tile__num">{index + 1}</span>
            <TileIcon name={name} look={look} />
          </div>
          <span className="tile__label">{name.toUpperCase()}</span>
        </li>
      ))}
    </ol>
  );
}

function TileIcon({ name, look }: { name: PitPhase; look: ModelLook }) {
  if (name === "spin") {
    return (
      <svg className="tile__icon tile__icon--spin" viewBox="0 0 24 24" shapeRendering="crispEdges" aria-hidden="true">
        {Array.from({ length: 12 }, (_, i) => {
          const a = (i / 12) * Math.PI * 2;
          return <rect key={i} x={11 + Math.cos(a) * 8} y={11 + Math.sin(a) * 8} width="2" height="2" fill="currentColor" opacity={0.35 + (i / 12) * 0.65} />;
        })}
      </svg>
    );
  }
  if (name === "drive") {
    return (
      <span className="tile__icon tile__icon--drive">
        <span className="tile__speed" />
        <CarSide palette={look.side} scale={1} />
      </span>
    );
  }
  return (
    <span className="tile__icon tile__icon--service">
      <svg viewBox="0 0 30 20" shapeRendering="crispEdges" aria-hidden="true">
        <rect x="1" y="1" width="28" height="3" fill="currentColor" />
        <rect x="2" y="4" width="3" height="15" fill="currentColor" />
        <rect x="25" y="4" width="3" height="15" fill="currentColor" />
      </svg>
      <CarSide palette={look.side} scale={0.6} />
    </span>
  );
}
