# NOVA backend — ByteShape phase

Python FastAPI implements the [v2 contract](../docs/api/endpoint.md). Taeho owns this backend; frontend code remains separate. The service binds to your Mac's loopback interface, reads CANON, calls OpenRouter, and supervises a private Slurm worker on Wright. Only ByteShape is enabled for execution in this phase.

## Start

From the repository root, install once and launch one worker:

```sh
uv sync --locked
uv run uvicorn nova_backend.app:app --host 127.0.0.1 --port 8000 --workers 1
```

For frontend development without GPU or OpenRouter calls:

```sh
NOVA_MODE=mock NOVA_STATE_DIR=var/mock uv run uvicorn nova_backend.app:app --host 127.0.0.1 --port 8000 --workers 1
```

Mock responses always include `simulation: true`; measurements also carry a simulation warning. Never present them as live results. Use a separate state directory for mock and real modes. Run only one real backend instance against Wright.

The pairing token is generated with owner-only permissions in `var/backend/pairing-token` (or the chosen state directory). Read it locally and supply `X-Pairing-Token` on every request except `/health`. The frontend must keep it out of logs and source control. OpenRouter's key remains in macOS Keychain under service `nova-openrouter-api-key`, account your macOS username. Allow the Keychain read dialog when it appears. No API route returns the key. An `OPENROUTER_API_KEY` environment value is supported for non-macOS deployments; do not put it in a shell command or commit it.

Wright SSH uses the existing authenticated control connection. Override local connection paths if necessary:

```sh
export NOVA_SSH_HOST=taeholee@wright.hss.cmu.edu
export NOVA_SSH_CONTROL=/tmp/wright-glimmer-20261105-501/control
export NOVA_SSH_KNOWN_HOSTS=/tmp/wright-access-check-20261103-known_hosts
```

The backend never relaxes host-key checking. It allocates through account/partition `cmist`, QoS `cmist_priority`, and uses 12 CPUs / 64 GiB per GPU lane. Inference runs under `srun`, not on the login node. Registered model and runtime hashes are checked on the compute node. No model downloads or runtime builds happen during Optimize.

## Frontend flow

1. `/health`, then authenticated `/status`, `/profiles`, and `/capabilities?model=qwen3.8-27b`.
2. `POST /optimize` with `{"model":"qwen3.8-27b"}` and a fresh `Idempotency-Key`. Read `data: {JSON}` SSE events. Sampling changes are authorized by default; the agent prefers the recorded MTP5 / temperature 0.75 candidate. Explicit sampling locks still work.
3. `verify_only` retains a verified service and reports its measured decode. To also measure default Ollama, pass `"mode":"sequential_compare"`. Baseline execution is untouched Ollama; engine, template, context, and sampler differences are disclosed.
4. A disconnected stream leaves work running. Poll `/runs/{run_id}`. Repeating the same mutation key/body returns JSON with `replayed:true`; never assume every successful POST response is SSE.
5. `POST /race` with a prompt and explicit `"mode":"sequential"` uses the retained GPU. For simultaneous mode, first optimize with `"resources":{"gpu_count":2}`; lanes get different GPUs and CPU sets. No silent sequential fallback.
6. `/revert` with the optimize result's `rollback_id` restores the previous verified service, or unloads and releases the allocation when it was previously empty. `/runs/{id}/cancel` cancels an in-flight operation and records cleanup.

`/action` shares the same runner for apply, context lowering, quant selection and benchmark. `/chat` and `/diagnose` are read-only OpenRouter assistance. Unknown settings are rejected. Capability controls marked unsupported are descriptive coverage, not executable flags.

The default throughput test uses exactly `Write a short essay explaining the causes of the Industrial Revolution`, capped at 256 generated tokens. Basic correctness is checked separately with arithmetic. For the full demo essay, send this same prompt to `/race` with `max_tokens: 2048` so reasoning and the final essay have room to complete. The rehearsal script does this automatically. Historical CANON ledger rates do not predict essay speed. `workload` selects the historical evidence category; the demo probe itself remains the exact prompt above.

## Boundaries

- OpenRouter model: `openai/gpt-6-astra`, high effort, latency routing. No silent model/effort substitution. Priority service is requested first; an explicit unsupported-tier rejection retries the same model at high effort on the default tier. The returned effective tier is recorded. Other API errors remain visible; no model substitution occurs.
- No web search: the OpenRouter selector has only `select_configuration`, no web plugin or online model suffix. Local essay generation has no tools or retrieval. Astra uses the supplied CANON evidence and profiles.
- Defaults: 180-second operation deadline, at most two repairs, plus bounded cleanup. The live rehearsal can use 300 seconds to separate first allocation/hash startup from the presentation budget.
- One model process / one request slot per GPU. ByteShape contexts 2K–64K, fixed quant/runtime/KV precision, draft size 1–5. Experimental combinations require `allow_experimental`; exact recorded MTP5/0.75 does not.
- Allocation reuse is limited to this backend's owned allocation. Resource expansion requires reverting to unloaded first. Two-GPU racing must reserve two lanes up front.
- Baseline reuse via `baseline_run_id` is not enabled: measure a fresh baseline. Quant switching currently resolves only the installed ByteShape artifact. Glimmer and Flash return an explicit deferred-execution error.
- Race streams final-answer text only. Incremental token counts and rates can be null until the engine supplies final timings; no invented token counts. A capped race answer is not a passed quality check.
- A restart cleans the recorded owned job after checking its identity, marks interrupted runs failed, and requires fresh verification. It does not replay jobs. Historical SQLite records and idempotency keys remain.
- Stopping the backend releases its owned Slurm allocation. Shared services, other jobs and GPU power settings are untouched.

## Tests

```sh
uv run pytest -q
# Explicitly performs GPU work and OpenRouter calls, then releases its allocation:
uv run python scripts/live_byteshape.py
# Same GPU test with a chosen registered profile, without an OpenRouter call:
uv run python scripts/live_byteshape.py --profile-only
# Verify the parallel race on two isolated L40 lanes:
uv run python scripts/live_byteshape.py --simultaneous
```

The rehearsal measures allocation/asset preparation separately before starting the API operation deadline. Prepare before the presentation timer. Private run data is ignored under `var/`. The live rehearsal records raw response metadata there; the remote worker keeps native responses and launch manifests in its private per-job directory. The sanitized live report belongs in `docs/demo/`. A run's `execution.deployment_id` resolves to its retained private `state/deployments/<id>.json` record, which identifies the remote directory for its raw measurement and launch receipts. `repro_ref` resolves through that run record.
