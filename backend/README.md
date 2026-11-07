# NOVA backend

FastAPI implements [contract v2.1](../docs/api/endpoint.md) for ByteShape Qwen 27B, Muse Glimmer, and Qwen Flash Next. It reads CANON, calls OpenRouter's GPT-6 Astra at high reasoning, applies a registered llama.cpp profile on Wright, verifies it, and retains the private service for terminal generation.

**Production Optimize never runs Ollama, for any of the three models.** Default Ollama is a standalone demo comparison. The old `sequential_compare` optimization mode and `/race` route return `409 unsupported_setting`; status advertises both race modes unavailable. `/profiles` returns only optimized llama.cpp profiles. Existing response fields `before` and `speedup` remain null.

## Start

From the repository root:

```sh
uv sync --locked
uv run uvicorn nova_backend.app:app --host 127.0.0.1 --port 8000 --workers 1
```

For the Flash demo, reserve its three GPUs and verify its large files before the presentation:

```sh
NOVA_PREPARE_MODEL=qwen3.8-flash-next uv run uvicorn nova_backend.app:app --host 127.0.0.1 --port 8000 --workers 1
```

Wait for `Application startup complete`. This optional startup preparation has a separate 600-second limit, runs no model and calls neither Ollama nor Astra. It retains the verified allocation for the subsequent normal `/optimize` request. Preparation failure or backend shutdown releases it. ByteShape and Glimmer model IDs are supported too. A cold Flash file check measured 332 seconds; it must not be counted as a sub-five-minute optimization. Without this option, all preparation remains inside Optimize's ordinary deadline.

Mock development (no GPU or OpenRouter calls):

```sh
NOVA_MODE=mock NOVA_STATE_DIR=var/mock uv run uvicorn nova_backend.app:app --host 127.0.0.1 --port 8000 --workers 1
```

Mock events and measurements are explicitly marked `simulation:true`. Use separate state directories for mock and real operation. Run one real backend against Wright. The pairing token is owner-only at `var/backend/pairing-token` (or `NOVA_STATE_DIR`). Supply `X-Pairing-Token` except on `/health`; never log the token.

OpenRouter's key remains in macOS Keychain, service `nova-openrouter-api-key`, account your macOS username. If first-time access prompts, choose **Always Allow** for this item's `/usr/bin/security` reader. The backend caches it only in process memory and clears it on a 401. Restart after replacing the key. `OPENROUTER_API_KEY` is supported for non-macOS deployments; never commit it or put its value in shell commands.

Wright uses the existing authenticated SSH control connection, with strict host-key checks:

```sh
export NOVA_SSH_HOST=taeholee@wright.hss.cmu.edu
export NOVA_SSH_CONTROL=/tmp/wright-glimmer-20261105-501/control
export NOVA_SSH_KNOWN_HOSTS=/tmp/wright-access-check-20261103-known_hosts
```

## Production flow

1. Read `/health`, authenticated `/status`, `/profiles?model=<id>`, and `/capabilities?model=<id>`.
2. POST `/optimize` with a new `Idempotency-Key`, selected model and its required GPU count. `verify_only` is the default and only enabled mode. Flash requires `resources.gpu_count:3`; one GPU is the default for ByteShape/Glimmer. There is no silent fallback to fewer GPUs.
3. Read the SSE stream through terminal `done`. Success requires a completed, correct arithmetic answer, healthy service, matching context/placement and memory headroom. A separate 256-token demo essay probe supplies decode/prefill rates. The returned rollback ID restores the prior owned configuration or releases the allocation.
4. Keep `GET /live?model=<id>` open, and send terminal requests with the helper below. Lost operation streams do not cancel work: poll `/runs/{run_id}`; duplicate mutation keys return the existing run as JSON. `/runs/{id}/cancel` interrupts an active operation and records cleanup.
5. Revert to unloaded before changing model families. Registries and Slurm workers are model-specific; a retained allocation is not silently reassigned to a different model.

| Model ID | GPUs per engine | Tested optimized profile family |
| --- | ---: | --- |
| `qwen3.8-27b` | 1 L40 | ByteShape IQ3_S, 64K context, Q8 KV, MTP3 or MTP5 |
| `muse-glimmer` | 1 L40 | UD-Q4_K_XL, 256K context, F16 KV, patched runtime, DFlash11 or DFlash15 |
| `qwen3.8-flash-next` | 3 L40s on one node | Four UD-Q4_K_XL shards, 128K context, F16 KV, shared Q8 MTP2 on CUDA2, preserved MMQ/lazy profile |

