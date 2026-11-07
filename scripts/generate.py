"""Send a terminal prompt to the verified Wright service observed by /live."""
import argparse
import json
import os
import sys
import uuid
from pathlib import Path
import httpx
from nova_backend.common import ROOT, MODEL
from nova_backend.engine import PROBE_PROMPT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", default=PROBE_PROMPT)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--state-dir", type=Path, default=Path(os.environ.get("NOVA_STATE_DIR", ROOT / "var/backend")))
    args = parser.parse_args()
    token = (args.state_dir / "pairing-token").read_text().strip()
    with httpx.Client(base_url=f"http://127.0.0.1:{args.port}", timeout=300) as client:
        with client.stream("POST", "/generate", headers={"X-Pairing-Token": token,
                "Idempotency-Key": "terminal-" + uuid.uuid4().hex},
                json={"model": MODEL, "prompt": args.prompt, "max_tokens": args.max_tokens}) as response:
            if response.status_code != 200:
                error = json.loads(response.read()).get("error", {})
                print(error.get("message", "Request failed."), file=sys.stderr)
                return 1
            for line in response.iter_lines():
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[6:])
                if event["type"] == "token":
                    print(event["text"], end="", flush=True)
                elif event["type"] == "done":
                    m = event["measurement"]
                    print(f"\nDecode: {m['decode_tps']:.2f} tok/s; output: {m['output_tokens']} tokens; completed: {m['completed']}", file=sys.stderr)
                    return 0
                elif event["type"] == "error":
                    print(event["error"]["message"], file=sys.stderr)
                    return 1
    print("Stream ended before completion; inspect the run in the backend.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
