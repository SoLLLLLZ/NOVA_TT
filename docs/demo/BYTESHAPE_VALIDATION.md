# ByteShape endpoint validation — November 7, 2026

The ByteShape backend passed live Wright tests with default Ollama and the registered MTP5 / temperature 0.75 llama.cpp profile. Glimmer and Flash were not loaded or tested. See the [machine-readable receipt](byteshape-validation-20261107.json) and [backend run instructions](../../backend/README.md).

| Test | Default decode tok/s | Optimized decode tok/s | Ratio |
| --- | ---: | ---: | ---: |
| Fixed 256-token probe, sequential on one L40 | 27.57 | 104.57 | 3.79× |
| Live race, separate L40s | 24.51 | 90.67 | 3.70× |

The fixed probe's prefill rates were 1155.34 tok/s for Ollama and 1481.52 tok/s for llama.cpp. The short race's prefill rates were 32.35 and 60.70 tok/s respectively. These are separate single observations, not pooled rates.

The full sequential optimize-and-compare operation took 82.8 seconds after 31.4 seconds of allocation/asset preparation. The later verify-only operation took 68.6 seconds after 11.1 seconds of preparation. Astra high selected the candidate through OpenRouter; the returned service tier was `priority`. Prepare allocation/assets before the presentation timer; these timings are observations, not a latency guarantee.

Both models are resident before paired race prompts are dispatched. The race used separate GPU UUIDs and disjoint allocated CPU groups; request intervals overlapped by 2.76 seconds. Final-answer streaming produced 69 default-lane chunks and 77 optimized-lane chunks. Reasoning delimiters are excluded from the delivered text. [Ollama's empty-prompt preload](https://github.com/ollama/ollama/blob/main/docs/api.md) changes no inference sampler parameters.

The retained optimized service passed a naturally completed arithmetic JSON check (`remaining=19`, `doubled=38`), runtime/context/placement checks, and the memory/temperature guard. Context was configured at 65,536 tokens; the correctness prompt used 56 native tokens. This does not certify full-context quality. Default Ollama used its native 32K context and baseline defaults; optimized llama.cpp used Q8 target/draft KV, MTP5, temperature 0.75, decode/prefill threads 2/6, and batch/microbatch 2048/512.

The comparison covers the complete configuration. It does not isolate MTP: templates, context, cache precision, sampling and timing conventions differ. Ollama uses generated-token count divided by native decode duration; the pinned llama.cpp runtime uses `(n-1)/duration`. Race output lengths differ. Loading is excluded from decode/prefill rates and recorded separately.

Revert succeeded and released the owned Slurm allocations after both rehearsals. The SSH master connection was left intact. Private native responses, launch manifests and model/runtime verification receipts remain under the worker's private deployment directory. The backend retains deployment references under its ignored state directory.

Validation: 46 local tests passed; lint/compilation checks passed. Three independent GPT-6.1 Sol xhigh reviewers worked read-only without SubagentComms. Their reported API, lifecycle, cancellation, native-float, runtime-link, streaming and provenance defects were corrected and rechecked. No CANON evidence bytes were changed in this implementation.

Native receipt readback confirmed disjoint CPU groups, verified artifact identity, exact equality between streamed text and native final-answer text, and no remaining user jobs. The pinned Ollama empty preload omits native `load_duration`; the backend now uses measured preload wall time when that field is absent, covered by a local regression test. This metadata fallback does not affect the native decode/prefill rates above.
