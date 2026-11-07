import asyncio, time
import httpx, pytest
from nova_backend.agent import Agent
from nova_backend.common import Problem


async def test_concurrent_calls_read_keychain_once(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    agent = Agent()
    calls = 0

    async def read_keychain():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return "test-placeholder"

    monkeypatch.setattr(agent, "_read_keychain", read_keychain)
    assert await asyncio.gather(*(agent.key() for _ in range(5))) == ["test-placeholder"] * 5
    assert await agent.key() == "test-placeholder"
    assert calls == 1


async def test_failed_keychain_read_is_retryable(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    agent = Agent()
    calls = 0

    async def read_keychain():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise Problem("ai_unavailable", "Access denied.", 503)
        return "test-placeholder"

    monkeypatch.setattr(agent, "_read_keychain", read_keychain)
    with pytest.raises(Problem):
        await agent.key()
    assert await agent.key() == "test-placeholder"
    assert calls == 2


async def test_unauthorized_response_invalidates_cached_key(monkeypatch):
    saved = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(401))
    monkeypatch.setattr(
        "nova_backend.agent.httpx.AsyncClient",
        lambda **kwargs: saved(transport=transport, **kwargs),
    )
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    agent = Agent()
    agent._cached_key = "test-placeholder"
    with pytest.raises(Problem):
        await agent.chat("hello", {}, time.time() + 1)
    assert agent._cached_key is None


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


async def test_key_limit_error_is_actionable_without_provider_details(monkeypatch):
    saved = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(403, json={
        'error': {'message': 'private account URL', 'metadata': {'limit_source': 'openrouter_key_limit'}}}))
    monkeypatch.setattr('nova_backend.agent.httpx.AsyncClient', lambda **kw: saved(transport=transport, **kw))
    agent = Agent()
    async def key():
        return 'test-placeholder'
    agent.key = key
    with pytest.raises(Problem) as error:
        await agent.chat('hello', {}, time.time() + 1)
    assert 'spending limit reached' in error.value.error['message']
    assert 'private account URL' not in str(error.value.error)
    assert agent.available is False
