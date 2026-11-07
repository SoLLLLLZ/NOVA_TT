import asyncio, time
import httpx, pytest
from nova_backend.agent import Agent
from nova_backend.common import Problem


async def test_malformed_provider_response_is_sanitized(monkeypatch):
    saved = httpx.AsyncClient
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content="not-json")
    )
    monkeypatch.setattr(
        "nova_backend.agent.httpx.AsyncClient",
        lambda **kwargs: saved(transport=transport, **kwargs),
    )
    agent = Agent()

    async def key():
        return "test-placeholder"

    agent.key = key
    with pytest.raises(Problem) as error:
        await agent.chat("hello", {}, time.time() + 1)
    assert error.value.error["code"] == "ai_unavailable"


async def test_total_deadline_includes_secret_access():
    agent = Agent()

    async def slow_key():
        await asyncio.sleep(10)

    agent.key = slow_key
    start = time.monotonic()
    with pytest.raises(Problem) as error:
        await agent.chat("hello", {}, time.time() + 0.03)
    assert error.value.error["code"] == "ai_unavailable"
    assert time.monotonic() - start < 0.5
