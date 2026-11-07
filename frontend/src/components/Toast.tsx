import { useEffect } from "react";
import { CheckIcon } from "./icons";

export function Toast({ message, onDone }: { message: string | null; onDone: () => void }) {
  useEffect(() => {
    if (!message) return;
    const timer = window.setTimeout(onDone, 2600);
    return () => window.clearTimeout(timer);
  }, [message, onDone]);
  return (
    <div className="toast-region" role="status" aria-live="polite">
      {message && (
        <div className="toast">
          <CheckIcon size={12} />
          <span>{message}</span>
        </div>
      )}
    </div>
  );
}