Astra receives only the selected model's compatible registered profiles, relevant L40 configuration rows, and qualitative CANON lessons. Sampling changes are allowed by default; explicit locks still apply. No web tool/plugin is provided. Unsupported settings fail explicitly. Capability limits describe accepted inputs, not proof that every combination has been benchmarked.

## Live speedometer

After Optimize, run on the Mac from the repository root:

```sh
uv run python scripts/generate.py --model muse-glimmer
uv run python scripts/generate.py --model qwen3.8-flash-next
# ByteShape is the default model if --model is omitted.
```

The default prompt is exactly `Write a short essay explaining the causes of the Industrial Revolution`. Use `--prompt`, `--max-tokens`, `--state-dir`, or `--port` as needed. The helper reads pairing locally, calls `/generate`, streams only final-answer text, and prints final native decode speed. It neither calls Astra nor reloads the model.

`/live` starts no work and emits `waiting`, `inference_started`, `metrics`, `inference_done`, and terminal `error` with per-connection sequence numbers. It targets **5 updates/sec** using the latest native timing sample, including reasoning-token counts; it never invents rates or estimates from text chunks. Rates are running request averages, not rolling instantaneous estimates. Transport delays can reduce delivery frequency. The final measurement uses `(predicted_n - 1) / native decode seconds`.

Optimize probes do not appear on `/live`. The stream persists across terminal requests and reconnects during generation without replaying old completed speeds. Replacement, failure, expiry, shutdown or revert closes it. Direct requests to private engine ports are not instrumented. Glimmer's `assistant to=user` final channel is extracted before any text is displayed.

## Standalone comparison and validation

These scripts are explicit developer/demo tests, not production optimization endpoints:

```sh
uv run pytest -q
uv run python scripts/check_live_models.py --model muse-glimmer
uv run python scripts/check_live_models.py --model qwen3.8-flash-next
uv run python scripts/check_live_models.py --model qwen3.8-27b
```

Each rehearsal prepares an owned Slurm allocation, checks all model/runtime hashes, runs default Ollama separately, stops it, then calls the real `/optimize` endpoint with **no explicit profile override**. OpenRouter/Astra chooses and verifies the optimized profile. The script then measures a completed essay via `/generate`, verifies `/live`, reverts and releases the allocation. Results retain engine-specific timing conventions and actual GPU IDs; differing output lengths, templates, context and sampling are disclosed. Ollama receives only an output cap, with no inference tuning. Preparation is timed separately and can take longer for Flash's large shards; prepare before the five-minute presentation.

`live_byteshape.py` is a convenience wrapper for the ByteShape production rehearsal. `check_live_byteshape.py` retains the explicit-profile live transport test and does not call OpenRouter. Private receipts are ignored under `var/`; sanitized results belong under `docs/demo/`.

## Runtime boundaries

- Slurm account/partition `cmist`, QoS `cmist_priority`; 12 allocated CPUs per engine group and 64 GiB RAM per GPU. One group is 1 / 1 / 3 GPUs for ByteShape / Glimmer / Flash. All GPU masks come from Slurm. Model/library hashing and inference run on the compute node.
- No new model downloads or builds in Optimize. Glimmer verifies its patched library as well as the shared executable. Flash retains its validated projector, MTP head, lazy n-gram loading and MMQ settings. Ollama's installation/hash is checked only when explicitly running a standalone comparison. No GPU power, MPS, shared service or V100 changes.
- GPU memory/temperature guards cover **every device in a model's group**, not just its first GPU. Native placement is verified against process ownership, per-device buffers and target/draft offload logs.
- Standard operation deadline 180 seconds, caller maximum 300, at most two repairs, bounded cleanup. Short arithmetic verification is not broad or full-context quality certification. Natural completion and cap status remain separate from throughput.
- OpenRouter uses `openai/gpt-6-astra`, high reasoning, priority tier when accepted. An explicit unsupported-tier response retries the same model/effort without that tier; no silent model substitution. Returned tier is recorded.
- Restart cleans only the recorded owned allocation and marks interrupted operations failed. It never replays completed work. Stopping the backend releases its allocation.

ByteShape draft depth now accepts 1–16 for explicitly experimental overrides. Registered defaults remain MTP3/MTP5; expanding the accepted range is not a performance or memory-fit guarantee. Glimmer and Flash draft caps are unchanged. Refresh capabilities after updating the backend.

Wright GPU admission resolves Slurm step/job GRES IDs through the node-specific `/etc/slurm/gres.conf` device files and `/proc/driver/nvidia/gpus/*/information` UUIDs. NVML visibility alone is not allocation ownership: an extra visible GPU is never substituted for an unavailable assigned device. Unsupported or inconsistent mappings fail closed.
