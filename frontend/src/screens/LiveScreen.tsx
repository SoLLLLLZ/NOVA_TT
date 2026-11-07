import { Header } from "../components/Header";
import { FlagIcon } from "../components/icons";
import { PixelButton } from "../components/PixelButton";
import { Speedometer } from "../components/Speedometer";
import { formatRate } from "../lib/format";
import type { ModelLook } from "../models";
import type { Baseline, RunKind } from "../state/machine";

type Props = {
  gpu: string | null;
  offline: boolean;
  decode: number | null;
  prefill: number | null;
  active: boolean;
  /** Which retained service is being measured. */
  kind: RunKind;
  look: ModelLook;
  /** Default-run speed for this model, shown next to tuned speed for comparison. */
  baseline: Baseline | null;
  reverting: boolean;
  revertError: string | null;
  onRevert: () => void;
  onOptimize: () => void;
};

export function LiveScreen({ gpu, offline, decode, prefill, active, kind, look, baseline, reverting, revertError, onRevert, onOptimize }: Props) {
  const isDefault = kind === "default";
  const speedup = baseline && decode ? decode / baseline.decode : null;
  return (
    <main className={`screen screen--live${isDefault ? " screen--live-default" : ""}`}>
      <Header gpu={gpu} connection={offline ? "offline" : "connected"} variant="line" boltColor="#F2B544" />
      <h1 className="live-title">
        <span className="live-title__rule" aria-hidden="true" />
        LIVE SPEED
        <span className="live-title__rule" aria-hidden="true" />
      </h1>
      <Speedometer decode={decode} prefill={prefill} />
      {baseline && (
        <p className="compare" aria-live="polite">
          <span className="compare__label">Default run</span>
          <strong className="compare__value">{formatRate(baseline.decode)}</strong> tok/s
          {speedup !== null && speedup > 0 && (
            <span className="compare__speedup">{speedup >= 10 ? Math.round(speedup) : speedup.toFixed(1)}× faster</span>
          )}
        </p>
      )}
      <p className={`tuned-pill${isDefault ? " tuned-pill--default" : ""}`}>
        <span className={`status-dot ${isDefault ? "status-dot--offline" : "status-dot--connected"}`} aria-hidden="true" />
        {isDefault ? "DEFAULT" : "TUNED"}
      </p>
      <p className="live-status" role="status">
        {active ? "Generating…" : "Waiting for terminal command…"}
      </p>
      {revertError && (
        <p className="inline-error" role="alert">
          {revertError}
        </p>
      )}
      {isDefault ? (
        <>
          <PixelButton variant="primary" icon={<FlagIcon size={22} />} accent={{ fill: look.accent, ink: look.accentInk }} disabled={reverting} onClick={onOptimize}>
            PITSTOP · OPTIMIZE
          </PixelButton>
          <button type="button" className="secondary-run" disabled={reverting} onClick={onRevert}>
            {reverting ? "Stopping…" : "Stop default run"}
          </button>
        </>
      ) : (
        <PixelButton variant="outline" onClick={onRevert} disabled={reverting} className="pbtn--small">
          {reverting ? "RESTORING…" : "REVERT TO DEFAULTS"}
        </PixelButton>
      )}
    </main>
  );
}
