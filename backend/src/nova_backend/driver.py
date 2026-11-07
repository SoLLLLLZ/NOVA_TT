from __future__ import annotations
import asyncio, base64, copy, json, os, shlex, time
from pathlib import Path
from .common import ROOT, MODEL, Problem, private_json, uid, now
from .catalog import manifest_for, gpu_count


class WrightDriver:
    simulated = False

    def __init__(self, state_dir):
        self.state_dir = Path(state_dir)
        self.session = None
        self.observed = None
        self.observed_at = None
        self.host = os.environ.get("NOVA_SSH_HOST", "taeholee@wright.hss.cmu.edu")
        self.socket = os.environ.get(
            "NOVA_SSH_CONTROL", "/tmp/wright-glimmer-20261105-501/control"
        )
        self.known = os.environ.get(
            "NOVA_SSH_KNOWN_HOSTS", "/tmp/wright-access-check-20261103-known_hosts"
        )

    async def ssh(self, script, data=None, timeout=20):
        args = [
            "ssh",
            "-S",
            self.socket,
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=8",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "UserKnownHostsFile=" + self.known,
            self.host,
            script,
        ]
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(data), timeout)
        except BaseException:
            proc.kill()
            await proc.wait()
            raise
        if proc.returncode:
            raise Problem(
                "ssh_unavailable",
                "Wright command failed; check connection or private worker logs.",
                503,
                retryable=True,
            )
        return out.decode()

    async def recover(self):
        path = self.state_dir / "wright.json"
        if path.exists():
            self.session = json.loads(path.read_text())
            # Do not replay work after a crash. Verify ownership, then clean only our job.
            await self.release()

    async def write_files(self, files):
        root = self.session["root"]
        payload = {
            name: base64.b64encode(data).decode() for name, data in files.items()
        }
        code = (
            "import sys,json,pathlib,base64,os; p=pathlib.Path("
            + repr(root)
            + "); p.mkdir(parents=True,exist_ok=True,mode=0o700); d=json.load(sys.stdin); [( (p/(n+'.tmp')).write_bytes(base64.b64decode(v)),os.chmod(p/(n+'.tmp'),0o600),(p/(n+'.tmp')).replace(p/n)) for n,v in d.items()]"
        )
        await self.ssh("python3 -c " + shlex.quote(code), json.dumps(payload).encode())

    async def read_file(self, name):
        # Open directly: NFS negative stat/directory caches can hide new receipts for 30s.
        code = (
            "import pathlib\np=pathlib.Path("
            + repr(self.session["root"] + "/" + name)
            + ")\ntry:\n print(p.read_text())\nexcept FileNotFoundError:\n print('null')"
        )
        output = await self.ssh("python3 -c " + shlex.quote(code))
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return None  # in-place result write not yet complete

    async def ensure(self, resources, deadline, model=MODEL):
        manifest = manifest_for(model)
        required = gpu_count(model)
        if resources.gpu_count != required:
            raise Problem("allocation_unavailable", f"This model needs {required} L40s per engine.", 409)
        if self.session:
            if self.session.get("model", MODEL) != model:
                raise Problem("allocation_unavailable", "Revert before changing models.", 409)
            if (
                resources.allocation_id
                and resources.allocation_id != self.session["job_id"]
            ):
                raise Problem(
                    "allocation_unavailable",
                    "Allocation is not owned by this backend.",
                    409,
                )
            if resources.gpu_count > self.session["gpu_count"]:
                raise Problem(
                    "allocation_unavailable",
                    "Retained allocation is too small. Revert to unloaded before requesting more GPUs.",
                    409,
                )
            saved = self.session.get("resources", {})
            for field in ("cpus_per_task", "host_memory_mib", "wall_time_seconds"):
                if saved and getattr(resources, field) != saved[field]:
                    raise Problem(
                        "constraint_violation",
                        "Cannot change resources of a retained allocation.",
                    )
            observation = await self.inspect(deadline)
            ids = [g["id"] for g in observation["gpus"]]
            if resources.gpu_ids is not None and resources.gpu_ids != ids:
                raise Problem(
                    "constraint_violation",
                    "Requested device IDs do not match owned allocation.",
                )
            return
        if resources.allocation_id:
            raise Problem(
                "allocation_unavailable",
                "Only allocations created and owned by this backend can be reused.",
                409,
            )
        sid = uid("nova")
        self.session = {
            "root": "/home/export/taeholee/nova/backend-runs/" + sid,
            "tag": sid,
            "model": model,
            "gpus_per_engine": required,
            "job_id": None,
            "gpu_count": resources.gpu_count,
            "expires_at": None,
            "resources": resources.model_dump(),
        }
        private_json(self.state_dir / "wright.json", self.session)
        private_json(
            self.state_dir / "deployments" / (self.session["tag"] + ".json"),
            self.session,
        )
        await self.write_files(
            {
                "inbox.jsonl": b"",
                "cancel": b"",
                "ready.json": b"null",
                "startup-error.json": b"null",
                "stopped.json": b"null",
                "worker.py": (ROOT / "deploy/wright/worker.py").read_bytes(),
                "manifest.json": json.dumps(manifest).encode(),
            }
        )
        root = self.session["root"]
        g = resources.gpu_count
        script = (
            "#!/bin/bash\nset -euo pipefail\numask 077\nexec srun --ntasks=1 python3 "
            + shlex.quote(root + "/worker.py")
            + " "
            + shlex.quote(root)
            + "\n"
        )
        await self.write_files({"job.sh": script.encode()})
        args = [
            "sbatch",
            "--parsable",
            "--job-name=" + sid,
            "--comment=" + sid,
            "--account=cmist",
            "--partition=cmist",
            "--qos=cmist_priority",
            "--nodes=1",
            "--ntasks=1",
            "--gres=gpu:nvidia-l40:" + str(g),
            "--cpus-per-task=" + str(resources.cpus_per_task * (g // required)),
            "--mem=" + str(resources.host_memory_mib * g) + "M",
            "--time=" + str((resources.wall_time_seconds + 59) // 60),
            "--no-requeue",
            "--output=" + root + "/slurm.log",
            root + "/job.sh",
        ]
        job = (await self.ssh(shlex.join(args))).strip().split(";")[0]
        if not job.isdigit():
            raise Problem(
                "allocation_unavailable",
                "Scheduler did not return a valid job ID.",
                503,
            )
        self.session["job_id"] = job
        self.session["expires_at"] = time.time() + resources.wall_time_seconds
        private_json(self.state_dir / "wright.json", self.session)
        private_json(
            self.state_dir / "deployments" / (self.session["tag"] + ".json"),
            self.session,
        )
        while time.time() < deadline:
            failure = await self.read_file("startup-error.json")
            if failure:
                raise Problem(
                    "runtime_unavailable",
                    "Worker preflight failed: " + failure["error"],
                    503,
                )
            ready = await self.read_file("ready.json")
            if ready:
                self.observed = ready
                self.observed_at = now()
                return
            await asyncio.sleep(1)
        raise Problem(
            "deadline_exceeded",
            "Allocation or asset verification exceeded the deadline.",
            409,
        )

    async def rpc(
        self,
        op,
        body=None,
        deadline=None,
        on_event=None,
        reset_cancel=False,
        reset_guard=False,
    ):
        if not self.session or not self.session["job_id"]:
            raise Problem("allocation_unavailable", "No owned worker allocation.", 409)
        deadline = deadline or time.time() + 20
        ident = uid("rpc")
        payload = {
            "id": ident,
            "op": op,
            "body": body or {},
            "deadline": deadline,
            "reset_cancel": reset_cancel,
            "reset_guard": reset_guard,
        }
        code = (
            "import sys,json,pathlib,os\np=pathlib.Path("
            + repr(self.session["root"])
            + ")\nb=json.load(sys.stdin)\nf=p/('result-'+b['id']+'.json')\nf.write_text('null')\nos.chmod(f,0o600)\ne=p/('events-'+b['id']+'.jsonl')\ne.write_text('')\nos.chmod(e,0o600)\nwith (p/'inbox.jsonl').open('a') as out:\n out.write(json.dumps(b)+'\\n');out.flush();os.fsync(out.fileno())"
        )
        await self.ssh("python3 -c " + shlex.quote(code), json.dumps(payload).encode())
        seen = 0

        async def drain():
            nonlocal seen
            if not on_event:
                return
            code = (
                "import pathlib,json\np=pathlib.Path("
                + repr(self.session["root"] + "/events-" + ident + ".jsonl")
                + ")\ntry:\n print(json.dumps(p.read_text()))\nexcept FileNotFoundError:\n print('\"\"')"
            )
            content = json.loads(await self.ssh("python3 -c " + shlex.quote(code)))
            lines = content.split("\n")[
                :-1
            ]  # incomplete final writes wait for the next poll
            for line in lines[seen:]:
                if line.strip():
                    on_event(json.loads(line))
            seen = len(lines)

        live_result = None
        if body and body.get("live") and on_event:
            live_result = await self.watch_live_rpc(ident, deadline, on_event)
        while live_result is not None or time.time() < deadline:
            if live_result is None:
                await drain()
            result = live_result or await self.read_file("result-" + ident + ".json")
            if result:
                if live_result is None:
                    await drain()  # include chunks written between the previous read and completion
                if not result["ok"]:
                    message = result["error"]
                    code = (
                        "deadline_exceeded"
                        if "deadline_exceeded" in message
                        else "cancelled"
                        if "cancelled" in message
                        else "gpu_busy"
                        if "gpu_busy" in message
                        else "out_of_memory"
                        if "memory" in message.lower()
                        else "validation_failed"
                    )
                    raise Problem(code, "Worker: " + message, 422)
                return result["result"]
            await asyncio.sleep(0.3)
        raise Problem(
            "deadline_exceeded", "Worker operation exceeded its deadline.", 409
        )

    async def watch_live_rpc(self, ident, deadline, on_event):
        # One persistent, private SSH channel avoids two SSH round trips per
        # sample. Read-only tail of this RPC's precreated files; no public port.
        code = """import json,pathlib,time
root=pathlib.Path(ROOT_VALUE)
position=0
pending=''
while time.time() < DEADLINE_VALUE:
 with (root / 'EVENT_FILE').open() as f:
  f.seek(position)
  pending+=f.read()
  position=f.tell()
 lines=pending.split('\\n')
 pending=lines.pop()
 for line in lines:
  if line.strip(): print(json.dumps({'event':json.loads(line)}),flush=True)
 try:
  result=json.loads((root / 'RESULT_FILE').read_text())
 except (ValueError,FileNotFoundError): result=None
 if result is not None:
  # Result publication follows all event writes. A second drain includes
  # the last samples/text before returning the completed measurement.
  with (root / 'EVENT_FILE').open() as f:
   f.seek(position)
   pending+=f.read()
  for line in pending.splitlines():
   if line.strip(): print(json.dumps({'event':json.loads(line)}),flush=True)
  print(json.dumps({'result':result}),flush=True)
  break
 time.sleep(0.04)
"""
        code = (code.replace("ROOT_VALUE", repr(self.session["root"]))
                .replace("DEADLINE_VALUE", repr(deadline))
                .replace("EVENT_FILE", "events-" + ident + ".jsonl")
                .replace("RESULT_FILE", "result-" + ident + ".json"))
        proc = await asyncio.create_subprocess_exec(
            "ssh", "-S", self.socket, "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
            "-o", "StrictHostKeyChecking=yes", "-o", "UserKnownHostsFile=" + self.known,
            self.host, "python3 -u -c " + shlex.quote(code),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            limit=1024 * 1024)
        try:
            async with asyncio.timeout(max(0.1, deadline - time.time())):
                while line := await proc.stdout.readline():
                    item = json.loads(line)
                    if "event" in item:
                        on_event(item["event"])
                    if "result" in item:
                        return item["result"]
            raise Problem("ssh_unavailable", "Live Wright observation channel closed.", 503, retryable=True)
        finally:
            if proc.returncode is None:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
            await proc.wait()

    async def inspect(self, deadline=None):
        if not self.session:
            await self.ssh("true")
            self.observed = {"gpus": [], "services": {}, "artifact_verified": False}
            self.observed_at = now()
            return self.observed
        self.observed = await self.rpc("inspect", deadline=deadline)
        self.observed_at = now()
        return self.observed

    async def load(
        self,
        c,
        deadline,
        lane="tuned",
        gpu_index=0,
        headroom=1024,
        recover=False,
        reset_guard=False,
    ):
        return await self.rpc(
            "load",
            {"config": c, "lane": lane, "gpu_index": gpu_index, "headroom": headroom},
            deadline,
            reset_cancel=recover,
            reset_guard=reset_guard,
        )

    async def generate(self, body, deadline, on_event=None):
        return await self.rpc("generate", body, deadline, on_event)

    async def stop(self, lane, deadline):
        return await self.rpc("stop", {"lane": lane}, deadline)

    async def cancel(self):
        if self.session:
            code = (
                "from pathlib import Path; p=Path("
                + repr(self.session["root"] + "/cancel")
                + "); p.write_text('cancel')"
            )
            await self.ssh("python3 -c " + shlex.quote(code))

    async def release(self):
        if not self.session:
            return
        job = self.session.get("job_id")
        if not job:
            candidates = (
                await self.ssh(
                    shlex.join(
                        [
                            "squeue",
                            "-h",
                            "-u",
                            self.host.split("@")[0],
                            "-n",
                            self.session["tag"],
                            "-o",
                            "%i",
                        ]
                    )
                )
            ).split()
            if len(candidates) > 1:
                raise Problem(
                    "rollback_failed", "Multiple jobs match the stored owner tag.", 409
                )
            job = candidates[0] if candidates else None
            if job and not job.isdigit():
                raise Problem(
                    "rollback_failed", "Unexpected scheduler job identity.", 409
                )
        if job:
            # Verify the scheduler's job name and user before cancellation; never trust stale numeric ID alone.
            info = (
                await self.ssh(shlex.join(["squeue", "-h", "-j", job, "-o", "%u|%j"]))
            ).strip()
            expected = self.host.split("@")[0] + "|" + self.session["tag"]
            if info and info != expected:
                raise Problem(
                    "rollback_failed",
                    "Stored job identity no longer matches; refusing cancellation.",
                    409,
                )
            if info:
                await self.ssh(shlex.join(["scancel", job]))
                for _ in range(20):
                    if not (
                        await self.ssh(
                            shlex.join(["squeue", "-h", "-j", job, "-o", "%i"])
                        )
                    ).strip():
                        break
                    await asyncio.sleep(0.5)
                else:
                    raise Problem(
                        "rollback_failed",
                        "Slurm has not confirmed job termination.",
                        503,
                    )
        self.session = None
        self.observed = None
        self.observed_at = None
        (self.state_dir / "wright.json").unlink(missing_ok=True)


class MockDriver:
    """Explicit synthetic transport used by frontend development and failure tests."""

    simulated = True

    def __init__(self, *_):
        self.session = None
        self.services = {}
        self.fail_quality = False
        self.delay = 0

    async def recover(self):
        pass

    async def ensure(self, r, deadline, model=MODEL):
        self.session = {
            "job_id": "MOCK",
            "model": model,
            "gpus_per_engine": gpu_count(model),
            "gpu_count": r.gpu_count,
            "expires_at": time.time() + 3600,
        }

    async def inspect(self, deadline=None):
        return {
            "gpus": [
                {
                    "id": "MOCK-GPU-" + str(i),
                    "node_id": "MOCK",
                    "local_index": i,
                    "label": "Simulated L40",
                    "name": "NVIDIA L40",
                    "memory_total_mib": 46068,
                    "memory_free_mib": 18000,
                    "temperature_c": 40,
                    "power_limit_w": 300,
                    "busy": bool(self.services),
                }
                for i in range(self.session["gpu_count"] if self.session else 0)
            ],
            "services": copy.deepcopy(self.services),
            "artifact_verified": bool(self.session),
            "runtime_hashes": {"mock": "SIMULATED"},
        }

    async def load(
        self,
        c,
        deadline,
        lane="tuned",
        gpu_index=0,
        headroom=1024,
        recover=False,
        reset_guard=False,
    ):
        if self.delay:
            await asyncio.sleep(self.delay)
        self.services[lane] = {
            "config": copy.deepcopy(c),
            "healthy": True,
            "context_per_slot": c["settings"]["context_per_slot"],
            "gpu_id": "MOCK-GPU-" + str(gpu_index),
        }
        return {}

    async def generate(self, b, deadline, on_event=None):
        if self.delay:
            await asyncio.sleep(self.delay)
        c = self.services[b.get("lane", "tuned")]["config"]
        o = 16 if b.get("purpose") == "quality" else b["max_tokens"]
        rate = 120 if c["engine"] == "llama.cpp" else 20
        if b.get("live") and on_event:
            on_event({"kind": "inference_started", "prompt_tokens": 100})
            on_event({"kind": "metrics", "decode_tps": rate, "prefill_tps": 1000,
                      "output_tokens": o, "timing_convention": "SIMULATED"})
            on_event({"lane": "tuned", "text": "Simulated answer.", "tokens": None, "tps": None})
        return {
            "prompt_tokens": 100,
            "output_tokens": o,
            "cached_tokens": 0,
            "decode_timed_tokens": o,
            "prefill_seconds": 0.1,
            "decode_seconds": o / rate,
            "wall_seconds": o / rate + 0.1,
            "load_seconds": 0.1,
            "queue_seconds": 0,
            "decode_tps": rate,
            "prefill_tps": 1000,
            "timing_convention": "SIMULATED",
            "output_cap": b["max_tokens"],
            "stop_reason": "eos",
            "completed": True,
            "quality_pass": not self.fail_quality
            if b.get("purpose") == "quality"
            else None,
            "gpu_ids": ["MOCK-GPU-0"],
            "min_free_gpu_memory_mib": {"MOCK-GPU-0": 18000},
            "peak_temperature_c": {"MOCK-GPU-0": 40},
            "request_hash": "MOCK",
            "final_text": '{"remaining":19,"doubled":38}',
            "service_healthy": True,
            "placement_matches": True,
            "context_matches": True,
            "configured_context_per_slot": c["settings"]["context_per_slot"],
            "memory_guard_pass": True,
            "warnings": ["SIMULATED: not measured on hardware."],
        }

    async def rpc(
        self,
        op,
        body=None,
        deadline=None,
        on_event=None,
        reset_cancel=False,
        reset_guard=False,
    ):
        if op == "race":
            return {
                "lanes": {
                    lane: await self.generate(dict(body, lane=lane), deadline)
                    for lane in ("default", "tuned")
                },
                "errors": {},
            }
        return await self.inspect()

    async def stop(self, lane, deadline):
        self.services.pop(lane, None)

    async def cancel(self):
        pass

    async def release(self):
        self.services = {}
        self.session = None
