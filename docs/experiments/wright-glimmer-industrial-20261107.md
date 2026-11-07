# Glimmer Industrial Revolution campaign — November 7, 2026

Completed 20 tests in two waves of two GPUs. Best observed decode: **59.339 tokens/s**, test **B3**. The 100 tokens/s target was not reached. These are single observations, not a repeatable optimum.

Four GPT-6.1 Sol xhigh agents worked without SubagentComms. A varied draft depth, B temperature, C decode threads, and D batch/microbatch sizes. A/B finished before C/D began; C reused A’s Slurm allocation and D reused B’s. At most two generation requests ran concurrently. All owned allocations and temporary idle holds were released.

Every test used exactly `Write a short essay explaining the causes of the Industrial Revolution`, seed 71430, a 2048-token ceiling with natural EOS enabled, zero prompt-cache reuse, and live streaming native timings. No extra generation warmups, quality prompts or inference retries were added. Intrinsic server startup warmup was retained.

Fixed configuration: Muse Glimmer UD-Q4_K_XL target and original kquant DFlash model, patched L40 runtime, 262144 context, F16 target/draft KV, high reasoning, one model/request per GPU, 300 W configured limit, 12 allocated CPU threads and 64 GiB host RAM. Each track changed only the listed setting(s). Base: DFlash15, temperature 0.75, threads 8/12, batch 4096/micro 512. DFlash’s actual maximum 15 was respected.

| Test | Setting | Prefill t/s | Decode t/s | Output tokens | Request seconds | Stop |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| A1 | draft 15 | 93.220 | 52.579 | 762 | 15.205 | eos |
| A2 | draft 11 | 95.335 | 53.009 | 762 | 15.072 | eos |
| A3 | draft 7 | 97.677 | 53.571 | 762 | 14.905 | eos |
| A4 | draft 5 | 98.068 | 40.900 | 731 | 18.550 | eos |
| A5 | draft 3 | 97.600 | 50.269 | 783 | 16.261 | eos |
| B1 | temperature 0.75 | 91.591 | 52.620 | 762 | 15.207 | eos |
| B2 | temperature 0.5 | 93.407 | 54.025 | 738 | 14.373 | eos |
| B3 | temperature 0.25 | 90.957 | 59.339 | 730 | 13.037 | eos |
| B4 | temperature 0.1 | 90.629 | 57.117 | 756 | 13.971 | eos |
| B5 | temperature 0 | 86.353 | 56.027 | 745 | 14.070 | eos |
| C1 | decode threads 8 | 89.952 | 52.469 | 762 | 15.258 | eos |
| C2 | decode threads 2 | 90.125 | 52.538 | 762 | 15.242 | eos |
| C3 | decode threads 4 | 88.746 | 52.550 | 762 | 15.244 | eos |
| C4 | decode threads 6 | 90.485 | 52.548 | 762 | 15.234 | eos |
| C5 | decode threads 12 | 90.133 | 52.542 | 762 | 15.237 | eos |
| D1 | batch/microbatch 4096/512 | 97.877 | 52.834 | 762 | 15.102 | eos |
| D2 | batch/microbatch 2048/512 | 128.913 | 53.672 | 762 | 14.708 | eos |
| D3 | batch/microbatch 1024/512 | 154.424 | 54.090 | 762 | 14.513 | eos |
| D4 | batch/microbatch 4096/256 | 116.634 | 52.751 | 762 | 15.014 | eos |
| D5 | batch/microbatch 4096/128 | 127.581 | 52.799 | 762 | 14.947 | eos |

## Observed comparisons

The fastest temperature setting, 0.25, measured 12.77% higher decode than its same-track 0.75 control (59.339 versus 52.620 tokens/s). Output length changed from 762 to 730 tokens. Draft 7 measured 53.571; draft 5 fell to 40.900. Decode-thread changes ranged 52.469–52.550. Batch 1024/micro 512 measured 54.090 versus 52.834 at 4096/512, while prefill rose from 97.877 to 154.424. These are descriptive single-run comparisons, not established repeatable gains.

## Evidence and limits

A1/B1/C1/D1 are repeated control observations with identical settings, not four unique configurations. Native output counts and decode rates include reasoning; final-answer channel text is preserved separately. The reported decode numerator is predicted_n−1. Loading is excluded. Concurrent tracks share a host; this is not a controlled serial-versus-parallel comparison.

Every final answer was read for completion/coherence and visible issues. This is not a factual-quality certification. Per-answer review notes and full raw output are in the supplement. Historical fixed-512/long-prompt records are different workloads and are not matched speed comparisons. Existing CANON lessons cover draft-depth, sampling, thread and batch tradeoffs. New lesson 018 records that fixed seeds do not guarantee identical text after runtime-setting changes: A1/A4/A5 share the exact native request but generated different final essays at different draft depths. This does not establish a distributional error or worse quality. Production presets were not promoted.

The first B allocation passed strict worker admission but its experiment harness rejected scheduler text formatting before loading. That job was released, the harness check corrected, and one replacement allocation obtained. Both attempts and local sandbox-start failures are retained as pre-inference provenance; none consumed an inference test. Temporary idle reservations of the known unusable slot ran no inference and were released before the two-GPU tests.

- [Native request/response and full configuration evidence](../../data/canon/experiments/wright-glimmer-industrial-20261107.json).
- [CANON](../../data/canon/CANON.csv): 20 new records before the 17 existing lessons, plus new lesson 018; all 160 prior records preserved.
- [Validation receipt](../../data/canon/CANON_VALIDATION.json).

`source_file` and audit archive paths locate ignored local receipts; the committed supplement embeds native evidence directly. Source hashes establish provenance, not broad model quality.
