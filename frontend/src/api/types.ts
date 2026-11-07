// Subset of contract v2.1 (docs/api/endpoint.md) that the widget reads.
// Responses may carry more fields; unknown ones are ignored.

export type ModelId = "qwen3.8-27b" | "qwen3.8-flash-next" | "muse-glimmer";

export type ErrorBody = {
  code: string;
  message: string;
  diagnosable?: boolean;
  retryable?: boolean;
  field?: string | null;
  details?: Record<string, unknown> | null;
};

export type Gpu = {
  id: string;
  node_id: string | null;
  local_index: number | null;
  label: string;
  name: string | null;
  memory_total_mib: number | null;
  memory_free_mib: number | null;
  busy: boolean | null;
};

export type Allocation = {
  id: string;
  state: "pending" | "running" | "completed" | "failed" | "unknown";
  node_ids: string[];
  gpu_ids: string[];
  expires_at: string | null;
  owned: boolean;
};

export type CatalogModel = {
  id: string;
  display_name: string;
  quant: string;
  installed: boolean;
  loaded: boolean;
  database_coverage: "verified" | "inferred" | "experimental" | "none";
  requirements: { gpu_type: string; gpu_count: number; same_node: boolean; context_per_slot: number };
  ready: boolean;
  readiness_reasons: string[];
};

export type Config = {
  profile_id: string | null;
  model: string;
  artifact_id: string | null;
  quant: string | null;
  engine: "ollama" | "llama.cpp" | string;
  runtime_id: string | null;
  settings: Record<string, unknown>;
};

export type StatusResponse = {
  contract_version: string;
  target_id: string;
  connection: "connected" | "disconnected" | "unknown";
  allocation: Allocation | null;
  all_gpus: Gpu[];
  models: CatalogModel[];
  current_config: Config | null;
  active_run_id: string | null;
  is_tuned: boolean;
};

export type Change = { path: string; from: unknown; to: unknown; reason?: string | null };

export type Confidence = "verified" | "inferred" | "experimental" | "none";

export type Evidence = { confidence: Confidence; source_rows?: number | null };

export type Validation = { status: "pending" | "passed" | "failed"; scope?: string | null };

export type Measurement = {
  decode_tps: number | null;
  prefill_tps: number | null;
  output_tokens: number | null;
  prompt_tokens: number | null;
};

export type StepName =
  | "detect_gpu" | "check_database" | "ask_ai" | "allocate" | "load_model"
  | "test_configs" | "verify" | "repair" | "apply" | "rollback";

export type StepStatus = "pending" | "running" | "done" | "failed" | "skipped";

type Envelope = { run_id: string; sequence: number; at: string };

export type StartEvent = Envelope & { type: "start"; operation: string; mode: string };
export type StepEvent = Envelope & {
  type: "step"; name: StepName; status: StepStatus; progress: number | null; detail: string | null;
};
export type ConfigEvent = Envelope & {
  type: "config"; phase: "proposed" | "effective"; config: Config; changes: Change[]; evidence: Evidence | null;
};
export type OptimizeDone = Envelope & {
  type: "done";
  status: "success";
  applied: boolean;
  config: Config;
  evidence: Evidence | null;
  validation: Validation | null;
  rollback_id: string | null;
};
export type RevertDone = Envelope & { type: "done"; status: "success"; restored: boolean; config: Config | null };
export type ErrorEvent = Envelope & { type: "error"; error: ErrorBody };
export type OtherEvent = Envelope & { type: "benchmark" | "validation" | "repair" };

export type RunEvent = StartEvent | StepEvent | ConfigEvent | OptimizeDone | ErrorEvent | OtherEvent;

export type RunSnapshot = {
  run_id: string;
  operation: string;
  state: "pending" | "running" | "cancelling" | "succeeded" | "failed" | "cancelled";
  current_step: StepName | null;
  latest_config: Config | null;
  evidence: Evidence | null;
  result: OptimizeDone | null;
  error: ErrorBody | null;
};

export type ReplayResponse = {
  run_id: string;
  state: RunSnapshot["state"];
  replayed: true;
  result: OptimizeDone | null;
  error: ErrorBody | null;
};

export type LiveEvent =
  | { type: "waiting"; model: string; service_id: string | null }
  | { type: "inference_started"; request_id: string; prompt_tokens: number | null }
  | { type: "metrics"; request_id: string; decode_tps: number | null; prefill_tps: number | null; output_tokens: number }
  | { type: "inference_done"; request_id: string; measurement: Measurement }
  | { type: "error"; error: ErrorBody };
