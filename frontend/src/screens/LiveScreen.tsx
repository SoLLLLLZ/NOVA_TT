import { Header } from "../components/Header";
import { PixelButton } from "../components/PixelButton";
import { Speedometer } from "../components/Speedometer";

type Props = {
  gpu: string | null;
  offline: boolean;
  decode: number | null;
  prefill: number | null;
  active: boolean;
  reverting: boolean;
  revertError: string | null;
  onRevert: () => void;
};

export function LiveScreen({ gpu, offline, decode, prefill, active, reverting, revertError, onRevert }: Props) {
  return (
    <main className="screen screen--live">
      <Header gpu={gpu} connection={offline ? "offline" : "connected"} variant="line" boltColor="#F2B544" />
      <h1 className="live-title">
        <span className="live-title__rule" aria-hidden="true" />
        LIVE SPEED
        <span className="live-title__rule" aria-hidden="true" />
      </h1>
      <Speedometer decode={decode} prefill={prefill} />
      <p className="tuned-pill">
        <span className="status-dot status-dot--connected" aria-hidden="true" />
        TUNED
      </p>
      <p className="live-status" role="status">
        {active ? "Generating…" : "Waiting for terminal command…"}
      </p>
      {revertError && (
        <p className="inline-error" role="alert">
          {revertError}
        </p>
      )}
      <PixelButton variant="outline" onClick={onRevert} disabled={reverting} className="pbtn--small">
        {reverting ? "RESTORING…" : "REVERT TO DEFAULTS"}
      </PixelButton>
    </main>
  );
}
