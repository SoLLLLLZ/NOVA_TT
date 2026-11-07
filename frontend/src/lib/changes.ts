import type { Change, Config } from "../api/types";
import { formatTokens } from "./format";

/** `advanced` rows are backend internals (templates, tensor placement…) shown only on request. */
export type ChangeRow = { key: string; label: string; from: string; to: string; reason: string; advanced: boolean };

type Field = { label: string; format?: (value: unknown) => string };

const onOff = (value: unknown) =>
  value === "on" || value === true ? "On" : value === "off" || value === false ? "Off" : value === "auto" ? "Auto" : show(value);

const ENGINE_NAMES: Record<string, string> = { ollama: "Ollama", "llama.cpp": "llama.cpp" };
const SPECULATION_NAMES: Record<string, string> = {
  none: "Off",
  "draft-mtp": "MTP",
  "draft-dflash": "DFlash",
  "ngram-simple": "N-gram",
};

const tokens = (value: unknown) => (typeof value === "number" ? formatTokens(value) : show(value));

// Display order follows this table; unknown paths come after, humanized.
const FIELDS: Record<string, Field> = {
  engine: { label: "Engine", format: (v) => ENGINE_NAMES[String(v)] ?? show(v) },
  quant: { label: "Quantization" },
  "settings.threads": { label: "Threads" },
  "settings.threads_decode": { label: "Decode threads" },
  "settings.threads_prefill": { label: "Prompt threads" },
  "settings.context_per_slot": { label: "Context length", format: tokens },
  "settings.context_tokens": { label: "Context length", format: tokens },
  "settings.batch_size": { label: "Batch size" },
  "settings.microbatch_size": { label: "Microbatch" },
  "settings.kv_type": { label: "KV cache" },
  "settings.kv_type_k": { label: "KV cache (K)" },
  "settings.kv_type_v": { label: "KV cache (V)" },
  "settings.flash_attention": { label: "Flash attention", format: onOff },
  "settings.speculative_mode": { label: "Speculative decoding", format: (v) => SPECULATION_NAMES[String(v)] ?? show(v) },
  "settings.draft_tokens": { label: "Draft tokens" },
  "settings.temperature": { label: "Temperature" },
  "settings.top_k": { label: "Top-k" },
  "settings.top_p": { label: "Top-p" },
  "settings.min_p": { label: "Min-p" },
  "settings.reasoning_effort": { label: "Reasoning effort" },
  "settings.gpu_layers": { label: "GPU layers" },
};
const ORDER = Object.keys(FIELDS);

function show(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "On" : "Off";
  if (Array.isArray(value)) return value.map(show).join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function humanize(path: string): string {
  const last = path.split(".").pop() ?? path;
  const words = last.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function row(change: Change): ChangeRow {
  const field = FIELDS[change.path];
  const format = field?.format ?? show;
  return {
    key: change.path,
    label: field?.label ?? humanize(change.path),
    from: format(change.from),
    to: format(change.to),
    reason: change.reason ?? "",
    advanced: !field,
  };
}

/** Merges a pair of related changes into one row when the backend sends both. */
function mergePair(byPath: Map<string, Change>, a: string, b: string, merged: string, label: string): ChangeRow | null {
  const first = byPath.get(a);
  const second = byPath.get(b);
  if (!first || !second) return null;
  byPath.delete(a);
  byPath.delete(b);
  const [ra, rb] = [row(first), row(second)];
  const join = (x: string, y: string) => (x === y ? x : `${x} / ${y}`);
  return {
    key: merged,
    label,
    from: join(ra.from, rb.from),
    to: join(ra.to, rb.to),
    reason: [...new Set([ra.reason, rb.reason].filter(Boolean))].join(" · "),
    advanced: false,
  };
}

export function changeRows(changes: Change[]): ChangeRow[] {
  const byPath = new Map(changes.map((change) => [change.path, change]));
  // One context row: per-slot context is what the student can use per request.
  if (byPath.has("settings.context_per_slot")) byPath.delete("settings.context_tokens");

  const rows: ChangeRow[] = [];
  const threads = mergePair(byPath, "settings.threads_decode", "settings.threads_prefill", "settings.threads", "Threads");
  const kv = mergePair(byPath, "settings.kv_type_k", "settings.kv_type_v", "settings.kv_type", "KV cache");
  for (const extra of [threads, kv]) if (extra) rows.push(extra);
  for (const change of byPath.values()) rows.push(row(change));

  const rank = (key: string) => {
    const index = ORDER.indexOf(key);
    return index === -1 ? ORDER.length : index;
  };
  return rows.sort((a, b) => rank(a.key) - rank(b.key));
}

/** Fallback when no `changes` array reached us: diff two configs. */
export function diffConfigs(before: Config, after: Config): Change[] {
  const changes: Change[] = [];
  for (const key of ["engine", "quant"] as const) {
    if (before[key] !== after[key]) changes.push({ path: key, from: before[key], to: after[key] });
  }
  const keys = new Set([...Object.keys(before.settings), ...Object.keys(after.settings)]);
  for (const key of keys) {
    if (!(`settings.${key}` in FIELDS)) continue;
    const from = before.settings[key];
    const to = after.settings[key];
    if (to !== undefined && JSON.stringify(from) !== JSON.stringify(to)) changes.push({ path: `settings.${key}`, from, to });
  }
  return changes;
}

// Performance settings worth comparing against the tuned profile (sampling is left out).
const CONFIG_SUMMARY = new Set([
  "engine", "settings.threads", "settings.threads_decode", "settings.context_per_slot", "settings.context_tokens",
  "settings.batch_size", "settings.kv_type", "settings.kv_type_k", "settings.flash_attention", "settings.speculative_mode",
]);

/** Key performance settings of a single config (no before/after), e.g. the untouched default. */
export function configRows(config: Config): ChangeRow[] {
  const empty: Config = { ...config, engine: "", quant: null, settings: {} };
  return changeRows(diffConfigs(empty, config)).filter((row) => CONFIG_SUMMARY.has(row.key));
}
