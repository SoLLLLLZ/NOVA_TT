import { desktop } from "../lib/desktop";

/** Drag handle and hide button for the frameless desktop widget. */
export function DesktopBar() {
  if (!desktop) return null;
  return (
    <div className="desk-bar">
      <span className="desk-bar__grip" aria-hidden="true" />
      <span className="desk-bar__hint">⌥ Space</span>
      <button type="button" className="desk-bar__hide" aria-label="Hide widget (Option+Space)" title="Hide (⌥Space)" onClick={desktop.hide}>
        <svg width="10" height="10" viewBox="0 0 5 5" shapeRendering="crispEdges" aria-hidden="true">
          <path d="M0 0h1v1H0zM4 0h1v1H4zM1 1h1v1H1zM3 1h1v1H3zM2 2h1v1H2zM1 3h1v1H1zM3 3h1v1H3zM0 4h1v1H0zM4 4h1v1H4z" fill="currentColor" />
        </svg>
      </button>
    </div>
  );
}
