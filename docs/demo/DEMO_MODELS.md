# NOVA demo models: frontend reference

Updated November 7, 2026. Repository: https://github.com/SoLLLLLZ/NOVA_TT

Build the model picker and results UI against [endpoint.md](../api/endpoint.md), contract v2.1. This document supplies the three demo model identities, supported Wright layouts and reference configurations. It does not change the API contract or prove that a backend endpoint has been implemented. Use [OPTIMIZER_AGENT.md](../../backend/prompts/OPTIMIZER_AGENT.md) for agent behavior and [CANON.csv](../../data/canon/CANON.csv) with [CANON_GUIDE.md](../../data/canon/CANON_GUIDE.md) for evidence.

## Model picker

Use these exact IDs in the `model` field of `/optimize` and `/race`. The 27B ID already appears in endpoint.md; the other two match CANON's model identifiers and are the agreed catalog names in this reference.

| API model ID | Display name | Quantization subtitle | L40s per engine | Optimized context per request |
| --- | --- | --- | ---: | ---: |
| `qwen3.8-27b` | ByteShape Qwen 3.8 27B | IQ3_S hybrid · 3.23 bits/weight | 1 | 65,536 tokens (64K) |
| `qwen3.8-flash-next` | Qwen 3.8 Flash Next | Q4 · UD-Q4_K_XL | 3, on one node | 131,072 tokens (128K) |
| `muse-glimmer` | Muse Glimmer 30B | Q4 · UD-Q4_K_XL | 1 | 262,144 tokens (256K) |

The exact API `quant` strings are `IQ3_S hybrid 3.23bpw` for ByteShape and `UD-Q4_K_XL` for both Q4 models. ByteShape is not a Q4 model. These are tested profile context settings, not a claim about every model's architectural maximum. The demo is text-only; do not expose image upload merely because a projector file exists.

Suggested starting selection: ByteShape Qwen 3.8 27B, preset `fastest`. Present decode tokens/second as the main result and prefill as a secondary metric. GPU requirements are for these validated demo profiles, not universal minimum requirements on every runtime.

### `/status` model catalog example

This is an illustrative v2 `models` fragment with downloaded files but no active allocation. IDs prefixed `example-` are placeholders; it is not a live `/status` response:

```json
{
  "models": [
    {
      "id": "qwen3.8-27b",
      "display_name": "ByteShape Qwen 3.8 27B",
      "installed": true,
      "database_coverage": "verified",
      "quant": "IQ3_S hybrid 3.23bpw",
      "artifact_id": "example-qwen3.8-27b-target",
      "loaded": false,
      "requirements": {
        "gpu_type": "L40",
        "gpu_count": 1,
        "same_node": true,
        "context_per_slot": 65536
      },
      "ready": false,
      "readiness_reasons": [
        "Example: no active GPU allocation"
      ],
      "race": {
        "simultaneous_available": false,
        "sequential_available": false,
        "required_gpus_simultaneous": 2,
        "reasons": [
          "Example: allocate GPUs before running"
        ]
      }
    },
    {
      "id": "qwen3.8-flash-next",
      "display_name": "Qwen 3.8 Flash Next",
      "installed": true,
      "database_coverage": "verified",
      "quant": "UD-Q4_K_XL",
      "artifact_id": "example-qwen3.8-flash-next-target",
      "loaded": false,
      "requirements": {
        "gpu_type": "L40",
        "gpu_count": 3,
        "same_node": true,
        "context_per_slot": 131072
      },
      "ready": false,
      "readiness_reasons": [
        "Example: no active GPU allocation"
      ],
      "race": {
        "simultaneous_available": false,
        "sequential_available": false,
        "required_gpus_simultaneous": 6,
        "reasons": [
          "Example: allocate GPUs before running"
        ]
      }
    },
    {
      "id": "muse-glimmer",
      "display_name": "Muse Glimmer 30B",
      "installed": true,
      "database_coverage": "verified",
      "quant": "UD-Q4_K_XL",
      "artifact_id": "example-muse-glimmer-target",
      "loaded": false,
      "requirements": {
        "gpu_type": "L40",
        "gpu_count": 1,
        "same_node": true,
        "context_per_slot": 262144
      },
      "ready": false,
      "readiness_reasons": [
        "Example: no active GPU allocation"
      ],
      "race": {
        "simultaneous_available": false,
        "sequential_available": false,
        "required_gpus_simultaneous": 2,
        "reasons": [
          "Example: allocate GPUs before running"
        ]
      }
    }
  ]
}
```

`installed` and `database_coverage` must come from the backend at runtime. The example reflects downloaded artifacts and matching L40 evidence, not an assertion that all models are currently loaded or that an arbitrary selected GPU has verified coverage. `verified` is a database evidence badge; it does not mean today's optimization or quality test has passed. The backend must resolve this catalog to the staged GGUF files and private Ollama registrations; API IDs are not necessarily Ollama model tags.

