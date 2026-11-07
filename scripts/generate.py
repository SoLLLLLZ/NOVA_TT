"""Send a terminal prompt to the verified Wright service observed by /live."""
import argparse
import json
import os
import sys
import uuid
from pathlib import Path
import httpx
from nova_backend.common import ROOT, MODEL, private_json
from nova_backend.engine import PROBE_PROMPT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", default=PROBE_PROMPT)
    parser.add_argument("--interactive", action="store_true", help="Select the retained model, then type a prompt")
    parser.add_argument("--model", default=MODEL, choices=[MODEL, "muse-glimmer", "qwen3.8-flash-next"])
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--state-dir", type=Path, default=Path(os.environ.get("NOVA_STATE_DIR", ROOT / "var/backend")))
    args = parser.parse_args()
    token = (args.state_dir / "pairing-token").read_text().strip()
    with httpx.Client(base_url=f"http://127.0.0.1:{args.port}", timeout=300) as client:
        if args.interactive:
            status_response = client.get("/status", headers={"X-Pairing-Token": token})
            status_response.raise_for_status()
            status = status_response.json()
            config = status.get("current_config")
            if not status.get("is_tuned") or not config or config["model"] != args.model:
                print("Optimize this model in the widget first.", file=sys.stderr)
                return 1
            print(f"Optimized {args.model} | {config['engine']} | Wright job {status['allocation']['id']}")
            print(f"Profile: {config['profile_id']} | draft {config['settings']['draft_tokens']} | temperature {config['settings']['temperature']}")
            args.prompt = input(">>> ").strip()
            if not args.prompt:
                return 0
        receipt = {"model": args.model, "prompt": args.prompt, "events": []}
        with client.stream("POST", "/generate", headers={"X-Pairing-Token": token,
                "Idempotency-Key": "terminal-" + uuid.uuid4().hex},
                json={"model": args.model, "prompt": args.prompt, "max_tokens": args.max_tokens}) as response:
            if response.status_code != 200:
                error = json.loads(response.read()).get("error", {})
                print(error.get("message", "Request failed."), file=sys.stderr)
                return 1
            for line in response.iter_lines():
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[6:])
                receipt["events"].append(event)
                if event["type"] == "token":
                    print(event["text"], end="", flush=True)
                elif event["type"] == "done":
                    m = event["measurement"]
                    private_json(ROOT / "var/terminal" / (event["run_id"] + ".json"), receipt)
                    print(f"\nDecode: {m['decode_tps']:.2f} tok/s; output: {m['output_tokens']} tokens; completed: {m['completed']}", file=sys.stderr)
                    return 0
                elif event["type"] == "error":
                    print(event["error"]["message"], file=sys.stderr)
                    return 1
    print("Stream ended before completion; inspect the run in the backend.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
