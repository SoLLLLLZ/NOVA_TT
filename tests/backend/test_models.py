import copy
import json
import pytest
from fastapi.testclient import TestClient
from nova_backend.app import create_app
from nova_backend.catalog import MODEL, profiles_for, manifest_for, gpu_count, capabilities, resolve
from nova_backend.schemas import Optimize
from nova_backend.driver import MockDriver
from nova_backend.common import Problem
from test_api import events, post
from test_worker import load_function

MODELS = [MODEL, 'muse-glimmer', 'qwen3.8-flash-next']


@pytest.mark.parametrize('model', MODELS)
def test_production_pipeline_never_loads_ollama(tmp_path, model):
    class ProductionDriver(MockDriver):
        async def load(self, config, *args, **kwargs):
            assert config['engine'] == 'llama.cpp'
            assert config['model'] == model
            return await super().load(config, *args, **kwargs)
    app = create_app(tmp_path, mock=True, driver=ProductionDriver())
    with TestClient(app) as c:
        c.headers['X-Pairing-Token'] = app.state.token
        catalog = c.get('/profiles', params={'model': model}).json()['profiles']
        assert catalog and all(p['config']['model'] == model and p['config']['engine'] == 'llama.cpp' for p in catalog)
        cap = c.get('/capabilities', params={'model': model}).json()
        assert cap['contract_version'] == '2.1'
        result = events(post(c, '/optimize', {'model': model, 'resources': {'gpu_count': gpu_count(model)}}, 'optimize'))[-1]
        assert result['type'] == 'done', result
        assert result['before'] is None and result['speedup'] is None
        assert result['validation']['status'] == 'passed'
        assert result['config']['model'] == model
        status = c.get('/status').json()
        assert [m['id'] for m in status['models'] if m['loaded']] == [model]
        current = next(m for m in status['models'] if m['id'] == model)
        assert current['requirements']['context_per_slot'] == result['config']['settings']['context_per_slot']
        assert all(not m['race']['sequential_available'] and not m['race']['simultaneous_available'] for m in status['models'])
        for rejected in ({'model': model, 'mode': 'sequential_compare'},):
            response = post(c, '/optimize', rejected, 'old-mode')
            assert response.status_code == 409 and response.json()['error']['code'] == 'unsupported_setting'
        assert post(c, '/race', {'model': model, 'prompt': 'hello'}, 'race').status_code == 409
        generated = events(post(c, '/generate', {'model': model, 'prompt': 'hello'}, 'generate'))[-1]
        assert generated['type'] == 'done'
        assert generated['measurement']['profile_id'] == result['config']['profile_id']
        other = next(m for m in MODELS if m != model)
        assert post(c, '/generate', {'model': other, 'prompt': 'hello'}, 'wrong-model').status_code == 404
        assert post(c, '/optimize', {'model': other}, 'switch').status_code == 409
        reverted = events(post(c, '/revert', {'rollback_id': result['rollback_id']}, 'revert'))[-1]
        assert reverted['type'] == 'done' and app.state.engine.driver.session is None


def test_model_specific_caps_and_cross_model_profile_rejection():
    for model, cap in [('muse-glimmer', 15), ('qwen3.8-flash-next', 2)]:
        assert capabilities(model)['fields']['settings.draft_tokens']['schema']['maximum'] == cap
        with pytest.raises(Problem):
            resolve(Optimize(model=model, resources={'gpu_count': gpu_count(model)}, profile_id=profiles_for(MODEL)[0]['config']['profile_id']))
        with pytest.raises(Problem):
            resolve(Optimize(model=model, resources={'gpu_count': gpu_count(model)}, overrides={'settings': {'draft_tokens': cap + 1}}))
    for count in (1, 2, 4, 5):
        with pytest.raises(Problem) as error:
            resolve(Optimize(model='qwen3.8-flash-next', resources={'gpu_count': count}))
        assert error.value.error['code'] == 'allocation_unavailable'
    assert len(manifest_for('qwen3.8-flash-next')['artifact']['files']) == 6
    assert manifest_for('muse-glimmer')['runtime_hashes']['libllama.so.0.4.0'] != manifest_for(MODEL)['runtime_hashes']['libllama.so.0.4.0']


def test_glimmer_final_channel_and_incremental_markers():
    final = load_function('final_text', {})
    marker = '<|start|>assistant to=user<|message|>'
    assert final('private reasoning', 'muse-glimmer') == ''
    for i in range(len(marker)):
        assert final('private reasoning' + marker[:i], 'muse-glimmer', streaming=True) == ''
    assert final('private reasoning' + marker + '{"remaining":19,"doubled":38}\n', 'muse-glimmer') == '{"remaining":19,"doubled":38}'
    assert final('private reasoning' + marker + 'Answer<|end|>', 'muse-glimmer', streaming=True) == 'Answer'
    assert final('private reasoning' + marker + 'Answer<', 'muse-glimmer', streaming=True) == 'Answer'
    assert final('private</think>Answer', MODEL, streaming=True) == 'Answer'


