# Flash Next Industrial Revolution campaign — November 7, 2026

Completed 15 sequential tests on the same three Slurm-allocated L40s. Best observed decode was **73.844 tokens/s** (A5), versus 72.600 for its track control (A1), a 1.71% difference. These are single observations, not a repeatable optimum.

Three GPT-6.1 Sol xhigh agents worked without SubagentComms. A tested MTP depth and temperature; B tested decode threads; C tested batch/microbatch sizes. Every track finished and was audited before the next began. The same allocation and ordered GPU UUIDs were retained; at most one generation request ran at a time.

Exact prompt: `Write a short essay explaining the causes of the Industrial Revolution`. Every request used seed 71430, a 2048-token ceiling with natural EOS enabled, no prompt-cache reuse, and live streaming native timings. No extra generation warmups, quality prompts or inference retries were added. Intrinsic server startup warmup remained enabled.

Fixed settings: Flash Next UD-Q4_K_XL target, original shared Q8_0 MTP draft, stock L40 b10820 runtime, 131072 context, F16 target/draft KV, medium reasoning, 12 allocated CPUs, 192 GiB host RAM and 300 W configured limit per GPU. Base settings were MTP 2, temperature 1, threads 8/12 and batch 2048/micro 1024; MMQ, lazy loading, layer split, projector and auto-fit with 1024/1024/4096 MiB targets were preserved. The backend-supported Flash MTP range 1–2 was used.

| Test | Setting | Prefill t/s | Decode t/s | Output tokens | Request seconds | Stop |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| A1 | MTP 2, temperature 1.0 | 10.325 | 72.600 | 811 | 13.198 | eos |
| A2 | MTP 1, temperature 1.0 | 10.655 | 70.615 | 647 | 11.121 | eos |
| A3 | MTP 2, temperature 0.75 | 10.605 | 70.194 | 798 | 13.340 | eos |
| A4 | MTP 1, temperature 0.75 | 10.589 | 72.098 | 798 | 13.040 | eos |
| A5 | MTP 2, temperature 0.5 | 10.574 | 73.844 | 912 | 14.325 | eos |
| B1 | decode threads 8 | 10.586 | 72.567 | 811 | 13.153 | eos |
| B2 | decode threads 2 | 10.611 | 72.305 | 811 | 13.188 | eos |
| B3 | decode threads 4 | 10.566 | 72.024 | 811 | 13.242 | eos |
| B4 | decode threads 6 | 10.596 | 72.457 | 811 | 13.167 | eos |
| B5 | decode threads 12 | 10.584 | 72.673 | 811 | 13.137 | eos |
| C1 | batch/microbatch 2048/1024 | 10.673 | 72.574 | 811 | 13.134 | eos |
| C2 | batch/microbatch 1024/1024 | 10.760 | 72.710 | 811 | 13.097 | eos |
| C3 | batch/microbatch 512/512 | 17.177 | 71.985 | 811 | 12.482 | eos |
| C4 | batch/microbatch 2048/512 | 16.550 | 72.579 | 811 | 12.437 | eos |
| C5 | batch/microbatch 2048/256 | 23.013 | 72.681 | 811 | 12.064 | eos |

## Evidence and limits

Best-decode request time was 14.325s versus 13.198s for its control, with 912 versus 811 output tokens. Decode throughput and total answer latency are separate outcomes.

A1/B1/C1 repeat the same control settings as separate observations. Track A is a partial factorial: compare MTP 1 versus 2 at a matched temperature, or temperatures at a matched MTP depth. A2 versus A3 changes two variables and cannot isolate either effect. Threads and batches were not combined with the winning temperature setting in a later test.

Prefill rates come from only 21 formatted prompt tokens and do not establish long-prompt prefill performance. Native output counts include reasoning; final-answer channel text is preserved separately. Decode is (predicted_n−1)/decode_seconds, excluding model loading. Different output lengths/content limit conclusions about latency and general speed. All final essays were read for completion/coherence and visible issues, not broadly certified for factual quality. Each observation retains its review note. These short naturally stopped requests are not matched comparisons with the older fixed-512/long-prompt experiments.

The scheduler assigned physical slots 0, 2, 3, verified through GRES device minors to UUIDs. A bounded read-only diagnostic occupied slot 0 briefly so the previously approved idle reservation could hold unusable slot 1 without inference. The diagnostic was released before the three-GPU allocation; the idle hold was released before Track A. All owned reservations and the shared worker were released. Three-GPU admission succeeded, so no two-GPU fallback test was needed.

Existing CANON lessons already cover speculation, sampling, threads, batches and fixed-seed limitations. User-requested lesson 019 adds a conditional preference: prefer temperatures closer to 1 when matched tests show no decode decrease. MTP2 at temperature 1 beat 0.75 here, while 0.5 was slightly faster than 1. This does not establish a universal temperature winner or superior quality; production presets remain unchanged.

- [Full native requests, responses, configs, timings and cleanup evidence](../../data/canon/experiments/wright-flash-industrial-20261107.json).
- [CANON](../../data/canon/CANON.csv): 15 rows inserted before the existing 18 lessons; all 181 previous records preserved exactly, with new lesson 019 appended.
- [Validation receipt](../../data/canon/CANON_VALIDATION.json).

Ignored local receipt paths remain provenance locators; the committed supplement embeds the native evidence directly. Hashes establish integrity, not broad model quality.
