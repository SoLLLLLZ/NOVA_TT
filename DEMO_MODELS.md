# NOVA demo models: frontend reference

Updated November 7, 2026. Repository: https://github.com/SoLLLLLZ/NOVA_TT

Build the model picker and results UI against [endpoint.md](endpoint.md), contract v0.1. This document supplies the three demo model identities, supported Wright layouts and reference configurations. It does not change the API contract or prove that a backend endpoint has been implemented. Use [OPTIMIZER_AGENT.md](OPTIMIZER_AGENT.md) for agent behavior and [CANON.csv](CANON.csv) with [CANON_GUIDE.md](CANON_GUIDE.md) for evidence.

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

This is the `models` fragment of a response, not a replacement for the full `/status` response:

```json
{
  "models": [
    {
      "id": "qwen3.8-27b",
      "display_name": "ByteShape Qwen 3.8 27B",
      "installed": true,
      "database_coverage": "verified"
    },
    {
      "id": "qwen3.8-flash-next",
      "display_name": "Qwen 3.8 Flash Next",
      "installed": true,
      "database_coverage": "verified"
    },
    {
      "id": "muse-glimmer",
      "display_name": "Muse Glimmer 30B",
      "installed": true,
      "database_coverage": "verified"
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

### Public `config` projections

The following mapping is documentation, keyed by model ID. Each value is an example of the existing API's `config` object, suitable for a mock **after optimization**, not a new endpoint payload. Here `threads` projects the decode-thread count; detailed prefill threads and draft settings remain in the backend profile. `speculative_mode` values come from CANON; render MTP and DFlash as friendly labels.

```json
{
  "qwen3.8-27b": {
    "engine": "llama.cpp",
    "threads": 2,
    "context_tokens": 65536,
    "batch_size": 2048,
    "kv_type": "q8_0",
    "flash_attention": true,
    "quant": "IQ3_S hybrid 3.23bpw",
    "speculative_mode": "draft-mtp"
  },
  "qwen3.8-flash-next": {
    "engine": "llama.cpp",
    "threads": 8,
    "context_tokens": 131072,
    "batch_size": 2048,
    "kv_type": "f16",
    "flash_attention": true,
    "quant": "UD-Q4_K_XL",
    "speculative_mode": "draft-mtp"
  },
  "muse-glimmer": {
    "engine": "llama.cpp",
    "threads": 8,
    "context_tokens": 262144,
    "batch_size": 4096,
    "kv_type": "f16",
    "flash_attention": true,
    "quant": "UD-Q4_K_XL",
    "speculative_mode": "draft-dflash"
  }
}
```

Contract v0.1 does not expose draft depth, temperature, prefill threads, microbatch, profile ID or GPU-group selection as public `config` fields. Do not add these fields to requests or assume the frontend can set them. The backend must retain the complete validated profile internally and apply it with supported tools. Treat the table as reference information, not executable launch arguments.

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

Example ByteShape request:

```json
{
  "model": "qwen3.8-27b",
  "preset": "fastest",
  "constraints": {
    "min_context_tokens": 32768,
    "quant": "IQ3_S hybrid 3.23bpw"
  }
}
```

For the other two choices, replace `model` with the exact catalog ID and `quant` with `UD-Q4_K_XL`. The demo can keep this 32K minimum requirement; the optimized profiles retain their larger contexts. Do not imply that Flash's optimized 128K profile satisfies a caller who explicitly requires 256K. Use `gpu_index` only when supplied by the live backend; a historical physical index is not reusable.

- Use the existing `X-Pairing-Token` header and POST streaming format from endpoint.md. The frontend never receives the OpenRouter API key.
- Follow `step` events for `detect_gpu`, `check_database`, `ask_ai`, `test_configs`, and `apply`. Put loading/queue details in the existing `detail` text; do not invent new step enum values or fake progress with a completion timer.
- Render returned `config`, `changed`, `reasoning` and `confidence`. Do not announce success until the terminal `done` event has `applied: true`. Render terminal `error` events and the existing diagnose/action flow when applicable.
- Drive the main speed display from live `benchmark`/`done` data. Show an empty/pending state until results arrive. Use `decode_tps` as primary, `prefill_tps` as secondary and the returned `speedup`; do not seed live meters with CANON values.
- Keep selection locked during an active operation, or require backend-supported cancellation before switching. There is no cancellation endpoint in v0.1. The backend retains service ownership and handles rollback through `/revert`.

### Multiple GPUs and race availability

One ByteShape or Glimmer engine needs one L40. A simultaneous race needs **two separate equivalent L40 allocations total**. Flash needs **three L40s on one node per engine**, so a simultaneous race needs **six L40s total**, with each engine's trio on a single node. Never run both lanes on the same GPUs and present the contention result as standalone speed.

The planned live presentation is a **sequential** default-then-optimized comparison, which only needs one profile's allocation (1 / 3 / 1 L40s). Do not label a sequential comparison as a simultaneous race or replay saved text as live output.

Contract v0.1 has one optional `gpu_index`, no GPU-group selector, and no `race_available` field. The backend must validate the whole required allocation and choose the group; selecting one GPU does not make Flash ready. Render allocation failures using the existing error mechanism. Do not invent extra request fields or infer race readiness solely from `installed: true`. If a richer readiness/group-selection API is needed, coordinate a versioned contract change separately.

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
