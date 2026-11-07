"""Transparent standalone Ollama demo on an owned Wright allocation (not a tool endpoint)."""
import argparse
import asyncio
import fcntl
import json
import signal
import time
from pathlib import Path
from nova_backend.catalog import baseline_for, gpu_count, manifest_for
from nova_backend.common import ROOT, MODEL, private_json, uid
from nova_backend.driver import WrightDriver
from nova_backend.schemas import Resources

STATE = ROOT / 'var/ollama-demo'


def lock(name):
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    handle = (STATE / name).open('a')
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise RuntimeError('Another standalone Ollama operation owns this demo. Stop it first.')
    return handle


async def serve(model):
    owner = lock('serve.lock')
    driver = WrightDriver(STATE)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    print('Standalone Ollama on WRIGHT L40 — no Astra, no optimization.', flush=True)
    try:
        await driver.recover()
        (STATE / 'ready.json').unlink(missing_ok=True)
        print('Allocating via Slurm and verifying installed weights/runtime…', flush=True)
        async def prepare():
            await driver.ensure(Resources(gpu_count=gpu_count(model)), time.time()+600, model=model)
            manifest = manifest_for(model)
            binary = manifest.get('shared_root', manifest['asset_root']) + '/ollama-0.40.13/bin/ollama'
            print(f"Slurm job {driver.session['job_id']}; model {model}; {gpu_count(model)} L40 GPU(s).", flush=True)
            print(f'Wright command: {binary} serve', flush=True)
            print('Private loopback server; untouched model defaults. Loading…', flush=True)
            await driver.load(baseline_for(model), time.time()+300, lane='default')
            obs = await driver.inspect()
            private_json(STATE/'ready.json', {'model':model,'job_id':driver.session['job_id'],'gpu_ids':[g['id'] for g in obs['gpus']]})
            print(f'READY. In another Terminal: ./scripts/ollama-wright run {model}', flush=True)
            print('After the baseline, Ctrl+C HERE releases Ollama before widget optimization.', flush=True)
        preparing = asyncio.create_task(prepare())
        stopping = asyncio.create_task(stop.wait())
        done, _ = await asyncio.wait([preparing, stopping], return_when=asyncio.FIRST_COMPLETED)
        if preparing in done:
            await preparing
            try:
                await asyncio.wait_for(stopping, max(1, driver.session['expires_at']-time.time()-10))
            except asyncio.TimeoutError:
                print('Demo allocation lifetime reached.', flush=True)
        else:
            preparing.cancel()
            await asyncio.gather(preparing, return_exceptions=True)
        stopping.cancel()
    finally:
        (STATE/'ready.json').unlink(missing_ok=True)
        await driver.release()
        owner.close()
        print('Ollama stopped. Owned Slurm allocation released.', flush=True)


async def run(model):
    request_lock = lock('request.lock')
    try:
        if not (STATE/'ready.json').exists():
            raise RuntimeError('Start ./scripts/ollama-wright serve and wait for READY before running a prompt.')
        ready = json.loads((STATE/'ready.json').read_text())
        if ready['model'] != model:
            raise RuntimeError('The standalone server is serving a different model.')
        driver = WrightDriver(STATE)
        driver.session = json.loads((STATE/'wright.json').read_text())
        if ready['job_id'] != driver.session['job_id']:
            raise RuntimeError('Standalone readiness belongs to an expired allocation.')
        obs = await driver.inspect()
        service = obs['services'].get('default', {})
        if not service.get('healthy') or service['config']['engine'] != 'ollama':
            raise RuntimeError('No healthy standalone Ollama service.')
        print(f"Default Ollama 0.40.13 | {model} | Wright job {ready['job_id']}")
        print('Only output cap = 2048; other inference settings are Ollama defaults.')
        prompt = input('>>> ').strip()
        if not prompt:
            return
        ident = uid('ollama')
        try:
            result = await driver.generate({'lane':'default','prompt':prompt,'max_tokens':2048,
                'purpose':'throughput','fixed_length':False,'measurement_id':ident,'stream':True},
                time.time()+180, on_event=lambda e: print(e.get('text',''),end='',flush=True))
        except BaseException:
            await driver.cancel()
            raise
        private_json(STATE/(ident+'.json'),{'model':model,'prompt':prompt,'measurement':result,'deployment':driver.session})
        print(f"\n\nDefault Ollama decode: {result['decode_tps']:.2f} tok/s")
        print(f"Prefill: {result['prefill_tps']:.2f} tok/s | output: {result['output_tokens']} | completed: {result['completed']}")
        print(f'Receipt: var/ollama-demo/{ident}.json')
        if not all(result[k] for k in ('service_healthy','placement_matches','context_matches','memory_guard_pass')):
            raise RuntimeError('Baseline validation failed; do not use this rate.')
    finally:
        request_lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['serve','run'])
    parser.add_argument('model', nargs='?', default=MODEL, choices=[MODEL,'muse-glimmer','qwen3.8-flash-next'])
    args = parser.parse_args()
    try:
        asyncio.run(serve(args.model) if args.command=='serve' else run(args.model))
    except (Exception, KeyboardInterrupt) as error:
        print(f'\nStopped: {error}')
        return 1
    return 0

if __name__=='__main__':
    raise SystemExit(main())
