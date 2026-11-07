#!/usr/bin/env python3
"""Pretend the student just ran the tuned model from their terminal.

Tells the mock backend to stream one fake inference to GET /live subscribers,
which flips the widget from SETUP OPTIMIZED to LIVE SPEED.

    python3 tests/mocks/simulate_terminal.py --model qwen3.8-27b
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default=None, help="catalog model ID (default: whichever model is tuned)")
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--code", default=os.environ.get("NOVA_PAIRING_CODE", "7K4-92X"))
    args = parser.parse_args()

    body = json.dumps({"model": args.model} if args.model else {}).encode()
    request = urllib.request.Request(f"{args.base}/mock/inference", data=body, method="POST", headers={
        "Content-Type": "application/json", "X-Pairing-Token": args.code})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            print("Inference started:", json.loads(response.read())["request_id"])
            return 0
    except urllib.error.HTTPError as err:
        print("Mock refused:", json.loads(err.read())["error"]["message"], file=sys.stderr)
        return 1
    except urllib.error.URLError as err:
        print("Mock backend not reachable:", err.reason, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
