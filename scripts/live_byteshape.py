"""Opt-in live API rehearsal. Reads Keychain internally; never prints credentials."""

import json, time, sys
from nova_backend.catalog import PROFILES
from nova_backend.schemas import Resources
from fastapi.testclient import TestClient
from nova_backend.app import create_app
from nova_backend.common import ROOT, MODEL


def events(r):
    return [json.loads(x[6:]) for x in r.text.splitlines() if x.startswith("data: ")]


def main():
    root = ROOT / "var/live-byteshape"
    root.mkdir(parents=True, exist_ok=True)
    app = create_app(root / "state", mock=False)
    simultaneous = "--simultaneous" in sys.argv
    resources = Resources(gpu_count=2 if simultaneous else 1)
    report_path = root / ("simultaneous-report.json" if simultaneous else "report.json")
    report = {
        "started": time.time(),
        "model": MODEL,
        "race_mode": "simultaneous" if simultaneous else "sequential",
    }
    with TestClient(app) as c:
        c.headers["X-Pairing-Token"] = app.state.token
        report["status_before"] = c.get("/status").json()
        print(
            json.dumps(
                {"phase": "status", "connection": report["status_before"]["connection"]}
            ),
            flush=True,
        )
        prepare_start = time.monotonic()

        async def prepare():
            await app.state.engine.driver.ensure(resources, time.time() + 240)

        c.portal.call(prepare)
        report["preparation_seconds"] = time.monotonic() - prepare_start
        print(
            json.dumps({"phase": "prepared", "seconds": report["preparation_seconds"]}),
            flush=True,
        )
        r = c.post(
            "/optimize",
            headers={"Idempotency-Key": "live-" + str(time.time_ns())},
            json={
                "model": MODEL,
                "mode": "verify_only" if simultaneous else "sequential_compare",
                "resources": resources.model_dump(),
                **(
                    {"profile_id": PROFILES[1]["config"]["profile_id"]}
                    if "--profile-only" in sys.argv
                    else {}
                ),
                "budget": {"deadline_seconds": 180 if simultaneous else 300, "max_repair_attempts": 2},
            },
        )
        report["http_status"] = r.status_code
        report["events"] = events(r) if r.status_code == 200 else r.json()
        report_path.write_text(json.dumps(report, indent=2))
        if isinstance(report["events"], list):
            terminal = report["events"][-1]
            print(
                json.dumps(
                    {
                        "phase": "optimize",
                        "type": terminal["type"],
                        "error": terminal.get("error"),
                        "validation": terminal.get("validation"),
                        "speedup": terminal.get("speedup"),
                        "before_decode": (terminal.get("before") or {}).get(
                            "decode_tps"
                        ),
                        "after_decode": (terminal.get("after") or {}).get("decode_tps"),
                    }
                ),
                flush=True,
            )
            if terminal["type"] == "done":
                race = c.post(
                    "/race",
                    headers={"Idempotency-Key": "live-race-" + str(time.time_ns())},
                    json={
                        "model": MODEL,
                        "mode": "simultaneous" if simultaneous else "sequential",
                        "resources": resources.model_dump(),
                        "prompt": "Explain how a rainbow forms in three concise sentences.",
                        "max_tokens": 256,
                        "budget": {"deadline_seconds": 180},
                    },
                )
                report["race"] = (
                    events(race) if race.status_code == 200 else race.json()
                )
                print(
                    json.dumps(
                        {
                            "phase": "race",
                            "result": report["race"][-1]
                            if isinstance(report["race"], list)
                            else report["race"],
                        }
                    ),
                    flush=True,
                )
                reverted = c.post(
                    "/revert",
                    headers={"Idempotency-Key": "live-revert-" + str(time.time_ns())},
                    json={"rollback_id": terminal["rollback_id"]},
                )
                report["revert"] = events(reverted)
                print(
                    json.dumps({"phase": "revert", "result": report["revert"][-1]}),
                    flush=True,
                )
        else:
            print(
                json.dumps({"phase": "optimize", "error": report["events"]}), flush=True
            )
        report["status_after"] = c.get("/status").json()
    report_path.write_text(json.dumps(report, indent=2))
    print("Receipt: " + str(report_path.relative_to(ROOT)), flush=True)


if __name__ == "__main__":
    main()
