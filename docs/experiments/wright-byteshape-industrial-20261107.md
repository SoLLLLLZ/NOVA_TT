# ByteShape Industrial Revolution campaign — November 7, 2026

All 15 authorized tests completed. Best observed decode: **77.10 tokens/s**, test A2. The 100 tokens/s target was not reached.

Three GPT-6.1 Sol xhigh agents each ran five tests without SubagentComms. Two working L40s were available: A and B used separate devices, then C reused B’s released device. A temporary unusable-slot reservation ran no inference and was released as soon as C secured its device. The campaign never exceeded three scheduler reservations. Allocation setup overlapped, but startup staggering meant the recorded generation requests did not overlap (B, then A, then C).

The exact user prompt was `Write a short essay explaining the causes of the Industrial Revolution`. Every generation used seed 71430, a 2048-token ceiling with natural EOS, no prompt-cache reuse, and streaming native timing. No extra inference warmup or quality generations were sent; intrinsic server startup warmup remained enabled.

All trials retained the ByteShape IQ3_S hybrid quant, llama.cpp b10820 runtime, 65,536 context, Q8 target/draft KV, one model/request per GPU, a 300 W configured power limit, 12 allocated CPU threads and 64 GiB host RAM. Tracks changed only the settings listed below. Loading is excluded from decode timing.

| Test | Changed setting | Prefill t/s | Decode t/s | Output tokens | Request seconds |
| --- | --- | ---: | ---: | ---: | ---: |
| A1 | draft 5 | 64.768 | 69.566 | 764 | 11.299 |
| A2 | draft 3 | 64.279 | 77.103 | 812 | 10.851 |
| A3 | draft 7 | 64.111 | 52.407 | 759 | 14.795 |
| A4 | draft 9 | 63.580 | 44.453 | 870 | 19.889 |
| A5 | draft 12 | 63.306 | 39.098 | 870 | 22.568 |
| B1 | temperature 0.75 | 64.544 | 69.707 | 764 | 11.277 |
| B2 | temperature 0.5 | 64.799 | 69.649 | 842 | 12.411 |
| B3 | temperature 0.25 | 64.360 | 68.755 | 781 | 11.676 |
| B4 | temperature 0.1 | 64.421 | 71.583 | 830 | 11.918 |
| B5 | temperature 0.0 | 64.809 | 70.234 | 847 | 12.382 |
| C1 | decode threads 2; batch/microbatch 2048/512 | 65.148 | 69.679 | 764 | 11.276 |
| C2 | decode threads 1; batch/microbatch 2048/512 | 65.057 | 69.558 | 764 | 11.298 |
| C3 | decode threads 4; batch/microbatch 2048/512 | 64.775 | 69.313 | 764 | 11.338 |
| C4 | decode threads 8; batch/microbatch 2048/512 | 65.251 | 69.109 | 764 | 11.368 |
| C5 | decode threads 2; batch/microbatch 1024/256 | 78.288 | 69.182 | 764 | 11.302 |

A starts at draft 5 and varies draft depth at temperature 0.75. B starts at temperature 0.75 and varies temperature at draft 5. C starts at decode/prefill threads 2/6, batch/microbatch 2048/512, draft 5 and temperature 0.75; its final test reduces batch/microbatch together. A1/B1/C1 intentionally repeat identical settings as three independently recorded controls, so the 15 rows are observations rather than 15 unique parameter combinations.

## Interpretation

Draft 3 was faster than draft 5 in this essay observation; deeper drafts 7/9/12 became slower. Draft 9 and draft 12 produced identical final essays and accepted 526 draft tokens each, while draft 12 proposed 4164 versus 3123 tokens and took longer. These results reinforce existing lessons 001 and 006; they do not establish a universal best depth.

Temperature results ranged from 68.755 to 71.583 tokens/s. Each setting has one observation, and changing sampling can change both answer content and length. Small differences are not repeatable gains established by this campaign. Thread/batch results likewise remain single observations.

Every answer reached EOS, and service, placement, context and memory guards passed. All final essays were read, but no broad factual-quality pass is claimed. A3 contains a water-wheel/Watt wording defect, B4 describes iron as energy, and B5 has an internal contradiction. Other sweeping historical claims remain unaudited. Per-answer caveats and full responses are retained in the evidence.

The historical 130–140 tokens/s records used different prompts and fixed 512-output probes. These runs use 21 formatted prompt tokens and naturally completed essays. They are not a matched regression comparison; do not overwrite historical rates or infer a universal slowdown.

## Admission fix and cleanup

Preflight exposed an old worker fallback that could confuse NVML visibility with Slurm ownership. The rejected job loaded no model and generated no tokens. The worker now resolves Slurm GRES entries through physical device minors to UUIDs and rejects unavailable or ambiguous mappings. Its regression test includes the actual remapped-index pattern. CANON lesson 017 records this new operational lesson.

Track C’s local launcher stalled before any load/generate call. It resumed the same owned allocation with an optional host-information probe omitted; inference guards were unchanged. There were exactly 15 model-generation requests and no inference retries. All owned allocations and the temporary idle reservation were released. GPU clock and instantaneous power-draw samples were unavailable.

The user-authorized experimental ByteShape draft limit is now 16, with the existing experimental gate. Registered profiles and production defaults were not promoted or changed. This campaign did not call OpenRouter, Ollama, or the widget.

## Evidence and validation

- [Full native requests, responses, configurations, launch arguments and cleanup](../../data/canon/experiments/wright-byteshape-industrial-20261107.json).
- [CANON](../../data/canon/CANON.csv): 15 experiment rows inserted before the original 16 lessons; one new lesson appended.
- [Validation receipt](../../data/canon/CANON_VALIDATION.json): all 144 old rows preserved across 83 columns, 15 native timing pairs recomputed, source hashes and references checked.

The supplement embeds the raw JSON needed to inspect each new speed pair. `source_file` paths point to the local ignored experiment receipts; they are provenance locators, not additional files promised in the repository. Historical raw sources were not re-audited.
