import { useState } from "react";
import type { ChangeRow } from "../lib/changes";
import { GearIcon } from "./icons";

function Rows({ rows }: { rows: ChangeRow[] }) {
  return (
    <>
      {rows.map((row) => (
        <tr key={row.key} title={row.reason || undefined}>
          <th scope="row">{row.label}</th>
          <td className="changes__from">{row.from}</td>
          <td className="changes__arrow" aria-hidden="true">
            →
          </td>
          <td className="changes__to">{row.to}</td>
        </tr>
      ))}
    </>
  );
}

export function ChangedSettings({ rows }: { rows: ChangeRow[] }) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const key = rows.filter((row) => !row.advanced);
  const advanced = rows.filter((row) => row.advanced);
  return (
    <section className="changes" aria-labelledby="changes-title">
      <h2 className="changes__title" id="changes-title">
        <GearIcon size={16} />
        <span>Changed settings</span>
        <span className="changes__rule" aria-hidden="true" />
      </h2>
      {rows.length === 0 ? (
        <p className="changes__empty">The backend kept your current settings.</p>
      ) : (
        <div className="changes__scroll">
          <table className="changes__table">
            <thead className="sr-only">
              <tr>
                <th scope="col">Setting</th>
                <th scope="col">Before</th>
                <th scope="col">After</th>
              </tr>
            </thead>
            <tbody>
              <Rows rows={key} />
              {showAdvanced && <Rows rows={advanced} />}
            </tbody>
          </table>
        </div>
      )}
      {advanced.length > 0 && (
        <button type="button" className="changes__more" aria-expanded={showAdvanced} onClick={() => setShowAdvanced((v) => !v)}>
          {showAdvanced ? "Hide advanced settings" : `+ ${advanced.length} advanced setting${advanced.length === 1 ? "" : "s"}`}
        </button>
      )}
    </section>
  );
}
