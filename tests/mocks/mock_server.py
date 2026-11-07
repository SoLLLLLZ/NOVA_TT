#!/usr/bin/env python3
"""NOVA mock backend, contract v2.1 (see ../endpoint.md).

Standard library only. It lets the frontend run every screen without Wright,
Slurm, llama.cpp or OpenRouter. Every number it emits is a mock fixture and is
labelled as such in measurement warnings; nothing here is a real benchmark.

    python3 tests/mocks/mock_server.py [--port 8000]

Environment:
    NOVA_PAIRING_CODE            pairing code to accept (default 7K4-92X)
    MOCK_SCENARIO                success | repair | fail   (default success)
    MOCK_ALLOCATION              running | none            (default running)
    MOCK_SPEED                   step-time multiplier       (default 1.0; tests use 0.01)
    MOCK_AUTO_INFERENCE_SECONDS  if set, fake a terminal run N s after a successful optimize

Mock-only route (not part of the contract):
    POST /mock/inference {"model": "<id>"}   pretend the student ran the model in a terminal (default or tuned)
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import queue
import random
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

CONTRACT_VERSION = "2.1"
PAIRING_CODE = os.environ.get("NOVA_PAIRING_CODE", "7K4-92X")
SCENARIO = os.environ.get("MOCK_SCENARIO", "success")
ALLOCATION_MODE = os.environ.get("MOCK_ALLOCATION", "running")
SPEED = float(os.environ.get("MOCK_SPEED", "1.0"))
AUTO_INFERENCE = os.environ.get("MOCK_AUTO_INFERENCE_SECONDS")
MOCK_WARNING = "mock fixture: not a real measurement"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def later_iso(seconds: float) -> str:
    stamp = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    return stamp.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def pause(seconds: float) -> None:
    time.sleep(seconds * SPEED)


# --------------------------------------------------------------------------
# Catalog (mirrors DEMO_MODELS.md)
# --------------------------------------------------------------------------

RUNTIME_SHARED = "mock-llamacpp-b10820-sm89"
RUNTIME_GLIMMER = "mock-glimmer-patched-sm89"

CATALOG = {
    "qwen3.8-27b": {
        "display_name": "ByteShape Qwen 3.8 27B",
        "quant": "IQ3_S hybrid 3.23bpw",
        "requirements": {"gpu_type": "L40", "gpu_count": 1, "same_node": True, "context_per_slot": 65536},
        "race_gpus": 2,
        "rows": 9,
        "default": {
            "context_tokens": 32768, "context_per_slot": 32768, "threads_decode": 128, "threads_prefill": 128,
            "batch_size": 1024, "kv_type_k": "f16", "kv_type_v": "f16", "flash_attention": "on",
            "speculative_mode": "none", "temperature": 1.0, "top_k": 20, "top_p": 0.95, "min_p": 0.0,
        },
        "profile": {
            "config_id": "cfg_549fe546f2fd44a6", "label": "Temperature 0.75 · MTP5", "runtime_id": RUNTIME_SHARED,
            "settings": {
                "context_tokens": 65536, "context_per_slot": 65536, "parallel_slots_per_process": 1, "replicas": 1,
                "batch_size": 2048, "microbatch_size": 512, "threads_decode": 2, "threads_prefill": 6,
                "draft_tokens": 5, "draft_gpu_layers": 99, "prompt_cache_ram_mib": 1024,
                "kv_type_k": "q8_0", "kv_type_v": "q8_0", "flash_attention": "on", "fit": "off",
                "speculative_mode": "draft-mtp", "draft_kv_k": "q8_0", "draft_kv_v": "q8_0", "split_mode": "none",
                "reasoning_effort": "medium", "temperature": 0.75, "top_p": 0.95, "min_p": 0.0, "top_k": 20,
                "draft_device": ["CUDA0"], "backend_sampling": True, "checkpoint_min_step": 512, "gpu_layers": 99,
                "main_gpu": 0, "tensor_overrides": [{"pattern": "token_embd.weight", "buffer": "CUDA0"}],
                "draft_model": None,
            },
        },
        "fallback": {"config_id": "cfg_aee1c8396d18230b", "label": "Production · MTP3",
                     "overrides": {"draft_tokens": 3, "temperature": 1.0}},
        "live": {"decode": 138.0, "prefill": 1805.0},
        "live_default": {"decode": 21.5, "prefill": 1240.0},
    },
    "qwen3.8-flash-next": {
        "display_name": "Qwen 3.8 Flash Next",
        "quant": "UD-Q4_K_XL",
        "requirements": {"gpu_type": "L40", "gpu_count": 3, "same_node": True, "context_per_slot": 131072},
        "race_gpus": 6,
        "rows": 2,
        "default": {
            "context_tokens": 262144, "context_per_slot": 262144, "threads_decode": 128, "threads_prefill": 128,
            "batch_size": 512, "kv_type_k": "f16", "kv_type_v": "f16", "flash_attention": "on",
            "speculative_mode": "none", "temperature": 1.0,
        },
        "profile": {
            "config_id": "cfg_22bd103c1aadb59c", "label": "Production · MTP2", "runtime_id": RUNTIME_SHARED,
            "settings": {
                "context_tokens": 131072, "context_per_slot": 131072, "parallel_slots_per_process": 1, "replicas": 1,
                "batch_size": 2048, "microbatch_size": 1024, "threads_decode": 8, "threads_prefill": 12,
                "draft_tokens": 2, "draft_gpu_layers": 99, "prompt_cache_ram_mib": 4096,
                "kv_type_k": "f16", "kv_type_v": "f16", "flash_attention": "on", "fit": "on",
                "speculative_mode": "draft-mtp", "draft_kv_k": "f16", "draft_kv_v": "f16", "split_mode": "layer",
                "reasoning_effort": "medium", "temperature": 1.0, "top_p": 0.95, "min_p": 0.0, "top_k": 20,
                "draft_device": ["CUDA2"], "fit_target_mib": [1024, 1024, 4096], "backend_sampling": True,
                "force_mmq_runtime": True, "load_mode": "none", "lazy_mode": "on", "draft_probability_min": 0.5,
                "draft_model": "mock-qwen3.8-flash-next-draft",
            },
        },
        "fallback": None,
        "live": {"decode": 88.0, "prefill": 960.0},
        "live_default": {"decode": 19.6, "prefill": 1610.0},
    },
    "muse-glimmer": {
        "display_name": "Muse Glimmer 30B",
        "quant": "UD-Q4_K_XL",
        "requirements": {"gpu_type": "L40", "gpu_count": 1, "same_node": True, "context_per_slot": 262144},
        "race_gpus": 2,
        "rows": 3,
        "default": {
            "context_tokens": 32768, "context_per_slot": 32768, "threads_decode": 128, "threads_prefill": 128,
            "batch_size": 1024, "kv_type_k": "f16", "kv_type_v": "f16", "flash_attention": "on",
            "speculative_mode": "none", "temperature": 0.8, "top_k": 40, "top_p": 0.9,
        },
        "profile": {
            "config_id": "cfg_0956f7625217646c", "label": "Temperature 0.75 · DFlash15", "runtime_id": RUNTIME_GLIMMER,
            "settings": {
                "context_tokens": 262144, "context_per_slot": 262144, "parallel_slots_per_process": 1, "replicas": 1,
                "batch_size": 4096, "microbatch_size": 512, "threads_decode": 8, "threads_prefill": 12,
                "draft_tokens": 15, "draft_gpu_layers": 99, "prompt_cache_ram_mib": 4096,
                "kv_type_k": "f16", "kv_type_v": "f16", "flash_attention": "on", "fit": "off",
                "speculative_mode": "draft-dflash", "draft_kv_k": "f16", "draft_kv_v": "f16", "split_mode": "none",
                "reasoning_effort": "high", "temperature": 0.75, "top_p": 0.95, "min_p": 0.0, "top_k": 64,
                "draft_device": ["CUDA0"], "draft_model": "mock-muse-glimmer-draft",
            },
        },
        "fallback": {"config_id": "cfg_91cf36411e6d4895", "label": "Production · DFlash11",
                     "overrides": {"draft_tokens": 11, "temperature": 1.0}},
        "live": {"decode": 172.0, "prefill": 1740.0},
        "live_default": {"decode": 18.9, "prefill": 1960.0},
    },
}

# Settings shown as "changes" when moving from default Ollama to the tuned profile.
CHANGE_KEYS = [
    "context_tokens", "threads_decode", "threads_prefill", "batch_size", "microbatch_size", "kv_type_k",
    "kv_type_v", "flash_attention", "speculative_mode", "draft_tokens", "temperature", "top_k", "top_p",
]
REASONS = {
    "engine": "Saved llama.cpp profile supports speculative decoding",
    "context_tokens": "Tested profile context for this model",
    "threads_decode": "Default oversubscribes the 12-CPU allocation",
    "threads_prefill": "Separate prompt-processing threads",
    "batch_size": "Matches the tested profile",
    "microbatch_size": "Matches the tested profile",
    "kv_type_k": "Tested KV precision for this profile",
    "kv_type_v": "Tested KV precision for this profile",
    "flash_attention": "Required by the tested profile",
    "speculative_mode": "Draft tokens are verified in one target pass",
    "draft_tokens": "Fastest tested draft depth that fits memory",
    "temperature": "Tested candidate sampling (allowed by request)",
    "top_k": "Tested candidate sampling (allowed by request)",
    "top_p": "Tested candidate sampling (allowed by request)",
}


def default_config(model: str) -> dict:
    entry = CATALOG[model]
    return {
        "profile_id": f"mock-default-ollama-{model}",
        "model": model,
        "artifact_id": f"mock-{model}-target",
        "quant": entry["quant"],
        "engine": "ollama",
        "runtime_id": "mock-ollama-0.40.13",
        "settings": copy.deepcopy(entry["default"]),
        "unresolved_fields": [],
    }


def tuned_config(model: str, fallback: bool = False) -> dict:
    entry = CATALOG[model]
    profile = entry["profile"]
    settings = copy.deepcopy(profile["settings"])
    profile_id = f"mock-{profile['config_id']}"
    if fallback and entry["fallback"]:
        settings.update(entry["fallback"]["overrides"])
        profile_id = f"mock-{entry['fallback']['config_id']}"
    return {
        "profile_id": profile_id,
        "model": model,
        "artifact_id": f"mock-{model}-target",
        "quant": entry["quant"],
        "engine": "llama.cpp",
        "runtime_id": profile["runtime_id"],
        "settings": settings,
        "unresolved_fields": [],
    }


def compute_changes(before: dict, after: dict) -> list:
    changes = []
    if before["engine"] != after["engine"]:
        changes.append({"path": "engine", "from": before["engine"], "to": after["engine"], "reason": REASONS["engine"]})
    for key in CHANGE_KEYS:
        old = before["settings"].get(key)
        new = after["settings"].get(key)
        if old != new and new is not None:
            changes.append({"path": f"settings.{key}", "from": old, "to": new, "reason": REASONS.get(key, "Profile setting")})
    return changes


def evidence_for(model: str, fallback: bool = False) -> dict:
    entry = CATALOG[model]
    config_id = entry["fallback"]["config_id"] if fallback and entry["fallback"] else entry["profile"]["config_id"]
    return {
        "confidence": "verified",
        "source_config_ids": [config_id],
        "lesson_ids": ["lesson_001", "lesson_003", "lesson_005"],
        "source_rows": entry["rows"],
        "match": {"model": True, "quant": True, "gpu_type": True, "gpu_count": True, "context": True,
                  "concurrency": True, "runtime": True},
        "deviations": [],
        "cautions": ["Mock evidence for frontend development"],
    }


# --------------------------------------------------------------------------
# Hardware fixture
# --------------------------------------------------------------------------

GPUS = [
    {"id": f"mock-gpu-{i}", "node_id": "n03", "local_index": i, "label": "L40", "name": "NVIDIA L40",
     "memory_total_mib": 46068, "memory_free_mib": 45210, "busy": False, "power_limit_w": 300, "temperature_c": 34}
    for i in range(3)
]


def allocation() -> dict | None:
    if ALLOCATION_MODE == "none":
        return None
    return {"id": "mock-alloc-266901", "state": "running", "node_ids": ["n03"], "gpu_ids": [g["id"] for g in GPUS],
            "cpus_per_task": 12, "host_memory_mib": 65536, "expires_at": later_iso(3600), "owned": True}


# --------------------------------------------------------------------------
# Mutable backend state
# --------------------------------------------------------------------------


class Run:
    def __init__(self, operation: str, mode: str, deadline: float):
        self.run_id = f"run_{uuid.uuid4().hex[:12]}"
        self.operation = operation
        self.mode = mode
        self.state = "running"
        self.started_at = now_iso()
        self.deadline_at = later_iso(deadline)
        self.events: list[dict] = []
        self.sequence = 0
        self.cond = threading.Condition()
        self.cancel_requested = False
        self.progress = None
        self.current_step = None
        self.latest_config = None
        self.evidence = None
        self.validation = None
        self.measurements: list = []
        self.repairs: list = []
        self.result = None
        self.error = None
        self.cleanup = None

    def emit(self, event_type: str, **fields) -> dict:
        with self.cond:
            self.sequence += 1
            event = {"type": event_type, "run_id": self.run_id, "sequence": self.sequence, "at": now_iso(), **fields}
            self.events.append(event)
            if event_type == "step":
                self.current_step = fields.get("name")
                if fields.get("progress") is not None:
                    self.progress = fields["progress"]
            elif event_type == "config":
                self.latest_config = fields.get("config")
                self.evidence = fields.get("evidence")
            elif event_type == "validation":
                self.validation = fields.get("validation")
            elif event_type == "benchmark":
                self.measurements.append(fields.get("measurement"))
            elif event_type == "repair":
                self.repairs.append({k: v for k, v in fields.items()})
            elif event_type == "done":
                self.state = "succeeded"
                self.result = event
            elif event_type == "error":
                self.state = "cancelled" if fields["error"]["code"] == "cancelled" else "failed"
                self.error = fields["error"]
                self.cleanup = fields.get("cleanup")
            self.cond.notify_all()
            return event

    @property
    def terminal(self) -> bool:
        return self.state in ("succeeded", "failed", "cancelled")

    def snapshot(self) -> dict:
        with self.cond:
            return {
                "run_id": self.run_id, "operation": self.operation, "state": self.state, "sequence": self.sequence,
                "started_at": self.started_at, "deadline_at": self.deadline_at, "progress": self.progress,
                "current_step": self.current_step, "latest_config": self.latest_config, "evidence": self.evidence,
                "validation": self.validation, "measurements": self.measurements, "repairs": self.repairs,
                "result": self.result, "error": self.error, "cleanup": self.cleanup,
            }


class Cancelled(Exception):
    pass


class State:
    def __init__(self):
        self.lock = threading.RLock()
        self.runs: dict[str, Run] = {}
        self.idempotency: dict[str, tuple[str, str]] = {}
        self.active_run_id: str | None = None
        self.current_config: dict | None = None
        self.is_tuned = False
        # Model whose retained service (tuned or untouched default) is running.
        self.service_model: str | None = None
        self.service: dict | None = None
        self.rollbacks: dict[str, dict | None] = {}
        self.live_subscribers: dict[str, list[queue.Queue]] = {}


STATE = State()


# --------------------------------------------------------------------------
# Live hub (GET /live)
# --------------------------------------------------------------------------


def live_publish(target_model: str, event_type: str, **fields) -> None:
    event = {"type": event_type, "at": now_iso(), **fields}
    with STATE.lock:
        subscribers = list(STATE.live_subscribers.get(target_model, []))
    for q in subscribers:
        q.put(event)


def fake_terminal_inference(model: str) -> str:
    """Pretend the student sent one request to the retained (tuned or default) service."""
    entry = CATALOG[model]
    tuned = STATE.is_tuned
    rates = entry["live"] if tuned else entry["live_default"]
    engine = "llama.cpp" if tuned else "ollama"
    convention = "llama.cpp (n-1)/decode_seconds" if tuned else "ollama n/decode_seconds"
    request_id = f"req_{uuid.uuid4().hex[:10]}"
    service_id = STATE.service["id"] if STATE.service else None
    prompt_tokens = 412

    def run():
        live_publish(model, "inference_started", request_id=request_id, model=model, service_id=service_id,
                     engine=engine, tuned=tuned, prompt_tokens=prompt_tokens)
        target, prefill = rates["decode"], rates["prefill"]
        prefill_tps = round(prefill * random.uniform(0.97, 1.03), 1)
        output_tokens, decode_tps = 0, 0.0
        for tick in range(1, 17):
            pause(0.25)
            ramp = min(1.0, 0.35 + tick * 0.08)
            decode_tps = round(target * ramp * random.uniform(0.97, 1.03), 1)
            output_tokens += max(1, int(decode_tps * 0.25))
            live_publish(model, "metrics", request_id=request_id, decode_tps=decode_tps, prefill_tps=prefill_tps,
                         output_tokens=output_tokens, timing_convention=convention)
        decode_seconds = round(output_tokens / decode_tps, 3)
        prefill_seconds = round(prompt_tokens / prefill_tps, 3)
        live_publish(model, "inference_done", request_id=request_id, measurement=measurement(
            model, "live-terminal", decode_tps, prefill_tps, prompt_tokens, output_tokens, decode_seconds,
            prefill_seconds, purpose="throughput", run_id=None, engine=engine,
            profile_id=None if tuned else f"mock-default-ollama-{model}"))

    threading.Thread(target=run, daemon=True).start()
    return request_id


def measurement(model, workload, decode_tps, prefill_tps, prompt_tokens, output_tokens, decode_seconds,
                prefill_seconds, purpose="throughput", run_id=None, engine="llama.cpp", profile_id=None) -> dict:
    return {
        "measurement_id": f"meas_{uuid.uuid4().hex[:10]}", "run_id": run_id,
        "profile_id": profile_id or f"mock-{CATALOG[model]['profile']['config_id']}", "origin": "live",
        "purpose": purpose, "workload": workload, "prompt_hash": None, "request_hash": None, "engine": engine,
        "runtime_id": CATALOG[model]["profile"]["runtime_id"], "gpu_ids": [GPUS[0]["id"]],
        "rate_scope": "per_request", "cache_state": "uncached", "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens, "cached_tokens": 0, "decode_timed_tokens": max(0, output_tokens - 1),
        "prefill_seconds": prefill_seconds, "decode_seconds": decode_seconds,
        "wall_seconds": round(prefill_seconds + decode_seconds, 3), "load_seconds": None, "queue_seconds": None,
        "decode_tps": decode_tps, "prefill_tps": prefill_tps,
        "timing_convention": "ollama n/decode_seconds" if engine == "ollama" else "llama.cpp (n-1)/decode_seconds",
        "output_cap": 256, "stop_reason": "length", "completed": False, "quality_pass": None,
        "min_free_gpu_memory_mib": {GPUS[0]["id"]: 22100}, "peak_temperature_c": {GPUS[0]["id"]: 51},
        "settings_hash": None, "artifact_ref": None, "sample_count": 1, "warnings": [MOCK_WARNING],
    }


# --------------------------------------------------------------------------
# Operation runners
# --------------------------------------------------------------------------


def checkpoint(run: Run) -> None:
    if run.cancel_requested:
        raise Cancelled()


def step(run: Run, name: str, status: str, progress, detail: str) -> None:
    checkpoint(run)
    run.emit("step", name=name, status=status, progress=progress, detail=detail)


def finish_active(run: Run) -> None:
    with STATE.lock:
        if STATE.active_run_id == run.run_id:
            STATE.active_run_id = None


def cleanup_obj(status="not_needed", restored=None, retained=None, issues=None, elapsed=0.0) -> dict:
    return {"status": status, "restored_profile_id": restored, "retained_service_id": retained,
            "released_allocation_ids": [], "issues": issues or [], "elapsed_seconds": elapsed}


def run_optimize(run: Run, body: dict) -> None:
    model = body["model"]
    entry = CATALOG[model]
    mode = body.get("mode", "verify_only")
    started = time.time()
    current = STATE.current_config
    # Only a config for this same model is a meaningful "before"; otherwise compare with its untouched default.
    prior = copy.deepcopy(current) if current and current.get("model") == model else None
    try:
        run.emit("start", operation=run.operation, mode=mode, started_at=run.started_at, deadline_at=run.deadline_at)
        need = entry["requirements"]["gpu_count"]
        step(run, "detect_gpu", "running", 0.02, "Reading the Slurm allocation")
        pause(0.8)
        step(run, "detect_gpu", "done", 0.08, f"Found {len(GPUS)} × L40 · 48 GB on n03")
        if ALLOCATION_MODE == "none":
            step(run, "allocate", "running", 0.1, f"Requesting {need} × L40 from Slurm")
            pause(1.2)
            step(run, "allocate", "done", 0.16, f"Slurm granted {need} × L40 on n03")
        else:
            step(run, "allocate", "skipped", 0.1, "Using existing allocation mock-alloc-266901")

        step(run, "check_database", "running", 0.18, "Filtering CANON for this model on L40")
        pause(0.9)
        step(run, "check_database", "done", 0.28, f"Found {entry['rows']} matching L40 runs")

        step(run, "ask_ai", "running", 0.3, "Asking the optimizer agent for the best decode profile")
        pause(1.6)
        before = prior or default_config(model)
        proposed = tuned_config(model)
        run.emit("config", phase="proposed", config=proposed, changes=compute_changes(before, proposed),
                 evidence=evidence_for(model))
        step(run, "ask_ai", "done", 0.45, f"Picked {entry['profile']['label']}")

        baseline = None
        if mode == "sequential_compare":
            step(run, "test_configs", "running", 0.48, "Measuring untouched default Ollama")
            pause(1.4)
            base = entry["live"]
            baseline = measurement(model, "short", round(base["decode"] / 6.4, 2), round(base["prefill"] * 0.9, 1),
                                   4078, 256, 12.0, 3.1, run_id=run.run_id, engine="ollama",
                                   profile_id=f"mock-default-ollama-{model}")
            run.emit("benchmark", label="default", measurement=baseline)
            step(run, "test_configs", "done", 0.55, "Default baseline recorded")

        step(run, "load_model", "running", 0.58, "Starting llama.cpp with the selected profile")
        pause(1.3)
        step(run, "load_model", "done", 0.68, "Target and draft loaded on the allocation")

        used_fallback = False
        step(run, "verify", "running", 0.7, "Running the short completed-answer check")
        pause(1.2)
        if SCENARIO in ("repair", "fail"):
            step(run, "verify", "failed", 0.74, "Draft KV did not fit the memory guard")
            if SCENARIO == "fail":
                cleanup = cleanup_obj("completed", restored=(prior or {}).get("profile_id"), elapsed=1.1)
                run.emit("error", error={"code": "out_of_memory", "message":
                         "The tuned profile needs more GPU memory than is free on this L40.",
                         "diagnosable": True, "retryable": True, "field": None, "details": {"min_free_mib": 768}},
                         cleanup=cleanup, last_verified_profile_id=(prior or {}).get("profile_id"))
                return
            used_fallback = entry["fallback"] is not None
            fallback = tuned_config(model, fallback=True) if used_fallback else proposed
            run.emit("repair", attempt=1, error_code="out_of_memory", summary="Switched to the production fallback profile",
                     changes=compute_changes(proposed, fallback),
                     fallback_profile_id=fallback["profile_id"] if used_fallback else None)
            step(run, "repair", "done", 0.76, "Fallback profile selected")
            step(run, "load_model", "running", 0.78, "Restarting with the fallback profile")
            pause(1.0)
            step(run, "load_model", "done", 0.82, "Fallback loaded")
            step(run, "verify", "running", 0.84, "Re-running the completed-answer check")
            pause(1.0)

        effective = tuned_config(model, fallback=used_fallback)
        validation = {
            "status": "passed", "completed_answer": True, "answer_correct": True, "service_healthy": True,
            "placement_matches": True, "context_matches": True, "memory_guard_pass": True,
            "configured_context_per_slot": effective["settings"]["context_per_slot"], "tested_prompt_tokens": 61,
            "checked_at": now_iso(), "scope": "One short completed-answer check (mock)", "issues": [],
        }
        run.emit("validation", validation=validation)
        step(run, "verify", "done", 0.9, "Answer correct: {\"remaining\":19,\"doubled\":38}")

        after = None
        if mode == "sequential_compare":
            base = entry["live"]
            after = measurement(model, "short", base["decode"], base["prefill"], 4036, 256, 1.85, 2.2,
                                run_id=run.run_id, profile_id=effective["profile_id"])
            run.emit("benchmark", label="tuned", measurement=after)

        step(run, "apply", "running", 0.93, "Keeping the verified service under backend supervision")
        pause(0.6)
        changes = compute_changes(prior or default_config(model), effective)
        evidence = evidence_for(model, fallback=used_fallback)
        run.emit("config", phase="effective", config=effective, changes=changes, evidence=evidence)
        step(run, "apply", "done", 1.0, "Tuned service is ready")

        rollback_id = f"rb_{uuid.uuid4().hex[:10]}"
        service = {"id": f"svc_{uuid.uuid4().hex[:8]}", "state": "running", "allocation_id": "mock-alloc-266901",
                   "expires_at": later_iso(3600)}
        with STATE.lock:
            STATE.rollbacks[rollback_id] = copy.deepcopy(current) if current else None
            STATE.current_config = effective
            STATE.is_tuned = True
            STATE.service_model = model
            STATE.service = service

        speedup = None
        comparison = {"available": False, "mode": mode, "baseline_run_id": None,
                      "reason": "verify_only mode does not run a baseline", "conditions_differ": []}
        if baseline and after:
            speedup = round(after["decode_tps"] / baseline["decode_tps"], 2)
            comparison = {"available": True, "mode": mode, "baseline_run_id": run.run_id, "reason": None,
                          "conditions_differ": ["engine", "chat template", "timing convention", "sampling"]}
        run.emit("done", status="success", mode=mode, applied=True, config=effective, evidence=evidence,
                 validation=validation, before=baseline, after=after, speedup=speedup, comparison=comparison,
                 reason=f"Applied {entry['profile']['label'] if not used_fallback else entry['fallback']['label']} "
                        f"for decode speed on L40.",
                 repairs=run.repairs, elapsed_seconds=round(time.time() - started, 2), service=service,
                 rollback_id=rollback_id, repro_command=None, repro_ref=f"mock-repro-{run.run_id}")
        if AUTO_INFERENCE:
            def later():
                time.sleep(float(AUTO_INFERENCE))
                fake_terminal_inference(model)
            threading.Thread(target=later, daemon=True).start()
    except Cancelled:
        run.emit("error", error={"code": "cancelled", "message": "Optimization was cancelled.", "diagnosable": False,
                                 "retryable": True}, cleanup=cleanup_obj("completed", restored=(prior or {}).get("profile_id"), elapsed=0.4),
                 last_verified_profile_id=(prior or {}).get("profile_id"))
    finally:
        finish_active(run)


def run_default(run: Run, body: dict) -> None:
    """apply_default: start and retain the untouched default Ollama service."""
    model = body["model"]
    started = time.time()
    current = copy.deepcopy(STATE.current_config) if STATE.current_config else None
    try:
        run.emit("start", operation=run.operation, mode="apply_default", started_at=run.started_at,
                 deadline_at=run.deadline_at)
        step(run, "detect_gpu", "running", 0.1, "Reading the Slurm allocation")
        pause(0.6)
        step(run, "detect_gpu", "done", 0.25, f"Found {len(GPUS)} × L40 · 48 GB on n03")
        step(run, "load_model", "running", 0.35, "Starting untouched Ollama with its defaults")
        pause(1.4)
        step(run, "load_model", "done", 0.8, "Default Ollama is serving the model")
        config = default_config(model)
        step(run, "apply", "running", 0.9, "Keeping the default service for your terminal")
        pause(0.4)
        step(run, "apply", "done", 1.0, "Default service is ready")
        rollback_id = f"rb_{uuid.uuid4().hex[:10]}"
        service = {"id": f"svc_{uuid.uuid4().hex[:8]}", "state": "running", "allocation_id": "mock-alloc-266901",
                   "expires_at": later_iso(3600)}
        with STATE.lock:
            STATE.rollbacks[rollback_id] = current
            STATE.current_config = config
            STATE.is_tuned = False
            STATE.service_model = model
            STATE.service = service
        run.emit("done", status="success", mode="apply_default", applied=True, config=config, evidence=None,
                 validation=None, before=None, after=None, speedup=None,
                 comparison={"available": False, "mode": "apply_default", "baseline_run_id": None,
                             "reason": "Default run makes no comparison", "conditions_differ": []},
                 reason="Untouched default Ollama is running.", repairs=[],
                 elapsed_seconds=round(time.time() - started, 2), service=service, rollback_id=rollback_id,
                 repro_command=None, repro_ref=None)
    except Cancelled:
        run.emit("error", error={"code": "cancelled", "message": "Default run was cancelled.", "diagnosable": False,
                                 "retryable": True}, cleanup=cleanup_obj("completed"), last_verified_profile_id=None)
    finally:
        finish_active(run)


def run_revert(run: Run, rollback_id: str) -> None:
    started = time.time()
    try:
        run.emit("start", operation=run.operation, mode="revert", started_at=run.started_at, deadline_at=run.deadline_at)
        step(run, "rollback", "running", 0.2, "Stopping the running service")
        pause(0.8)
        with STATE.lock:
            prior = STATE.rollbacks.pop(rollback_id, None)
            model = STATE.service_model
        step(run, "rollback", "running", 0.6, "Restoring the previous configuration")
        pause(0.7)
        restored = prior or (default_config(model) if model else None)
        with STATE.lock:
            STATE.current_config = restored
            STATE.is_tuned = False
            STATE.service_model = None
            STATE.service = None
        step(run, "rollback", "done", 1.0, "Defaults restored")
        run.emit("done", status="success", restored=True, config=restored, service=None,
                 validation={"status": "passed", "completed_answer": None, "answer_correct": None,
                             "service_healthy": True, "placement_matches": None, "context_matches": None,
                             "memory_guard_pass": None, "configured_context_per_slot": None,
                             "tested_prompt_tokens": None, "checked_at": now_iso(),
                             "scope": "Restoration to the previous owned configuration (mock)", "issues": []},
                 elapsed_seconds=round(time.time() - started, 2))
    except Cancelled:
        run.emit("error", error={"code": "cancelled", "message": "Revert was cancelled.", "diagnosable": False,
                                 "retryable": True}, cleanup=cleanup_obj("completed"), last_verified_profile_id=None)
    finally:
        finish_active(run)


def run_benchmark(run: Run, params: dict) -> None:
    model = params["model"]
    try:
        run.emit("start", operation=run.operation, mode="run_benchmark", started_at=run.started_at,
                 deadline_at=run.deadline_at)
        step(run, "test_configs", "running", 0.3, "Running a capped throughput probe")
        pause(1.5)
        base = CATALOG[model]["live"]
        m = measurement(model, params.get("workload", "short"), base["decode"], base["prefill"], 4036,
                        params.get("max_tokens", 256), 1.85, 2.2, purpose=params.get("purpose", "throughput"),
                        run_id=run.run_id)
        run.emit("benchmark", label="tuned", measurement=m)
        step(run, "test_configs", "done", 1.0, "Probe complete")
        run.emit("done", status="success", measurements=[m], validation=None, applied=False, service=STATE.service,
                 cleanup=cleanup_obj(), elapsed_seconds=1.5)
    except Cancelled:
        run.emit("error", error={"code": "cancelled", "message": "Benchmark was cancelled.", "diagnosable": False,
                                 "retryable": True}, cleanup=cleanup_obj("completed"), last_verified_profile_id=None)
    finally:
        finish_active(run)


# --------------------------------------------------------------------------
# HTTP layer
# --------------------------------------------------------------------------

OPTIMIZE_FIELDS = {"model", "preset", "objective", "workload", "mode", "resources", "constraints", "profile_id",
                   "overrides", "budget", "baseline_run_id", "capabilities_revision"}
RESOURCE_FIELDS = {"target_id", "allocation_id", "gpu_type", "gpu_count", "gpu_ids", "same_node",
                   "replica_gpu_groups", "cpus_per_task", "host_memory_mib", "wall_time_seconds", "account",
                   "partition", "qos", "power_limit_w"}
CONSTRAINT_FIELDS = {"min_context_tokens", "quant", "allow_quant_change", "allow_sampling_change",
                     "allow_experimental", "fixed_settings", "min_free_gpu_memory_mib", "max_gpu_count",
                     "runtime_requirements", "allow_cpu_offload"}
ACTIONS = {"apply_config", "revert", "lower_context", "switch_quantization", "run_benchmark", "apply_default"}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, field: str | None = None, details: dict | None = None,
                 diagnosable: bool = False, retryable: bool = False, extra: dict | None = None):
        super().__init__(message)
        self.status = status
        self.body = {"error": {"code": code, "message": message, "diagnosable": diagnosable, "retryable": retryable}}
        if field:
            self.body["error"]["field"] = field
        if details:
            self.body["error"]["details"] = details
        if extra:
            self.body.update(extra)


def reject_unknown(obj: dict, allowed: set, prefix: str = "") -> None:
    if not isinstance(obj, dict):
        raise ApiError(400, "bad_request", f"{prefix or 'body'} must be an object", field=prefix or None)
    for key in obj:
        if key not in allowed:
            path = f"{prefix}.{key}" if prefix else key
            raise ApiError(400, "bad_request", f"Unknown field '{path}'.", field=path)


def model_payload(model_id: str) -> dict:
    entry = CATALOG[model_id]
    alloc = allocation()
    need = entry["requirements"]["gpu_count"]
    reasons = []
    if alloc is None:
        reasons.append(f"No active GPU allocation; optimizing will request {need} × L40")
    elif len(alloc["gpu_ids"]) < need:
        reasons.append(f"Needs {need} × L40 on one node")
    loaded = STATE.service_model == model_id
    return {
        "id": model_id, "display_name": entry["display_name"], "quant": entry["quant"],
        "artifact_id": f"mock-{model_id}-target", "installed": True, "loaded": loaded,
        "database_coverage": "verified", "requirements": entry["requirements"], "ready": not reasons,
        "readiness_reasons": reasons,
        "race": {
            "simultaneous_available": False, "sequential_available": alloc is not None,
            "required_gpus_simultaneous": entry["race_gpus"],
            "reasons": [f"Simultaneous race needs {entry['race_gpus']} × L40"],
        },
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "NOVAMock/2.1"

    # -- plumbing ----------------------------------------------------------
    def log_message(self, fmt, *args):  # quieter than the default
        if os.environ.get("MOCK_QUIET") != "1":
            super().log_message(fmt, *args)

    def cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Pairing-Token, Idempotency-Key")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def send_json(self, status: int, body) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def start_sse(self) -> None:
        self.send_response(200)
        self.cors()
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

    def sse(self, event: dict) -> None:
        self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
        self.wfile.flush()

    def sse_comment(self, text: str) -> None:
        self.wfile.write(f": {text}\n\n".encode())
        self.wfile.flush()

    def read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            raise ApiError(400, "bad_request", "Body is not valid JSON.")
        if not isinstance(body, dict):
            raise ApiError(400, "bad_request", "Body must be a JSON object.")
        return body

    def require_auth(self) -> None:
        if self.headers.get("X-Pairing-Token") != PAIRING_CODE:
            raise ApiError(401, "unauthorized", "Missing or wrong pairing code.")

    def idempotency_key(self) -> str:
        key = self.headers.get("Idempotency-Key")
        if not key:
            raise ApiError(400, "bad_request", "Idempotency-Key header is required for this request.",
                           field="Idempotency-Key")
        return key

    def stream_run(self, run: Run) -> None:
        """Relay a run's events. A dropped client does not affect the run."""
        self.start_sse()
        index = 0
        try:
            while True:
                with run.cond:
                    while index >= len(run.events) and not run.terminal:
                        if not run.cond.wait(timeout=10):
                            break
                    pending = run.events[index:]
                    finished = run.terminal
                if not pending and not finished:
                    self.sse_comment("heartbeat")
                    continue
                for event in pending:
                    self.sse(event)
                index += len(pending)
                if finished and index >= len(run.events):
                    return
        except (BrokenPipeError, ConnectionResetError):
            return

    def launch(self, key: str, body: dict, operation: str, mode: str, target, *args) -> None:
        digest = hashlib.sha256(json.dumps({"path": self.path, "body": body}, sort_keys=True).encode()).hexdigest()
        with STATE.lock:
            if key in STATE.idempotency:
                known_digest, run_id = STATE.idempotency[key]
                if known_digest != digest:
                    raise ApiError(409, "idempotency_conflict", "This Idempotency-Key was used with a different body.")
                run = STATE.runs[run_id]
                snap = run.snapshot()
                self.send_json(200, {"run_id": run_id, "state": run.state, "replayed": True,
                                     "result": snap["result"], "error": snap["error"]})
                return
            if STATE.active_run_id and not STATE.runs[STATE.active_run_id].terminal:
                raise ApiError(409, "operation_in_progress", "Another operation is still running.",
                               extra={"active_run_id": STATE.active_run_id})
            run = Run(operation, mode, deadline=180)
            STATE.runs[run.run_id] = run
            STATE.idempotency[key] = (digest, run.run_id)
            STATE.active_run_id = run.run_id
        threading.Thread(target=target, args=(run, *args), daemon=True).start()
        self.stream_run(run)

    # -- verbs -------------------------------------------------------------
    def do_OPTIONS(self):
        self.send_response(204)
        self.cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")

    def dispatch(self, method: str) -> None:
        url = urlparse(self.path)
        path = url.path.rstrip("/") or "/"
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if method == "GET" and path == "/health":
                return self.send_json(200, {"ok": True, "contract_version": CONTRACT_VERSION})
            self.require_auth()
            if method == "GET":
                if path == "/status":
                    return self.get_status()
                if path == "/capabilities":
                    return self.get_capabilities(query)
                if path == "/profiles":
                    return self.get_profiles(query)
                if path == "/live":
                    return self.get_live(query)
                if path.startswith("/runs/"):
                    return self.get_run(path.split("/")[2])
            else:
                if path == "/optimize":
                    return self.post_optimize()
                if path == "/revert":
                    return self.post_revert()
                if path == "/action":
                    return self.post_action()
                if path == "/chat":
                    return self.post_chat()
                if path == "/diagnose":
                    return self.post_diagnose()
                if path == "/mock/inference":
                    return self.post_mock_inference()
                if path.startswith("/runs/") and path.endswith("/cancel"):
                    return self.post_cancel(path.split("/")[2])
            raise ApiError(404, "not_found", f"No route for {method} {path}.")
        except ApiError as err:
            self.send_json(err.status, err.body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    # -- GET handlers --------------------------------------------------------
    def get_status(self) -> None:
        alloc = allocation()
        with STATE.lock:
            body = {
                "contract_version": CONTRACT_VERSION, "observed_at": now_iso(), "target_id": "wright",
                "connection": "connected", "allocation": alloc, "all_gpus": GPUS if alloc else [],
                "models": [model_payload(m) for m in CATALOG], "current_config": STATE.current_config,
                "active_run_id": STATE.active_run_id, "is_tuned": STATE.is_tuned,
                "contribute_results": False,
                "optimizer_agent": {"model": "openai/gpt-6-astra", "reasoning_effort": "high",
                                    "requested_service_tier": "priority", "effective_service_tier": None,
                                    "available": True},
            }
        self.send_json(200, body)

    def get_capabilities(self, query: dict) -> None:
        model = query.get("model")
        if model not in CATALOG:
            raise ApiError(404, "model_not_found", f"Unknown model '{model}'.", field="model")
        if query.get("target_id") != "wright":
            raise ApiError(400, "bad_request", "target_id is required (try 'wright').", field="target_id")
        cap = 15 if model == "muse-glimmer" else 9
        field = lambda schema, group, mapping, **kw: {  # noqa: E731
            "schema": schema, "support": "supported", "access": kw.get("access", "writable"),
            "apply": kw.get("apply", "restart"), "evidence": "tested", "reason": kw.get("reason"),
            "ui_group": group, "advanced": kw.get("advanced", True), "runtime_mapping": mapping}
        self.send_json(200, {
            "contract_version": CONTRACT_VERSION, "capabilities_revision": "mock-rev-1", "model": model,
            "target_id": "wright", "runtime_id": query.get("runtime_id"),
            "fields": {
                "settings.draft_tokens": field({"type": "integer", "minimum": 0, "maximum": cap}, "speculation",
                                               "--spec-draft-n-max"),
                "settings.temperature": field({"type": "number", "minimum": 0}, "sampling", "--temp", apply="request",
                                              advanced=False),
                "settings.threads_decode": field({"type": "integer", "minimum": 1, "maximum": 12}, "cpu", "--threads"),
                "settings.threads_prefill": field({"type": "integer", "minimum": 1, "maximum": 12}, "cpu",
                                                  "--threads-batch"),
                "settings.context_per_slot": field({"type": "integer", "minimum": 4096}, "context", "--ctx-size",
                                                   advanced=False),
                "resources.power_limit_w": field({"type": "number"}, "resources", "nvidia-smi power.limit readback",
                                                 access="read_only", apply="observe_only",
                                                 reason="Managed by Wright; observe only"),
            },
            "constraints": [{"code": "microbatch_le_batch", "paths": ["settings.microbatch_size", "settings.batch_size"],
                             "message": "Microbatch must not exceed batch."}],
            "artifacts": [{"id": f"mock-{model}-target", "model": model, "kind": "target", "quant": CATALOG[model]["quant"],
                           "installed": True, "files": []}],
            "runtimes": [{"runtime_id": CATALOG[model]["profile"]["runtime_id"], "installed": True, "reasons": []}],
            "resource_options": {"gpu_types": ["L40"], "max_gpu_count": 3, "cpus_per_task": [12],
                                 "accounts": ["cmist"], "partitions": ["cmist"], "qos": ["cmist_priority"]},
        })

    def get_profiles(self, query: dict) -> None:
        model = query.get("model")
        if model not in CATALOG:
            raise ApiError(404, "model_not_found", f"Unknown model '{model}'.", field="model")
        entry = CATALOG[model]
        profiles = [{"profile_id": tuned_config(model)["profile_id"], "label": entry["profile"]["label"],
                     "config": tuned_config(model), "resource_requirements": entry["requirements"],
                     "evidence": evidence_for(model), "compatibility": "compatible", "reasons": []}]
        if entry["fallback"]:
            profiles.append({"profile_id": tuned_config(model, True)["profile_id"], "label": entry["fallback"]["label"],
                             "config": tuned_config(model, True), "resource_requirements": entry["requirements"],
                             "evidence": evidence_for(model, True), "compatibility": "compatible", "reasons": []})
        self.send_json(200, {"profiles": profiles})

    def get_run(self, run_id: str) -> None:
        run = STATE.runs.get(run_id)
        if not run:
            raise ApiError(404, "not_found", f"Unknown run '{run_id}'.")
        self.send_json(200, run.snapshot())

    def get_live(self, query: dict) -> None:
        model = query.get("model")
        if model not in CATALOG:
            raise ApiError(404, "model_not_found", f"Unknown model '{model}'.", field="model")
        with STATE.lock:
            if STATE.service_model != model:
                raise ApiError(404, "not_found", "No service is running for this model.")
            q: queue.Queue = queue.Queue()
            STATE.live_subscribers.setdefault(model, []).append(q)
            service_id = STATE.service["id"] if STATE.service else None
        sequence = 0

        def send(event: dict) -> None:
            nonlocal sequence
            sequence += 1
            self.sse({**event, "sequence": sequence})

        try:
            self.start_sse()
            send({"type": "waiting", "at": now_iso(), "model": model, "service_id": service_id})
            while True:
                try:
                    event = q.get(timeout=10)
                except queue.Empty:
                    with STATE.lock:
                        still_tuned = STATE.service_model == model
                    if not still_tuned:
                        send({"type": "error", "at": now_iso(), "error": {
                            "code": "not_found", "message": "The service was stopped.",
                            "diagnosable": False, "retryable": False}})
                        return
                    self.sse_comment("heartbeat")
                    continue
                send(event)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            with STATE.lock:
                subs = STATE.live_subscribers.get(model, [])
                if q in subs:
                    subs.remove(q)

    # -- POST handlers -------------------------------------------------------
    def post_optimize(self) -> None:
        key = self.idempotency_key()
        body = self.read_body()
        reject_unknown(body, OPTIMIZE_FIELDS)
        if "resources" in body:
            reject_unknown(body["resources"], RESOURCE_FIELDS, "resources")
        if "constraints" in body:
            reject_unknown(body["constraints"], CONSTRAINT_FIELDS, "constraints")
        model = body.get("model")
        if model not in CATALOG:
            raise ApiError(404, "model_not_found", f"Unknown model '{model}'.", field="model")
        mode = body.get("mode", "verify_only")
        if mode not in ("verify_only", "sequential_compare"):
            raise ApiError(400, "bad_request", "mode must be verify_only or sequential_compare.", field="mode")
        if body.get("objective", "decode") != "decode":
            raise ApiError(422, "unsupported_setting", "Only the decode objective is supported.", field="objective")
        resources = body.get("resources") or {}
        need = CATALOG[model]["requirements"]["gpu_count"]
        if resources.get("gpu_count") is not None and resources["gpu_count"] < need:
            raise ApiError(409, "allocation_unavailable", f"This profile needs {need} × L40 on one node.",
                           field="resources.gpu_count", details={"required": need})
        self.launch(key, body, "optimize", mode, run_optimize, body)

    def post_revert(self) -> None:
        key = self.idempotency_key()
        body = self.read_body()
        reject_unknown(body, {"rollback_id"})
        rollback_id = body.get("rollback_id")
        with STATE.lock:
            known = rollback_id in STATE.rollbacks
        if not known:
            raise ApiError(404, "not_found", "Unknown or already used rollback_id.", field="rollback_id")
        self.launch(key, body, "revert", "revert", run_revert, rollback_id)

    def post_action(self) -> None:
        key = self.idempotency_key()
        body = self.read_body()
        reject_unknown(body, {"action", "params", "budget"})
        action = body.get("action")
        params = body.get("params") or {}
        if action not in ACTIONS:
            raise ApiError(400, "bad_request", f"Unknown action '{action}'.", field="action")
        if action == "revert":
            if params.get("rollback_id") not in STATE.rollbacks:
                raise ApiError(404, "not_found", "Unknown or already used rollback_id.", field="params.rollback_id")
            return self.launch(key, body, "action", action, run_revert, params["rollback_id"])
        if params.get("model") not in CATALOG:
            raise ApiError(404, "model_not_found", "params.model must be a catalog model.", field="params.model")
        if action == "run_benchmark":
            return self.launch(key, body, "action", action, run_benchmark, params)
        if action == "apply_default":
            reject_unknown(params, {"model", "resources"}, "params")
            return self.launch(key, body, "action", action, run_default, params)
        return self.launch(key, body, "action", "verify_only", run_optimize,
                           {"model": params["model"], "mode": "verify_only"})

    def post_cancel(self, run_id: str) -> None:
        run = STATE.runs.get(run_id)
        if not run:
            raise ApiError(404, "not_found", f"Unknown run '{run_id}'.")
        if run.terminal:
            return self.send_json(200, {"run_id": run_id, "state": run.state})
        run.cancel_requested = True
        with run.cond:
            run.state = "cancelling"
        self.send_json(202, {"run_id": run_id, "state": "cancelling"})

    def post_chat(self) -> None:
        body = self.read_body()
        reject_unknown(body, {"message", "history", "model", "run_id"})
        if not isinstance(body.get("message"), str) or not body["message"].strip():
            raise ApiError(400, "bad_request", "message is required.", field="message")
        self.start_sse()
        reply = ("Your default setup ran Ollama with 128 threads inside a 12-CPU allocation. "
                 "The tuned profile uses llama.cpp with speculative decoding, so the GPU accepts "
                 "several drafted tokens per pass. (Mock reply.)")
        try:
            for word in reply.split(" "):
                self.sse({"type": "delta", "text": word + " "})
                time.sleep(0.03 * SPEED)
            self.sse({"type": "done", "suggested_questions": ["Is quality affected?", "What is MTP?"],
                      "suggested_actions": []})
        except (BrokenPipeError, ConnectionResetError):
            pass

    def post_diagnose(self) -> None:
        body = self.read_body()
        reject_unknown(body, {"model", "run_id", "error_code", "log_tail"})
        self.send_json(200, {
            "explanation": "The draft model's KV cache pushed free memory below the 768 MiB guard. (Mock.)",
            "can_auto_repair": True,
            "suggested_action": {"action": "apply_config", "label": "Use the production fallback profile",
                                 "params": {"model": body.get("model"), "profile_id": "mock-fallback"},
                                 "constraint_changes": []},
        })

    def post_mock_inference(self) -> None:
        body = self.read_body()
        model = body.get("model") or STATE.service_model
        if model not in CATALOG:
            raise ApiError(404, "model_not_found", "Pass a catalog model.", field="model")
        if STATE.service_model != model:
            raise ApiError(404, "not_found", "Start a default run or optimize this model first.")
        request_id = fake_terminal_inference(model)
        self.send_json(202, {"ok": True, "request_id": request_id})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True
    print(f"NOVA mock backend (contract {CONTRACT_VERSION}) on http://{args.host}:{args.port}")
    print(f"Pairing code: {PAIRING_CODE}   scenario={SCENARIO} allocation={ALLOCATION_MODE}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
