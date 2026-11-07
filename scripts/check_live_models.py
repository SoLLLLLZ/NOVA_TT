"""Standalone Ollama comparison, then the actual OpenRouter/Astra production path."""
import argparse
import asyncio
import json
import socket
import time
from pathlib import Path
import httpx
import uvicorn
from nova_backend.app import create_app
from nova_backend.common import ROOT
from nova_backend.catalog import gpu_count, baseline_for
from nova_backend.engine import PROBE_PROMPT
from nova_backend.schemas import Resources


def parse(text):
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


async def main(model, baseline_receipt=None):
    root = ROOT / "var" / ("production-" + model + "-" + str(time.time_ns()))
    root.mkdir(parents=True, mode=0o700)
    prep_start = time.monotonic()
    app = create_app(root / "state", mock=False, prepare_model=model)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
    serving = asyncio.create_task(server.serve(sockets=[sock]))
    report = {"prompt": PROBE_PROMPT, "live": [], "received_monotonic": [], "generations": [], "model": model}
    observer = None
    try:
        while not server.started:
            if serving.done():
                await serving
            await asyncio.sleep(0.05)
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}",
                headers={"X-Pairing-Token": app.state.token}, timeout=360) as client:
            assert (await client.get("/health")).json()["contract_version"] == "2.1"
            assert (await client.get("/live", params={"model": model})).status_code == 404
            driver = app.state.engine.driver
            resources = Resources(gpu_count=gpu_count(model))
            report["preparation_seconds"] = time.monotonic() - prep_start
            print(json.dumps({"phase": "allocated"}), flush=True)
            # Standalone reference test: this does not call any production
            # endpoint or the selector. Both engines reuse the same physical GPUs.
            if baseline_receipt:
                prior = json.loads(Path(baseline_receipt).read_text())
                assert prior["model"] == model and prior["prompt"] == PROBE_PROMPT
                report["baseline"] = prior["baseline"]
                report["baseline_receipt"] = str(baseline_receipt)
            else:
                await driver.load(baseline_for(model), time.time() + 300, lane="default")
                report["baseline"] = await driver.generate({"lane": "default", "prompt": PROBE_PROMPT,
                    "max_tokens": 2048, "purpose": "throughput", "fixed_length": False,
                    "measurement_id": "standalone-ollama", "stream": False}, time.time() + 180)
                print(json.dumps({"phase": "standalone_ollama", "model": model,
                    "decode": report["baseline"]["decode_tps"], "completed": report["baseline"]["completed"]}), flush=True)
                await driver.stop("default", time.time() + 30)
            assert all(report["baseline"][key] is True for key in (
                "service_healthy", "placement_matches", "context_matches", "memory_guard_pass"))
            response = await client.post("/optimize", headers={"Idempotency-Key": "prepare"}, json={
                "model": model, "resources": resources.model_dump(), "mode": "verify_only",
                "budget": {"deadline_seconds": 300}})
            report["optimize"] = parse(response.text)
            optimized = report["optimize"][-1]
            print(json.dumps({"phase": "optimized", "type": optimized["type"], "error": optimized.get("error")}), flush=True)
            assert optimized["type"] == "done", optimized
            report["agent"] = {"model": app.state.engine.agent.model, "available": app.state.engine.agent.available, "effective_tier": app.state.engine.agent.effective_tier}
            assert report["agent"]["available"] is True
            assert optimized["before"] is None and optimized["speedup"] is None
            report["deployment"] = app.state.engine.driver.session.copy()
            waiting = asyncio.Event()

            async def observe():
                async with client.stream("GET", "/live", params={"model": model}) as response:
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
            for i in range(1):
                response = await client.post("/generate", headers={"Idempotency-Key": "essay-" + str(i)},
                    json={"model": model, "prompt": PROBE_PROMPT, "max_tokens": 2048})
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
            assert [e["type"] for e in report["live"]].count("inference_started") == 1
            assert (await client.get("/live", params={"model": model})).status_code == 404
            report["passed"] = True
    finally:
        if observer:
            if not observer.done():
                observer.cancel()
            await asyncio.gather(observer, return_exceptions=True)
        server.should_exit = True
        await serving
        (root / "report.json").write_text(json.dumps(report, indent=2))
        print("Receipt: " + str(root / "report.json"), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, choices=["qwen3.8-27b", "muse-glimmer", "qwen3.8-flash-next"])
    parser.add_argument("--baseline-receipt", type=Path, help="Reuse a completed standalone comparison receipt when retrying only production validation; never presented as a new baseline measurement.")
    args = parser.parse_args()
    asyncio.run(main(args.model, args.baseline_receipt))