async def test_astra_receives_only_selected_models_profiles_and_evidence(monkeypatch):
    from nova_backend.agent import Agent
    agent = Agent()
    for model in ('muse-glimmer', 'qwen3.8-flash-next'):
        async def completion(messages, deadline, tools):
            body = json.loads(messages[-1]['content'])
            assert body['request']['model'] == model
            assert all(p['config']['model'] == model for p in body['profiles'])
            assert all(r['model'] == model for r in body['canon'] if r['record_type'] == 'configuration')
            assert body['capabilities']['model'] == model
            assert len(tools) == 1 and tools[0]['function']['name'] == 'select_configuration'
            chosen = body['profiles'][-1]['config']['profile_id']
            return {'tool_calls': [{'function': {'name': 'select_configuration', 'arguments': json.dumps({'profile_id': chosen, 'reason': 'Evidence-backed selection', 'lesson_ids': []})}}]}
        monkeypatch.setattr(agent, 'completion', completion)
        config, _ = await agent.select(Optimize(model=model, resources={'gpu_count': gpu_count(model)}), 9999999999)
        assert config['model'] == model


def test_guard_covers_all_three_flash_devices(tmp_path):
    import signal
    from types import SimpleNamespace
    samples = [dict(memory_free_mib=10000, temperature_c=40) for _ in range(3)]
    samples[2]['memory_free_mib'] = 500
    calls = []
    iterations = iter([False, True])
    service = {'process': SimpleNamespace(pid=123, poll=lambda: None), 'gpu_index': 0,
               'gpu_indices': [0, 1, 2], 'headroom': 1024}
    scope = {'EXIT': SimpleNamespace(wait=lambda _: next(iterations)), 'telemetry': lambda: samples,
             'VIOLATIONS': [], 'is_cancelled': lambda: False, 'ACTIVE_DEADLINE': 0,
             'SERVICES': {'tuned': service}, 'os': SimpleNamespace(killpg=lambda *args: calls.append(args)),
             'signal': signal}
    load_function('guard', scope)()
    assert calls == [(123, signal.SIGTERM)]
    assert service['min_free_by_gpu'][2] == 500


def test_model_specific_worker_cpu_and_hash_manifest():
    # Exact launch settings and identities are checked independently of the
    # response mocks: Flash must preserve its three-device draft placement;
    # Glimmer must retain its own patched library and original draft head.
    flash = manifest_for('qwen3.8-flash-next')
    args = flash['llama_argv']
    assert args[args.index('--spec-draft-device') + 1] == 'CUDA2'
    assert args[args.index('--fit-target') + 1] == '1024,1024,4096'
    assert flash['runtime_env'] == {'FLASH_NEXT_FORCE_MMQ': '1'}
    assert len([f for f in flash['artifact']['files'] if f['role'] == 'target']) == 4
    glimmer = manifest_for('muse-glimmer')
    assert glimmer['runtime_dir'].endswith('wright-glimmer-1l40-20261105/runtime/bin')
    assert next(f for f in glimmer['artifact']['files'] if f['role'] == 'draft')['name'] == 'dflash-kquant.gguf'


def test_preparation_reserves_model_without_loading_or_calling_agent(tmp_path):
    class PrepareDriver(MockDriver):
        async def load(self, *args, **kwargs):
            pytest.fail('Preparation must not load any engine')
    class NoAgent:
        async def select(self, *args, **kwargs):
            pytest.fail('Preparation must not call Astra')
    driver = PrepareDriver()
    app = create_app(tmp_path, mock=True, driver=driver, agent=NoAgent(), prepare_model='qwen3.8-flash-next')
    with TestClient(app):
        assert driver.session['model'] == 'qwen3.8-flash-next'
        assert driver.session['gpu_count'] == 3
        assert app.state.engine.current is None
    assert driver.session is None


def test_failed_preparation_releases_allocation(tmp_path):
    class FailingDriver(MockDriver):
        async def ensure(self, *args, **kwargs):
            await super().ensure(*args, **kwargs)
            raise Problem('runtime_unavailable', 'Preflight failed')
    driver = FailingDriver()
    app = create_app(tmp_path, mock=True, driver=driver, prepare_model='muse-glimmer')
    with pytest.raises(Problem):
        with TestClient(app):
            pass
    assert driver.session is None


def test_desktop_origin_keeps_pairing_required(tmp_path):
    app = create_app(tmp_path, mock=True)
    with TestClient(app) as client:
        headers = {"Origin":"app://widget", "Access-Control-Request-Method":"GET", "Access-Control-Request-Headers":"X-Pairing-Token"}
        response = client.options('/status', headers=headers)
        assert response.headers['access-control-allow-origin']=='app://widget'
        assert client.get('/status', headers={"Origin":"app://widget"}).status_code==401
        headers['Origin']='https://untrusted.example'
        assert 'access-control-allow-origin' not in client.options('/status', headers=headers).headers
