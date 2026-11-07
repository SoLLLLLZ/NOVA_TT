#!/usr/bin/env python3
"""Private file-RPC worker, run ONLY under srun in our owned Slurm job.
No network listener except owned model servers on loopback. No credentials.
"""

import concurrent.futures, hashlib, json, math, os, re, pathlib, signal, socket, subprocess, sys, threading, time, urllib.request
from datetime import datetime, timezone

ROOT = pathlib.Path(sys.argv[1]).resolve()
MANIFEST = json.loads((ROOT / "manifest.json").read_text())
ASSETS = pathlib.Path(MANIFEST["asset_root"])
MODEL = ASSETS / MANIFEST["artifact"]["files"][0]["name"]
SERVICES = {}
EXIT = threading.Event()
VIOLATIONS = []
GPUS = []
CPU_GROUPS = []
ACTIVE_DEADLINE = 0
EVENT_PATH = None
EVENT_LOCK = threading.Lock()


def save(path, obj):
    if path.name in ("ready.json", "startup-error.json", "stopped.json"):
        path.write_text(json.dumps(obj, allow_nan=False))
        return
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, allow_nan=False))
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def command(argv, timeout=20, env=None):
    return subprocess.check_output(
        list(map(str, argv)),
        text=True,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        env=env,
    ).strip()


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def query(gpu, fields):
    return command(
        [
            "nvidia-smi",
            "-i",
            gpu,
            "--query-gpu=" + fields,
            "--format=csv,noheader,nounits",
        ]
    )


def processes(gpu):
    return command(
        [
            "nvidia-smi",
            "-i",
            gpu,
            "--query-compute-apps=pid,process_name,used_gpu_memory",
            "--format=csv,noheader,nounits",
        ]
    )


def is_cancelled():
    try:
        return (ROOT / "cancel").read_text().strip() == "cancel"
    except OSError:
        VIOLATIONS.append("control_channel_unavailable")
        return True


def admit_command(body):
    if body.get("reset_cancel"):
        (ROOT / "cancel").write_text("")
        VIOLATIONS.clear()
    elif is_cancelled() and body["op"] not in ("stop", "shutdown", "inspect"):
        raise RuntimeError("cancelled")
    elif body.get("reset_guard"):
        VIOLATIONS.clear()


def check():
    if EXIT.is_set() or is_cancelled():
        raise RuntimeError("cancelled")
    if VIOLATIONS:
        raise RuntimeError("memory_or_thermal_guard")
    if ACTIVE_DEADLINE and time.time() > ACTIVE_DEADLINE:
        raise RuntimeError("deadline_exceeded")


