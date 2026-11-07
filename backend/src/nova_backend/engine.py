from __future__ import annotations
import asyncio, copy, time
from datetime import datetime, timezone
from .common import Problem, digest, now, uid
from .catalog import profiles_for, evidence, model_check, profile, resolve
from .schemas import Optimize, Race, Revert, Benchmark, Generate
from .store import TERMINAL
from .live import LiveFeed

QUALITY_PROMPT = 'A shop starts with 17 notebooks, receives 8, then sells 6. Return only a JSON object with integer keys "remaining" (notebooks left) and "doubled" (twice that number).'
PROBE_PROMPT = "Write a short essay explaining the causes of the Industrial Revolution"
DIFFERENCES = [
    "Default Ollama versus optimized llama.cpp: templates, context, cache precision, sampling, speculation and timing conventions differ. This is a whole-configuration comparison, not an MTP-only ablation."
]


class Engine:
    def __init__(self, store, driver, agent):
        self.store = store
        self.driver = driver
        self.agent = agent
        self.active = None
        self.tasks = {}
        self.current = None
        self.current_headroom = 1024
        self.generation = 0
        self.verified = {}
        self.recovery_error = None
        self.live = LiveFeed(simulation=driver.simulated)
        self.live_monitor = None
        self.live_ready = False
        self.submission_revision = 0

    async def recover(self):
        try:
            await self.driver.recover()
        except Problem as e:
            self.recovery_error = e
            return
        for s in self.store.unfinished():
            s.update(
                state="failed",
                error={
                    "code": "internal",
                    "message": "Backend restarted; owned allocation was cleaned up. Resubmit with a new key.",
                    "diagnosable": True,
                    "retryable": True,
                },
                cleanup={"status": "completed", "issues": []},
            )
            self.store.save(s)
            self.store.emit(
                s["run_id"], "error", error=s["error"], cleanup=s["cleanup"]
            )

    def patch(self, rid, **kw):
        s = self.store.get(rid)
        s.update(kw)
        self.store.save(s)

    def emit(self, rid, kind, **kw):
        return self.store.emit(rid, kind, **kw)

    def step(self, rid, name, status="running"):
        previous = self.store.get(rid)["current_step"]
        if previous and previous != name:
            self.emit(
                rid, "step", name=previous, status="done", progress=None, detail=None
            )
        self.patch(rid, current_step=name)
        self.emit(rid, "step", name=name, status=status, progress=None, detail=None)

    def service(self):
        s = self.driver.session
        return (
            None
            if not self.current or not s
            else {
                "id": "service_" + self.current["profile_id"],
                "state": "ready",
                "allocation_id": s["job_id"],
                "expires_at": datetime.fromtimestamp(
                    s["expires_at"], timezone.utc
                ).isoformat()
                if s.get("expires_at")
                else None,
            }
        )

    def lookup_profile(self, pid):
        try:
            return profile(pid)
        except Problem:
            return self.store.profile(pid)

    def submit(self, operation, req, key, body):
        old = self.store.existing(key, body)
        if old:
            return old, True
        if self.recovery_error:
            raise self.recovery_error
        if self.active:
            raise Problem(
                "operation_in_progress",
                "Another mutation owns the demo resources.",
                409,
                retryable=True,
            )
        if hasattr(req, "model"):
            model_check(req.model)
        if isinstance(req, Race) or (isinstance(req, Optimize) and req.mode != "verify_only"):
            raise Problem("unsupported_setting", "Ollama baselines and races are standalone demo tests, not production tool operations. Use Optimize verify_only.", 409)
        if isinstance(req, Optimize):
            if self.driver.session and self.driver.session.get("model", "qwen3.8-27b") != req.model:
                raise Problem("allocation_unavailable", "Revert the retained model to unloaded before selecting another model.", 409)
            if req.baseline_run_id:
                raise Problem(
                    "unsupported_setting",
                    "Ollama comparisons are standalone tests; baseline_run_id is not accepted by Optimize.",
                )
            # Validate explicit overrides before sending any work to Wright.
            candidates = (
                [self.lookup_profile(req.profile_id)]
                if req.profile_id
                else [p["config"] for p in profiles_for(req.model)]
            )
            failures = []
            for candidate in candidates:
                try:
                    resolve(req, candidate, self.current)
                    break
                except Problem as error:
                    failures.append(error)
            else:
                raise failures[0]
        if isinstance(req, Revert):
            snapshot = self.store.prior(req.rollback_id)
            if snapshot["generation"] != self.generation:
                raise Problem(
                    "constraint_violation",
                    "Rollback snapshot is stale for the current service.",
                    409,
                )
        if isinstance(req, Benchmark):
            if not self.current or self.current["model"] != req.model or (
                req.profile_id and req.profile_id != self.current["profile_id"]
            ):
                raise Problem(
                    "validation_failed",
                    "Benchmark requires the current verified profile.",
                    409,
                )
        if isinstance(req, Generate):
            if not self.live_ready or not self.current or self.current["model"] != req.model or self.current["profile_id"] not in self.verified or not self.driver.session:
                raise Problem("not_found", "No optimized service is running for this model.", 404)
        budget = getattr(req, "budget", None)
        seconds = budget.deadline_seconds if budget else 180
        deadline = time.time() + seconds
        s = self.store.create(
            key,
            body,
            operation,
            datetime.fromtimestamp(deadline, timezone.utc).isoformat(),
        )
        rid = s["run_id"]
        self.submission_revision += 1
        if not isinstance(req, Generate):
            self.live_ready = False
            self.live.close()
        self.active = rid
        self.tasks[rid] = asyncio.create_task(self.run(rid, req, deadline))
        return s, False

    async def cancel(self, rid):
        s = self.store.get(rid)
        if s["state"] in TERMINAL:
            return s["state"]
        if s["state"] == "cancelling":
            return "cancelling"
        self.patch(rid, state="cancelling")
        task = self.tasks.get(rid)
        if task:
            # Let a newly created task enter its try/finally before cancelling it.
            if s["state"] == "pending":
                await asyncio.sleep(0)
            task.cancel()
        return "cancelling"

    async def run(self, rid, req, deadline):
        prior = copy.deepcopy(self.current)
        prior_headroom = self.current_headroom
        start = time.monotonic()
        self.patch(rid, state="running")
        snapshot = self.store.get(rid)
        self.emit(
            rid,
            "start",
            operation=snapshot["operation"],
            mode=getattr(req, "mode", "verify_only"),
            started_at=snapshot["started_at"],
            deadline_at=snapshot["deadline_at"],
            simulation=self.driver.simulated,
        )
        try:
            async with asyncio.timeout(max(0.1, deadline - time.time())):
                if isinstance(req, Optimize):
                    result = await self.optimize(rid, req, deadline)
                elif isinstance(req, Generate):
                    result = await self.generate(rid, req, deadline)
                elif isinstance(req, Revert):
                    result = await self.revert(rid, req, deadline)
                else:
                    result = await self.benchmark(rid, req, deadline)
            result.update(
                elapsed_seconds=time.monotonic() - start,
                simulation=self.driver.simulated,
            )
            current_step = self.store.get(rid)["current_step"]
            if current_step:
                self.emit(
                    rid,
                    "step",
                    name=current_step,
                    status="done",
                    progress=1,
                    detail=None,
                )
            self.live_ready = bool(self.service())
            self.patch(rid, state="succeeded", result=result, progress=1)
            self.emit(rid, "done", **result)
        except (Exception, asyncio.CancelledError) as exc:
            cancelled = isinstance(exc, asyncio.CancelledError)
            if cancelled:
                p = Problem("cancelled", "Run cancelled.", 409)
            elif isinstance(exc, TimeoutError):
                p = Problem("deadline_exceeded", "Run exceeded its deadline.", 409)
            elif isinstance(exc, Problem):
                p = exc
            else:
                p = Problem(
                    "internal",
                    "Operation failed; consult private backend diagnostics.",
                    500,
                )
            current_step = self.store.get(rid)["current_step"]
            if current_step:
                self.emit(
                    rid,
                    "step",
                    name=current_step,
                    status="failed",
                    progress=None,
                    detail=None,
                )
            self.live_ready = False
            self.live.close("Generation or service operation failed; reconnect after recovery.")
            cleanup = await self.cleanup(prior, rid, prior_headroom)
            self.live_ready = cleanup["status"] == "completed" and bool(self.service())
            self.patch(
                rid,
                state="cancelled" if cancelled else "failed",
                error=p.error,
                cleanup=cleanup,
            )
            self.emit(
                rid,
                "error",
                error=p.error,
                cleanup=cleanup,
                partial_measurements=self.store.get(rid)["measurements"],
                service=self.service(),
                last_verified_profile_id=self.current["profile_id"]
                if self.current
                else None,
            )
        finally:
            self.active = None
            self.tasks.pop(rid, None)

    async def cleanup(self, prior, rid, headroom=1024):
        started = time.monotonic()
        released = []
        issues = []
        restored = None
        try:
            async with asyncio.timeout(45):
                await self.driver.cancel()
                if prior and self.driver.session:
                    await self.driver.stop("default", time.time() + 15)
                    await self.driver.stop("tuned", time.time() + 15)
                    await self.driver.load(
                        prior, time.time() + 40, headroom=headroom, recover=True
                    )
                    _, v = await self.measure(
                        rid, prior, "quality", "short", time.time() + 30
                    )
                    if v["status"] != "passed":
                        raise Problem(
                            "rollback_failed", "Restored service failed verification."
                        )
                    self.current = prior
                    self.current_headroom = headroom
                    restored = prior["profile_id"]
                else:
                    if self.driver.session:
                        released.append(self.driver.session.get("job_id"))
                    await self.driver.release()
                    self.current = None
        except (Exception, asyncio.CancelledError):
            issues.append(
                "rollback_failed: could not verify restoration; service is not advertised ready."
            )
            self.current = None
            try:
                await asyncio.wait_for(
                    self.driver.release(), max(0.1, 60 - (time.monotonic() - started))
                )
            except Exception:
                issues.append(
                    "Owned allocation cleanup could not be confirmed; inspect Wright before retrying."
                )
                self.recovery_error = Problem("rollback_failed", issues[-1], 503)
        return {
            "status": "failed" if issues else "completed",
            "restored_profile_id": restored,
            "retained_service_id": self.service()["id"] if self.service() else None,
            "released_allocation_ids": released,
            "issues": issues,
            "elapsed_seconds": time.monotonic() - started,
        }

    async def measure(
        self,
        rid,
        c,
        purpose,
        workload,
        deadline,
        lane="tuned",
        prompt=None,
        cap=None,
        seed=71430,
        stream=False,
    ):
        text = (
            prompt
            if prompt is not None
            else QUALITY_PROMPT
            if purpose == "quality"
            else PROBE_PROMPT
        )
        cap = cap or (2048 if purpose == "quality" else 256)
        mid = uid("measurement")
        b = {
            "lane": lane,
            "prompt": text,
            "max_tokens": cap,
            "purpose": purpose,
            "seed": seed,
            "fixed_length": purpose == "throughput" and prompt is None,
            "measurement_id": mid,
            "stream": stream,
        }
        raw = await self.driver.generate(
            b,
            min(deadline, time.time() + 45) if purpose == "quality" else deadline,
            on_event=(lambda e: self.emit(rid, "token", **e)) if stream else None,
        )
        return self.record(rid, c, raw, mid, purpose, workload, text)

    def record(self, rid, c, raw, mid, purpose, workload, text):
        raw = copy.deepcopy(raw)
        raw.pop("final_text", "")
        validation = {
            "status": "pending",
            "completed_answer": raw["completed"],
            "answer_correct": raw["quality_pass"],
            "service_healthy": raw.pop("service_healthy"),
            "placement_matches": raw.pop("placement_matches"),
            "context_matches": raw.pop("context_matches"),
            "memory_guard_pass": raw.pop("memory_guard_pass"),
            "configured_context_per_slot": raw.pop("configured_context_per_slot"),
            "tested_prompt_tokens": raw["prompt_tokens"],
            "checked_at": now(),
            "scope": "Short arithmetic completed-answer check only."
            if purpose == "quality"
            else "Throughput probe only; no semantic correctness assertion.",
            "issues": [],
        }
        if purpose == "quality":
            checks = (
                "completed_answer",
                "answer_correct",
                "service_healthy",
                "placement_matches",
                "context_matches",
                "memory_guard_pass",
            )
            validation["issues"] = [k for k in checks if validation[k] is not True]
            validation["status"] = "failed" if validation["issues"] else "passed"
        m = dict(
            raw,
            measurement_id=mid,
            run_id=rid,
            profile_id=c["profile_id"],
            origin="live",
            purpose=purpose,
            workload=workload,
            prompt_hash=digest(text),
            engine=c["engine"],
            runtime_id=c["runtime_id"],
            rate_scope="per_request",
            cache_state="uncached"
            if raw["cached_tokens"] == 0
            else "unknown"
            if raw["cached_tokens"] is None
            else "reused",
            settings_hash=digest(c),
            artifact_ref=mid + "-raw.json",
            sample_count=1,
            simulation=self.driver.simulated,
        )
        s = self.store.get(rid)
        s["measurements"].append(m)
        self.store.save(s)
        self.emit(
            rid,
            "benchmark",
            label="default" if c["engine"] == "ollama" else "tuned",
            measurement=m,
        )
        return m, validation

    async def optimize(self, rid, req, deadline):
        self.step(rid, "check_database")
        reason = "Explicit registered profile requested."
        if req.profile_id:
            selected = self.lookup_profile(req.profile_id)
        else:
            self.step(rid, "ask_ai")
            selected, reason = await self.agent.select(
                req, deadline, current=self.current
            )
        c = resolve(req, selected, self.current)
        ev = evidence(c)
        self.patch(rid, latest_config=c, evidence=ev)
        old = self.current or profiles_for(req.model)[0]["config"]
        changes = [
            {
                "path": "settings." + k,
                "from": old["settings"].get(k),
                "to": v,
                "reason": "CANON-backed decode selection.",
            }
            for k, v in c["settings"].items()
            if old["settings"].get(k) != v
        ]
        self.emit(
            rid, "config", phase="proposed", config=c, changes=changes, evidence=ev
        )
        self.step(rid, "allocate")
        await self.driver.ensure(req.resources, deadline, model=req.model)
        if self.driver.session:
            self.patch(
                rid,
                execution={
                    "deployment_id": self.driver.session.get("tag", "MOCK"),
                    "allocation_id": self.driver.session["job_id"],
                },
            )
        before = None
        repairs = []
        for attempt in range(req.budget.max_repair_attempts + 1):
            try:
                self.step(rid, "load_model")
                await self.driver.load(
                    c,
                    deadline,
                    headroom=req.constraints.min_free_gpu_memory_mib,
                    reset_guard=attempt > 0,
                )
                self.step(rid, "verify")
                _, validation = await self.measure(rid, c, "quality", "short", deadline)
                self.patch(rid, validation=validation)
                self.emit(rid, "validation", validation=validation)
                if validation["status"] != "passed":
                    raise Problem(
                        "validation_failed",
                        "Completed-answer or service checks failed: "
                        + ", ".join(validation["issues"]),
                    )
                after, probe_validation = await self.measure(
                    rid, c, "throughput", req.workload, deadline
                )
                if not all(probe_validation[k] is True for k in (
                    "service_healthy", "placement_matches", "context_matches", "memory_guard_pass")):
                    raise Problem("validation_failed", "Throughput probe failed service or placement checks.")
                break
            except Problem as error:
                if (
                    attempt >= req.budget.max_repair_attempts
                    or deadline - time.time() < 30
                ):
                    raise
                self.step(rid, "repair")
                record = {
                    "attempt": attempt + 1,
                    "error": error.error,
                    "summary": "Re-select a compatible registered profile and restart owned service.",
                    "changes": [],
                    "fallback": False,
                }
                repairs.append(record)
                selected, repair_reason = await self.agent.select(
                    req, deadline, repairs, current=self.current
                )
                new = resolve(req, selected, self.current)
                record["fallback"] = new["profile_id"] != c["profile_id"]
                record["summary"] = repair_reason
                record["changes"] = [
                    {
                        "path": "settings." + k,
                        "from": c["settings"].get(k),
                        "to": v,
                        "reason": "Repair selection.",
                    }
                    for k, v in new["settings"].items()
                    if c["settings"].get(k) != v
                ]
                c = new
                ev = evidence(c)
                self.patch(rid, repairs=repairs, latest_config=c, evidence=ev)
                self.emit(
                    rid,
                    "repair",
                    **record,
                    error_code=error.error["code"],
                    fallback_profile_id=c["profile_id"] if record["fallback"] else None,
                )
        comparison = self.comparison(before, after, req.mode)
        self.generation += 1
        rollback = self.store.snapshot(
            {
                "prior": self.current,
                "headroom": self.current_headroom,
                "generation": self.generation,
            }
        )
        self.current = c
        self.current_headroom = req.constraints.min_free_gpu_memory_mib
        self.verified[c["profile_id"]] = validation
        self.store.put_profile(c)
        self.patch(rid, latest_config=c, evidence=ev, validation=validation)
        changes = [
            {
                "path": "settings." + k,
                "from": old["settings"].get(k),
                "to": v,
                "reason": "Final verified configuration.",
            }
            for k, v in c["settings"].items()
            if old["settings"].get(k) != v
        ]
        if repairs:
            reason = repairs[-1]["summary"]
        self.emit(
            rid, "config", phase="effective", config=c, changes=changes, evidence=ev
        )
        return {
            "status": "success",
            "mode": req.mode,
            "applied": True,
            "config": c,
            "evidence": ev,
            "validation": validation,
            "before": before,
            "after": after,
            "speedup": after["decode_tps"] / before["decode_tps"]
            if comparison["available"]
            else None,
            "comparison": comparison,
            "reason": reason,
            "repairs": repairs,
            "service": self.service(),
            "rollback_id": rollback,
            "repro_command": None,
            "repro_ref": rid,
        }

    def comparison(self, before, after, mode):
        available = bool(
            before
            and after
            and before["decode_tps"]
            and after["decode_tps"]
            and before["prompt_hash"] == after["prompt_hash"]
            and before["output_cap"] == after["output_cap"]
        )
        return {
            "available": available,
            "mode": mode,
            "baseline_run_id": before["run_id"] if before else None,
            "reason": "Measured whole-configuration decode comparison."
            if available
            else "No matched baseline was measured.",
            "conditions_differ": DIFFERENCES,
        }

    async def revert(self, rid, req, deadline):
        snapshot = self.store.prior(req.rollback_id)
        prior = snapshot["prior"]
        headroom = snapshot.get("headroom", 1024)
        self.step(rid, "rollback")
        if prior:
            await self.driver.stop("default", deadline)
            await self.driver.load(prior, deadline, headroom=headroom)
            _, v = await self.measure(rid, prior, "quality", "short", deadline)
            if v["status"] != "passed":
                raise Problem(
                    "rollback_failed", "Prior configuration failed verification."
                )
            self.current = prior
            self.current_headroom = headroom
            self.verified[prior["profile_id"]] = v
        else:
            await self.driver.release()
            self.current = None
            v = {
                "status": "passed",
                "scope": "restoration-to-unloaded",
                "completed_answer": None,
                "answer_correct": None,
                "issues": [],
            }
        self.generation += 1
        return {
            "status": "success",
            "restored": True,
            "config": self.current,
            "service": self.service(),
            "validation": v,
        }

    async def benchmark(self, rid, req, deadline):
        await self.driver.ensure(req.resources, deadline, model=req.model)
        if self.driver.session:
            self.patch(
                rid,
                execution={
                    "deployment_id": self.driver.session.get("tag", "MOCK"),
                    "allocation_id": self.driver.session["job_id"],
                },
            )
        m, v = await self.measure(
            rid,
            self.current,
            req.purpose,
            req.workload,
            deadline,
            cap=req.max_tokens,
            seed=req.seed,
        )
        if req.purpose == "quality" and v["status"] != "passed":
            raise Problem("validation_failed", "Benchmark quality check failed.")
        return {
            "status": "success",
            "measurements": [m],
            "validation": v,
            "applied": False,
            "service": self.service(),
            "cleanup": {"status": "not_needed", "issues": []},
        }

    async def generate(self, rid, req, deadline):
        config = copy.deepcopy(self.current)
        service_id = self.service()["id"]
        mid = uid("measurement")

        def observe(event):
            kind = event.get("kind")
            if kind == "inference_started":
                self.live.publish("inference_started", request_id=rid, model=req.model,
                                  service_id=service_id, prompt_tokens=event.get("prompt_tokens"))
            elif kind == "metrics":
                self.live.publish("metrics", request_id=rid, **{
                    k: event[k] for k in ("decode_tps", "prefill_tps", "output_tokens", "timing_convention")})
            else:
                self.emit(rid, "token", **event)

        raw = await self.driver.generate({
            "lane": "tuned", "prompt": req.prompt, "max_tokens": req.max_tokens,
            "purpose": "throughput", "seed": 71430, "fixed_length": False,
            "measurement_id": mid, "stream": True, "live": True,
        }, deadline, on_event=observe)
        measurement, validation = self.record(rid, config, raw, mid, "throughput", "short", req.prompt)
        if not all(validation[k] is True for k in (
            "service_healthy", "placement_matches", "context_matches", "memory_guard_pass")):
            raise Problem("validation_failed", "Retained service failed its post-request checks.")
        self.live.publish("inference_done", request_id=rid, measurement=measurement)
        return {"status": "success", "measurement": measurement, "service": self.service(),
                "cleanup": {"status": "not_needed", "issues": []}}

    def observe_live(self, model):
        if model not in ("qwen3.8-27b", "qwen3.8-flash-next", "muse-glimmer"):
            raise Problem("model_not_found", "Unknown model.", 404)
        service = self.service()
        operation = self.store.get(self.active)["operation"] if self.active else None
        if (not self.live_ready or not service or self.current["model"] != model or self.recovery_error
                or (operation and operation != "generate")
                or (self.driver.session.get("expires_at", float("inf")) <= time.time())):
            raise Problem("not_found", "No optimized service is running for this model.", 404)
        queue = self.live.subscribe(model, service["id"])
        if self.live_monitor is None or self.live_monitor.done():
            self.live_monitor = asyncio.create_task(self.monitor_live())
        return queue

    async def monitor_live(self):
        while self.live.listeners:
            await asyncio.sleep(5)
            if not self.live.listeners:
                return
            if not self.service() or self.driver.session.get("expires_at", float("inf")) <= time.time():
                self.live_ready = False
                self.live.close("The retained service has stopped or expired.")
                return
            if self.active:
                continue  # Native generation failure is reported by the runner.
            revision = self.submission_revision
            try:
                observed = await self.driver.inspect(time.time() + 10)
                if revision != self.submission_revision:
                    continue
                if not observed.get("services", {}).get("tuned", {}).get("healthy"):
                    raise Problem("runtime_unavailable", "Retained service is not healthy.", 503)
            except Exception:
                if revision != self.submission_revision:
                    continue
                self.live_ready = False
                self.live.close("The retained service is unreachable; reconnect after recovery.")
                return

    async def close(self):
        self.live.close("Backend is shutting down.")
        if self.live_monitor:
            self.live_monitor.cancel()
            await asyncio.gather(self.live_monitor, return_exceptions=True)
        tasks = list(self.tasks.values())
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await self.driver.release()
