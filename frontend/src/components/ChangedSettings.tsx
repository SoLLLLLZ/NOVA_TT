import type { ChangeRow } from "../lib/changes";
import { GearIcon } from "./icons";

export function ChangedSettings({ rows }: { rows: ChangeRow[] }) {
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
        <table className="changes__table">
          <thead className="sr-only">
            <tr>
              <th scope="col">Setting</th>
              <th scope="col">Before</th>
              <th scope="col">After</th>
            </tr>
          </thead>
          <tbody>
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
          </tbody>
        </table>
      )}
    </section>
  );
}
