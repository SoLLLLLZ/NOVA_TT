import type {
  Change,
  Config,
  Confidence,
  ErrorBody,
  LiveEvent,
  OptimizeDone,
  RunEvent,
  RunSnapshot,
  StatusResponse,
  StepEvent,
  StepName,
} from "../api/types";
import { diffConfigs } from "../lib/changes";

export type Phase =
  | "connecting"
  | "pairing"
  | "detecting_gpu"
  | "select_model"
  | "optimizing"
  | "optimized"
  | "live_speed"
  | "reverting"
  | "error";

/** What the widget remembers about the applied tuned profile. */
export type TunedResult = {
  model: string;
  runId: string;
  rollbackId: string | null;
  changes: Change[];
  confidence: Confidence;
  gpuType: string;
};

export type RunState = {
  runId: string | null;
  model: string;
  gpuType: string;
  idempotencyKey: string;
  /** Config active before this optimize, for the changes fallback. */
  before: Config | null;
  steps: StepEvent[];
  lastSequence: number;
  /** current_step from a snapshot when we reconnected without the event history. */
  snapshotStep: StepName | null;
  changes: Change[] | null;
  confidence: Confidence | null;
  done: OptimizeDone | null;
  /** The pitstop animation has reached the service bay. */
  animationReady: boolean;
};

export type LiveState = {
  decode: number | null;
  prefill: number | null;
  requestId: string | null;
  active: boolean;
};

export type State = {
  phase: Phase;
  status: StatusResponse | null;
  contractMinor: number;
  pairingError: string | null;
  clusterId: string;
  gpuType: string | null;
  model: string;
  run: RunState | null;
  result: TunedResult | null;
  live: LiveState;
  liveUnavailable: string | null;
  error: ErrorBody | null;
  /** Inline error shown on the optimized/live screens after a failed revert. */
  revertError: string | null;
  toast: string | null;
};

export const DEFAULT_MODEL = "qwen3.8-27b";

export const initialState: State = {
  phase: "connecting",
  status: null,
  contractMinor: 0,
  pairingError: null,
  clusterId: "wright",
  gpuType: null,
  model: DEFAULT_MODEL,
  run: null,
  result: null,
  live: { decode: null, prefill: null, requestId: null, active: false },
  liveUnavailable: null,
  error: null,
  revertError: null,
  toast: null,
};

export type Action =
  | { type: "connected"; contractMinor: number }
  | { type: "need_pairing"; message: string | null }
  | { type: "paired" }
  | { type: "status_loaded"; status: StatusResponse }
  | { type: "fatal"; error: ErrorBody }
  | { type: "select_cluster"; clusterId: string }
  | { type: "select_gpu"; gpuType: string }
  | { type: "select_model"; model: string }
  | { type: "optimize_start"; idempotencyKey: string; before: Config | null }
  | { type: "run_event"; event: RunEvent }
  | { type: "run_snapshot"; snapshot: RunSnapshot }
  | { type: "run_failed"; error: ErrorBody }
  | { type: "resume_run"; runId: string; model: string; gpuType: string; idempotencyKey: string; before: Config | null }
  | { type: "animation_ready" }
  | { type: "resume_tuned"; result: TunedResult }
  | { type: "live_event"; event: LiveEvent }
  | { type: "live_unavailable"; message: string }
  | { type: "revert_start" }
  | { type: "revert_done" }
  | { type: "revert_failed"; message: string }
  | { type: "back_to_select" }
  | { type: "clear_toast" };

const emptyLive: LiveState = initialState.live;

function newRun(model: string, gpuType: string, idempotencyKey: string, before: Config | null, runId: string | null): RunState {
  return {
    runId,
    model,
    gpuType,
    idempotencyKey,
    before,
    steps: [],
    lastSequence: 0,
    snapshotStep: null,
    changes: null,
    confidence: null,
    done: null,
    animationReady: false,
  };
}

/** Moves to "optimized" once the backend is done and the car is in the bay. */
function settle(state: State): State {
  const run = state.run;
  if (state.phase !== "optimizing" || !run?.done || !run.animationReady) return state;
  const done = run.done;
  if (!done.applied || done.validation?.status !== "passed") {
    return {
      ...state,
      phase: "error",
      error: {
        code: "validation_failed",
        message: "The backend finished without a passed verification, so nothing was marked as tuned.",
        retryable: true,
      },
    };
  }
  const changes = run.changes ?? (run.before ? diffConfigs(run.before, done.config) : []);
  return {
    ...state,
    phase: "optimized",
    live: emptyLive,
    liveUnavailable: null,
    revertError: null,
    result: {
      model: run.model,
      runId: done.run_id,
      rollbackId: done.rollback_id,
      changes,
      confidence: done.evidence?.confidence ?? run.confidence ?? "none",
      gpuType: run.gpuType,
    },
  };
}

