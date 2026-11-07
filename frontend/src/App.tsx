import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { ApiError, Client, newIdempotencyKey, parseVersion } from "./api/client";
import type { Config, ErrorBody, ReplayResponse, RunEvent } from "./api/types";
import { DesktopBar } from "./components/DesktopBar";
import { Wordmark } from "./components/Header";
import { desktop } from "./lib/desktop";
import { PairingForm } from "./components/PairingForm";
import { Toast } from "./components/Toast";
import { CONTRACT_MAJOR, DEFAULT_API_BASE, LIVE_MIN_MINOR } from "./config";
import { changeRows } from "./lib/changes";
import { gpuLabel } from "./lib/format";
import { KEYS, load, remove, save } from "./lib/storage";
import { lookFor } from "./models";
import { DefaultScreen } from "./screens/DefaultScreen";
import { ErrorScreen } from "./screens/ErrorScreen";
import { LiveScreen } from "./screens/LiveScreen";
import { OptimizedScreen } from "./screens/OptimizedScreen";
import { PitstopScreen } from "./screens/PitstopScreen";
import { SelectScreen } from "./screens/SelectScreen";
import { initialState, reducer, type Baseline, type RunKind, type TunedResult } from "./state/machine";
import { deriveChecklist } from "./state/steps";

type PendingRun = { runId: string | null; model: string; gpuType: string; idempotencyKey: string; before: Config | null; kind?: RunKind };

const POLL_MS = 1500;
const STATUS_REFRESH_MS = 15000;
const LIVE_RETRY_MS = 3000;
const MIN_DETECT_MS = 700;

const asErrorBody = (error: unknown): ErrorBody =>
  error instanceof ApiError
    ? error.body
    : { code: "internal", message: error instanceof Error ? error.message : String(error) };

const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

