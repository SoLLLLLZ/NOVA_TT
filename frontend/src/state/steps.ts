import type { StepEvent, StepName } from "../api/types";

export type ChecklistStatus = "pending" | "running" | "done" | "failed";

export type ChecklistItem = { id: string; label: string; status: ChecklistStatus };

// The five checklist rows in the UX brief, mapped onto contract step names.
export const CHECKLIST: { id: string; label: string; steps: StepName[] }[] = [
  { id: "gpu", label: "Detecting GPU", steps: ["detect_gpu", "allocate"] },
  { id: "database", label: "Checking database", steps: ["check_database"] },
  { id: "ai", label: "Asking AI", steps: ["ask_ai"] },
  { id: "test", label: "Testing configs", steps: ["load_model", "test_configs", "verify", "repair"] },
  { id: "apply", label: "Applying", steps: ["apply", "rollback"] },
];

const groupOf = (name: StepName) => CHECKLIST.findIndex((group) => group.steps.includes(name));

/**
 * Derives row states from the step events seen so far. When only a run
 * snapshot is available (after reopening the widget) pass its current_step.
 */
export function deriveChecklist(
  events: StepEvent[],
  options: { currentStep?: StepName | null; failed?: boolean; finished?: boolean } = {},
): ChecklistItem[] {
  const last = new Map<number, StepEvent>();
  for (const event of events) {
    const group = groupOf(event.name);
    if (group !== -1) last.set(group, event);
  }
  const snapshotGroup = options.currentStep ? groupOf(options.currentStep) : -1;
  const furthest = Math.max(snapshotGroup, ...[...last.keys()], -1);

  return CHECKLIST.map((group, index) => {
    let status: ChecklistStatus = "pending";
    const event = last.get(index);
    if (options.finished) status = "done";
    else if (event) {
      status = event.status === "running" ? "running" : event.status === "failed" ? "failed" : "done";
    } else if (index < furthest) status = "done";
    else if (index === snapshotGroup) status = "running";

    // A later group has started, so this one is behind us whatever its last event said.
    if (status === "running" && index < furthest) status = "done";
    if (status === "failed" && index < furthest) status = "done";
    if (options.failed && status === "running") status = "failed";
    return { id: group.id, label: group.label, status };
  });
}
