import asyncio
import json
import time
import math
import pytest
from fastapi.testclient import TestClient
from nova_backend.app import create_app
from nova_backend.common import MODEL, Problem
from nova_backend.live import LiveFeed
from nova_backend.driver import MockDriver
from test_api import events, optimize, post
from test_worker import load_function


def test_live_auth_models_and_no_start(tmp_path):
    driver = MockDriver()
    app = create_app(tmp_path, mock=True, driver=driver)
    with TestClient(app) as client:
        assert client.get('/live', params={'model': MODEL}).status_code == 401
        client.headers['X-Pairing-Token'] = app.state.token
        assert client.get('/live', params={'model': 'unknown'}).json()['error']['code'] == 'model_not_found'
        for model in (MODEL, 'muse-glimmer', 'qwen3.8-flash-next'):
            result = client.get('/live', params={'model': model})
            assert result.status_code == 404
            assert result.json()['error']['code'] == 'not_found'
        assert client.get('/live').status_code == 400
        assert post(client, '/generate', {'model': MODEL, 'prompt': 'hi'}).status_code == 404
        assert driver.session is None and not driver.services


async def test_idle_reconnect_boundaries_and_disconnect():
    feed = LiveFeed()
    queue = feed.subscribe(MODEL, 'service')
    stream = feed.events(queue)
    assert (await anext(stream))['type'] == 'waiting'
    feed.publish('inference_started', request_id='a', model=MODEL, service_id='service', prompt_tokens=None)
    assert (await anext(stream))['sequence'] == 2
    feed.publish('metrics', request_id='a', decode_tps=47, prefill_tps=None, output_tokens=12, timing_convention='native')
    assert (await anext(stream))['decode_tps'] == 47
    reconnect = feed.events(feed.subscribe(MODEL, 'service'))
    assert (await anext(reconnect))['sequence'] == 1
    assert (await anext(reconnect))['type'] == 'metrics'
    await reconnect.aclose()
    assert len(feed.listeners) == 1
    feed.publish('inference_done', request_id='a', measurement={'origin': 'live'})
    assert (await anext(stream))['type'] == 'inference_done'
    idle = feed.events(feed.subscribe(MODEL, 'service'))
    assert (await anext(idle))['type'] == 'waiting'  # no stale speed
    await idle.aclose()
    feed.publish('inference_started', request_id='b')
    assert (await anext(stream))['request_id'] == 'b'
    feed.close()
    assert (await anext(stream))['type'] == 'error'
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    assert not feed.listeners


async def test_bounded_observers_and_rate_limit():
    feed = LiveFeed()
    q = feed.subscribe(MODEL, 'service')
    for i in range(100):
        feed.publish('metrics', output_tokens=i)
    assert q.qsize() == 1 and q.get_nowait()['type'] == 'error'
    assert not feed.listeners
    q = feed.subscribe(MODEL, 'service')
    stream = feed.events(q)
    await anext(stream)  # waiting
    feed.publish('metrics', output_tokens=1)
    assert (await anext(stream))['output_tokens'] == 1
    feed.publish('metrics', output_tokens=2)
    feed.publish('inference_done', request_id='x')
    assert (await anext(stream))['type'] == 'inference_done'  # burst sample coalesced
    await stream.aclose()