function applyRunEvent(state: State, event: RunEvent): State {
  const run = state.run;
  if (!run || state.phase !== "optimizing") return state;
  if (run.runId && event.run_id !== run.runId) return state;
  if (event.sequence <= run.lastSequence) return state; // replayed or duplicate
  const next: RunState = { ...run, runId: event.run_id, lastSequence: event.sequence };
  switch (event.type) {
    case "step":
      next.steps = [...run.steps, event];
      break;
    case "config":
      // The effective config's changes win; proposed ones fill in until then.
      if (event.phase === "effective" || !run.changes) next.changes = event.changes;
      if (event.evidence) next.confidence = event.evidence.confidence;
      break;
    case "done":
      next.done = event as OptimizeDone;
      break;
    case "error":
      return { ...state, run: next, phase: "error", error: event.error };
    default:
      break;
  }
  return settle({ ...state, run: next });
}

export function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "connected":
      return { ...state, contractMinor: action.contractMinor, phase: "detecting_gpu", pairingError: null };
    case "need_pairing":
      return { ...state, phase: "pairing", pairingError: action.message };
    case "paired":
      return { ...state, phase: "detecting_gpu", pairingError: null };
    case "status_loaded": {
      const status = action.status;
      const types = status.all_gpus.length
        ? status.all_gpus.map((gpu) => gpu.label)
        : status.models.map((model) => model.requirements.gpu_type);
      const gpuType = state.gpuType && types.includes(state.gpuType) ? state.gpuType : types[0] ?? null;
      const model = status.models.some((m) => m.id === state.model) ? state.model : status.models[0]?.id ?? state.model;
      const phase = state.phase === "detecting_gpu" || state.phase === "connecting" ? "select_model" : state.phase;
      return { ...state, status, gpuType, model, phase };
    }
    case "fatal":
      return { ...state, phase: "error", error: action.error };
    case "select_cluster":
      return { ...state, clusterId: action.clusterId };
    case "select_gpu":
      return { ...state, gpuType: action.gpuType };
    case "select_model":
      return { ...state, model: action.model };
    case "optimize_start":
      return {
        ...state,
        phase: "optimizing",
        error: null,
        result: null,
        run: newRun(state.model, state.gpuType ?? "L40", action.idempotencyKey, action.before, null),
      };
    case "resume_run":
      return {
        ...state,
        phase: "optimizing",
        model: action.model,
        gpuType: action.gpuType,
        error: null,
        run: newRun(action.model, action.gpuType, action.idempotencyKey, action.before, action.runId),
      };
    case "run_event":
      return applyRunEvent(state, action.event);
    case "run_snapshot": {
      const run = state.run;
      const snap = action.snapshot;
      if (!run || state.phase !== "optimizing" || (run.runId && run.runId !== snap.run_id)) return state;
      const next: RunState = {
        ...run,
        runId: snap.run_id,
        snapshotStep: snap.current_step,
        confidence: snap.evidence?.confidence ?? run.confidence,
      };
      if (snap.state === "succeeded" && snap.result) next.done = snap.result;
      if ((snap.state === "failed" || snap.state === "cancelled") && snap.error) {
        return { ...state, run: next, phase: "error", error: snap.error };
      }
      return settle({ ...state, run: next });
    }
    case "run_failed":
      return { ...state, phase: "error", error: action.error };
    case "animation_ready":
      if (!state.run) return state;
      return settle({ ...state, run: { ...state.run, animationReady: true } });
    case "resume_tuned":
      return {
        ...state,
        phase: "optimized",
        model: action.result.model,
        gpuType: action.result.gpuType,
        result: action.result,
        live: emptyLive,
      };
    case "live_event": {
      if (state.phase !== "optimized" && state.phase !== "live_speed") return state;
      const event = action.event;
      switch (event.type) {
        case "inference_started":
          return {
            ...state,
            phase: "live_speed",
            live: { ...state.live, requestId: event.request_id, active: true },
          };
        case "metrics":
          return {
            ...state,
            phase: "live_speed",
            live: {
              requestId: event.request_id,
              active: true,
              decode: event.decode_tps ?? state.live.decode,
              prefill: event.prefill_tps ?? state.live.prefill,
            },
          };
        case "inference_done":
          return {
            ...state,
            phase: "live_speed",
            live: {
              requestId: event.request_id,
              active: false,
              decode: event.measurement.decode_tps ?? state.live.decode,
              prefill: event.measurement.prefill_tps ?? state.live.prefill,
            },
          };
        case "error":
          return { ...state, liveUnavailable: event.error.message };
        default:
          return state;
      }
    }
    case "live_unavailable":
      return { ...state, liveUnavailable: action.message };
    case "revert_start":
      return { ...state, phase: "reverting", revertError: null };
    case "revert_done":
      return {
        ...state,
        phase: "select_model",
        result: null,
        run: null,
        live: emptyLive,
        liveUnavailable: null,
        toast: "Defaults restored",
      };
    case "revert_failed":
      return {
        ...state,
        phase: state.live.decode !== null ? "live_speed" : "optimized",
        revertError: action.message,
      };
    case "back_to_select":
      return { ...state, phase: state.status ? "select_model" : "connecting", error: null, run: null };
    case "clear_toast":
      return { ...state, toast: null };
    default:
      return state;
  }
}
