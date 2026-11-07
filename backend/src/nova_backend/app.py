from __future__ import annotations
import asyncio, fcntl, hmac, json, os, secrets, time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from .common import ROOT, MODEL, VERSION, Problem, now
from .catalog import PROFILES, REVISION, profiles_for, gpu_count, capabilities, evidence, model_check
from .schemas import Optimize, Race, Revert, Chat, Diagnose, Action, Benchmark, Empty, Generate, Resources
from .store import Store, TERMINAL
from .driver import WrightDriver, MockDriver
from .agent import Agent
from .engine import Engine


def create_app(state_dir=None, mock=None, driver=None, agent=None, prepare_model=None):
    state_dir = Path(
        state_dir or os.environ.get("NOVA_STATE_DIR", ROOT / "var/backend")
    )
    simulation = (
        mock if mock is not None else os.environ.get("NOVA_MODE", "wright") == "mock"
    )

    @asynccontextmanager
    async def lifespan(app):
        state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(state_dir, 0o700)
        lock = (state_dir / "backend.lock").open("a")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(
                "Another backend owns this state directory. Use one uvicorn worker."
            )
        token_path = state_dir / "pairing-token"
        if not token_path.exists():
            fd = os.open(token_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(secrets.token_urlsafe(32))
        os.chmod(token_path, 0o600)
        token = token_path.read_text().strip()
        if len(token) < 32:
            raise RuntimeError("Invalid pairing token file.")
        app.state.token = token
        app.state.engine = Engine(
            Store(state_dir / "runs.sqlite3"),
            driver
            or (MockDriver(state_dir) if simulation else WrightDriver(state_dir)),
            agent or Agent(simulation),
        )
        try:
            await app.state.engine.recover()
            preparing = prepare_model or os.environ.get("NOVA_PREPARE_MODEL")
            if preparing:
                model_check(preparing)
                if app.state.engine.recovery_error:
                    raise app.state.engine.recovery_error
                async with asyncio.timeout(600):
                    await app.state.engine.driver.ensure(
                        Resources(gpu_count=gpu_count(preparing)),
                        time.time() + 600, model=preparing,
                    )
            yield
        finally:
            try:
                await app.state.engine.close()
            finally:
                app.state.engine.store.db.close()
                lock.close()

    app = FastAPI(title="NOVA Backend", version=VERSION, lifespan=lifespan)
    origins = os.environ.get(
        "NOVA_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,tauri://localhost,app://widget",
    ).split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Pairing-Token", "Idempotency-Key"],
    )

    @app.middleware("http")
    async def auth(request, call_next):
        if request.url.path not in ("/health",) and request.method != "OPTIONS":
            supplied = request.headers.get("X-Pairing-Token", "")
            if not hmac.compare_digest(supplied, getattr(app.state, "token", "!")):
                return JSONResponse(
                    {
                        "error": Problem(
                            "unauthorized", "Pairing token required.", 401
                        ).error
                    },
                    401,
                )
        # Bound inbound bodies, including chunked requests, before JSON parsing.
        if request.method == "POST":
            chunks = []
            size = 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 128 * 1024:
                    return JSONResponse(
                        {
                            "error": Problem(
                                "bad_request", "Request body exceeds 128 KiB.", 400
                            ).error
                        },
                        400,
                    )
                chunks.append(chunk)
            request._body = b"".join(chunks)
        return await call_next(request)

    @app.exception_handler(Problem)
    async def problem_handler(request, exc):
        return JSONResponse({"error": exc.error}, exc.status)

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(ValidationError)
    async def invalid_handler(request, exc):
        fields = [
            {"field": ".".join(map(str, e["loc"])), "type": e["type"]}
            for e in exc.errors()
        ]
        p = Problem("bad_request", "Invalid request fields or types.", 400)
        p.error["details"] = {"fields": fields}
        return JSONResponse({"error": p.error}, 400)

    def engine():
        return app.state.engine

    def idem(request):
        key = request.headers.get("Idempotency-Key", "")
        if not key or len(key) > 200:
            raise Problem(
                "bad_request",
                "A nonempty Idempotency-Key of at most 200 characters is required.",
                400,
            )
        return key

    async def stream(rid):
        seq = 0
        while True:
            events = engine().store.events(rid, seq)
            for e in events:
                seq = e["sequence"]
                yield "data: " + json.dumps(e, allow_nan=False) + "\n\n"
            if engine().store.get(rid)["state"] in TERMINAL:
                break
            if not events:
                yield ": keepalive\n\n"
            await asyncio.sleep(0.2)

    def start(operation, req, request, original=None):
        body = {"operation": operation, "request": original or req.model_dump()}
        s, replayed = engine().submit(operation, req, idem(request), body)
        if replayed:
            return JSONResponse(
                {k: s[k] for k in ("run_id", "state", "result", "error")}
                | {"replayed": True}
            )
        return StreamingResponse(
            stream(s["run_id"]),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/health")
    async def health():
        return {
            "ok": True,
            "status": "ok",
            "contract_version": VERSION,
            "simulation": simulation,
        }

    @app.get("/live")
    async def live(model: str):
        e = engine()
        queue = e.observe_live(model)

        async def observe():
            async for event in e.live.events(queue):
                yield ("data: " + json.dumps(event, allow_nan=False) + "\n\n") if event else ": keepalive\n\n"

        return StreamingResponse(observe(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/generate")
    async def generate(req: Generate, request: Request):
        return start("generate", req, request)

    @app.get("/profiles")
    async def profiles(model: str = MODEL, target_id: str = "wright"):
        model_check(model)
        if target_id != "wright":
            raise Problem("not_found", "Unknown target.", 404)
        registered = profiles_for(model) + [
            {"config": c, "label": "Verified session profile"}
            for c in engine().store.profiles()
            if c["model"] == model and c["engine"] == "llama.cpp" and c["profile_id"] not in {p["config"]["profile_id"] for p in PROFILES}
        ]
        return {
            "contract_version": VERSION,
            "profiles": [
                {
                    "profile_id": p["config"]["profile_id"],
                    "label": p["label"],
                    "config": p["config"],
                    "resource_requirements": {
                        "gpu_type": "L40",
                        "gpu_count": gpu_count(model),
                        "same_node": True,
                        "context_per_slot": p["config"]["settings"]["context_per_slot"],
                    },
                    "evidence": evidence(p["config"]),
                    "compatibility": "compatible",
                    "reasons": [],
                }
                for p in registered
            ],
        }

    @app.get("/capabilities")
    async def get_capabilities(
        model: str = MODEL, runtime_id: str | None = None, target_id: str = "wright"
    ):
        if target_id != "wright":
            raise Problem("not_found", "Unknown target.", 404)
        if runtime_id and runtime_id != profiles_for(model)[0]["config"]["runtime_id"]:
            raise Problem(
                "runtime_unavailable", "No writable adapter for this runtime.", 409
            )
        return capabilities(model)

    @app.get("/status")
    async def status():
        e = engine()
        connection = "connected"
        observed_at = now()
        stale = False
        try:
            if e.active:
                obs = e.driver.observed if hasattr(e.driver, "observed") else None
                obs = obs or {"gpus": [], "services": {}, "artifact_verified": False}
                stale = True
                observed_at = getattr(e.driver, "observed_at", None)
            else:
                obs = await e.driver.inspect()
        except Problem:
            connection = "disconnected"
            obs = {"gpus": [], "services": {}, "artifact_verified": False}
        s = e.driver.session
        allocation = None
        if s:
            allocation = {
                "id": s["job_id"],
                "state": "running" if connection == "connected" else "unknown",
                "node_ids": list({g["node_id"] for g in obs["gpus"]}),
                "gpu_ids": [g["id"] for g in obs["gpus"]],
                "cpus_per_task": s.get("resources", {}).get("cpus_per_task", 12)
                * (s["gpu_count"] // s.get("gpus_per_engine", 1)),
                "host_memory_mib": s.get("resources", {}).get("host_memory_mib", 65536)
                * s["gpu_count"],
                "expires_at": e.service()["expires_at"] if e.service() else None,
                "owned": True,
            }
        models = []
        current_live = bool(
            e.current
            and connection == "connected"
            and obs["services"].get("tuned", {}).get("healthy")
        )
        for mid, name, count in [
            (MODEL, "ByteShape Qwen 27B", 1),
            ("qwen3.8-flash-next", "Qwen 3.8 Flash Next", 3),
            ("muse-glimmer", "Muse Glimmer 30B", 1),
        ]:
            model_config = profiles_for(mid)[0]["config"]
            allocated = bool(s and s.get("model", MODEL) == mid)
            loaded = current_live and e.current["model"] == mid
            ready = (
                allocated
                and connection == "connected"
                and bool(obs["artifact_verified"])
                and bool(obs["gpus"])
                and not e.recovery_error
                and (not e.current or loaded)
            )
            reasons = (
                []
                if ready
                else [
                    "Owned allocation and installed assets must be checked; Optimize performs preparation."
                ]
                if not s
                else ["Current service is unavailable or unverified."]
            )
            models.append(
                {
                    "id": mid,
                    "display_name": name,
                    "quant": model_config["quant"],
                    "artifact_id": model_config["artifact_id"],
                    "installed": True if allocated and obs["artifact_verified"] else None,
                    "loaded": loaded,
                    "database_coverage": "verified",
                    "requirements": {
                        "gpu_type": "L40",
                        "gpu_count": count,
                        "same_node": True,
                        "context_per_slot": model_config["settings"]["context_per_slot"],
                    },
                    "ready": bool(ready),
                    "readiness_reasons": reasons,
                    "race": {
                        "simultaneous_available": False,
                        "sequential_available": False,
                        "required_gpus_simultaneous": 2 * count,
                        "reasons": ["Ollama comparison is a standalone demo test."],
                    },
                }
            )
        return {
            "contract_version": VERSION,
            "observed_at": observed_at,
            "observations_stale": stale,
            "target_id": "wright",
            "connection": connection,
            "allocation": allocation,
            "all_gpus": obs["gpus"],
            "models": models,
            "current_config": e.current if current_live else None,
            "active_run_id": e.active,
            "is_tuned": current_live,
            "contribute_results": False,
            "optimizer_agent": {
                "model": e.agent.model,
                "reasoning_effort": "high",
                "requested_service_tier": os.environ.get(
                    "NOVA_OPENROUTER_SERVICE_TIER", "priority"
                ),
                "effective_service_tier": e.agent.effective_tier,
                "available": e.agent.available,
            },
            "simulation": simulation,
        }

    @app.post("/optimize")
    async def optimize(req: Optimize, request: Request):
        return start("optimize", req, request)

    @app.post("/race")
    async def race(req: Race, request: Request):
        return start("race", req, request)

    @app.post("/revert")
    async def revert(req: Revert, request: Request):
        return start("revert", req, request)

    @app.get("/runs/{rid}")
    async def run(rid: str):
        return engine().store.get(rid)

    @app.post("/runs/{rid}/cancel")
    async def cancel(rid: str, req: Empty, request: Request):
        key = idem(request)
        body = {"operation": "cancel", "run_id": rid}
        old = engine().store.existing(key, body)
        if old:
            return JSONResponse(
                {"run_id": rid, "state": old["state"], "replayed": True},
                200 if old["state"] in TERMINAL else 202,
            )
        engine().store.get(rid)
        engine().store.bind_cancel(key, body, rid)
        state = await engine().cancel(rid)
        return JSONResponse(
            {"run_id": rid, "state": state}, 200 if state in TERMINAL else 202
        )

    @app.post("/action")
    async def action(req: Action, request: Request):
        p = dict(req.params)
        if req.capabilities_revision and req.capabilities_revision != REVISION:
            raise Problem(
                "constraint_violation", "Capabilities changed; refresh first.", 409
            )
        if req.action == "revert":
            if set(p) != {"rollback_id"}:
                raise Problem(
                    "bad_request", "Revert params require only rollback_id.", 400
                )
            parsed = Revert(**p, budget=req.budget)
        elif req.action == "run_benchmark":
            if set(p) - {
                "model",
                "profile_id",
                "resources",
                "workload",
                "purpose",
                "max_tokens",
                "seed",
            }:
                raise Problem("bad_request", "Unknown benchmark parameter.", 400)
            parsed = Benchmark(**p, budget=req.budget)
        else:
            allowed = (
                {"model", "profile_id", "overrides", "resources", "constraints"}
                if req.action == "apply_config"
                else {"model", "profile_id", "resources", "context_per_slot"}
                if req.action == "lower_context"
                else {"model", "profile_id", "resources", "constraints", "artifact_id"}
            )
            if set(p) - allowed or not {"model", "profile_id"} <= set(p):
                raise Problem(
                    "bad_request", "Unexpected or missing action parameters.", 400
                )
            if req.action == "lower_context":
                ctx = p.pop("context_per_slot", None)
                if type(ctx) is not int:
                    raise Problem(
                        "bad_request", "context_per_slot must be an integer.", 400
                    )
                p["overrides"] = {
                    "settings": {"context_tokens": ctx, "context_per_slot": ctx}
                }
                p["constraints"] = {"min_context_tokens": ctx}
            elif req.action == "switch_quantization":
                p["overrides"] = {"artifact_id": p.pop("artifact_id", None)}
            parsed = Optimize(
                **p, budget=req.budget, capabilities_revision=req.capabilities_revision
            )
        return start("action", parsed, request, req.model_dump())

    @app.post("/chat")
    async def chat(req: Chat):
        e = engine()
        if req.model:
            model_check(req.model)
        context = {
            "current_config": e.current,
            "run": e.store.get(req.run_id) if req.run_id else None,
            "profiles": [p for p in PROFILES if p["config"]["engine"] == "llama.cpp"],
            "history": req.history,
        }

        async def events():
            try:
                text = await e.agent.chat(req.message, context, time.time() + 60)
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "type": "delta",
                            "run_id": None,
                            "sequence": 1,
                            "at": now(),
                            "text": text,
                        }
                    )
                    + "\n\n"
                )
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "type": "done",
                            "run_id": None,
                            "sequence": 2,
                            "at": now(),
                            "suggested_questions": [],
                            "suggested_actions": [],
                        }
                    )
                    + "\n\n"
                )
            except (Problem, TimeoutError) as exc:
                error = (
                    exc.error
                    if isinstance(exc, Problem)
                    else Problem("ai_unavailable", "Assistant timed out.", 503).error
                )
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "type": "error",
                            "run_id": None,
                            "sequence": 1,
                            "at": now(),
                            "error": error,
                        }
                    )
                    + "\n\n"
                )

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.post("/diagnose")
    async def diagnose(req: Diagnose):
        model_check(req.model)
        e = engine()
        # Do not forward arbitrary log text, which may contain accidentally pasted credentials.
        context = {
            "run": e.store.get(req.run_id) if req.run_id else None,
            "error_code": req.error_code,
            "current_config": e.current,
        }
        explanation = await e.agent.chat(
            "Explain this failure and the next safe step. Do not claim that repairs were executed.",
            context,
            time.time() + 60,
        )
        return {
            "explanation": explanation,
            "can_auto_repair": False,
            "suggested_action": None,
        }

    return app


app = create_app()
