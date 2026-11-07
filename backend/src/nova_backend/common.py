from __future__ import annotations
import hashlib, json, os, secrets
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(
    os.environ.get("NOVA_REPO_ROOT", Path(__file__).resolve().parents[3])
).resolve()
VERSION = "2.0"
MODEL = "qwen3.8-27b"


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def uid(prefix):
    return prefix + "_" + secrets.token_hex(10)


class Problem(Exception):
    def __init__(self, code, message, status=422, field=None, retryable=False):
        self.status = status
        self.error = {
            "code": code,
            "message": message,
            "diagnosable": code not in ("unauthorized", "bad_request"),
            "retryable": retryable,
        }
        if field:
            self.error["field"] = field
        super().__init__(message)


def private_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(value, f, allow_nan=False)
    os.replace(tmp, path)