def req(port, path, body=None, timeout=90):
    check()
    timeout = (
        min(timeout, max(1, ACTIVE_DEADLINE - time.time()))
        if ACTIVE_DEADLINE
        else timeout
    )
    request = urllib.request.Request(
        "http://127.0.0.1:" + str(port) + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as f:
        result = json.load(f)
    check()
    return result


def stop(lane):
    entry = SERVICES.pop(lane, None)
    if not entry:
        return
    p = entry["process"]
    if p.poll() is None:
        try:
            os.killpg(p.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            p.wait(timeout=8)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            p.wait(timeout=5)
    entry["log"].close()
    for _ in range(12):
        if not processes(GPUS[entry["gpu_index"]]):
            break
        time.sleep(0.3)
    else:
        raise RuntimeError("owned_service_cleanup_incomplete")


def telemetry():
    out = []
    for i, g in enumerate(GPUS):
        v = [
            x.strip()
            for x in query(
                g, "uuid,name,memory.total,memory.free,temperature.gpu,power.limit"
            ).split(",")
        ]
        out.append(
            {
                "id": v[0],
                "node_id": socket.gethostname(),
                "local_index": i,
                "label": f"L40 {i + 1}",
                "name": v[1],
                "memory_total_mib": float(v[2]),
                "memory_free_mib": float(v[3]),
                "temperature_c": float(v[4]),
                "power_limit_w": float(v[5]),
                "busy": bool(processes(g)),
            }
        )
    return out


def inspect():
    return {
        "job_id": os.environ["SLURM_JOB_ID"],
        "node_id": socket.gethostname(),
        "gpus": telemetry(),
        "services": {
            k: {
                "config": s["config"],
                "healthy": s["process"].poll() is None,
                "gpu_id": GPUS[s["gpu_index"]],
                "context_per_slot": s.get("context"),
            }
            for k, s in SERVICES.items()
        },
        "artifact_verified": True,
        "runtime_hashes": RUNTIME_HASHES,
        "cpu_groups": CPU_GROUPS,
    }


def guard():
    while not EXIT.wait(1):
        try:
            samples = telemetry()
            for s in list(SERVICES.values()):
                g = samples[s["gpu_index"]]
                s["min_free"] = min(
                    s.get("min_free", g["memory_free_mib"]), g["memory_free_mib"]
                )
                s["max_temp"] = max(
                    s.get("max_temp", g["temperature_c"]), g["temperature_c"]
                )
                if (
                    g["memory_free_mib"] < s.get("headroom", 1024)
                    or g["temperature_c"] >= 80
                ):
                    VIOLATIONS.append("memory_or_thermal_guard")
        except Exception:
            VIOLATIONS.append("telemetry_unavailable")
        abort = (
            is_cancelled()
            or (ACTIVE_DEADLINE and time.time() > ACTIVE_DEADLINE)
            or VIOLATIONS
        )
        if abort:
            for s in list(SERVICES.values()):
                if s["process"].poll() is not None:
                    continue
                try:
                    os.killpg(s["process"].pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass


def load(body):
    lane = body.get("lane", "tuned")
    gi = body.get("gpu_index", 0)
    c = body["config"]
    settings = c["settings"]
    if gi not in range(len(GPUS)):
        raise RuntimeError("allocation_unavailable")
    stop(lane)
    check()
    if any(s["gpu_index"] == gi for s in SERVICES.values()) or processes(GPUS[gi]):
        raise RuntimeError("gpu_busy")
    if float(query(GPUS[gi], "memory.free")) < 40000:
        raise RuntimeError("insufficient_startup_headroom")
    if c["artifact_id"] != MANIFEST["artifact"]["id"] or c["model"] != "qwen3.8-27b":
        raise RuntimeError("unsupported_artifact")
    ollama = c["engine"] == "ollama"
    if c["runtime_id"] != ("ollama-0.40.13" if ollama else "llama-l40-b10820"):
        raise RuntimeError("unsupported_runtime")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("OLLAMA_", "LLAMA_", "GGML_", "APPTAINERENV_"))
        and k != "LD_LIBRARY_PATH"
    }
    for key in ("GPU_DEVICE_ORDINAL", "ROCR_VISIBLE_DEVICES", "HIP_VISIBLE_DEVICES"):
        env.pop(key, None)
    env["CUDA_VISIBLE_DEVICES"] = GPUS[gi]
    if ollama:
        store = ROOT / "ollama-models"
        (store / "blobs").mkdir(parents=True, exist_ok=True)
        blob = (
            store / "blobs" / ("sha256-" + MANIFEST["artifact"]["files"][0]["sha256"])
        )
        if not blob.exists():
            os.link(MODEL, blob)
        env.update(
            OLLAMA_HOST="127.0.0.1:" + str(port),
            OLLAMA_MODELS=str(store),
            OLLAMA_VULKAN="0",
            OLLAMA_NOPRUNE="1",
        )
        argv = [str(ASSETS / "ollama-0.40.13/bin/ollama"), "serve"]
    else:
        argv = [str(ASSETS / "build-l40/bin/llama-server")] + MANIFEST[
            "llama_argv"
        ].copy()
        mapping = {
            "context_tokens": "--ctx-size",
            "draft_tokens": "--spec-draft-n-max",
            "threads_decode": "--threads",
            "threads_prefill": "--threads-batch",
            "batch_size": "--batch-size",
            "microbatch_size": "--ubatch-size",
            "temperature": "--temp",
            "top_p": "--top-p",
            "top_k": "--top-k",
            "min_p": "--min-p",
        }
        for flag, value in [
            ("--model", str(MODEL)),
            ("--port", str(port)),
            ("--alias", "nova-byteshape"),
        ] + [(flag, settings[key]) for key, flag in mapping.items()]:
            argv[argv.index(flag) + 1] = str(value)
        container = [
            "apptainer",
            "exec",
            "--cleanenv",
            "--nv",
            "--bind",
            "/home/export/taeholee/nova:/home/export/taeholee/nova",
            "--env",
            "CUDA_VISIBLE_DEVICES=" + GPUS[gi],
            "--env",
            "LD_LIBRARY_PATH=" + str(ASSETS / "build-l40/bin"),
            str(ASSETS / "cuda-12.9.1-devel-ubuntu24.04.sif"),
        ]
        devices = command(container + [argv[0], "--list-devices"], env=env)
        if devices.count("CUDA0:") != 1 or "CUDA1:" in devices:
            raise RuntimeError("device_mapping_failed")
        argv = container + argv
    argv = ["taskset", "-c", ",".join(map(str, CPU_GROUPS[gi]))] + argv
    log_path = ROOT / (lane + "-server.log")
    log_offset = log_path.stat().st_size if log_path.exists() else 0
    log = log_path.open("a")
    start = time.monotonic()
    p = subprocess.Popen(
        argv, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
    )
    SERVICES[lane] = {
        "process": p,
        "log": log,
        "port": port,
        "config": c,
        "gpu_index": gi,
        "headroom": body.get("headroom", 1024),
        "log_offset": log_offset,
        "log_path": log_path,
    }
    save(
        ROOT / (lane + "-launch.json"),
        {
            "argv": argv,
            "config": c,
            "gpu_uuid": GPUS[gi],
            "cpu_affinity": CPU_GROUPS[gi],
            "runtime_hashes": RUNTIME_HASHES,
        },
    )
    while True:
        check()
        if p.poll() is not None:
            raise RuntimeError("model_server_exited")
        try:
            ready = req(port, "/api/version" if ollama else "/health", timeout=2)
            break
        except (OSError, ValueError):
            time.sleep(0.4)
    if ollama:
        if ready.get("version") != "0.40.13":
            raise RuntimeError("runtime_version_mismatch")
        # The verified GGUF is already a local blob. Avoid CLI re-hashing/uploading 11 GB.
        created = req(
            port,
            "/api/create",
            {
                "model": "nova-byteshape",
                "files": {
                    MODEL.name: "sha256:" + MANIFEST["artifact"]["files"][0]["sha256"]
                },
                "stream": False,
            },
            timeout=60,
        )
        if created.get("status") != "success":
            raise RuntimeError("ollama_model_registration_failed")
        save(
            ROOT / "ollama-model-show.json",
            req(port, "/api/show", {"model": "nova-byteshape"}),
        )
        # Load without a prompt or inference overrides, so both race lanes are ready.
        preload_start = time.monotonic()
        loaded = req(
            port,
            "/api/generate",
            {"model": "nova-byteshape", "stream": False},
            timeout=90,
        )
        if not loaded.get("done"):
            raise RuntimeError("ollama_preload_failed")
        SERVICES[lane]["model_load_seconds"], SERVICES[lane]["load_timing_source"] = (
            preload_duration(loaded, time.monotonic() - preload_start)
        )
        models = req(port, "/api/ps").get("models", [])
        if (
            len(models) != 1
            or models[0].get("context_length") != settings["context_per_slot"]
        ):
            raise RuntimeError("context_mismatch")
        SERVICES[lane]["context"] = models[0]["context_length"]
        save(ROOT / (lane + "-preload.json"), {"response": loaded, "models": models})
    else:
        slots = req(port, "/slots")
        props = req(port, "/props")
        if len(slots) != 1 or slots[0]["n_ctx"] != settings["context_per_slot"]:
            raise RuntimeError("context_mismatch")
        SERVICES[lane]["context"] = slots[0]["n_ctx"]
        save(ROOT / (lane + "-props.json"), props)
    SERVICES[lane]["load_seconds"] = time.monotonic() - start
    return {
        "load_seconds": SERVICES[lane]["load_seconds"],
        "context_per_slot": SERVICES[lane]["context"],
        "gpu_id": GPUS[gi],
        "runtime_hashes": RUNTIME_HASHES,
    }


def final_text(text):
    if "</think>" in text:
        return text.rsplit("</think>", 1)[1].strip()
    if "<think>" in text:
        return ""
    return text.strip()


def live_metrics(item):
    """Native phase counters only; no text/chunk counts or transport wall time."""
    t = item.get("timings") or {}
    n, elapsed = t.get("predicted_n"), t.get("predicted_ms")
    if type(n) is not int or n < 1 or type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed <= 0:
        return None
    pn, pt = t.get("prompt_n"), t.get("prompt_ms")
    prefill = (pn * 1000 / pt if type(pn) is int and pn >= 0 and
               type(pt) in (int, float) and math.isfinite(pt) and pt > 0 else None)
    decode = max(0, n - 1) * 1000 / elapsed
    if not math.isfinite(decode) or (prefill is not None and not math.isfinite(prefill)):
        return None
    return {"kind": "metrics", "decode_tps": decode, "prefill_tps": prefill,
            "output_tokens": n, "timing_convention": "(predicted_n - 1) / predicted_ms"}


def worker_event(event):
    if EVENT_PATH:
        with EVENT_LOCK:
            with EVENT_PATH.open("a") as f:
                f.write(json.dumps(event, allow_nan=False) + "\n")


def stream_request(port, path, request, lane, ollama, live=False):
    request["stream"] = True
    if live and not ollama:
        request["timings_per_token"] = True
    wire = urllib.request.Request(
        "http://127.0.0.1:" + str(port) + path,
        data=json.dumps(request).encode(),
        headers={"Content-Type": "application/json"},
    )
    text = ""
    visible_sent = 0
    last = {}
    separate_thinking = False
    last_metric_at = 0
    with urllib.request.urlopen(
        wire, timeout=max(1, ACTIVE_DEADLINE - time.time())
    ) as response:
        if live:
            worker_event({"kind": "inference_started", "prompt_tokens": None})
        for line in response:
            check()
            line = line.decode().strip()
            if not line:
                continue
            if line.startswith("data: "):
                line = line[6:]
            if line == "[DONE]":
                break
            item = json.loads(line)
            last = item
            if live:
                metric = live_metrics(item)
                if metric and time.monotonic() - last_metric_at >= 0.05:
                    worker_event(metric)
                    last_metric_at = time.monotonic()
            text += item.get("response" if ollama else "content", "")
            separate_thinking = separate_thinking or bool(item.get("thinking"))
            # Thinking is always enabled. Native completion may start inside a think block.
            visible = (
                text
                if ollama and separate_thinking
                else text.split("</think>", 1)[1]
                if "</think>" in text
                else ""
            )
            delta = visible[visible_sent:]
            visible_sent = len(visible)
            if delta and EVENT_PATH:
                with EVENT_LOCK:
                    with EVENT_PATH.open("a") as f:
                        f.write(
                            json.dumps(
                                {
                                    "lane": lane,
                                    "text": delta,
                                    "tokens": None,
                                    "tps": None,
                                }
                            )
                            + "\n"
                        )
            if item.get("done") or item.get("stop"):
                break
    last["response" if ollama else "content"] = text
    return last


def preload_duration(response, elapsed):
    duration = response.get("load_duration")
    if type(duration) in (int, float) and duration >= 0:
        return duration / 1e9, "native_load_duration"
    return elapsed, "preload_wall"


def sampler_matches(observed, wanted, integer=False):
    if integer:
        return type(observed) is int and observed == wanted
    return type(observed) in (int, float) and math.isclose(
        observed, wanted, rel_tol=1e-6, abs_tol=1e-7
    )


def generate(body):
    lane = body.get("lane", "tuned")
    s = SERVICES[lane]
    port = s["port"]
    c = s["config"]
    ollama = c["engine"] == "ollama"
    text = body["prompt"]
    cap = body["max_tokens"]
    quality = body.get("purpose") == "quality"
    if ollama:
        request = {
            "model": "nova-byteshape",
            "prompt": text,
            "stream": False,
            "options": {"num_predict": cap},
        }
        path = "/api/generate"
    else:
        formatted = req(
            port,
            "/apply-template",
            {
                "messages": [{"role": "user", "content": text}],
                "add_generation_prompt": True,
                "chat_template_kwargs": c["settings"]["chat_template_kwargs"],
            },
        )
        request = {
            "prompt": formatted["prompt"],
            "stream": False,
            "n_predict": cap,
            "cache_prompt": False,
            "ignore_eos": body.get("fixed_length", False) and not quality,
            "seed": body.get("seed", 71430),
            "temperature": c["settings"]["temperature"],
            "top_p": c["settings"]["top_p"],
            "top_k": c["settings"]["top_k"],
            "min_p": c["settings"]["min_p"],
            "repeat_penalty": 1.0,
            "presence_penalty": 0.0,
        }
        path = "/completion"
    request_start = time.time()
    start = time.monotonic()
    r = (
        stream_request(port, path, request, lane, ollama, live=body.get("live", False))
        if body.get("stream")
        else req(port, path, request)
    )
    wall = time.monotonic() - start
    request_end = time.time()
    save(
        ROOT / (body["measurement_id"] + "-raw.json"),
        {"request": request, "response": r, "config": c},
    )
    if ollama:
        n = r.get("prompt_eval_count")
        o = r.get("eval_count")
        pt = r.get("prompt_eval_duration", 0) / 1e9
        dt = r.get("eval_duration", 0) / 1e9
        dn = o
        cache = r.get("prompt_eval_cached_count")
        completed = r.get("done_reason") == "stop"
        stop_reason = r.get("done_reason")
        content = r.get("response", "")
        convention = "eval_count / eval_duration"
        ps = req(port, "/api/ps")
        save(ROOT / (lane + "-loaded.json"), ps)
        models = ps.get("models", [])
        if len(models) != 1:
            raise RuntimeError("placement_unverified")
        s["context"] = models[0].get("context_length")
    else:
        t = r.get("timings", {})
        n = t.get("prompt_n")
        o = t.get("predicted_n")
        pt = t.get("prompt_ms", 0) / 1000
        dt = t.get("predicted_ms", 0) / 1000
        dn = max(0, o - 1) if o is not None else None
        cache = t.get("cache_n")
        completed = r.get("stop_type") == "eos"
        stop_reason = r.get("stop_type")
        content = final_text(r.get("content", ""))
        convention = "(predicted_n - 1) / predicted_ms"
        actual = r.get("generation_settings", {})
        for key in ("temperature", "top_p", "top_k", "min_p"):
            wanted = c["settings"][key]
            observed = actual.get(key)
            if not sampler_matches(observed, wanted, integer=key == "top_k"):
                raise RuntimeError("effective_sampling_mismatch")
    visible = final_text(content)
    correct = None
    if quality:
        try:
            if visible.startswith("```"):
                visible = visible.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            parsed = json.loads(visible)
            correct = (
                completed
                and parsed == {"remaining": 19, "doubled": 38}
                and all(type(v) is int for v in parsed.values())
            )
        except (ValueError, IndexError):
            correct = False
    gpu_processes = processes(GPUS[s["gpu_index"]])

    def owned(pid):
        for _ in range(16):
            if pid == s["process"].pid:
                return True
            try:
                status = pathlib.Path("/proc/" + str(pid) + "/status").read_text()
                pid = int(
                    next(
                        line.split()[1]
                        for line in status.splitlines()
                        if line.startswith("PPid:")
                    )
                )
            except (OSError, ValueError, StopIteration):
                return False
            if pid <= 1:
                return False
        return False

    pids = [
        int(line.split(",")[0].strip())
        for line in gpu_processes.splitlines()
        if line.strip()
    ]
    placement = bool(pids) and all(owned(pid) for pid in pids)
    if ollama:
        placement = placement and models[0].get("size_vram", 0) >= models[0].get(
            "size", 1
        )
    else:
        with s["log_path"].open() as log:
            log.seek(s["log_offset"])
            launch_log = log.read(4 * 1024 * 1024)
        placement = (
            placement
            and bool(re.search(r"offloaded 66/66 layers to GPU", launch_log))
            and launch_log.count("CUDA0 KV buffer size") >= 2
            and "ctx_dft=yes, devices=[CUDA0]" in launch_log
        )
    healthy = req(port, "/api/version" if ollama else "/health") is not None
    context_ok = s["context"] == c["settings"]["context_per_slot"]
    t = telemetry()[s["gpu_index"]]
    free = min(s.get("min_free", t["memory_free_mib"]), t["memory_free_mib"])
    temp = max(s.get("max_temp", t["temperature_c"]), t["temperature_c"])
    return {
        "prompt_tokens": n,
        "output_tokens": o,
        "cached_tokens": cache,
        "decode_timed_tokens": dn,
        "prefill_seconds": pt or None,
        "decode_seconds": dt or None,
        "wall_seconds": wall,
        "request_started_at": datetime.fromtimestamp(
            request_start, timezone.utc
        ).isoformat(),
        "request_finished_at": datetime.fromtimestamp(
            request_end, timezone.utc
        ).isoformat(),
        "load_seconds": s.get("model_load_seconds", r.get("load_duration", 0) / 1e9)
        if ollama
        else s["load_seconds"],
        "load_timing_source": s.get("load_timing_source", "service_startup_wall"),
        "queue_seconds": None,
        "decode_tps": dn / dt if dn is not None and dt > 0 else None,
        "prefill_tps": n / pt if n is not None and pt > 0 else None,
        "timing_convention": convention,
        "output_cap": cap,
        "stop_reason": stop_reason,
        "completed": completed,
        "quality_pass": correct,
        "gpu_ids": [GPUS[s["gpu_index"]]],
        "min_free_gpu_memory_mib": {GPUS[s["gpu_index"]]: free},
        "peak_temperature_c": {GPUS[s["gpu_index"]]: temp},
        "request_hash": hashlib.sha256(
            json.dumps(request, sort_keys=True).encode()
        ).hexdigest(),
        "final_text": visible,
        "service_healthy": healthy,
        "placement_matches": placement,
        "context_matches": context_ok,
        "configured_context_per_slot": s["context"],
        "memory_guard_pass": free >= s["headroom"] and temp < 80,
        "warnings": []
        if cache == 0
        else [
            "Cache reuse was not ruled out."
            if cache is None
            else "Prompt cache was reused."
        ],
    }


def shutdown(*_):
    EXIT.set()


for sig in (signal.SIGTERM, signal.SIGINT):
    signal.signal(sig, shutdown)
RUNTIME_HASHES = {}
try:
    if not os.environ.get("SLURM_JOB_ID") or not os.environ.get("CUDA_VISIBLE_DEVICES"):
        raise RuntimeError("slurm_allocation_required")
    inventory = command(
        ["nvidia-smi", "--query-gpu=index,uuid,name", "--format=csv,noheader,nounits"]
    )
    entries = [[x.strip() for x in line.split(",")] for line in inventory.splitlines()]
    assigned = os.environ.get("SLURM_JOB_GPUS", "").split(",")
    if len(entries) == len(assigned):
        chosen = entries
    else:
        chosen = [r for r in entries if r[0] in assigned or r[1] in assigned]
    if (
        len(chosen) != len(assigned)
        or not 1 <= len(chosen) <= 2
        or any(r[2] != "NVIDIA L40" for r in chosen)
    ):
        raise RuntimeError("allocation_mapping_failed")
    GPUS = [r[1] for r in chosen]
    if any(processes(g) for g in GPUS):
        raise RuntimeError("gpu_busy")
    cpus = sorted(os.sched_getaffinity(0))
    per_lane = int(os.environ.get("SLURM_CPUS_PER_TASK", "0")) // len(GPUS)
    if per_lane < 12 or len(cpus) < per_lane * len(GPUS):
        raise RuntimeError("insufficient_cpu_allocation")
    CPU_GROUPS = [cpus[i * per_lane : (i + 1) * per_lane] for i in range(len(GPUS))]
    if (
        MODEL.stat().st_size != MANIFEST["artifact"]["files"][0]["size_bytes"]
        or sha(MODEL) != MANIFEST["artifact"]["files"][0]["sha256"]
    ):
        raise RuntimeError("artifact_hash_mismatch")
    for p in (ASSETS / "build-l40/bin").iterdir():
        if p.is_file() and not p.is_symlink():
            RUNTIME_HASHES[p.name] = sha(p)
    RUNTIME_HASHES["ollama"] = sha(ASSETS / "ollama-0.40.13/bin/ollama")
    if RUNTIME_HASHES != MANIFEST["runtime_hashes"]:
        raise RuntimeError("runtime_hash_mismatch")
    for p in (ASSETS / "build-l40/bin").iterdir():
        if p.is_symlink():
            target = p.resolve(strict=True)
            if (
                target.parent != (ASSETS / "build-l40/bin").resolve()
                or target.name not in RUNTIME_HASHES
            ):
                raise RuntimeError("runtime_symlink_mismatch")
            if sha(p) != RUNTIME_HASHES[target.name]:
                raise RuntimeError("runtime_symlink_hash_mismatch")
    save(ROOT / "ready.json", inspect())
    threading.Thread(target=guard, daemon=True).start()
    processed = set()
    while not EXIT.is_set():
        # A stable, pre-created inbox uses NFS close-to-open consistency, not cached directory scans.
        lines = (ROOT / "inbox.jsonl").read_text().split("\n")[:-1]
        for line in lines:
            if EXIT.is_set():
                break
            b = json.loads(line)
            out = ROOT / ("result-" + b["id"] + ".json")
            if b["id"] in processed:
                continue
            EVENT_PATH = ROOT / ("events-" + b["id"] + ".jsonl")
            ACTIVE_DEADLINE = b["deadline"]
            try:
                admit_command(b)
                op = b["op"]
                arg = b.get("body", {})
                if op == "inspect":
                    result = inspect()
                elif op == "load":
                    result = load(arg)
                elif op == "generate":
                    result = generate(arg)
                elif op == "stop":
                    stop(arg.get("lane", "tuned"))
                    result = {"stopped": True}
                elif op == "shutdown":
                    for lane in list(SERVICES):
                        stop(lane)
                    result = {"stopped": True}
                    EXIT.set()
                elif op == "race":
                    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                        futures = {
                            lane: pool.submit(
                                generate,
                                dict(
                                    arg,
                                    lane=lane,
                                    stream=True,
                                    measurement_id=arg["measurement_id"] + "-" + lane,
                                ),
                            )
                            for lane in ("default", "tuned")
                        }
                        result = {"lanes": {}, "errors": {}}
                        for lane, f in futures.items():
                            try:
                                result["lanes"][lane] = f.result()
                            except Exception as error:
                                result["errors"][lane] = str(error)[:300]
                else:
                    raise RuntimeError("unknown_operation")
                out.write_text(
                    json.dumps({"ok": True, "result": result}, allow_nan=False)
                )
            except Exception as e:
                # Exception messages contain no secrets, but keep full logs private.
                out.write_text(
                    json.dumps({"ok": False, "error": str(e)[:300]}, allow_nan=False)
                )
            finally:
                processed.add(b["id"])
                ACTIVE_DEADLINE = 0
        EXIT.wait(0.2)
except Exception as e:
    save(ROOT / "startup-error.json", {"error": str(e)[:300]})
finally:
    for lane in list(SERVICES):
        try:
            stop(lane)
        except Exception:
            pass
    save(ROOT / "stopped.json", {"stopped": True, "gpu_ids": GPUS})