export function App() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const [client, setClient] = useState<Client | null>(null);
  const [offline, setOffline] = useState(false);
  const pollAbort = useRef<AbortController | null>(null);
  const opAbort = useRef<AbortController | null>(null);

  // ---------------------------------------------------------------- connect
  const bootstrap = useCallback(async (tokenOverride?: string) => {
    const base = (await load<string>(KEYS.apiBase)) ?? DEFAULT_API_BASE;
    let version: { major: number; minor: number };
    try {
      const health = await new Client(base, null).health();
      version = parseVersion(health.contract_version);
    } catch (error) {
      dispatch({ type: "fatal", error: asErrorBody(error) });
      return;
    }
    if (version.major !== CONTRACT_MAJOR) {
      dispatch({
        type: "fatal",
        error: { code: "contract_mismatch", message: `The backend speaks contract ${version.major}.x; this widget needs ${CONTRACT_MAJOR}.x.` },
      });
      return;
    }
    const token = tokenOverride ?? (await load<string>(KEYS.pairing));
    if (!token) {
      dispatch({ type: "need_pairing", message: null });
      return;
    }
    dispatch({ type: "connected", contractMinor: version.minor });
    const authed = new Client(base, token);
    const started = performance.now();
    try {
      const status = await authed.status();
      await save(KEYS.pairing, token);
      const wait = MIN_DETECT_MS - (performance.now() - started);
      if (wait > 0) await sleep(wait);
      setClient(authed);
      setOffline(false);
      dispatch({ type: "status_loaded", status });
      const baselines = await load<Record<string, Baseline>>(KEYS.baselines);
      if (baselines) dispatch({ type: "baselines_loaded", baselines });

      // Pick up where a closed widget left off.
      if (status.active_run_id) {
        const pending = await load<PendingRun>(KEYS.pendingRun);
        dispatch({
          type: "resume_run",
          runId: status.active_run_id,
          model: pending?.model ?? status.models[0]?.id ?? initialState.model,
          gpuType: pending?.gpuType ?? status.all_gpus[0]?.label ?? "L40",
          idempotencyKey: pending?.idempotencyKey ?? newIdempotencyKey(),
          before: pending?.before ?? null,
          kind: pending?.kind,
        });
      } else if (status.current_config) {
        // Reopen on the retained service: tuned, or the untouched default run.
        const stored = await load<TunedResult>(KEYS.tuned);
        const result = stored ? { ...stored, kind: stored.kind ?? "tuned" } : null;
        if (result && status.current_config.model === result.model && (result.kind === "tuned") === status.is_tuned) {
          dispatch({ type: "resume_tuned", result });
        }
      }
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        await remove(KEYS.pairing);
        dispatch({ type: "need_pairing", message: tokenOverride ? "That code didn't work. Check the backend's console." : null });
        return;
      }
      dispatch({ type: "fatal", error: asErrorBody(error) });
    }
  }, []);

  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  // Keep GPU/readiness fresh while choosing a model.
  useEffect(() => {
    if (!client || state.phase !== "select_model") return;
    const timer = window.setInterval(async () => {
      try {
        dispatch({ type: "status_loaded", status: await client.status() });
        setOffline(false);
      } catch {
        setOffline(true);
      }
    }, STATUS_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [client, state.phase]);

  // ---------------------------------------------------------------- optimize
  const pollRun = useCallback(
    async (runId: string) => {
      if (!client) return;
      pollAbort.current?.abort();
      const controller = new AbortController();
      pollAbort.current = controller;
      let failures = 0;
      while (!controller.signal.aborted) {
        try {
          const snapshot = await client.run(runId);
          failures = 0;
          dispatch({ type: "run_snapshot", snapshot });
          if (["succeeded", "failed", "cancelled"].includes(snapshot.state)) return;
        } catch (error) {
          if (error instanceof ApiError && error.status === 404) {
            dispatch({ type: "run_failed", error: error.body });
            return;
          }
          if (++failures >= 20) {
            dispatch({ type: "run_failed", error: asErrorBody(error) });
            return;
          }
        }
        await sleep(POLL_MS);
      }
    },
    [client],
  );

  // Resume polling for a run we reattached to.
  const resumedRunId = state.phase === "optimizing" && state.run?.runId && state.run.lastSequence === 0 ? state.run.runId : null;
  useEffect(() => {
    if (resumedRunId && !opAbort.current) void pollRun(resumedRunId);
  }, [resumedRunId, pollRun]);

  /** POSTs a streaming run, falling back to polling if the stream drops or is replayed. */
  const streamRun = useCallback(
    async (path: string, body: unknown, pending: PendingRun, resumeOnConflict: boolean) => {
      if (!client) return;
      const controller = new AbortController();
      opAbort.current = controller;
      let runId: string | null = null;
      let terminal = false;
      const onEvent = (event: RunEvent) => {
        if (event.type === "start" && !runId) {
          runId = event.run_id;
          void save(KEYS.pendingRun, { ...pending, runId });
        }
        if (event.type === "done" || event.type === "error") terminal = true;
        dispatch({ type: "run_event", event });
      };
      try {
        const replay: ReplayResponse | null = await client.operation(path, body, pending.idempotencyKey, onEvent, controller.signal);
        if (replay) runId = replay.run_id;
        if (!terminal && runId) void pollRun(runId); // stream dropped or replayed: follow the run instead of re-posting
        else if (!terminal) dispatch({ type: "run_failed", error: { code: "internal", message: "The stream ended without a result." } });
      } catch (error) {
        if (controller.signal.aborted) return;
        if (resumeOnConflict && error instanceof ApiError && error.activeRunId) {
          dispatch({ type: "resume_run", runId: error.activeRunId, model: pending.model, gpuType: pending.gpuType, idempotencyKey: pending.idempotencyKey, before: pending.before });
        } else if (runId && !terminal) {
          void pollRun(runId);
        } else {
          dispatch({ type: "run_failed", error: asErrorBody(error) });
        }
      } finally {
        if (opAbort.current === controller) opAbort.current = null;
      }
    },
    [client, pollRun],
  );

  const resourcesFor = useCallback(() => {
    const selected = state.status?.models.find((m) => m.id === state.model);
    if (!state.status || !selected) return null;
    const gpuType = state.gpuType ?? selected.requirements.gpu_type;
    return {
      gpuType,
      resources: {
        target_id: state.status.target_id,
        gpu_type: gpuType,
        gpu_count: selected.requirements.gpu_count,
        same_node: selected.requirements.same_node,
      },
    };
  }, [state.status, state.model, state.gpuType]);

  const optimize = useCallback(async () => {
    const target = resourcesFor();
    if (!client || !state.status || !target) return;
    const idempotencyKey = newIdempotencyKey();
    // Only a config for the same model is a meaningful "before" for the changes fallback.
    const before = state.status.current_config?.model === state.model ? state.status.current_config : null;
    const pending: PendingRun = { runId: null, model: state.model, gpuType: target.gpuType, idempotencyKey, before };
    dispatch({ type: "optimize_start", idempotencyKey, before });
    await save(KEYS.pendingRun, pending);
    await streamRun(
      "/optimize",
      {
        model: state.model,
        preset: "fastest",
        objective: "decode",
        workload: "short",
        mode: "verify_only",
        resources: target.resources,
        constraints: { allow_sampling_change: true },
      },
      pending,
      true,
    );
  }, [client, state.status, state.model, resourcesFor, streamRun]);

  /** Starts the untouched default (contract 2.1 `apply_default`) so its live speed can be compared. */
  const runDefault = useCallback(async () => {
    const target = resourcesFor();
    if (!client || !target) return;
    const idempotencyKey = newIdempotencyKey();
    const pending: PendingRun = { runId: null, model: state.model, gpuType: target.gpuType, idempotencyKey, before: null, kind: "default" };
    dispatch({ type: "default_start", idempotencyKey });
    await save(KEYS.pendingRun, pending);
    await streamRun(
      "/action",
      { action: "apply_default", params: { model: state.model, resources: target.resources } },
      pending,
      false,
    );
  }, [client, state.model, resourcesFor, streamRun]);

  const onArrived = useCallback(() => dispatch({ type: "animation_ready" }), []);

  // Persist the tuned result so a reopened widget lands back on it.
  useEffect(() => {
    if (state.result) {
      void save(KEYS.tuned, state.result);
      void remove(KEYS.pendingRun);
    }
  }, [state.result]);

  useEffect(() => {
    if (state.phase === "error") void remove(KEYS.pendingRun);
  }, [state.phase]);

  useEffect(() => {
    if (Object.keys(state.baselines).length) void save(KEYS.baselines, state.baselines);
  }, [state.baselines]);

  // ---------------------------------------------------------------- live speed
  const tuned = state.phase === "optimized" || state.phase === "live_speed" || state.phase === "reverting";
  const liveModel = tuned ? state.result?.model ?? null : null;
  const liveKey = tuned ? state.result?.runId ?? null : null;
  useEffect(() => {
    if (!client || !liveModel || !liveKey) return;
    if (state.contractMinor < LIVE_MIN_MINOR) {
      dispatch({ type: "live_unavailable", message: "Live speed needs backend contract 2.1." });
      return;
    }
    const controller = new AbortController();
    (async () => {
      while (!controller.signal.aborted) {
        try {
          await client.live(liveModel, (event) => dispatch({ type: "live_event", event }), controller.signal);
        } catch (error) {
          if (controller.signal.aborted) return;
          if (error instanceof ApiError && error.status === 404) {
            dispatch({ type: "live_unavailable", message: error.body.message });
            return;
          }
        }
        await sleep(LIVE_RETRY_MS);
      }
    })();
    return () => controller.abort();
    // state.contractMinor is fixed once connected.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, liveModel, liveKey]);

  // ---------------------------------------------------------------- revert
  const revert = useCallback(async () => {
    if (!client || !state.result) return;
    if (!state.result.rollbackId) {
      dispatch({ type: "revert_failed", message: "The backend didn't return a rollback ID, so there is nothing to revert to." });
      return;
    }
    dispatch({ type: "revert_start" });
    let outcome: { ok: true } | { ok: false; message: string } | null = null;
    try {
      const replay = await client.operation(
        "/revert",
        { rollback_id: state.result.rollbackId },
        newIdempotencyKey(),
        (event) => {
          if (event.type === "done") outcome = { ok: true };
          if (event.type === "error") outcome = { ok: false, message: event.error.message };
        },
      );
      if (replay) outcome = replay.result ? { ok: true } : { ok: false, message: replay.error?.message ?? "Revert did not finish." };
    } catch (error) {
      outcome = { ok: false, message: asErrorBody(error).message };
    }
    const result = outcome as { ok: true } | { ok: false; message: string } | null;
    if (result?.ok) {
      await remove(KEYS.tuned);
      dispatch({ type: "revert_done" });
      try {
        dispatch({ type: "status_loaded", status: await client.status() });
      } catch {
        setOffline(true);
      }
    } else {
      dispatch({ type: "revert_failed", message: result?.message ?? "Revert ended without a result." });
    }
  }, [client, state.result]);

  // Escape hides the desktop widget unless a dropdown or text field has it.
  useEffect(() => {
    if (!desktop) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      if (document.querySelector(".pselect.is-open") || document.activeElement instanceof HTMLInputElement) return;
      desktop?.hide();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // ---------------------------------------------------------------- render
  const clearToast = useCallback(() => dispatch({ type: "clear_toast" }), []);
  const checklist = useMemo(() => {
    const run = state.run;
    if (!run) return deriveChecklist([]);
    return deriveChecklist(run.steps, {
      currentStep: run.snapshotStep,
      finished: !!run.done,
      failed: state.phase === "error",
    });
  }, [state.run, state.phase]);
  const detail = state.run?.steps.at(-1)?.detail ?? null;

  const modelId = state.run?.model ?? state.result?.model ?? state.model;
  const catalogEntry = state.status?.models.find((m) => m.id === modelId);
  const look = lookFor(modelId, catalogEntry?.display_name);
  const gpuType = state.result?.gpuType ?? state.gpuType;
  const gpuText = gpuType ? gpuLabel(gpuType, state.status?.all_gpus) : null;
  const reverting = state.phase === "reverting";

  let screen;
  switch (state.phase) {
    case "pairing":
      screen = (
        <main className="screen screen--pairing">
          <Wordmark />
          <PairingForm error={state.pairingError} onSubmit={(code) => void bootstrap(code)} />
        </main>
      );
      break;
    case "optimizing":
      screen = <PitstopScreen key={state.run?.idempotencyKey} look={look} items={checklist} detail={detail} onArrived={onArrived} />;
      break;
    case "starting_default":
      screen = <DefaultScreen look={look} modelKey={modelId} config={null} detail={detail} waitingText="" onOptimize={() => void optimize()} onStop={() => void revert()} stopping={false} stopError={null} />;
      break;
    case "optimized":
    case "reverting":
    case "live_speed":
      if (state.phase === "live_speed" || (reverting && state.live.decode !== null)) {
        screen = (
          <LiveScreen
            gpu={gpuText}
            offline={offline}
            decode={state.live.decode}
            prefill={state.live.prefill}
            active={state.live.active}
            kind={state.result?.kind ?? "tuned"}
            look={look}
            baseline={state.result?.kind === "tuned" ? state.baselines[modelId] ?? null : null}
            onOptimize={() => void optimize()}
            reverting={reverting}
            revertError={state.revertError}
            onRevert={() => void revert()}
          />
        );
      } else if (state.result?.kind === "default") {
        screen = (
          <DefaultScreen
            look={look}
            modelKey={modelId}
            config={state.result.config}
            detail={null}
            waitingText={state.liveUnavailable ?? "Run the model in your terminal…"}
            onOptimize={() => void optimize()}
            onStop={() => void revert()}
            stopping={reverting}
            stopError={state.revertError}
          />
        );
      } else {
        screen = (
          <OptimizedScreen
            look={look}
            modelKey={modelId}
            confidence={state.result?.confidence ?? "none"}
            rows={changeRows(state.result?.changes ?? [])}
            waitingText={state.liveUnavailable ?? "Waiting for terminal command…"}
            reverting={reverting}
            revertError={state.revertError}
            onRevert={() => void revert()}
          />
        );
      }
      break;
    case "error":
      screen = (
        <ErrorScreen
          error={state.error}
          retryLabel={state.status ? "TRY AGAIN" : "RETRY CONNECTION"}
          onRetry={() => (!state.status ? void bootstrap() : state.run?.kind === "default" ? void runDefault() : void optimize())}
          onBack={state.status ? () => dispatch({ type: "back_to_select" }) : null}
        />
      );
      break;
    default:
      screen = (
        <SelectScreen
          status={state.phase === "select_model" ? state.status : null}
          offline={offline}
          clusterId={state.clusterId}
          gpuType={state.gpuType}
          model={state.model}
          onCluster={(clusterId) => dispatch({ type: "select_cluster", clusterId })}
          onGpu={(type) => dispatch({ type: "select_gpu", gpuType: type })}
          onModel={(model) => dispatch({ type: "select_model", model })}
          onOptimize={() => void optimize()}
          onRunDefault={() => void runDefault()}
        />
      );
  }

  return (
    <div className="app">
      <DesktopBar />
      {screen}
      <Toast message={state.toast} onDone={clearToast} />
    </div>
  );
}
