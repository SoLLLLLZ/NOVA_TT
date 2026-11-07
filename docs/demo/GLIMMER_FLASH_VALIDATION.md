# Glimmer and Flash production validation — November 7, 2026

Production optimization excludes Ollama for **all three models**: ByteShape, Glimmer and Flash. `/optimize` only selects and verifies llama.cpp; `/profiles` only lists native profiles. Legacy comparison mode and `/race` return 409 before any agent call or allocation. Default Ollama is a standalone test, never an optimization step or frontend operation.

The new Glimmer and Flash adapters use their own hashed assets, runtime configuration, model-specific capability limits and Slurm GPU groups. Glimmer uses its patched runtime and original DFlash draft; Flash uses four Q4 target shards and its existing projector/Q8 MTP head on three L40s. No models were downloaded again. Every assigned GPU is covered by memory, temperature and placement checks.

## Live results

Prompt: `Write a short essay explaining the causes of the Industrial Revolution`

| Model | L40s | Standalone Ollama decode | Optimized decode | Ratio | Production result |
| --- | ---: | ---: | ---: | ---: | --- |
| Muse Glimmer | 1 | 23.60 tokens/s | 54.86 tokens/s | 2.32× | OpenRouter → Astra high → Optimize → Generate → Live passed |
| Qwen Flash Next | 3 | 15.18 tokens/s | 71.33 tokens/s | 4.70× | OpenRouter → Astra high → Optimize → Generate → Live passed |

Glimmer's Astra-selected profile was DFlash15, temperature 0.75, 256K context and F16 KV. The completed optimized essay generated 762 tokens; Ollama generated 839. The live observer delivered 70 metric updates at **4.97 updates/second**. Its final measurement exactly matched `/generate`; waiting, start, finish, stream sequence, revert and service removal checks passed. Glimmer's final user channel was emitted without raw reasoning/channel markers. The separate completed arithmetic check passed; this is not broad quality certification.

Glimmer's final run requested priority but returned the **default** service tier. Actual optimization took 23.26 seconds after separately timed preparation of 15.69 seconds. An earlier successful Astra selection returned priority. No web tool was supplied to either request.

Flash's retry passed after the user raised the OpenRouter key limit. The real `openai/gpt-6-astra` call used high reasoning and returned **priority** tier. With no explicit profile override, Astra selected the registered MTP2 profile: 128K context, F16 KV, temperature 1.0, three L40s and the draft on CUDA2. The completed arithmetic check, all-device placement, context, service and memory checks passed without repairs. The completed essay produced 640 tokens (639 timed decode tokens), versus 554 in the reused standalone Ollama result. Native decode was **71.33 tokens/s**, 4.70× the earlier 15.18 tokens/s baseline.

Flash's live observer received **44 metric updates at 4.77 updates/second**, with a final measurement exactly matching `/generate`. Waiting, inference start/finish, sequence continuity, revert, stream closure and post-revert 404 checks passed. The final visible essay contained no native reasoning/channel markers. The owned Slurm job was **268033** on n03. Its command audit contains one llama.cpp load and no Ollama load or log; the original baseline was reused unchanged.

The original attempt's HTTP 403 spending-limit failure remains recorded in the JSON history. The successful retry's private receipt is `var/production-qwen3.8-flash-next-1794075744740759000/report.json`; tested backend commit: `5a3c105a90de676b82f2a720785e511b548f7728`.

## Measurement limits and timing

These are single, whole-configuration comparisons, not isolated draft-size experiments. Glimmer's default Ollama context was 32K versus native 256K; Flash's Ollama context was 256K versus the registered native 128K. Sampling, templates and output lengths differ. Decode includes the engine's generated reasoning tokens. Ollama uses `eval_count / eval_duration`; native uses `(predicted_n - 1) / predicted_ms`. Loading, file verification and Astra latency are excluded from decode throughput. Native Glimmer prefill measured 894.59 tokens/s; Ollama measured 141.44. Flash optimized prefill measured 12.96 tokens/s, versus Ollama 27.57 tokens/s; decode improved while this short-prompt prefill rate was lower. These short prompts are not long-context prefill benchmarks.

The first Glimmer rehearsal had an incorrect HTTP assertion in its observer harness after successful optimization. That assertion was fixed. Its completed standalone Ollama baseline was explicitly reused for the successful second production run; it was not presented as a new measurement. Actual GPU identities in the receipts match for the Glimmer comparison. Flash reused the earlier baseline from a different three-GPU allocation on n03; the allocations share one physical GPU. Its 4.70× ratio is a single whole-configuration comparison, not an identical-allocation causal trial.

Flash's initial asset preparation took **331.64 seconds**, before loading Ollama. The successful retry took **258.90 seconds** for startup preparation, then **40.21 seconds** for the actual Astra optimization/verification operation. The subsequent completed essay took 10.74 seconds wall time. A fresh five-minute demo cannot be promised with all of those stages included. Use `NOVA_PREPARE_MODEL=qwen3.8-flash-next` when starting the backend before presenting; see [backend instructions](../../backend/README.md). Preparation has its own explicit 600-second deadline and performs no inference or OpenRouter call. The subsequent production operation retains its normal deadline.

## Checks and reproduction

67 local tests passed, covering all three models' Ollama exclusion, rejected legacy comparison operations, model/profile isolation, GPU requirements, preparation without inference, preparation-failure cleanup, all-device guards, Glimmer channel extraction and actionable sanitized API-limit errors. The optional startup preparation and stricter target-buffer checks now also passed the Flash hardware retry. Glimmer was not rerun in this follow-up. All owned test allocations and diagnostic steps were released; final `squeue` showed no jobs for this user.

Sanitized measurement/configuration evidence: [JSON receipt](glimmer-flash-validation-20261107.json). Private full receipts remain under ignored `var/`.

The successful Flash retry used this command, preserving the original standalone baseline:

```sh
uv run python scripts/check_live_models.py --model qwen3.8-flash-next \
  --baseline-receipt var/production-qwen3.8-flash-next-1794074883620274000/report.json
```

On another machine, omit `--baseline-receipt` to run a new standalone baseline followed by the actual Astra production test. Neither command adds Ollama to the production tool. ByteShape was covered by regression tests here; its earlier live receipts remain separate.
