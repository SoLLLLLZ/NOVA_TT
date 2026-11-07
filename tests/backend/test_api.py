import asyncio, json
import pytest
from fastapi.testclient import TestClient
from nova_backend.app import create_app
from nova_backend.catalog import MODEL, PROFILES, resolve
from nova_backend.schemas import Optimize
from nova_backend.driver import MockDriver
from nova_backend.common import Problem


def events(response):
    return [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


@pytest.fixture
def client(tmp_path):
    driver = MockDriver()
    app = create_app(tmp_path, mock=True, driver=driver)
    with TestClient(app) as c:
        c.headers["X-Pairing-Token"] = app.state.token
        c.driver = driver
        c.engine = app.state.engine
        yield c


def post(c, path, body, key="test"):
    return c.post(path, json=body, headers={"Idempotency-Key": key})


def optimize(c, **kw):
    return events(post(c, "/optimize", {"model": MODEL, **kw}))[-1]


def test_auth_and_contract(client):
    assert client.get("/health").json()["contract_version"] == "2.1"
    assert (
        client.get("/status", headers={"X-Pairing-Token": "wrong"}).status_code == 401
    )
    assert (
        client.get("/capabilities").json()["fields"]["settings.draft_tokens"]["schema"][
            "maximum"
        ]
        == 5
    )
    assert client.get("/status").json()["simulation"] is True


def test_optimized_candidate_and_replay(client):
    result = optimize(client)
    assert result["type"] == "done", result
    assert result["config"]["settings"]["draft_tokens"] == 5
    assert result["config"]["settings"]["temperature"] == 0.75
    assert result["validation"]["status"] == "passed"
    assert result["before"] is None and result["speedup"] is None
    replay = post(client, "/optimize", {"model": MODEL})
    assert replay.json()["replayed"] is True
    assert replay.json()["run_id"] == result["run_id"]
    assert (
        post(
            client, "/optimize", {"model": MODEL, "mode": "sequential_compare"}
        ).status_code
        == 409
    )
    snapshot = client.get("/runs/" + result["run_id"]).json()
    assert (
        snapshot["state"] == "succeeded"
        and snapshot["result"]["config"] == result["config"]
    )


def test_compare_and_revert(client):
    result = optimize(client, mode="sequential_compare")
    assert result["type"] == "done", result
    assert result["speedup"] == 6
    reverted = events(
        post(client, "/revert", {"rollback_id": result["rollback_id"]}, "revert")
    )[-1]
    assert reverted["type"] == "done" and reverted["config"] is None
    assert client.driver.session is None


def test_quality_failure_never_promotes(client):
    client.driver.fail_quality = True
    result = optimize(client, budget={"max_repair_attempts": 1})
    assert result["type"] == "error" and result["error"]["code"] == "validation_failed"
    assert client.engine.current is None and client.driver.session is None
    assert client.get("/runs/" + result["run_id"]).json()["state"] == "failed"


@pytest.mark.parametrize(
    "body",
    [
        {"model": MODEL, "unknown": 1},
        {"model": MODEL, "overrides": {"settings": {"draft_tokens": "5"}}},
        {"model": MODEL, "overrides": {"settings": {"draft_tokens": True}}},
        {"model": MODEL, "overrides": {"settings": {"temperature": None}}},
        {"model": MODEL, "overrides": {"settings": {"extra_args": "rm -rf"}}},
        {"model": MODEL, "resources": {"gpu_ids": ["GPU-0"]}},
        {"model": MODEL, "resources": {"power_limit_w": 350.0}},
        {"model": MODEL, "constraints": {"runtime_requirements": {"bogus": True}}},
        {"model": MODEL, "capabilities_revision": "old"},
        {"model": "muse-glimmer"},
        {"model": "qwen3.8-flash-next"},
    ],
)
def test_invalid_inputs_do_not_allocate(client, body):
    r = post(client, "/optimize", body)
    assert r.status_code in (400, 409, 422), r.text
    assert client.driver.session is None


def test_sampling_can_be_locked(client):
    result = optimize(client, constraints={"allow_sampling_change": False})
    assert result["config"]["settings"]["temperature"] == 1.0
    assert result["config"]["settings"]["draft_tokens"] == 3


def test_context_constraint():
    with pytest.raises(Problem):
        resolve(
            Optimize(
                model=MODEL,
                overrides={
                    "settings": {"context_tokens": 4096, "context_per_slot": 4096}
                },
            )
        )
    c = resolve(
        Optimize(
            model=MODEL,
            constraints={"min_context_tokens": 4096},
            overrides={"settings": {"context_tokens": 4096, "context_per_slot": 4096}},
        )
    )
    assert c["settings"]["context_tokens"] == 4096


def test_actions_and_race(client):
    optimized = optimize(client)
    assert (
        post(client, "/race", {"model": MODEL, "prompt": "Hello"}, "race0").status_code
        == 409
    )
    race = events(
        post(
            client,
            "/race",
            {"model": MODEL, "prompt": "Hello", "mode": "sequential"},
            "race",
        )
    )[-1]
    assert race["type"] == "done", race
    assert race["speedup"] == 6 and client.engine.current is not None
    action = events(
        post(
            client,
            "/action",
            {
                "action": "run_benchmark",
                "params": {"model": MODEL, "purpose": "quality", "max_tokens": 2048},
            },
            "bench",
        )
    )[-1]
    assert action["type"] == "done" and action["applied"] is False
    lowered = events(
        post(
            client,
            "/action",
            {
                "action": "lower_context",
                "params": {
                    "model": MODEL,
                    "profile_id": optimized["config"]["profile_id"],
                    "context_per_slot": 4096,
                },
            },
            "lower",
        )
    )[-1]
    assert lowered["type"] == "done", lowered
    assert lowered["config"]["settings"]["context_per_slot"] == 4096


def test_cancel_and_duplicate_lock(client):
    async def exercise():
        e = client.engine
        e.driver.delay = 1
        req = Optimize(model=MODEL)
        s, _ = e.submit("optimize", req, "async", {"x": 1})
        await asyncio.sleep(0.05)
        with pytest.raises(Problem) as err:
            e.submit("optimize", req, "other", {"x": 2})
        assert err.value.error["code"] == "operation_in_progress"
        task = e.tasks[s["run_id"]]
        await e.cancel(s["run_id"])
        await task
        state = e.store.get(s["run_id"])
        assert (
            state["state"] == "cancelled" and state["cleanup"]["status"] == "completed"
        )
        assert e.current is None

    client.portal.call(exercise)


def test_chat_and_diagnose(client):
    assert (
        events(client.post("/chat", json={"message": "Explain MTP"}))[-1]["type"]
        == "done"
    )
    assert (
        client.post(
            "/diagnose", json={"model": MODEL, "error_code": "out_of_memory"}
        ).json()["can_auto_repair"]
        is False
    )


def test_cancel_before_task_starts(client):
    async def exercise():
        e = client.engine
        e.driver.delay = 1
        s, _ = e.submit("optimize", Optimize(model=MODEL), "instant", {"instant": True})
        t = e.tasks[s["run_id"]]
        await e.cancel(s["run_id"])
        await t
        assert e.store.get(s["run_id"])["state"] == "cancelled"
        assert e.active is None

    client.portal.call(exercise)


def test_large_body_and_action_unknown(client):
    assert client.post("/chat", content=b"x" * 140000).status_code == 400
    assert (
        post(
            client,
            "/action",
            {"action": "run_benchmark", "params": {"model": MODEL, "shell": "hello"}},
        ).status_code
        == 400
    )


def test_explicit_fixed_settings_select_compatible_profile(client):
    r = optimize(client, constraints={"fixed_settings": {"draft_tokens": 5}})
    assert r["type"] == "done" and r["config"]["settings"]["temperature"] == 0.75


def test_stale_rollback_does_not_stop_new_service(client):
    first = optimize(client)
    second = events(post(client, "/optimize", {"model": MODEL}, "second"))[-1]
    assert second["type"] == "done"
    assert (
        post(
            client, "/revert", {"rollback_id": first["rollback_id"]}, "old-revert"
        ).status_code
        == 409
    )
    assert client.engine.current is not None


def test_simultaneous_requires_two_lanes(client):
    optimized = optimize(client, resources={"gpu_count": 2})
    assert optimized["type"] == "done"
    r = events(
        post(
            client,
            "/race",
            {"model": MODEL, "prompt": "Explain inference", "mode": "simultaneous"},
            "parallel",
        )
    )
    assert r[-1]["type"] == "done", r[-1]
    assert {e["lane"] for e in r if e["type"] == "lane_done"} == {"default", "tuned"}
    assert r[-1]["mode"] == "simultaneous"


def test_persistent_idempotency_and_interrupted_recovery(tmp_path):
    from nova_backend.store import Store

    store = Store(tmp_path / "state.db")
    req = {"model": MODEL}
    s = store.create("stable", req, "optimize", "future")
    store.db.close()
    reopened = Store(tmp_path / "state.db")
    assert reopened.existing("stable", req)["run_id"] == s["run_id"]
    assert len(reopened.unfinished()) == 1
    reopened.db.close()


def test_mutations_require_idempotency(client):
    r = client.post("/optimize", json={"model": MODEL})
    assert r.status_code == 400 and client.driver.session is None


def test_missing_run_and_rollback(client):
    assert client.get("/runs/unknown").status_code == 404
    assert post(client, "/revert", {"rollback_id": "unknown"}).status_code == 404


def test_documented_objective_and_capability_revision(client):
    cap = client.get("/capabilities").json()
    assert cap["capabilities_revision"]
    assert (
        optimize(
            client,
            objective="decode",
            capabilities_revision=cap["capabilities_revision"],
        )["type"]
        == "done"
    )


def test_sampling_lock_preserves_active_sampler(client):
    first = optimize(client)
    assert first["config"]["settings"]["temperature"] == 0.75
    second = events(
        post(
            client,
            "/optimize",
            {"model": MODEL, "constraints": {"allow_sampling_change": False}},
            "locked-active",
        )
    )[-1]
    assert second["type"] == "done"
    assert second["config"]["settings"]["temperature"] == 0.75


def test_dynamic_profiles_can_be_reused(client):
    original = optimize(client)

    def lower(pid, n, key):
        return events(
            post(
                client,
                "/action",
                {
                    "action": "lower_context",
                    "params": {
                        "model": MODEL,
                        "profile_id": pid,
                        "context_per_slot": n,
                    },
                },
                key,
            )
        )[-1]

    one = lower(original["config"]["profile_id"], 4096, "lower1")
    two = lower(one["config"]["profile_id"], 2048, "lower2")
    assert two["type"] == "done", two
    assert two["config"]["settings"]["context_per_slot"] == 2048
    assert two["config"]["profile_id"] in [
        p["profile_id"] for p in client.get("/profiles").json()["profiles"]
    ]


def test_huge_integer_rejected_without_crash(client):
    r = post(
        client,
        "/optimize",
        {"model": MODEL, "overrides": {"settings": {"draft_tokens": 10**400}}},
    )
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_request"


def test_status_readiness_requires_observation_and_healthy_service(client):
    s = client.get("/status").json()
    assert s["models"][0]["ready"] is False and s["models"][0]["readiness_reasons"]
    optimize(client)
    client.driver.services["tuned"]["healthy"] = False
    s = client.get("/status").json()
    assert (
        s["is_tuned"] is False
        and s["current_config"] is None
        and s["models"][0]["ready"] is False
    )


def test_stream_matches_v2_keys(client):
    ev = events(post(client, "/optimize", {"model": MODEL}))
    assert {"mode", "started_at", "deadline_at"} <= set(ev[0])
    assert all({"name", "detail"} <= set(e) for e in ev if e["type"] == "step")
    assert all(
        e["phase"] in ("proposed", "effective") for e in ev if e["type"] == "config"
    )
    assert client.get("/health").json()["ok"] is True


def test_guard_reserve_survives_failed_replacement_and_race(client):
    e = client.engine
    original_load = e.driver.load
    original_generate = e.driver.generate
    heads = []
    fail = [False]

    async def load(*args, **kwargs):
        heads.append(
            (
                kwargs.get("lane", args[2] if len(args) > 2 else "tuned"),
                kwargs.get("headroom", 1024),
            )
        )
        return await original_load(*args, **kwargs)

    async def generate(body, deadline, **kwargs):
        result = await original_generate(body, deadline, **kwargs)
        if fail[0] and body.get("purpose") == "quality":
            result["quality_pass"] = False
            fail[0] = False
        return result

    e.driver.load = load
    e.driver.generate = generate
    optimize(client, constraints={"min_free_gpu_memory_mib": 8192})
    fail[0] = True
    failed = events(
        post(
            client,
            "/optimize",
            {"model": MODEL, "budget": {"max_repair_attempts": 0}},
            "fail-once",
        )
    )[-1]
    assert failed["type"] == "error" and failed["cleanup"]["status"] == "completed"
    assert heads[-1] == ("tuned", 8192) and e.current_headroom == 8192
    race = events(
        post(
            client,
            "/race",
            {"model": MODEL, "prompt": "Hello", "mode": "sequential"},
            "guard-race",
        )
    )[-1]
    assert race["type"] == "done"
    assert heads[-1] == ("tuned", 8192)


def test_repaired_effective_changes_describe_final_profile(client):
    e = client.engine
    original = e.driver.generate
    fail = [True]

    async def generate(body, deadline, **kwargs):
        r = await original(body, deadline, **kwargs)
        if fail[0] and body.get("purpose") == "quality":
            fail[0] = False
            r["quality_pass"] = False
        return r

    async def select(req, deadline, failures=None, current=None):
        return PROFILES[0 if failures else 1][
            "config"
        ], "Fallback selected." if failures else "Candidate selected."

    e.driver.generate = generate
    e.agent.select = select
    ev = events(post(client, "/optimize", {"model": MODEL}))
    assert ev[-1]["type"] == "done" and ev[-1]["reason"] == "Fallback selected."
    effective = next(
        x for x in ev if x["type"] == "config" and x["phase"] == "effective"
    )
    assert effective["config"]["settings"]["draft_tokens"] == 3
    assert (
        next(x for x in effective["changes"] if x["path"] == "settings.draft_tokens")[
            "to"
        ]
        == 3
    )
    assert not any(x["path"] == "settings.temperature" for x in effective["changes"])


def test_partial_race_failure_keeps_completed_lane(client):
    optimize(client, resources={"gpu_count": 2})
    original = client.driver.rpc

    async def rpc(op, body=None, deadline=None, **kwargs):
        result = await original(op, body, deadline, **kwargs)
        if op == "race":
            result["lanes"].pop("tuned")
            result["errors"]["tuned"] = "test failure"
        return result

    client.driver.rpc = rpc
    result = events(
        post(
            client,
            "/race",
            {"model": MODEL, "prompt": "Hello", "mode": "simultaneous"},
            "partial",
        )
    )[-1]
    assert result["type"] == "error" and result["error"]["code"] == "benchmark_failed"
    measured = next(
        m for m in result["partial_measurements"] if m["engine"] == "ollama"
    )
    assert measured["measurement_id"].startswith("race_")
    assert measured["artifact_ref"] == measured["measurement_id"] + "-raw.json"


def test_race_cancel_preempts_before_serial_cleanup(client):
    optimize(client)
    e = client.engine
    old_generate = e.driver.generate
    old_stop = e.driver.stop
    busy = [False]
    first = [True]
    calls = []

    async def generate(body, deadline, **kwargs):
        if first[0]:
            first[0] = False
            busy[0] = True
            await asyncio.sleep(60)
        return await old_generate(body, deadline, **kwargs)

    async def stop(lane, deadline):
        calls.append("stop:" + lane)
        if busy[0]:
            raise Problem("deadline_exceeded", "Stop queued behind generation.")
        return await old_stop(lane, deadline)

    async def cancel():
        calls.append("cancel")
        busy[0] = False

    e.driver.generate = generate
    e.driver.stop = stop
    e.driver.cancel = cancel

    async def exercise():
        from nova_backend.schemas import Race

        s, _ = e.submit(
            "race",
            Race(model=MODEL, prompt="Hello", mode="sequential"),
            "cancel-race",
            {"cancel-race": 1},
        )
        task = e.tasks[s["run_id"]]
        await asyncio.sleep(0.02)
        await e.cancel(s["run_id"])
        await task
        assert e.store.get(s["run_id"])["state"] == "cancelled"
        assert calls.index("cancel") < calls.index("stop:default")

    client.portal.call(exercise)
