"""Opt-in real /live rehearsal on one Wright L40; no OpenRouter call."""
import asyncio
import json
import socket
import time
from pathlib import Path
import httpx
import uvicorn
from nova_backend.app import create_app
from nova_backend.common import MODEL, ROOT
from nova_backend.catalog import PROFILES
from nova_backend.engine import PROBE_PROMPT
from nova_backend.schemas import Resources


def parse(text):
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


async def main():
    root = ROOT / "var" / ("live-speedometer-" + str(time.time_ns()))
    root.mkdir(parents=True, mode=0o700)
    app = create_app(root / "state", mock=False)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
    serving = asyncio.create_task(server.serve(sockets=[sock]))
    report = {"prompt": PROBE_PROMPT, "live": [], "received_monotonic": [], "generations": []}
    observer = None
    try:
        while not server.started:
            if serving.done():
                await serving
            await asyncio.sleep(0.05)
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}",
                headers={"X-Pairing-Token": app.state.token}, timeout=360) as client:
            assert (await client.get("/health")).json()["contract_version"] == "2.1"
            assert (await client.get("/live", params={"model": MODEL})).status_code == 404
            await app.state.engine.driver.ensure(Resources(), time.time() + 240)
            print(json.dumps({"phase": "allocated"}), flush=True)
            response = await client.post("/optimize", headers={"Idempotency-Key": "prepare"}, json={
                "model": MODEL, "profile_id": PROFILES[1]["config"]["profile_id"],
                "budget": {"deadline_seconds": 180}})
            report["optimize"] = parse(response.text)
            optimized = report["optimize"][-1]
            print(json.dumps({"phase": "optimized", "type": optimized["type"], "error": optimized.get("error")}), flush=True)
            assert optimized["type"] == "done", optimized
            report["deployment"] = app.state.engine.driver.session.copy()
            waiting = asyncio.Event()

            async def observe():
                async with client.stream("GET", "/live", params={"model": MODEL}) as response:
                    assert response.status_code == 200
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            event = json.loads(line[6:])
                            report["live"].append(event)
                            report["received_monotonic"].append(time.monotonic())
                            if event["type"] == "waiting":
                                waiting.set()
            observer = asyncio.create_task(observe())
            await asyncio.wait_for(waiting.wait(), 10)
            for i in range(2):
                response = await client.post("/generate", headers={"Idempotency-Key": "essay-" + str(i)},
                    json={"model": MODEL, "prompt": PROBE_PROMPT, "max_tokens": 2048})
                generated = parse(response.text)
                report["generations"].append(generated)
                final = generated[-1]
                print(json.dumps({"phase": "essay", "index": i, "type": final["type"],
                    "error": final.get("error"), "measurement": final.get("measurement")}), flush=True)
                assert final["type"] == "done", final
                await asyncio.sleep(0.1)
                request = final["run_id"]
                samples = [e for e in report["live"] if e["type"] == "metrics" and e["request_id"] == request]
                assert len(samples) >= 5, samples
                finished = [e for e in report["live"] if e["type"] == "inference_done" and e["request_id"] == request]
                assert finished[0]["measurement"] == final["measurement"]
                assert final["measurement"]["origin"] == "live" and not final["simulation"]
            response = await client.post("/revert", headers={"Idempotency-Key": "revert"}, json={"rollback_id": optimized["rollback_id"]})
            report["revert"] = parse(response.text)
            await asyncio.wait_for(observer, 15)
            assert report["live"][-1]["type"] == "error"
            assert [e["sequence"] for e in report["live"]] == list(range(1, len(report["live"]) + 1))
            assert [e["type"] for e in report["live"]].count("inference_started") == 2
            assert (await client.get("/live", params={"model": MODEL})).status_code == 404
            report["passed"] = True
    finally:
        if observer and not observer.done():
            observer.cancel()
            await asyncio.gather(observer, return_exceptions=True)
        server.should_exit = True
        await serving
        (root / "report.json").write_text(json.dumps(report, indent=2))
        print("Receipt: " + str(root / "report.json"), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
