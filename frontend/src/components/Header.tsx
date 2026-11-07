import { APP_NAME } from "../config";
import { BoltIcon, ChipIcon } from "./icons";

type Props = {
  gpu: string | null;
  connection: "detecting" | "connected" | "offline";
  /** The live screen shows one quiet status line instead of the GPU card. */
  variant?: "card" | "line";
  boltColor?: string;
};

export function Wordmark({ boltColor }: { boltColor?: string }) {
  return (
    <div className="wordmark">
      <span className="wordmark__bolt" style={boltColor ? { color: boltColor } : undefined}>
        <BoltIcon size={18} />
      </span>
      <span className="wordmark__text">{APP_NAME}</span>
    </div>
  );
}

export function Header({ gpu, connection, variant = "card", boltColor }: Props) {
  const statusText =
    connection === "detecting" ? "Detecting…" : connection === "offline" ? "Disconnected" : variant === "line" ? "Backend connected" : "Connected";
  return (
    <header className={`header header--${variant}`}>
      <Wordmark boltColor={boltColor} />
      {variant === "card" ? (
        <div className="gpu-pill" role="status" aria-live="polite">
          <ChipIcon size={18} className="gpu-pill__chip" />
          <div className="gpu-pill__gpu">
            <span className="micro">{connection === "detecting" ? "GPU" : "GPU detected"}</span>
            <span className="gpu-pill__name">{connection === "detecting" ? "…" : gpu ?? "—"}</span>
          </div>
          <span className="gpu-pill__divider" aria-hidden="true" />
          <span className={`status-dot status-dot--${connection}`} aria-hidden="true" />
          <span className="gpu-pill__status">{statusText}</span>
        </div>
      ) : (
        <div className="header__line" role="status">
          <span className={`status-dot status-dot--${connection}`} aria-hidden="true" />
          <span>
            {statusText}
            {gpu ? ` · ${gpu}` : ""}
          </span>
        </div>
      )}
    </header>
  );
}
