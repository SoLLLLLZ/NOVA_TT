"""Contract-shape tests for the mock backend.  python3 -m unittest tests/mocks/test_mock_server.py"""

import json
import os
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid
from http.server import ThreadingHTTPServer

os.environ.setdefault("MOCK_SPEED", "0.01")
os.environ.setdefault("MOCK_QUIET", "1")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mock_server  # noqa: E402

CODE = mock_server.PAIRING_CODE


class MockServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), mock_server.Handler)
        cls.server.daemon_threads = True
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        mock_server.SCENARIO = "success"
        mock_server.STATE.__init__()

    # -- helpers -------------------------------------------------------------
    def request(self, method, path, body=None, token=CODE, key=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Pairing-Token"] = token
        if key:
            headers["Idempotency-Key"] = key
        data = json.dumps(body).encode() if body is not None else None
        return urllib.request.urlopen(urllib.request.Request(self.base + path, data=data, method=method,
                                                             headers=headers), timeout=10)

    def json(self, method, path, body=None, **kw):
        try:
            with self.request(method, path, body, **kw) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read())

    def stream(self, path, body, key=None):
        with self.request("POST", path, body, key=key or str(uuid.uuid4())) as r:
            self.assertEqual(r.headers["Content-Type"], "text/event-stream")
            events = []
            for raw in r:
                line = raw.decode().strip()
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))
            return events

    def optimize(self, model="qwen3.8-27b", key=None):
        return self.stream("/optimize", {"model": model, "mode": "verify_only",
                                         "resources": {"target_id": "wright", "gpu_type": "L40", "gpu_count": 1,
                                                       "same_node": True},
                                         "constraints": {"allow_sampling_change": True}}, key=key)

    # -- tests ---------------------------------------------------------------
    def test_health_has_no_auth(self):
        status, body = self.json("GET", "/health", token=None)
        self.assertEqual(status, 200)
        self.assertEqual(body, {"ok": True, "contract_version": "2.1"})

    def test_status_requires_pairing(self):
        status, body = self.json("GET", "/status", token=None)
        self.assertEqual(status, 401)
        self.assertEqual(body["error"]["code"], "unauthorized")

    def test_status_shape(self):
        status, body = self.json("GET", "/status")
        self.assertEqual(status, 200)
        self.assertEqual(body["contract_version"], "2.1")
        self.assertEqual([m["id"] for m in body["models"]], ["qwen3.8-27b", "qwen3.8-flash-next", "muse-glimmer"])
        self.assertEqual(body["all_gpus"][0]["label"], "L40")
        self.assertIn("memory_total_mib", body["all_gpus"][0])
        for key in ("allocation", "current_config", "active_run_id", "is_tuned", "optimizer_agent"):
            self.assertIn(key, body)

    def test_optimize_stream_order_and_done(self):
        events = self.optimize()
        types = [e["type"] for e in events]
        self.assertEqual(types[0], "start")
        self.assertEqual(types[-1], "done")
        self.assertEqual([e["sequence"] for e in events], list(range(1, len(events) + 1)))
        effective = [e for e in events if e["type"] == "config" and e["phase"] == "effective"][0]
        paths = {c["path"]: c for c in effective["changes"]}
        self.assertEqual(paths["engine"]["to"], "llama.cpp")
        self.assertEqual(paths["settings.draft_tokens"]["to"], 5)
        self.assertEqual(paths["settings.temperature"]["from"], 1.0)
        self.assertEqual(paths["settings.temperature"]["to"], 0.75)
        done = events[-1]
        self.assertTrue(done["applied"])
        self.assertEqual(done["validation"]["status"], "passed")
        self.assertIsNone(done["before"])
        self.assertIsNone(done["speedup"])
        self.assertTrue(done["rollback_id"])

    def test_unknown_field_rejected(self):
        status, body = self.json("POST", "/optimize", {"model": "qwen3.8-27b", "bogus": 1}, key="k1")
        self.assertEqual(status, 400)
        self.assertEqual(body["error"]["field"], "bogus")

    def test_idempotent_replay_and_conflict(self):
        key = str(uuid.uuid4())
        self.optimize(key=key)
        status, body = self.json("POST", "/optimize", {"model": "qwen3.8-27b", "mode": "verify_only",
                                                       "resources": {"target_id": "wright", "gpu_type": "L40",
                                                                     "gpu_count": 1, "same_node": True},
                                                       "constraints": {"allow_sampling_change": True}}, key=key)
        self.assertEqual(status, 200)
        self.assertTrue(body["replayed"])
        self.assertEqual(body["state"], "succeeded")
        status, body = self.json("POST", "/optimize", {"model": "muse-glimmer"}, key=key)
        self.assertEqual(status, 409)
        self.assertEqual(body["error"]["code"], "idempotency_conflict")

    def test_fail_scenario_ends_with_error(self):
        mock_server.SCENARIO = "fail"
        events = self.optimize()
        self.assertEqual(events[-1]["type"], "error")
        self.assertEqual(events[-1]["error"]["code"], "out_of_memory")
        self.assertIn("cleanup", events[-1])

    def test_repair_scenario_uses_fallback(self):
        mock_server.SCENARIO = "repair"
        events = self.optimize()
        self.assertIn("repair", [e["type"] for e in events])
        self.assertEqual(events[-1]["config"]["settings"]["draft_tokens"], 3)

    def test_live_before_optimize_is_404(self):
        status, body = self.json("GET", "/live?model=qwen3.8-27b")
        self.assertEqual(status, 404)

    def test_live_receives_terminal_inference(self):
        self.optimize()
        received = []

        def listen():
            with self.request("GET", "/live?model=qwen3.8-27b") as r:
                for raw in r:
                    line = raw.decode().strip()
                    if line.startswith("data: "):
                        received.append(json.loads(line[6:]))
                        if received[-1]["type"] == "inference_done":
                            return

        listener = threading.Thread(target=listen, daemon=True)
        listener.start()
        for _ in range(100):
            if received:
                break
            time.sleep(0.01)
        status, _ = self.json("POST", "/mock/inference", {"model": "qwen3.8-27b"})
        self.assertEqual(status, 202)
        listener.join(timeout=10)
        types = [e["type"] for e in received]
        self.assertEqual(types[0], "waiting")
        self.assertIn("inference_started", types)
        self.assertIn("metrics", types)
        self.assertEqual(types[-1], "inference_done")
        self.assertGreater(received[-1]["measurement"]["decode_tps"], 0)

    def test_revert_restores_defaults(self):
        done = self.optimize()[-1]
        events = self.stream("/revert", {"rollback_id": done["rollback_id"]})
        self.assertEqual(events[-1]["type"], "done")
        self.assertTrue(events[-1]["restored"])
        self.assertEqual(events[-1]["config"]["engine"], "ollama")
        _, status = self.json("GET", "/status")
        self.assertFalse(status["is_tuned"])

    def test_changes_use_the_selected_models_defaults_after_switching(self):
        done = self.optimize()[-1]
        self.stream("/revert", {"rollback_id": done["rollback_id"]})
        events = self.optimize(model="muse-glimmer")
        effective = [e for e in events if e["type"] == "config" and e["phase"] == "effective"][0]
        paths = {c["path"]: c for c in effective["changes"]}
        self.assertEqual(paths["settings.temperature"]["from"], 0.8)
        self.assertEqual(paths["settings.top_p"]["to"], 0.95)

    def listen_live(self, model, received):
        with self.request("GET", f"/live?model={model}") as r:
            for raw in r:
                line = raw.decode().strip()
                if line.startswith("data: "):
                    received.append(json.loads(line[6:]))
                    if received[-1]["type"] == "inference_done":
                        return

    def test_default_run_streams_default_speed(self):
        events = self.stream("/action", {"action": "apply_default", "params": {"model": "qwen3.8-27b"}})
        done = events[-1]
        self.assertEqual(done["type"], "done")
        self.assertEqual(done["config"]["engine"], "ollama")
        self.assertIsNone(done["validation"])
        self.assertTrue(done["rollback_id"])
        _, status = self.json("GET", "/status")
        self.assertFalse(status["is_tuned"])
        self.assertEqual(status["current_config"]["engine"], "ollama")

        received = []
        listener = threading.Thread(target=self.listen_live, args=("qwen3.8-27b", received), daemon=True)
        listener.start()
        for _ in range(100):
            if received:
                break
            time.sleep(0.01)
        self.assertEqual(self.json("POST", "/mock/inference", {"model": "qwen3.8-27b"})[0], 202)
        listener.join(timeout=10)
        started = [e for e in received if e["type"] == "inference_started"][0]
        self.assertFalse(started["tuned"])
        self.assertEqual(started["engine"], "ollama")
        self.assertLess(received[-1]["measurement"]["decode_tps"], 40)

        # Optimizing afterwards compares against the running default.
        events = self.optimize()
        effective = [e for e in events if e["type"] == "config" and e["phase"] == "effective"][0]
        self.assertIn("engine", {c["path"] for c in effective["changes"]})

    def test_run_snapshot(self):
        done = self.optimize()[-1]
        status, snap = self.json("GET", f"/runs/{done['run_id']}")
        self.assertEqual(status, 200)
        self.assertEqual(snap["state"], "succeeded")
        self.assertEqual(snap["result"]["rollback_id"], done["rollback_id"])


if __name__ == "__main__":
    unittest.main()
