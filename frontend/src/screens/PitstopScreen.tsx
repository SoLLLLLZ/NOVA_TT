import { useEffect, useState, type CSSProperties } from "react";
import { Checklist } from "../components/Checklist";
import { PitstopScene, type PitPhase } from "../components/PitstopScene";
import { usePrefersReducedMotion } from "../lib/motion";
import type { ModelLook } from "../models";
import type { ChecklistItem } from "../state/steps";

// Keep in sync with the pit keyframes in app.css.
const SPIN_MS = 700;
const DRIVE_MS = 1100;

type Props = { look: ModelLook; items: ChecklistItem[]; detail: string | null; onArrived: () => void };

export function PitstopScreen({ look, items, detail, onArrived }: Props) {
  const reduced = usePrefersReducedMotion();
  const [phase, setPhase] = useState<PitPhase>(reduced ? "service" : "spin");

  useEffect(() => {
    if (reduced) {
      setPhase("service");
      onArrived();
      return;
    }
    const toDrive = window.setTimeout(() => setPhase("drive"), SPIN_MS);
    const toService = window.setTimeout(() => {
      setPhase("service");
      onArrived();
    }, SPIN_MS + DRIVE_MS);
    return () => {
      window.clearTimeout(toDrive);
      window.clearTimeout(toService);
    };
    // Runs once per pitstop; onArrived is stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reduced]);

  return (
    <main className={`screen screen--pitstop${reduced ? " reduced" : ""}`} style={{ "--accent": look.accent } as CSSProperties}>
      <PitstopScene look={look} phase={phase} />
      <h1 className="pit-title">
        <span className="pit-title__accent">PITSTOP</span> IN PROGRESS.
      </h1>
      <Checklist items={items} />
      <p className="pit-footer">
        FINDING YOUR FASTEST SETUP<span className="dots" aria-hidden="true" />
      </p>
      {detail && <p className="pit-detail">{detail}</p>}
    </main>
  );
}