def test_generate_and_probe_isolation_replay_and_revert(tmp_path):
    app = create_app(tmp_path, mock=True)
    with TestClient(app) as c:
        c.headers['X-Pairing-Token'] = app.state.token
        optimized = optimize(c)
        engine = app.state.engine
        assert engine.live.started is None and engine.live.latest is None
        q = c.portal.call(engine.observe_live, MODEL)
        assert c.portal.call(q.get)['type'] == 'waiting'
        body = {'model': MODEL, 'prompt': 'User request', 'max_tokens': 256}
        result = events(post(c, '/generate', body, key='generate'))[-1]
        assert result['type'] == 'done'
        observed = [c.portal.call(q.get) for _ in range(3)]
        assert [e['type'] for e in observed] == ['inference_started', 'metrics', 'inference_done']
        assert all(e['simulation'] is True for e in observed)
        assert observed[-1]['measurement'] == result['measurement']
        assert post(c, '/generate', body, key='generate').json()['replayed'] is True
        assert q.empty()  # replay must not reexecute or publish history
        assert post(c, '/generate', {**body, 'prompt': 'different'}, key='generate').status_code == 409
        reverted = events(post(c, '/revert', {'rollback_id': optimized['rollback_id']}, key='revert'))[-1]
        assert reverted['type'] == 'done'
        assert c.portal.call(q.get)['type'] == 'error'
        assert c.get('/live', params={'model': MODEL}).status_code == 404


def test_generate_failure_ends_observers_and_restores(tmp_path):
    class FailingDriver(MockDriver):
        async def generate(self, body, deadline, on_event=None):
            if body.get('live'):
                on_event({'kind': 'inference_started', 'prompt_tokens': None})
                raise Problem('runtime_unavailable', 'Fixture generation failure')
            return await super().generate(body, deadline, on_event)
    app = create_app(tmp_path, mock=True, driver=FailingDriver())
    with TestClient(app) as c:
        c.headers['X-Pairing-Token'] = app.state.token
        optimize(c)
        engine = app.state.engine
        q = c.portal.call(engine.observe_live, MODEL)
        c.portal.call(q.get)
        result = events(post(c, '/generate', {'model': MODEL, 'prompt': 'hi'}, key='fail'))[-1]
        assert result['type'] == 'error'
        assert result['cleanup']['status'] == 'completed'
        assert c.portal.call(q.get)['type'] == 'inference_started'
        assert c.portal.call(q.get)['type'] == 'error'
        assert q.empty()  # restoration quality probe not broadcast
        assert engine.current is not None


def test_native_metrics_never_estimates_or_nonfinite():
    metrics = load_function('live_metrics', {'math': math})
    assert metrics({'content': 'a lot of text'}) is None
    native = {'prompt_n': 20, 'prompt_ms': 50, 'predicted_n': 101, 'predicted_ms': 2000}
    m = metrics({'timings': native})
    assert m['decode_tps'] == 50 and m['output_tokens'] == 101 and m['prefill_tps'] == 400
    for bad in (float('inf'), float('nan'), 0, -1, True):
        assert metrics({'timings': {**native, 'predicted_ms': bad}}) is None
    assert metrics({'timings': {**native, 'prompt_ms': 0}})['prefill_tps'] is None


async def test_live_delivery_targets_five_hz_without_repeating_samples():
    feed = LiveFeed()
    q = feed.subscribe(MODEL, 'service')
    stream = feed.events(q)
    await anext(stream)

    async def source():
        for i in range(25):
            feed.publish('metrics', output_tokens=i)
            await asyncio.sleep(0.04)
        feed.publish('inference_done', request_id='x')

    task = asyncio.create_task(source())
    seen = []
    async for event in stream:
        if event['type'] == 'inference_done':
            break
        seen.append((time.monotonic(), event['output_tokens']))
    await task
    await stream.aclose()
    assert 4 <= len(seen) <= 6
    assert all(b[0] - a[0] >= 0.19 for a, b in zip(seen, seen[1:]))
    assert all(b[1] > a[1] for a, b in zip(seen, seen[1:]))


