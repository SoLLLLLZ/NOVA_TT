import type { Confidence } from "../api/types";
import { CarStage } from "../components/CarStage";
import { ChangedSettings } from "../components/ChangedSettings";
import { CheckIcon, RefreshIcon } from "../components/icons";
import { PixelButton } from "../components/PixelButton";
import type { ChangeRow } from "../lib/changes";
import type { ModelLook } from "../models";

const BADGES: Record<Confidence, string> = {
  verified: "Verified on this exact GPU.",
  inferred: "Based on similar runs.",
  experimental: "Experimental setup.",
  none: "Applied without database evidence.",
};

type Props = {
  look: ModelLook;
  modelKey: string;
  confidence: Confidence;
  rows: ChangeRow[];
  waitingText: string;
  reverting: boolean;
  revertError: string | null;
  onRevert: () => void;
};

export function OptimizedScreen({ look, modelKey, confidence, rows, waitingText, reverting, revertError, onRevert }: Props) {
  return (
    <main className="screen screen--optimized">
      <h1 className="sr-only">Setup optimized</h1>
      <CarStage look={look} variant="hero" modelKey={modelKey} />
      <div className="optimized-head">
        <p className="kicker">SETUP OPTIMIZED</p>
        <p className={`badge badge--${confidence}`}>
          <span className="badge__ring" aria-hidden="true">
            <CheckIcon size={11} />
          </span>
          {BADGES[confidence]}
        </p>
      </div>
      <ChangedSettings rows={rows} />
      {revertError && (
        <p className="inline-error" role="alert">
          {revertError}
        </p>
      )}
      <PixelButton variant="outline" icon={<RefreshIcon size={16} />} onClick={onRevert} disabled={reverting} className="pbtn--wide">
        {reverting ? "RESTORING…" : "REVERT TO DEFAULTS"}
      </PixelButton>
      <p className="waiting" role="status">
        <span className="waiting__dot" aria-hidden="true" />
        {waitingText}
      </p>
    </main>
  );
}