## Reference optimized profiles

These are the initial short-prompt, decode-first candidates. The agent can choose a supported fallback based on workload and live constraints. The frontend displays the configuration actually returned by the backend; it must not force these values or display them as already applied.

| Setting | ByteShape Qwen 27B | Qwen Flash Next Q4 | Glimmer Q4 |
| --- | --- | --- | --- |
| CANON `config_id` | `cfg_549fe546f2fd44a6` | `cfg_22bd103c1aadb59c` | `cfg_0956f7625217646c` |
| Engine | llama.cpp | llama.cpp | llama.cpp |
| GPUs / request slots | 1 / 1 | 3 / 1 | 1 / 1 |
| Context tokens | 65536 | 131072 | 262144 |
| Decode / prefill threads | 2 / 6 | 8 / 12 | 8 / 12 |
| Batch / microbatch | 2048 / 512 | 2048 / 1024 | 4096 / 512 |
| Target and draft KV | q8_0 | f16 | f16 |
| Flash attention | true | true | true |
| Speculative mode | `draft-mtp` | `draft-mtp` | `draft-dflash` |
| Maximum draft tokens | 5 | 2 | 15 |
| Temperature | 0.75 | 1.0 | 0.75 |
| Top-k / top-p / min-p | 20 / 0.95 / 0 | 20 / 0.95 / 0 | 64 / 0.95 / 0 |
| Reasoning effort | medium | medium | high |
| Prompt cache RAM, MiB | 1024 | 4096 | 4096 |
| Split / fit | none / off | layer / on | none / off |
| Draft device within allocation | CUDA0 | CUDA2 | CUDA0 |

All three historical profiles used 12 allocated logical CPUs and 64 GiB host RAM. Let Slurm assign the physical GPUs; CUDA0/CUDA2 are allocation-local positions, not global GPU indices to hardcode in the frontend. Power was the cluster's unchanged 300 W limit; no power-setting UI is needed.

ByteShape fallback: `cfg_aee1c8396d18230b`, temperature 1 and MTP3, with the other listed settings unchanged. Glimmer fallback: `cfg_91cf36411e6d4895`, temperature 1 and DFlash11. Glimmer's short-prompt candidate is faster in the recorded evidence, but long-prompt results vary and do not establish a reliable general advantage. The saved Glimmer runtime caps drafts at 15; there is no tested draft17 profile. Flash has one supported optimized L40 profile in this comparison.

### V2 `config` examples

This mapping is documentation keyed by model ID, not a new endpoint payload. It uses the v2 config envelope and explicit settings so the frontend can show MTP/DFlash draft depth, separate thread counts and sampling changes. IDs prefixed `example-` are fixture identifiers; use the real IDs returned by `/profiles` and `/capabilities`. These examples include the important CANON settings; the backend's complete profile also resolves runtime/template details and effective placement. Do not submit example IDs to a live backend or guess missing settings from them.

