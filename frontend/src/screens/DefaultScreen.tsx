import type { CSSProperties } from "react";
import type { Config } from "../api/types";
import { CarStage } from "../components/CarStage";
import { ChangedSettings } from "../components/ChangedSettings";
import { FlagIcon } from "../components/icons";
import { PixelButton } from "../components/PixelButton";
import { configRows } from "../lib/changes";
import type { ModelLook } from "../models";

type Props = {
  look: ModelLook;
  modelKey: string;
  /** null while the default service is still starting. */
  config: Config | null;
  detail: string | null;
  waitingText: string;
  stopping: boolean;
  stopError: string | null;
  onOptimize: () => void;
  onStop: () => void;
};

/** The untouched default is starting or running, ready to be measured from a terminal. */
export function DefaultScreen({ look, modelKey, config, detail, waitingText, stopping, stopError, onOptimize, onStop }: Props) {
  const starting = config === null;
  return (
    <main className="screen screen--optimized screen--default" style={{ "--accent": look.accent } as CSSProperties}>
      <h1 className="sr-only">{starting ? "Starting default settings" : "Default settings running"}</h1>
      <CarStage look={look} variant="hero" modelKey={modelKey} />
      <div className="optimized-head">
        <p className="kicker kicker--amber">{starting ? "STARTING DEFAULTS" : "DEFAULT SETUP READY"}</p>
        <p className="badge badge--none">Untouched Ollama defaults.</p>
      </div>
      {starting ? (
        <p className="pit-footer" role="status">
          WARMING UP<span className="dots" aria-hidden="true" />
          {detail && <span className="default-detail">{detail}</span>}
        </p>
      ) : (
        <ChangedSettings rows={configRows(config)} valuesOnly title="Default settings" />
      )}
      {stopError && (
        <p className="inline-error" role="alert">
          {stopError}
        </p>
      )}
      {!starting && (
        <>
          <PixelButton variant="primary" icon={<FlagIcon size={22} />} accent={{ fill: look.accent, ink: look.accentInk }} disabled={stopping} onClick={onOptimize}>
            PITSTOP · OPTIMIZE
          </PixelButton>
          <button type="button" className="secondary-run" disabled={stopping} onClick={onStop}>
            {stopping ? "Stopping…" : "Stop default run"}
          </button>
          <p className="waiting" role="status">
            <span className="waiting__dot" aria-hidden="true" />
            {waitingText}
          </p>
        </>
      )}
    </main>
  );
}
