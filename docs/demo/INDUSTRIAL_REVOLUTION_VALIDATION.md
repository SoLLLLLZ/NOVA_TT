# Industrial Revolution demo benchmark — November 7, 2026

Exact backend speed-test prompt:

> Write a short essay explaining the causes of the Industrial Revolution

The actual OpenRouter `openai/gpt-6-astra` pipeline (high reasoning, effective priority tier) selected ByteShape MTP5 / temperature 0.75 from CANON. Default Ollama and optimized llama.cpp ran sequentially on the same Wright L40, Slurm job 268019. Neither Astra nor local essay generation has web-search tools or plugins.

| Test | Default Ollama decode | Astra-selected local decode | Decode speedup |
| --- | ---: | ---: | ---: |
| Capped 256-token probe | 27.35 tok/s | 74.48 tok/s | 2.72× |
| Naturally completed essay | 25.94 tok/s | 69.18 tok/s | 2.67× |

Both full essays stopped naturally below the 2048-token ceiling: Ollama generated 450 tokens in 17.35 native decode seconds; llama.cpp generated 764 tokens in 11.03 seconds. These counts/rates include reasoning as well as final prose. The frontend streams final prose only. Different output lengths mean the throughput ratio is not the answer-completion latency ratio.

The full-essay native prefill rates were 42.06 and 63.58 tok/s, with 63 and 21 input tokens respectively because templates differ. Both report zero cached input tokens. The optimized full essay accepted 30.8% of drafted tokens; historical repetitive-ledger speeds do not predict essay speed.

Preparation took 28.0 seconds. Optimize-and-compare took 86.9 seconds after preparation; the full sequential race took 77.1 seconds including model transitions. GPU decode rates exclude loading, OpenRouter, SSH and queue delays. No model downloads were needed.

The model/runtime, placement, 64K optimized context and arithmetic completed-answer check passed. This is not a factual quality audit of the historical essays. Each cell is one observation. Untouched Ollama retains its defaults; llama.cpp uses MTP5, temperature 0.75, Q8 KV and threads 2/6, so this compares whole configurations. Revert succeeded and the allocation was released; the user queue was empty on readback. Glimmer and Flash were not tested.

Native responses and launch manifests were read back; timing arithmetic and exact prompt were verified. All 46 backend tests passed. See the [structured receipt](industrial-revolution-validation-20261107.json).

For the frontend race, submit the exact prompt above with `max_tokens: 2048`. The default Optimize speed probe remains a fast capped 256-token test with a separate arithmetic correctness check. The default race API cap remains 256 unless the caller supplies 2048.