```json
{
  "qwen3.8-27b": {
    "profile_id": "example-cfg_549fe546f2fd44a6",
    "model": "qwen3.8-27b",
    "artifact_id": "example-qwen3.8-27b-target",
    "quant": "IQ3_S hybrid 3.23bpw",
    "engine": "llama.cpp",
    "runtime_id": "example-llamacpp-b10820-sm89",
    "settings": {
      "context_tokens": 65536,
      "context_per_slot": 65536,
      "parallel_slots_per_process": 1,
      "replicas": 1,
      "batch_size": 2048,
      "microbatch_size": 512,
      "threads_decode": 2,
      "threads_prefill": 6,
      "draft_tokens": 5,
      "draft_gpu_layers": 99,
      "prompt_cache_ram_mib": 1024,
      "kv_type_k": "q8_0",
      "kv_type_v": "q8_0",
      "flash_attention": "on",
      "fit": "off",
      "speculative_mode": "draft-mtp",
      "draft_kv_k": "q8_0",
      "draft_kv_v": "q8_0",
      "split_mode": "none",
      "reasoning_effort": "medium",
      "temperature": 0.75,
      "top_p": 0.95,
      "min_p": 0.0,
      "top_k": 20,
      "draft_device": [
        "CUDA0"
      ],
      "backend_sampling": true,
      "checkpoint_min_step": 512,
      "gpu_layers": 99,
      "main_gpu": 0,
      "tensor_overrides": [
        {
          "pattern": "token_embd.weight",
          "buffer": "CUDA0"
        }
      ],
      "draft_model": null
    }
  },
  "qwen3.8-flash-next": {
    "profile_id": "example-cfg_22bd103c1aadb59c",
    "model": "qwen3.8-flash-next",
    "artifact_id": "example-qwen3.8-flash-next-target",
    "quant": "UD-Q4_K_XL",
    "engine": "llama.cpp",
    "runtime_id": "example-llamacpp-b10820-sm89",
    "settings": {
      "context_tokens": 131072,
      "context_per_slot": 131072,
      "parallel_slots_per_process": 1,
      "replicas": 1,
      "batch_size": 2048,
      "microbatch_size": 1024,
      "threads_decode": 8,
      "threads_prefill": 12,
      "draft_tokens": 2,
      "draft_gpu_layers": 99,
      "prompt_cache_ram_mib": 4096,
      "kv_type_k": "f16",
      "kv_type_v": "f16",
      "flash_attention": "on",
      "fit": "on",
      "speculative_mode": "draft-mtp",
      "draft_kv_k": "f16",
      "draft_kv_v": "f16",
      "split_mode": "layer",
      "reasoning_effort": "medium",
      "temperature": 1.0,
      "top_p": 0.95,
      "min_p": 0.0,
      "top_k": 20,
      "draft_device": [
        "CUDA2"
      ],
      "fit_target_mib": [
        1024,
        1024,
        4096
      ],
      "backend_sampling": true,
      "force_mmq_runtime": true,
      "load_mode": "none",
      "lazy_mode": "on",
      "draft_probability_min": 0.5,
      "draft_model": "example-qwen3.8-flash-next-draft"
    }
  },
  "muse-glimmer": {
    "profile_id": "example-cfg_0956f7625217646c",
    "model": "muse-glimmer",
    "artifact_id": "example-muse-glimmer-target",
    "quant": "UD-Q4_K_XL",
    "engine": "llama.cpp",
    "runtime_id": "example-glimmer-patched-sm89",
    "settings": {
      "context_tokens": 262144,
      "context_per_slot": 262144,
      "parallel_slots_per_process": 1,
      "replicas": 1,
      "batch_size": 4096,
      "microbatch_size": 512,
      "threads_decode": 8,
      "threads_prefill": 12,
      "draft_tokens": 15,
      "draft_gpu_layers": 99,
      "prompt_cache_ram_mib": 4096,
      "kv_type_k": "f16",
      "kv_type_v": "f16",
      "flash_attention": "on",
      "fit": "off",
      "speculative_mode": "draft-dflash",
      "draft_kv_k": "f16",
      "draft_kv_v": "f16",
      "split_mode": "none",
      "reasoning_effort": "high",
      "temperature": 0.75,
      "top_p": 0.95,
      "min_p": 0.0,
      "top_k": 64,
      "draft_device": [
        "CUDA0"
      ],
      "draft_model": "example-muse-glimmer-draft"
    }
  }
}
```

Only edit fields advertised writable by `/capabilities`. The backend resolves the complete saved profile and reports proposed/effective config and any changes. Keep most settings in the details panel; ordinary users still choose model and GPU resources and click Optimize.

## Default Ollama lane

Use engine `ollama` in API objects and label the lane **Default Ollama**. The optimized lane is **Optimized llama.cpp**. Historical Ollama version was 0.40.13; the following defaults were actually observed, not knobs the frontend should force:

| Setting | ByteShape Qwen 27B | Qwen Flash Next Q4 | Glimmer Q4 |
| --- | ---: | ---: | ---: |
| CANON baseline ID | `cfg_66cefe35fcd0a30a` | `cfg_d93b6fcfd7905833` | `cfg_7bc565a253127cc7` |
| Context tokens | 32768 | 262144 | 32768 |
| Threads | 128 | 128 | 128 |
| Batch size | 1024 | 512 | 1024 |
| KV type | f16 | f16 | f16 |
| Flash attention | true | true | true |
| Speculative mode | none | none | none |

Quantization is the same as each model's optimized profile. The 128 threads were constrained by a 12-CPU allocation. Correcting the defaults creates a separate baseline; do not silently do that and still label it untouched Ollama. The full engine comparison also changes context, sampling and other settings, so the UI should describe a complete configuration speedup, not attribute it all to one technique.

## Requests, progress and results

Example ByteShape request (send `X-Pairing-Token` and an `Idempotency-Key`):

```json
{
  "model": "qwen3.8-27b",
  "preset": "fastest",
  "objective": "decode",
  "workload": "short",
  "mode": "verify_only",
  "resources": {
    "target_id": "wright",
    "gpu_type": "L40",
    "gpu_count": 1,
    "same_node": true
  },
  "constraints": {
    "min_context_tokens": 32768,
    "quant": "IQ3_S hybrid 3.23bpw",
    "allow_sampling_change": true
  },
  "budget": {
    "deadline_seconds": 180,
    "max_repair_attempts": 2
  }
}
```

