import { describe, expect, it } from "vitest";
import type { OptimizeDone, RunEvent, StatusResponse } from "../api/types";
import { initialState, reducer, type Action, type State } from "./machine";

const status: StatusResponse = {
  contract_version: "2.1",
  target_id: "wright",
  connection: "connected",
  allocation: null,
  all_gpus: [{ id: "g0", node_id: "n03", local_index: 0, label: "L40", name: "NVIDIA L40", memory_total_mib: 46068, memory_free_mib: 45000, busy: false }],
  models: [
    { id: "qwen3.8-27b", display_name: "ByteShape Qwen 3.8 27B", quant: "IQ3_S", installed: true, loaded: false,
      database_coverage: "verified", requirements: { gpu_type: "L40", gpu_count: 1, same_node: true, context_per_slot: 65536 },
      ready: true, readiness_reasons: [] },
  ],
  current_config: null,
  active_run_id: null,
  is_tuned: false,
};

const run = (states: Action[], from: State = initialState) => states.reduce(reducer, from);

const done = (overrides: Partial<OptimizeDone> = {}): OptimizeDone => ({
  type: "done", run_id: "r1", sequence: 3, at: "", status: "success", applied: true,
  config: { profile_id: "p", model: "qwen3.8-27b", artifact_id: null, quant: null, engine: "llama.cpp", runtime_id: null, settings: {} },
  evidence: { confidence: "verified" }, validation: { status: "passed" }, rollback_id: "rb1", ...overrides,
});

const configEvent: RunEvent = {
  type: "config", run_id: "r1", sequence: 2, at: "", phase: "effective",
  config: done().config, changes: [{ path: "settings.draft_tokens", from: null, to: 5 }], evidence: { confidence: "verified" },
};

const ready = run([{ type: "connected", contractMinor: 1 }, { type: "status_loaded", status }]);

describe("reducer", () => {
  it("goes from status to model selection with the first GPU type", () => {
    expect(ready.phase).toBe("select_model");
    expect(ready.gpuType).toBe("L40");
    expect(ready.model).toBe("qwen3.8-27b");
  });

  it("waits for both the done event and the animation before showing results", () => {
    const optimizing = run([{ type: "optimize_start", idempotencyKey: "k", before: null }, { type: "run_event", event: configEvent }], ready);
    const finished = reducer(optimizing, { type: "run_event", event: done() });
    expect(finished.phase).toBe("optimizing");
    const shown = reducer(finished, { type: "animation_ready" });
    expect(shown.phase).toBe("optimized");
    expect(shown.result).toMatchObject({ rollbackId: "rb1", confidence: "verified", changes: configEvent.changes });
  });

  it("ignores duplicate sequence numbers", () => {
    const once = run([{ type: "optimize_start", idempotencyKey: "k", before: null }, { type: "run_event", event: configEvent }], ready);
    const twice = reducer(once, { type: "run_event", event: { ...configEvent, changes: [] } });
    expect(twice.run?.changes).toEqual(configEvent.changes);
  });

  it("refuses success without passed validation", () => {
    const state = run([
      { type: "optimize_start", idempotencyKey: "k", before: null },
      { type: "animation_ready" },
      { type: "run_event", event: done({ validation: { status: "failed" } }) },
    ], ready);
    expect(state.phase).toBe("error");
    expect(state.error?.code).toBe("validation_failed");
  });

  it("shows stream errors", () => {
    const state = run([
      { type: "optimize_start", idempotencyKey: "k", before: null },
      { type: "run_event", event: { type: "error", run_id: "r1", sequence: 1, at: "", error: { code: "out_of_memory", message: "no" } } },
    ], ready);
    expect(state.phase).toBe("error");
    expect(state.error?.code).toBe("out_of_memory");
  });

  it("reveals live speed only after a terminal request", () => {
    const optimized = run([
      { type: "optimize_start", idempotencyKey: "k", before: null },
      { type: "animation_ready" },
      { type: "run_event", event: done() },
      { type: "live_event", event: { type: "waiting", model: "qwen3.8-27b", service_id: "s" } },
    ], ready);
    expect(optimized.phase).toBe("optimized");
    expect(optimized.live.decode).toBeNull();
    const live = reducer(optimized, { type: "live_event", event: { type: "metrics", request_id: "q", decode_tps: 54, prefill_tps: 2192, output_tokens: 10 } });
    expect(live.phase).toBe("live_speed");
    expect(live.live).toMatchObject({ decode: 54, prefill: 2192, active: true });
  });

  it("returns to model selection with a toast after revert", () => {
    const state = run([
      { type: "optimize_start", idempotencyKey: "k", before: null },
      { type: "animation_ready" },
      { type: "run_event", event: done() },
      { type: "revert_start" },
      { type: "revert_done" },
    ], ready);
    expect(state.phase).toBe("select_model");
    expect(state.toast).toBe("Defaults restored");
    expect(state.result).toBeNull();
  });

  it("stays on the tuned screen when revert fails", () => {
    const state = run([
      { type: "optimize_start", idempotencyKey: "k", before: null },
      { type: "animation_ready" },
      { type: "run_event", event: done() },
      { type: "revert_start" },
      { type: "revert_failed", message: "nope" },
    ], ready);
    expect(state.phase).toBe("optimized");
    expect(state.revertError).toBe("nope");
  });
});
