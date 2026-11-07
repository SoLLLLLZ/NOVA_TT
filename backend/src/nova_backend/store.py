import json, sqlite3
from pathlib import Path
from .common import now, uid, digest, Problem

TERMINAL = {"succeeded", "failed", "cancelled"}


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(
            "CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, snapshot TEXT NOT NULL); CREATE TABLE IF NOT EXISTS idem(key TEXT PRIMARY KEY, hash TEXT NOT NULL, run_id TEXT NOT NULL); CREATE TABLE IF NOT EXISTS events(run_id TEXT, sequence INTEGER, payload TEXT, PRIMARY KEY(run_id,sequence)); CREATE TABLE IF NOT EXISTS snapshots(id TEXT PRIMARY KEY, payload TEXT NOT NULL); CREATE TABLE IF NOT EXISTS profiles(id TEXT PRIMARY KEY, config TEXT NOT NULL);"
        )

    def get(self, rid):
        row = self.db.execute("SELECT snapshot FROM runs WHERE id=?", (rid,)).fetchone()
        if not row:
            raise Problem("not_found", "Unknown run.", 404)
        return json.loads(row[0])

    def save(self, s):
        self.db.execute(
            "INSERT OR REPLACE INTO runs VALUES(?,?)",
            (s["run_id"], json.dumps(s, allow_nan=False)),
        )
        self.db.commit()

    def existing(self, key, body):
        row = self.db.execute(
            "SELECT hash,run_id FROM idem WHERE key=?", (key,)
        ).fetchone()
        if row:
            if row[0] != digest(body):
                raise Problem(
                    "idempotency_conflict",
                    "Idempotency key was used for a different request.",
                    409,
                )
            return self.get(row[1])

    def create(self, key, body, operation, deadline):
        rid = uid("run")
        s = {
            "run_id": rid,
            "operation": operation,
            "state": "pending",
            "sequence": 0,
            "started_at": now(),
            "deadline_at": deadline,
            "progress": None,
            "current_step": None,
            "latest_config": None,
            "evidence": None,
            "validation": None,
            "measurements": [],
            "repairs": [],
            "result": None,
            "error": None,
            "cleanup": None,
        }
        with self.db:
            self.db.execute("INSERT INTO runs VALUES(?,?)", (rid, json.dumps(s)))
            self.db.execute("INSERT INTO idem VALUES(?,?,?)", (key, digest(body), rid))
        return s

    def bind_cancel(self, key, body, rid):
        with self.db:
            self.db.execute("INSERT INTO idem VALUES(?,?,?)", (key, digest(body), rid))

    def emit(self, rid, kind, **payload):
        s = self.get(rid)
        s["sequence"] += 1
        e = dict(payload, type=kind, run_id=rid, sequence=s["sequence"], at=now())
        with self.db:
            self.db.execute(
                "INSERT INTO events VALUES(?,?,?)",
                (rid, s["sequence"], json.dumps(e, allow_nan=False)),
            )
            self.db.execute(
                "UPDATE runs SET snapshot=? WHERE id=?", (json.dumps(s), rid)
            )
        return e

    def events(self, rid, after):
        return [
            json.loads(r[0])
            for r in self.db.execute(
                "SELECT payload FROM events WHERE run_id=? AND sequence>? ORDER BY sequence",
                (rid, after),
            )
        ]

    def snapshot(self, c):
        sid = uid("rollback")
        with self.db:
            self.db.execute("INSERT INTO snapshots VALUES(?,?)", (sid, json.dumps(c)))
        return sid

    def prior(self, sid):
        row = self.db.execute(
            "SELECT payload FROM snapshots WHERE id=?", (sid,)
        ).fetchone()
        if not row:
            raise Problem("not_found", "Unknown rollback ID.", 404)
        return json.loads(row[0])

    def unfinished(self):
        return [
            json.loads(r[0])
            for r in self.db.execute("SELECT snapshot FROM runs")
            if json.loads(r[0])["state"] not in TERMINAL
        ]

    def put_profile(self, c):
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO profiles VALUES(?,?)",
                (c["profile_id"], json.dumps(c)),
            )

    def profile(self, pid):
        r = self.db.execute("SELECT config FROM profiles WHERE id=?", (pid,)).fetchone()
        if not r:
            raise Problem("not_found", "Unknown registered profile.", 404)
        return json.loads(r[0])

    def profiles(self):
        return [
            json.loads(r[0]) for r in self.db.execute("SELECT config FROM profiles")
        ]
