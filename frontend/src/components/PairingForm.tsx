import { useState, type FormEvent } from "react";
import { PixelButton } from "./PixelButton";

export function PairingForm({ error, onSubmit }: { error: string | null; onSubmit: (code: string) => void }) {
  const [code, setCode] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (code.trim()) onSubmit(code.trim());
  };
  return (
    <form className="pairing" onSubmit={submit}>
      <h1 className="title">Pair with backend.</h1>
      <p className="muted">Paste the pairing code the backend printed when it started.</p>
      <label className="pairing__label" htmlFor="pairing-code">
        Pairing code
      </label>
      <input
        id="pairing-code"
        className="pairing__input"
        value={code}
        onChange={(event) => setCode(event.target.value)}
        placeholder="ABC-123"
        autoComplete="off"
        spellCheck={false}
        autoFocus
        aria-invalid={!!error}
        aria-describedby={error ? "pairing-error" : undefined}
      />
      {error && (
        <p className="pairing__error" id="pairing-error" role="alert">
          {error}
        </p>
      )}
      <PixelButton variant="outline" type="submit" disabled={!code.trim()}>
        Connect
      </PixelButton>
    </form>
  );
}
