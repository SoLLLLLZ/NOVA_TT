import pytest

"""Exercise pure worker functions without importing its Slurm-only bootstrap."""

import ast, math, signal, time
from types import SimpleNamespace
from nova_backend.common import ROOT


def load_function(name, namespace):
    source = ast.parse((ROOT / "deploy/wright/worker.py").read_text())
    node = next(
        n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == name
    )
    exec(
        compile(ast.Module(body=[node], type_ignores=[]), "worker.py", "exec"),
        namespace,
    )
    return namespace[name]


def test_native_sampler_float_precision():
    match = load_function("sampler_matches", {"math": math})
    assert match(0.949999988079071, 0.95)  # pinned native response's float32 top_p
    assert match(0.75, 0.75) and match(20, 20, integer=True)
    assert match(0.0, 0) and match(1.0, 1)
    assert not match(20.0, 20, integer=True)
    assert not match(0.9, 0.95) and not match(True, 1) and not match(20.5, 20)


@pytest.mark.parametrize("returncode", [None, 0])
def test_telemetry_failure_terminates_owned_process(tmp_path, returncode):
    (tmp_path / "cancel").write_text("")
    calls = []
    iterations = iter([False, True])

    def unavailable():
        raise OSError("telemetry unavailable")

    scope = {
        "EXIT": SimpleNamespace(wait=lambda _: next(iterations)),
        "telemetry": unavailable,
        "VIOLATIONS": [],
        "ROOT": tmp_path,
        "is_cancelled": lambda: False,
        "ACTIVE_DEADLINE": 0,
        "SERVICES": {
            "tuned": {"process": SimpleNamespace(pid=123, poll=lambda: returncode)}
        },
        "os": SimpleNamespace(killpg=lambda *args: calls.append(args)),
        "signal": signal,
        "time": time,
    }
    load_function("guard", scope)()
    assert calls == ([(123, signal.SIGTERM)] if returncode is None else [])


def test_cancelled_queued_generation_is_rejected_until_explicit_recovery(tmp_path):
    (tmp_path / "cancel").write_text("cancel")
    scope = {
        "ROOT": tmp_path,
        "VIOLATIONS": [],
        "is_cancelled": lambda: (tmp_path / "cancel").read_text() == "cancel",
    }
    admit = load_function("admit_command", scope)
    with pytest.raises(RuntimeError, match="cancelled"):
        admit({"op": "generate"})
    assert (tmp_path / "cancel").read_text() == "cancel"
    with pytest.raises(RuntimeError, match="cancelled"):
        admit({"op": "load", "reset_guard": True})
    admit({"op": "stop"})
    assert (tmp_path / "cancel").read_text() == "cancel"
    admit({"op": "load", "reset_cancel": True})
    assert (tmp_path / "cancel").read_text() == ""


def test_missing_native_load_duration_uses_measured_wall_time():
    duration = load_function("preload_duration", {})
    assert duration({}, 2.5) == (2.5, "preload_wall")
    assert duration({"load_duration": None}, 2.5) == (2.5, "preload_wall")
    assert duration({"load_duration": 3_000_000_000}, 3.2) == (
        3.0,
        "native_load_duration",
    )
