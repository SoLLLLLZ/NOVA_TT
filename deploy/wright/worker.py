#!/usr/bin/env python3
"""Private file-RPC worker, run ONLY under srun in our owned Slurm job.
No network listener except owned model servers on loopback. No credentials.
"""

import concurrent.futures, hashlib, json, math, os, re, pathlib, signal, socket, subprocess, sys, threading, time, urllib.request
from datetime import datetime, timezone

ROOT = pathlib.Path(sys.argv[1]).resolve()
MANIFEST = json.loads((ROOT / "manifest.json").read_text())
ASSETS = pathlib.Path(MANIFEST["asset_root"])
SHARED = pathlib.Path(MANIFEST.get("shared_root", str(ASSETS)))
RUNTIME = pathlib.Path(MANIFEST.get("runtime_dir", str(SHARED / "build-l40/bin")))
MODEL_ID = MANIFEST["artifact"]["model"]
GPUS_PER_ENGINE = MANIFEST.get("gpu_count", 1)
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
        if all(not processes(GPUS[i]) for i in entry["gpu_indices"]):
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
                "gpu_ids": [GPUS[i] for i in s["gpu_indices"]],
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
                for gi in s.get("gpu_indices", [s["gpu_index"]]):
                    g = samples[gi]
                    s.setdefault("min_free_by_gpu", {})[gi] = min(s.get("min_free_by_gpu", {}).get(gi, g["memory_free_mib"]), g["memory_free_mib"])
                    s.setdefault("max_temp_by_gpu", {})[gi] = max(s.get("max_temp_by_gpu", {}).get(gi, g["temperature_c"]), g["temperature_c"])
                    if g["memory_free_mib"] < s.get("headroom", 1024) or g["temperature_c"] >= 80:
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
    indices = list(range(gi, gi + GPUS_PER_ENGINE))
    if gi % GPUS_PER_ENGINE or any(i not in range(len(GPUS)) for i in indices):
        raise RuntimeError("allocation_unavailable")
    stop(lane)
    check()
    if any(set(s["gpu_indices"]) & set(indices) for s in SERVICES.values()) or any(processes(GPUS[i]) for i in indices):
        raise RuntimeError("gpu_busy")
    if any(float(query(GPUS[i], "memory.free")) < 40000 for i in indices):
        raise RuntimeError("insufficient_startup_headroom")
    if c["artifact_id"] != MANIFEST["artifact"]["id"] or c["model"] != MODEL_ID:
        raise RuntimeError("unsupported_artifact")
    ollama = c["engine"] == "ollama"
    if c["runtime_id"] != ("ollama-0.40.13" if ollama else MANIFEST["profiles"][0]["config"]["runtime_id"]):
        raise RuntimeError("unsupported_runtime")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("OLLAMA_", "LLAMA_", "GGML_", "FLASH_NEXT_", "APPTAINERENV_"))
        and k != "LD_LIBRARY_PATH"
    }
    for key in ("GPU_DEVICE_ORDINAL", "ROCR_VISIBLE_DEVICES", "HIP_VISIBLE_DEVICES"):
        env.pop(key, None)
    visible_devices = ",".join(GPUS[i] for i in indices)
    env["CUDA_VISIBLE_DEVICES"] = visible_devices
    if ollama:
        # Only standalone comparison tests depend on the Ollama installation.
        if sha(SHARED / "ollama-0.40.13/bin/ollama") != MANIFEST["runtime_hashes"]["ollama"]:
            raise RuntimeError("runtime_hash_mismatch: ollama")
        store = ROOT / "ollama-models"
        (store / "blobs").mkdir(parents=True, exist_ok=True)
        for file in MANIFEST["artifact"]["files"]:
            if file.get("role", "target") != "target":
                continue
            blob = store / "blobs" / ("sha256-" + file["sha256"])
            if not blob.exists():
                os.link(ASSETS / file["name"], blob)
        env.update(
            OLLAMA_HOST="127.0.0.1:" + str(port),
            OLLAMA_MODELS=str(store),
            OLLAMA_VULKAN="0",
            OLLAMA_NOPRUNE="1",
        )
        argv = [str(SHARED / "ollama-0.40.13/bin/ollama"), "serve"]
    else:
        argv = [str(RUNTIME / "llama-server")] + MANIFEST[
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
            ("--alias", "nova-" + MODEL_ID),
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
            "CUDA_VISIBLE_DEVICES=" + visible_devices,
            "--env",
            "LD_LIBRARY_PATH=" + str(RUNTIME),
            str(SHARED / "cuda-12.9.1-devel-ubuntu24.04.sif"),
        ]
        container[-1:-1] = [v for k, value in MANIFEST.get("runtime_env", {}).items() for v in ("--env", k + "=" + value)]
        devices = command(container + [argv[0], "--list-devices"], env=env)
        found = re.findall(r"CUDA(\d+):", devices)
        if sorted(found) != [str(i) for i in range(GPUS_PER_ENGINE)]:
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
        "gpu_indices": indices,
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
            "gpu_ids": [GPUS[i] for i in indices],
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
        # Verified target shards are local blobs; avoid re-uploading model weights.
        created = req(
            port,
            "/api/create",
            {
                "model": "nova-" + MODEL_ID,
                "files": {
                    f["name"]: "sha256:" + f["sha256"] for f in MANIFEST["artifact"]["files"] if f.get("role", "target") == "target"
                },
                "stream": False,
            },
            timeout=180,
        )
        if created.get("status") != "success":
            raise RuntimeError("ollama_model_registration_failed")
        save(
            ROOT / "ollama-model-show.json",
            req(port, "/api/show", {"model": "nova-" + MODEL_ID}),
        )
        # Standalone baseline preload uses no prompt or inference overrides.
        preload_start = time.monotonic()
        loaded = req(
            port,
            "/api/generate",
            {"model": "nova-" + MODEL_ID, "stream": False},
            timeout=180,
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


def final_text(text, model=None, streaming=False):
    if model == "muse-glimmer":
        marker = "<|start|>assistant to=user<|message|>"
        if marker not in text:
            return ""  # An unfinished reasoning channel is never a final answer.
        text = text.split(marker, 1)[1]
        # Never forward native channel/end markers, including partial markers.
        text = text.split("<|", 1)[0]
        if streaming and text.endswith("<"):
            text = text[:-1]
        return text if streaming else text.strip()
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
        return text if streaming else text.strip()
    if "<think>" in text or streaming:
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
            model = SERVICES[lane]["config"]["model"]
            visible = (text if ollama and separate_thinking and model != "muse-glimmer"
                       else final_text(text, model, streaming=True))
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
            "model": "nova-" + MODEL_ID,
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
        content = r.get("content", "")
        convention = "(predicted_n - 1) / predicted_ms"
        actual = r.get("generation_settings", {})
        for key in ("temperature", "top_p", "top_k", "min_p"):
            wanted = c["settings"][key]
            observed = actual.get(key)
            if not sampler_matches(observed, wanted, integer=key == "top_k"):
                raise RuntimeError("effective_sampling_mismatch")
    visible = final_text(content, c["model"])
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
    gpu_processes = {i: processes(GPUS[i]) for i in s["gpu_indices"]}

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

    pids = {i: [int(line.split(",")[0].strip()) for line in value.splitlines() if line.strip()]
            for i, value in gpu_processes.items()}
    placement = all(ids and all(owned(pid) for pid in ids) for ids in pids.values())
    if ollama:
        placement = placement and models[0].get("size_vram", 0) >= models[0].get(
            "size", 1
        )
    else:
        with s["log_path"].open() as log:
            log.seek(s["log_offset"])
            launch_log = log.read(4 * 1024 * 1024)
        target_layers = MANIFEST.get("target_layers", 66)
        placement = placement and f"offloaded {target_layers}/{target_layers} layers to GPU" in launch_log
        buffers = {int(i): float(size) for i, size in re.findall(r"CUDA([0-9]+) model buffer size\s*=\s*([0-9.]+) MiB", launch_log.split("llama_context: constructing", 1)[0])}
        placement = placement and all(buffers.get(i, 0) > 0 for i in range(GPUS_PER_ENGINE))
        if MODEL_ID == "muse-glimmer":
            placement = placement and "offloaded 6/6 layers to GPU" in launch_log
        elif MODEL_ID == "qwen3.8-27b":
            placement = placement and launch_log.count("CUDA0 KV buffer size") >= 2 and "ctx_dft=yes, devices=[CUDA0]" in launch_log
        elif MODEL_ID == "qwen3.8-flash-next":
            placement = placement and "ctx_dft=yes, devices=[CUDA2]" in launch_log
    healthy = req(port, "/api/version" if ollama else "/health") is not None
    context_ok = s["context"] == c["settings"]["context_per_slot"]
    samples = telemetry()
    free_by_gpu = {GPUS[i]: min(s.get("min_free_by_gpu", {}).get(i, samples[i]["memory_free_mib"]), samples[i]["memory_free_mib"]) for i in s["gpu_indices"]}
    temp_by_gpu = {GPUS[i]: max(s.get("max_temp_by_gpu", {}).get(i, samples[i]["temperature_c"]), samples[i]["temperature_c"]) for i in s["gpu_indices"]}
    free, temp = min(free_by_gpu.values()), max(temp_by_gpu.values())
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
        "gpu_ids": [GPUS[i] for i in s["gpu_indices"]],
        "min_free_gpu_memory_mib": free_by_gpu,
        "peak_temperature_c": temp_by_gpu,
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


def allocated_gpu_uuids(environ, entries, gres_text, proc_information, node):
    """Resolve Slurm GRES IDs through device files, never remapped NVML indices.

    Wright exposes some unallocated devices to NVML. Visibility or matching
    inventory counts therefore cannot prove ownership of a device.
    """
    assigned = (environ.get("SLURM_STEP_GPUS") or environ.get("SLURM_JOB_GPUS") or "").split(",")
    job = environ.get("SLURM_JOB_GPUS")
    if not all(assigned) or len(set(assigned)) != len(assigned):
        raise RuntimeError("allocation_mapping_failed: missing or duplicate Slurm GPU IDs")
    if job and not set(assigned).issubset(job.split(",")):
        raise RuntimeError("allocation_mapping_failed: step exceeds job GPUs")
    files = []
    for line in gres_text.splitlines():
        fields = dict(part.split("=", 1) for part in line.split("#", 1)[0].split() if "=" in part)
        if fields.get("NodeName") == node.split(".")[0] and fields.get("Name") == "gpu":
            match = re.fullmatch(r"/dev/nvidia(\d+)", fields.get("File", ""))
            if not match:
                raise RuntimeError("allocation_mapping_failed: unsupported GRES device mapping")
            files.append(match.group(1))
    minors = {}
    for info in proc_information:
        values = dict(line.split(":", 1) for line in info.splitlines() if ":" in line)
        minor = values.get("Device Minor", "").strip()
        uuid = values.get("GPU UUID", "").strip()
        if minor in minors or not minor.isdigit() or not uuid.startswith("GPU-"):
            raise RuntimeError("allocation_mapping_failed: invalid physical GPU metadata")
        minors[minor] = uuid
    selected = []
    for assigned_id in assigned:
        if assigned_id.startswith("GPU-"):
            uuid = assigned_id
        elif assigned_id.isdigit() and int(assigned_id) < len(files):
            uuid = minors.get(files[int(assigned_id)])
        else:
            raise RuntimeError("allocation_mapping_failed: unresolved Slurm GPU ID")
        matches = [entry for entry in entries if entry[1] == uuid and entry[2] == "NVIDIA L40"]
        if len(matches) != 1:
            raise RuntimeError("allocation_mapping_failed: allocated GPU is unavailable")
        selected.append(uuid)
    if len(set(selected)) != len(selected):
        raise RuntimeError("allocation_mapping_failed: duplicate physical GPU")
    return selected


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
    GPUS = allocated_gpu_uuids(os.environ, entries, pathlib.Path("/etc/slurm/gres.conf").read_text(),
        [path.read_text() for path in pathlib.Path("/proc/driver/nvidia/gpus").glob("*/information")],
        socket.gethostname())
    if len(GPUS) != GPUS_PER_ENGINE:
        raise RuntimeError("allocation_mapping_failed")
    save(ROOT / "gpu-admission.json", {"job_id": os.environ["SLURM_JOB_ID"],
        "job_gpus": os.environ.get("SLURM_JOB_GPUS"), "step_gpus": os.environ.get("SLURM_STEP_GPUS"),
        "cuda_visible_devices": os.environ["CUDA_VISIBLE_DEVICES"], "gpu_ids": GPUS,
        "mapping": "Slurm GRES file -> physical device minor -> UUID; verified in visible inventory"})
    if any(processes(g) for g in GPUS):
        raise RuntimeError("gpu_busy")
    cpus = sorted(os.sched_getaffinity(0))
    lanes = len(GPUS) // GPUS_PER_ENGINE
    per_lane = int(os.environ.get("SLURM_CPUS_PER_TASK", "0")) // lanes
    if per_lane < 12 or len(cpus) < per_lane * lanes:
        raise RuntimeError("insufficient_cpu_allocation")
    CPU_GROUPS = [cpus[(i // GPUS_PER_ENGINE) * per_lane: (i // GPUS_PER_ENGINE + 1) * per_lane] for i in range(len(GPUS))]
    for file in MANIFEST["artifact"]["files"]:
        path = ASSETS / file["name"]
        if path.stat().st_size != file["size_bytes"] or sha(path) != file["sha256"]:
            raise RuntimeError("artifact_hash_mismatch: " + file["name"])
    native_hashes = {name: value for name, value in MANIFEST["runtime_hashes"].items() if name != "ollama"}
    for name in native_hashes:
        path = RUNTIME / name
        RUNTIME_HASHES[name] = sha(path)
    if RUNTIME_HASHES != native_hashes:
        raise RuntimeError("runtime_hash_mismatch")
    for path in RUNTIME.iterdir():
        if path.is_symlink():
            target = path.resolve(strict=True)
            if target.name not in RUNTIME_HASHES or sha(path) != RUNTIME_HASHES[target.name]:
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
