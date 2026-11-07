import type { ChecklistItem } from "../state/steps";
import { CheckIcon, CrossIcon } from "./icons";

export function Checklist({ items }: { items: ChecklistItem[] }) {
  return (
    <ol className="checklist" aria-live="polite">
      {items.map((item) => (
        <li key={item.id} className={`checklist__item is-${item.status}`}>
          <span className="checklist__mark" aria-hidden="true">
            {item.status === "done" && <CheckIcon size={11} />}
            {item.status === "failed" && <CrossIcon size={9} />}
          </span>
          <span className="checklist__label">{item.label}</span>
          <span className="sr-only">
            {item.status === "done" ? "done" : item.status === "running" ? "in progress" : item.status === "failed" ? "failed" : "pending"}
          </span>
        </li>
      ))}
    </ol>
  );
}
