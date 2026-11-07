import type { ErrorBody } from "../api/types";
import { Wordmark } from "../components/Header";
import { CrossIcon } from "../components/icons";
import { PixelButton } from "../components/PixelButton";

type Props = { error: ErrorBody | null; onRetry: () => void; onBack: (() => void) | null; retryLabel: string };

export function ErrorScreen({ error, onRetry, onBack, retryLabel }: Props) {
  return (
    <main className="screen screen--error">
      <Wordmark />
      <div className="error-card" role="alert">
        <p className="error-card__kicker">
          <CrossIcon size={10} /> PIT LANE BLOCKED
        </p>
        <h1 className="error-card__title">{error?.message ?? "Something went wrong."}</h1>
        {error?.code && <p className="error-card__code">{error.code}</p>}
      </div>
      <PixelButton variant="outline" className="pbtn--wide" onClick={onRetry}>
        {retryLabel}
      </PixelButton>
      {onBack && (
        <button type="button" className="link-button" onClick={onBack}>
          Back to model selection
        </button>
      )}
    </main>
  );
}
