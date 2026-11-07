from __future__ import annotations
import asyncio, copy, time
from datetime import datetime, timezone
from .common import Problem, digest, now, uid
from .catalog import BASELINE, PROFILES, evidence, model_check, profile, resolve
from .schemas import Optimize, Race, Revert, Benchmark
from .store import TERMINAL

QUALITY_PROMPT = 'A shop starts with 17 notebooks, receives 8, then sells 6. Return only a JSON object with integer keys "remaining" (notebooks left) and "doubled" (twice that number).'
PROBE_PROMPT = (
    "Analyze the following fictional ledger carefully and explain a general algorithm to reconcile it, then work through all entries in detail.\n"
    + "\n".join(
        f"Entry {i}: received {17 + i % 9}, sold {6 + i % 7}, returned {i % 3}."
        for i in range(80)
    )
)
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
        if isinstance(req, Optimize):
            if req.baseline_run_id:
                raise Problem(
                    "unsupported_setting",
                    "Baseline reuse is not enabled; omit baseline_run_id to measure a fresh baseline.",
                )
            # Validate explicit overrides before sending any work to Wright.
            candidates = (
                [self.lookup_profile(req.profile_id)]
                if req.profile_id
                else [p["config"] for p in PROFILES[:2]]
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
        if isinstance(req, Race):
            if not self.current or self.current["profile_id"] not in self.verified:
                raise Problem(
                    "validation_failed",
                    "Optimize and verify ByteShape before racing.",
                    409,
                )
            if (
                req.tuned_profile_id
                and req.tuned_profile_id != self.current["profile_id"]
            ):
                raise Problem(
                    "constraint_violation",
                    "Race must use the currently verified profile.",
                )
            if req.mode == "simultaneous" and (
                not self.driver.session or self.driver.session["gpu_count"] < 2
            ):
                raise Problem(
                    "allocation_unavailable",
                    "Simultaneous racing needs two preallocated L40s. Revert, then optimize with resources.gpu_count=2, or explicitly choose sequential.",
                    409,
                )
            if req.seed is not None:
                raise Problem(
                    "unsupported_setting",
                    "A seed override would alter untouched Ollama defaults; omit seed.",
                )
        if isinstance(req, Revert):
            snapshot = self.store.prior(req.rollback_id)
            if snapshot["generation"] != self.generation:
                raise Problem(
                    "constraint_violation",
                    "Rollback snapshot is stale for the current service.",
                    409,
                )
        if isinstance(req, Benchmark):
            if not self.current or (
                req.profile_id and req.profile_id != self.current["profile_id"]
            ):
                raise Problem(
                    "validation_failed",
                    "Benchmark requires the current verified profile.",
                    409,
                )
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

    def race_resources(self, mode):
        observation = getattr(self.driver, "observed", None) or {}
        gpus = observation.get("gpus", [])
        if self.driver.simulated and not gpus:
            gpus = [
                {"id": "MOCK-GPU-" + str(i), "node_id": "MOCK"}
                for i in range(self.driver.session["gpu_count"])
            ]
        indices = {"default": 1 if mode == "simultaneous" else 0, "tuned": 0}
        return {
            lane: {
                "gpu_ids": [gpus[i]["id"]],
                "node_id": gpus[i]["node_id"],
                "allocation_id": self.driver.session["job_id"],
            }
            for lane, i in indices.items()
            if i < len(gpus)
        }

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
            **(
                {
                    "lanes": ["default", "tuned"],
                    "lane_resources": self.race_resources(req.mode),
                }
                if isinstance(req, Race)
                else {}
            ),
        )
        try:
            async with asyncio.timeout(max(0.1, deadline - time.time())):
                if isinstance(req, Optimize):
                    result = await self.optimize(rid, req, deadline)
                elif isinstance(req, Race):
                    result = await self.race(rid, req, deadline)
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
            cleanup = await self.cleanup(prior, rid, prior_headroom)
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
            else PROBE_PROMPT * (4 if workload == "long" else 1)
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
        old = self.current or BASELINE
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
        await self.driver.ensure(req.resources, deadline)
        if self.driver.session:
            self.patch(
                rid,
                execution={
                    "deployment_id": self.driver.session.get("tag", "MOCK"),
                    "allocation_id": self.driver.session["job_id"],
                },
            )
        before = None
        before_validation = None
        if req.mode == "sequential_compare":
            self.step(rid, "test_configs")
            await self.driver.stop("tuned", deadline)
            await self.driver.load(
                BASELINE,
                deadline,
                "default",
                headroom=req.constraints.min_free_gpu_memory_mib,
            )
            before, before_validation = await self.measure(
                rid, BASELINE, "throughput", req.workload, deadline, "default"
            )
            _, bv = await self.measure(
                rid, BASELINE, "quality", "short", deadline, "default"
            )
            if bv["status"] != "passed":
                raise Problem(
                    "validation_failed",
                    "Default baseline failed its completed-answer verification.",
                )
            await self.driver.stop("default", deadline)
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
                after, _ = await self.measure(
                    rid, c, "throughput", req.workload, deadline
                )
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
        if req.mode == "sequential_compare" and not comparison["available"]:
            raise Problem("benchmark_failed", comparison["reason"])
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

    async def race(self, rid, req, deadline):
        c = copy.deepcopy(self.current)
        await self.driver.ensure(req.resources, deadline)
        if self.driver.session:
            self.patch(
                rid,
                execution={
                    "deployment_id": self.driver.session.get("tag", "MOCK"),
                    "allocation_id": self.driver.session["job_id"],
                },
            )
        before = None
        after = None
        ms = {}
        vs = {}
        try:
            if req.mode == "sequential":
                await self.driver.stop("tuned", deadline)
                await self.driver.load(
                    BASELINE, deadline, "default", headroom=self.current_headroom
                )
                before, vs["default"] = await self.measure(
                    rid,
                    BASELINE,
                    "throughput",
                    "custom",
                    deadline,
                    "default",
                    req.prompt,
                    req.max_tokens,
                    stream=True,
                )
                ms["default"] = before
                self.emit(
                    rid,
                    "lane_done",
                    lane="default",
                    measurement=before,
                    validation=vs["default"],
                )
                await self.driver.stop("default", deadline)
                await self.driver.load(c, deadline, headroom=self.current_headroom)
                after, vs["tuned"] = await self.measure(
                    rid,
                    c,
                    "throughput",
                    "custom",
                    deadline,
                    "tuned",
                    req.prompt,
                    req.max_tokens,
                    stream=True,
                )
                ms["tuned"] = after
                self.emit(
                    rid,
                    "lane_done",
                    lane="tuned",
                    measurement=after,
                    validation=vs["tuned"],
                )
            else:
                await self.driver.load(
                    BASELINE,
                    deadline,
                    "default",
                    gpu_index=1,
                    headroom=self.current_headroom,
                )
                observation = await self.driver.inspect(deadline)
                self.emit(
                    rid,
                    "step",
                    name="test_configs",
                    status="running",
                    progress=None,
                    detail=None,
                    lane_resources={
                        k: {"gpu_ids": [v["gpu_id"]]}
                        for k, v in observation["services"].items()
                    },
                )
                race_id = uid("race")
                raw = await self.driver.rpc(
                    "race",
                    {
                        "prompt": req.prompt,
                        "max_tokens": req.max_tokens,
                        "purpose": "throughput",
                        "fixed_length": False,
                        "measurement_id": race_id,
                    },
                    deadline,
                    on_event=lambda e: self.emit(rid, "token", **e),
                )
                for lane, conf in [("default", BASELINE), ("tuned", c)]:
                    if lane not in raw["lanes"]:
                        continue
                    m, v = self.record(
                        rid,
                        conf,
                        raw["lanes"][lane],
                        race_id + "-" + lane,
                        "throughput",
                        "custom",
                        req.prompt,
                    )
                    ms[lane] = m
                    vs[lane] = v
                    self.emit(rid, "lane_done", lane=lane, measurement=m, validation=v)
                if raw["errors"]:
                    raise Problem(
                        "benchmark_failed",
                        "A race lane failed; completed lane measurements are retained.",
                    )
                before = ms["default"]
                after = ms["tuned"]
            for lane, validation in vs.items():
                if not all(
                    validation[k] is True
                    for k in (
                        "service_healthy",
                        "placement_matches",
                        "context_matches",
                        "memory_guard_pass",
                    )
                ):
                    raise Problem(
                        "benchmark_failed",
                        lane + " lane failed service or placement checks.",
                    )
            # Short check confirms service after temporary baseline switching; race text isn't a correctness test.
            _, v = await self.measure(rid, c, "quality", "short", deadline)
            if v["status"] != "passed":
                raise Problem(
                    "validation_failed", "Post-race service verification failed."
                )
            self.verified[c["profile_id"]] = v
        except BaseException:
            # Interrupt an active generation before any stop RPC can queue behind it.
            try:
                await self.driver.cancel()
            except Exception:
                pass
            raise
        else:
            await self.driver.stop("default", deadline)
        comparison = self.comparison(before, after, req.mode)
        ratio = (
            after["decode_tps"] / before["decode_tps"]
            if comparison["available"]
            else None
        )
        return {
            "status": "success",
            "mode": req.mode,
            "measurements": ms,
            "winner": None
            if ratio is None
            else "tuned"
            if ratio > 1
            else "default"
            if ratio < 1
            else "tie",
            "speedup": ratio,
            "comparison": comparison,
            "cleanup": {
                "status": "completed",
                "retained_service_id": self.service()["id"],
                "issues": [],
            },
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
        await self.driver.ensure(req.resources, deadline)
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

    async def close(self):
        tasks = list(self.tasks.values())
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await self.driver.release()
