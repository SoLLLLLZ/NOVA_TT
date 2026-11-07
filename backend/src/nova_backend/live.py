"""Ephemeral observation of user requests, never benchmark/history replay."""
import asyncio
import time
from .common import Problem, now


class LiveFeed:
    def __init__(self, simulation=False):
        self.simulation = simulation
        self.listeners = set()
        self.started = None
        self.latest = None

    def publish(self, kind, **fields):
        event = {"type": kind, "at": now(), "simulation": self.simulation, **fields}
        if kind == "inference_started":
            self.started, self.latest = event, None
        elif kind == "metrics":
            self.latest = event
        elif kind in ("inference_done", "error"):
            self.started = self.latest = None
        for queue in list(self.listeners):
            if queue.full():
                # Never block GPU work or silently lose request boundaries.
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait({"type": "error", "at": now(), "error": Problem(
                    "runtime_unavailable", "Live observer fell behind; reconnect.",
                    503, retryable=True).error})
                self.listeners.discard(queue)
            else:
                queue.put_nowait(event)

    def close(self, message="The retained service is being changed; reconnect after it is ready."):
        self.publish("error", error=Problem("not_found", message, 404, retryable=True).error)
        self.listeners.clear()

    def subscribe(self, model, service_id):
        queue = asyncio.Queue(maxsize=64)
        self.listeners.add(queue)
        if self.started:
            queue.put_nowait(self.started)
            if self.latest:
                queue.put_nowait(self.latest)
        else:
            queue.put_nowait({"type": "waiting", "at": now(), "model": model,
                              "service_id": service_id, "simulation": self.simulation})
        return queue

    async def events(self, queue):
        sequence = 0
        last_metric = 0
        pending = None
        try:
            while True:
                timeout = max(0, 0.2 - (time.monotonic() - last_metric)) if pending else 5
                if pending and timeout == 0:
                    event, pending = pending, None
                    last_metric = time.monotonic()
                    sequence += 1
                    yield {**event, "sequence": sequence}
                    continue
                try:
                    event = await asyncio.wait_for(queue.get(), timeout)
                except TimeoutError:
                    if not pending:
                        yield None  # SSE heartbeat, not a metric
                    continue
                if event["type"] == "metrics":
                    # Keep the newest actual native sample until the next 200 ms
                    # delivery slot. Never interpolate, replay bursts, or repeat a
                    # rate when there is no new measurement.
                    pending = event
                    continue
                pending = None  # request boundary supersedes an undelivered sample
                if event["type"] == "inference_started":
                    last_metric = 0
                sequence += 1
                yield {**event, "sequence": sequence}
                if event["type"] == "error":
                    return
        finally:
            self.listeners.discard(queue)
