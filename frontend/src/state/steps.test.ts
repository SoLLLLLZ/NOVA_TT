import { describe, expect, it } from "vitest";
import type { StepEvent, StepName, StepStatus } from "../api/types";
import { deriveChecklist } from "./steps";

let seq = 0;
const step = (name: StepName, status: StepStatus): StepEvent => ({
  type: "step", run_id: "r", sequence: ++seq, at: "", name, status, progress: null, detail: null,
});
const statuses = (events: StepEvent[], options = {}) => deriveChecklist(events, options).map((i) => i.status);

describe("deriveChecklist", () => {
  it("starts all pending", () => {
    expect(statuses([])).toEqual(["pending", "pending", "pending", "pending", "pending"]);
  });

  it("tracks the running group and completes earlier ones", () => {
    const events = [step("detect_gpu", "running"), step("detect_gpu", "done"), step("allocate", "skipped"),
      step("check_database", "done"), step("ask_ai", "running")];
    expect(statuses(events)).toEqual(["done", "done", "running", "pending", "pending"]);
  });

  it("does not leave a failed verify marked failed once repair moves on", () => {
    const events = [step("ask_ai", "done"), step("verify", "failed"), step("repair", "done"),
      step("load_model", "running")];
    expect(statuses(events)[3]).toBe("running");
  });

  it("marks the running group failed on terminal error", () => {
    expect(statuses([step("ask_ai", "running")], { failed: true })[2]).toBe("failed");
  });

  it("works from a snapshot step only", () => {
    expect(statuses([], { currentStep: "verify" })).toEqual(["done", "done", "done", "running", "pending"]);
  });
});