async def test_persistent_transport_partial_lines_and_final_drain(tmp_path, monkeypatch):
    import shlex
    import sys
    from nova_backend.driver import WrightDriver
    driver = WrightDriver(tmp_path)
    driver.session = {'job_id': 'fixture', 'root': str(tmp_path)}
    (tmp_path / 'events-fixture.jsonl').write_text('')
    (tmp_path / 'result-fixture.json').write_text('null')
    create = asyncio.create_subprocess_exec

    async def local_transport(*args, **kwargs):
        assert args[0] == 'ssh' and 'StrictHostKeyChecking=yes' in args
        command = shlex.split(args[-1])
        return await create(sys.executable, *command[1:], **kwargs)

    monkeypatch.setattr(asyncio, 'create_subprocess_exec', local_transport)

    async def publish():
        await asyncio.sleep(0.08)
        with (tmp_path / 'events-fixture.jsonl').open('a') as f:
            f.write('{"kind":"metrics",')
            f.flush()
            await asyncio.sleep(0.08)
            f.write('"output_tokens":11}\n')
            f.flush()
            await asyncio.sleep(0.08)
            f.write('{"kind":"metrics","output_tokens":22}\n')
        (tmp_path / 'result-fixture.json').write_text(json.dumps({'ok': True, 'result': {'done': True}}))

    publisher = asyncio.create_task(publish())
    samples = []
    result = await driver.watch_live_rpc('fixture', time.time() + 5, samples.append)
    await publisher
    assert [e['output_tokens'] for e in samples] == [11, 22]
    assert result == {'ok': True, 'result': {'done': True}}


def test_generate_cancellation_closes_feed_and_recovers(tmp_path):
    from nova_backend.schemas import Generate

    class SlowDriver(MockDriver):
        async def generate(self, body, deadline, on_event=None):
            if body.get('live'):
                on_event({'kind': 'inference_started', 'prompt_tokens': None})
                await asyncio.sleep(10)
            return await super().generate(body, deadline, on_event)

    app = create_app(tmp_path, mock=True, driver=SlowDriver())
    with TestClient(app) as c:
        c.headers['X-Pairing-Token'] = app.state.token
        optimize(c)

        async def exercise():
            engine = app.state.engine
            q = engine.observe_live(MODEL)
            q.get_nowait()
            req = Generate(model=MODEL, prompt='hello')
            run, _ = engine.submit('generate', req, 'cancel-live', {'request': req.model_dump()})
            task = engine.tasks[run['run_id']]
            started = await asyncio.wait_for(q.get(), 1)
            assert started['type'] == 'inference_started'
            with pytest.raises(Problem) as error:
                engine.submit('generate', req, 'conflict', {'request': req.model_dump()})
            assert error.value.status == 409
            await engine.cancel(run['run_id'])
            await task
            assert (await q.get())['type'] == 'error'
            assert engine.current is not None and engine.active is None
            assert engine.store.get(run['run_id'])['state'] == 'cancelled'

        c.portal.call(exercise)


@pytest.mark.parametrize('changed_during_check', [False, True])
async def test_health_observation_does_not_override_new_operation(tmp_path, monkeypatch, changed_during_check):
    from nova_backend.engine import Engine
    from nova_backend.store import Store
    from nova_backend.catalog import PROFILES
    from nova_backend.schemas import Resources
    driver = MockDriver()
    engine = Engine(Store(tmp_path / 'runs.sqlite3'), driver, None)
    await driver.ensure(Resources(), time.time() + 10)
    engine.current = PROFILES[1]['config']
    engine.live_ready = True
    q = engine.live.subscribe(MODEL, 'service')
    q.get_nowait()
    original_sleep = asyncio.sleep

    async def fast_sleep(_):
        await original_sleep(0)

    async def failed_inspect(deadline=None):
        if changed_during_check:
            engine.submission_revision += 1
            engine.live.listeners.clear()
        raise Problem('ssh_unavailable', 'Fixture unavailable', 503)

    monkeypatch.setattr(asyncio, 'sleep', fast_sleep)
    monkeypatch.setattr(driver, 'inspect', failed_inspect)
    try:
        await engine.monitor_live()
        assert engine.live_ready is changed_during_check
        if changed_during_check:
            assert q.empty()
        else:
            assert q.get_nowait()['type'] == 'error'
            with pytest.raises(Problem) as error:
                engine.observe_live(MODEL)
            assert error.value.status == 404
    finally:
        engine.store.db.close()
