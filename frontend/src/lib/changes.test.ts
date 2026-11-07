import { describe, expect, it } from "vitest";
import { changeRows, configRows, diffConfigs, importantConfigRows } from "./changes";
import rehearsal from "../../../docs/demo/widget-integration-validation-20261107.json";

describe("importantConfigRows", () => {
  it("shows 20 active settings while highlighting only actual changes", () => {
    const rows = importantConfigRows(rehearsal.optimization.config, [
      { path: "settings.draft_tokens", from: 3, to: 5 },
      { path: "settings.temperature", from: 1, to: 0.75 },
    ]);
    expect(rows).toHaveLength(20);
    expect(rows.filter((item) => item.changed).map((item) => item.label)).toEqual(["Draft tokens", "Temperature"]);
    expect(rows.find((item) => item.key === "quant")?.to).toBe("IQ3_S hybrid 3.23bpw");
    expect(rows.find((item) => item.key === "settings.context_per_slot")?.to).toBe("64K");
    expect(rows.find((item) => item.key === "settings.threads_prefill")?.to).toBe("6");
  });

  it("uses the applied value over a stale proposed value and preserves unknowns", () => {
    const config = { ...rehearsal.optimization.config, settings: { draft_tokens: 3 } };
    const rows = importantConfigRows(config, [{ path: "settings.draft_tokens", from: 3, to: 5 }]);
    expect(rows.find((item) => item.key === "settings.draft_tokens")).toMatchObject({ to: "3", changed: false });
    expect(rows.find((item) => item.key === "settings.temperature")).toMatchObject({ to: "—", changed: false });
  });
});

describe("changeRows", () => {
  const changes = [
    { path: "settings.temperature", from: 1, to: 0.75, reason: "sampling" },
    { path: "engine", from: "ollama", to: "llama.cpp", reason: "speculation" },
    { path: "settings.threads_decode", from: 128, to: 2, reason: "cpu" },
    { path: "settings.threads_prefill", from: 128, to: 6, reason: "cpu" },
    { path: "settings.context_tokens", from: 32768, to: 65536 },
    { path: "settings.kv_type_k", from: "f16", to: "q8_0" },
    { path: "settings.kv_type_v", from: "f16", to: "q8_0" },
    { path: "settings.speculative_mode", from: "none", to: "draft-mtp" },
    { path: "settings.draft_tokens", from: null, to: 5 },
    { path: "settings.some_new_knob", from: false, to: true },
  ];

  it("merges paired settings and orders rows", () => {
    const rows = changeRows(changes);
    expect(rows.map((r) => r.label)).toEqual([
      "Engine", "Threads", "Context length", "KV cache", "Speculative decoding", "Draft tokens", "Temperature",
      "Some new knob",
    ]);
    const threads = rows.find((r) => r.label === "Threads")!;
    expect([threads.from, threads.to, threads.reason]).toEqual(["128", "2 / 6", "cpu"]);
    expect(rows.find((r) => r.label === "Context length")).toMatchObject({ from: "32K", to: "64K" });
    expect(rows.find((r) => r.label === "KV cache")).toMatchObject({ from: "f16", to: "q8_0" });
    expect(rows.find((r) => r.label === "Speculative decoding")).toMatchObject({ from: "Off", to: "MTP" });
    expect(rows.find((r) => r.label === "Draft tokens")).toMatchObject({ from: "—", to: "5" });
    expect(rows.find((r) => r.label === "Engine")).toMatchObject({ from: "Ollama", to: "llama.cpp" });
  });

  it("marks backend internals as advanced", () => {
    const rows = changeRows([
      { path: "settings.chat_template_id", from: null, to: "byteshape-embedded" },
      { path: "settings.draft_tokens", from: null, to: 5 },
    ]);
    expect(rows.map((r) => [r.label, r.advanced])).toEqual([["Draft tokens", false], ["Chat template id", true]]);
  });

  it("keeps unmerged K/V when they differ in presence", () => {
    const rows = changeRows([{ path: "settings.kv_type_k", from: "f16", to: "q8_0" }]);
    expect(rows[0].label).toBe("KV cache (K)");
  });

  it("prefers per-slot context over total context", () => {
    const rows = changeRows([
      { path: "settings.context_tokens", from: 32768, to: 131072 },
      { path: "settings.context_per_slot", from: 32768, to: 65536 },
    ]);
    expect(rows).toHaveLength(1);
    expect(rows[0].to).toBe("64K");
  });
});

describe("diffConfigs", () => {
  it("reports known settings that changed", () => {
    const base = { profile_id: null, model: "m", artifact_id: null, quant: "q", runtime_id: null };
    const diff = diffConfigs(
      { ...base, engine: "ollama", settings: { batch_size: 1024, top_k: 20 } },
      { ...base, engine: "llama.cpp", settings: { batch_size: 2048, top_k: 20, private_thing: 1 } },
    );
    expect(diff.map((c) => c.path)).toEqual(["engine", "settings.batch_size"]);
  });
});

describe("configRows", () => {
  it("summarises performance settings only", () => {
    const rows = configRows({
      profile_id: null, model: "m", artifact_id: null, quant: "q", runtime_id: null, engine: "ollama",
      settings: { threads_decode: 128, threads_prefill: 128, context_tokens: 32768, batch_size: 1024,
        kv_type_k: "f16", kv_type_v: "f16", flash_attention: "on", speculative_mode: "none", temperature: 1, top_k: 20 },
    });
    expect(rows.map((r) => [r.label, r.to])).toEqual([
      ["Engine", "Ollama"], ["Threads", "128"], ["Context length", "32K"], ["Batch size", "1024"],
      ["KV cache", "f16"], ["Flash attention", "On"], ["Speculative decoding", "Off"],
    ]);
  });
});