For Glimmer use model `muse-glimmer` and quant `UD-Q4_K_XL`. For Flash use `qwen3.8-flash-next`, quant `UD-Q4_K_XL`, and resources.gpu_count=3 with same_node=true. Obtain target/allocation/GPU IDs from the backend; never hardcode historical physical GPU indices. This 32K minimum lets the tested optimized profiles retain their larger contexts. A caller explicitly requiring 256K cannot be served by Flash's 128K profile without changing that request. `allow_sampling_change: true` permits the documented candidate temperatures; false preserves the active/baseline sampler.

- Check contract_version=2.1 before mutations. Follow the v2 POST SSE envelope and keep run_id for reconnect/cancel. The frontend never receives the OpenRouter key.
- Render step events including allocation, loading, verification and repair. Progress may be null; show the actual detail instead of a fake percentage.
- Render full config.settings, `changes` with dotted paths, evidence and independent validation. Announce success only on a terminal successful done result with applied=true and passed verification.
- Use live benchmark measurement.decode_tps as primary and prefill_tps as secondary. Before/speedup are null in verify_only. Do not seed live meters with CANON values.
- Use `/runs/{run_id}` after a lost stream instead of reposting the operation. Lock conflicting model changes while active; use `/runs/{run_id}/cancel` if cancellation is requested. `/revert` is streaming and takes the returned rollback_id.

### GPU requirements and external baseline

ByteShape and Glimmer each use one L40; Flash requires three L40s on one node. All three production Optimize pipelines only select, apply and verify optimized llama.cpp. Default Ollama is a separate demo baseline. Do not show an in-tool race action: `/race` and Optimize's old `sequential_compare` mode are disabled. Use `/generate` plus `/live` for the optimized terminal demonstration, and `scripts/check_live_models.py` for standalone comparison tests.

## Historical speed reference (not live UI values)

These are CANON's individual representative **short-prompt** measurements from November 4–5 on L40, in tokens/second. They are not pooled report rates, promised demo performance or mock values to pass off as current results.

| Model | Default decode | Optimized decode | Default prefill | Optimized prefill |
| --- | ---: | ---: | ---: | ---: |
| ByteShape Qwen 27B | 21.404 | 141.765 | 1222.169 | 1812.131 |
| Qwen Flash Next Q4 | 19.753 | 90.065 | 1616.598 | 967.580 |
| Glimmer Q4 | 18.860 | 179.653 | 1969.649 | 1748.437 |

Each optimized profile passed one separate short completed-answer check. That is not broad or full-context quality certification. Ollama and llama.cpp use different templates and timing conventions; Flash used different physical trios. Faster decode can coexist with slower prefill. Glimmer output requires correct final-answer-channel extraction by the backend before display; raw reasoning/format markers are not the final answer.

## Wright assets and current verification

At **2026-11-07 11:28 EST**, a read-only SSH check reached Wright's `headnode`. All nine files below existed and their byte sizes matched the saved records. This was a file-existence/size check, not a new hash check or model load. `squeue -u taeholee` showed **no active job** at that time. No GPU allocation or inference was started by this documentation task. Refresh readiness from the backend during the demo.

Paths below are backend references, not frontend input fields. All directories are under `/home/export/taeholee/nova/`:

| Asset directory | Required files |
| --- | --- |
| `byteshape-20261103/assets/` | `ByteShape-Qwen3.8-27B-IQ3_S-3.23bpw.gguf` (11,035,354,496 bytes) |
| `wright-flash-next-3l40-20261104/assets/` | `Qwen3.8-Flash-Next-UD-Q4_K_XL-00001-of-00004.gguf` through `00004-of-00004.gguf`, plus `mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf` and `mmproj-F16.gguf` |
| `wright-glimmer-1l40-20261105/assets/` | `Muse-Glimmer-30B-UD-Q4_K_XL.gguf` (15,878,222,368 bytes), `dflash-kquant.gguf` (1,631,205,312 bytes) |

Flash has **four required target shards**, not four alternative models. Their sizes in order are 10,946,624; 49,859,583,136; 49,376,141,504; and 12,087,983,520 bytes. Its draft is 2,786,568,256 bytes and projector is 904,004,000 bytes. Disk size is not total required VRAM.

The saved ByteShape/Flash llama.cpp runtime is `byteshape-20261103/assets/build-l40/bin/llama-server`. Glimmer uses `wright-glimmer-1l40-20261105/runtime/bin/llama-server` and its matching patched libraries. These runtime paths come from the handoff, not today's file listing. The backend must verify runtime compatibility before launch; a stock replacement may not support the saved profile. Preserve existing model downloads.
