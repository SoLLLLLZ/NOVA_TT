# CANON: compact inference configuration retrieval

Use **CANON.csv** as the primary retrieval table. It has **144 rows and 83 columns**, weighs **103,769 bytes**, and contains **128 configuration records followed by 16 qualitative takeaways**. No cell exceeds 335 characters. Created November 4, 2026; updated November 7, 2026. The original 128 records retain all 79 original field values exactly.

## Configuration records and qualitative takeaways

Filter `record_type=configuration` before ranking measured settings or calculating hardware/model coverage. These 128 records include 126 measured configurations and two explicit memory failures. Qualitative rows have `record_type=qualitative_takeaway`; their inference-setting, throughput, token-count and observation fields are blank. They are guidance, not additional experiments or deployable presets.

The four appended columns are:

- `record_type`: `configuration` or `qualitative_takeaway`.
- `takeaway`: the general engineering rule, populated only for takeaway rows.
- `evidence_config_ids`: semicolon-separated supporting configuration IDs already in CANON.
- `evidence_ref`: the supporting entry in `qualitative_lessons.json`, identified by its `id` after `#`.

Lesson IDs use the `lesson_001` namespace in `config_id`, distinct from measured `cfg_...` IDs. Their short title is in `candidate`; `cautions` carries limits of the evidence. General rules must not be read as universal performance guarantees. Blank lesson measurements are not zero throughput.

The lessons occupy spreadsheet rows **130–145**, after the header and 128 original configuration rows. Retrieve their relevant guidance alongside hardware-compatible configurations. The model should use the rules to choose what to test, retain the selected workload and constraints, and verify proposed settings locally. Do not use a lesson as a substitute for a matching measured configuration or as a numerical speed prediction.

`qualitative_lessons.json` contains the observed values, raw-record locators, scopes and parent review decisions. Its `path` values are relative to the **P100 Project research workspace**, not necessarily the shared GitHub repository. The shared repo's compact CSV/guide/supplement are not a mirror of all raw records or the full historical archive.

The November 7 append consolidates 23 proposals from four GPT-6.1 Sol xhigh reviewers into 16 parent-reviewed rules. The review used local L40 raw records and local/remote V100 historical records; it started no inference. Preservation checks compared all 10,112 existing data cells exactly, verified all lesson references to configuration IDs, and confirmed every lesson measurement field remains blank. `build_canon.py` appends the qualitative supplement after sorting configuration rows so a rebuild retains the lessons at the bottom.

## Included and removed

Each `configuration` row represents one configuration with recorded evidence: 126 measured records and two explicit memory-guard failures. Their inventory contains 92 Qwen3.8 27B, 16 Qwen3.8 Flash Next and 20 Muse Glimmer records. Hardware is explicit: 114 V100 records and 14 L40 records. These counts exclude the 16 qualitative rows and describe available evidence, not validated deployment recommendations.

The retained settings cover GPU count/power, context and concurrency, replica layout, tensor placement, batch/microbatch, decode/prefill threads, KV precision, Flash Attention, auto-fit, MTP/DFlash/ngram settings, CUDA controls, model loading, prompt caching, sampling and reasoning. Runtime variant/reference is retained because different libraries or custom kernels can produce different performance with otherwise identical flags.

The original condensation removed: 44 non-measured records and 12 measured-labeled records lacking usable paired raw prefill/decode timings; full command/environment dumps; addresses and ports; tokenizer/tensor inventories; compiler and profile metadata dumps; repeated settings; large validation payloads; unneeded hashes. No large JSON payload is hidden inside a remaining cell. The earlier Decisions and experimental Flash exclusions remain applied.

The original CSVs and evidence archive are unchanged. CANON_AUDIT.json records all 56 omitted configuration IDs, selected observations and setting mappings. CANON_VALIDATION.json records source/export hashes and verification results. These audit files do not need to be embedded for ordinary retrieval.

## Rates and representative examples

`prefill_tps` and `decode_tps` are a pair from **one actual raw observation**, rounded to three decimals. `prompt_tokens`, `output_tokens`, `workload`, `rate_scope`, `cache_state` and `observation_id` describe that observation. They are not independently selected maxima, pooled averages or estimates of general performance.

The primary example favors prompts below 8,192 tokens when available. Selection prioritizes explicit zero-cache evidence, throughput probes over quality/smoke checks, the most-supported exact workload/size/control group, then proximity to 4,096 prompt tokens. Within that group it selects the lower-middle decode observation, retaining that same observation's prefill. If only longer prompts exist, the primary example uses an available longer observation.

The `long_*` fields provide a separate example at or above 8,192 prompt tokens, with the same rules and a 32,768-token target. They are populated for 102 rows. This preserves useful short/long behavior without hundreds of per-run columns. Neither example represents every workload measured for that configuration.

Both examples exclude known cache reuse and effective/pooled workflow timing. Five primary examples have unknown cache state, explicitly labeled `unknown`; do not compare them as confirmed cold-prefill measurements. `per_agent` rates include concurrency contention and must not be added to manufacture aggregate throughput. `raw_measurement_count` counts usable evidence entries, not necessarily independent trials.

## Column conventions

- `context_tokens` is the recorded total configured context. `context_per_slot` is recorded where available, otherwise derived from total context divided by recorded slots and replica count. The audit marks derived values.
- `parallel_slots_per_process` and `replicas` are distinct. `gpu_layout` preserves the shared physical-GPU arrangement for separate replicas. In those rows, batch/thread/KV columns describe the matched per-replica settings.
- `power_limit_w` is per GPU. `fit_target_mib` and `tensor_split` can contain comma-separated per-device values. Draft devices/tensor overrides describe the draft model separately from the target model.
- Build controls and runtime overrides have separate names. Blank means unknown/not recorded/inapplicable, never an inferred default or `false`.
- Sampling/reasoning columns describe the saved configuration. `benchmark_controls` records available overrides and stopping behavior for the selected examples. A capped or ignore-EOS probe is not a completed-answer quality pass.
- `quality_evidence` preserves explicit case-pass counts where normalized source flags exist; otherwise it points to the full validation evidence without inventing a verdict. `cautions` contains compact source caveats and may abbreviate longer notes.
- `runtime_ref` is a short runtime-hash reference or a fingerprint of recorded runtime identity fields, not a portable executable or a version guarantee. Use `config_id` for exact lookup in the full archive or the supplemental evidence described below.
- `source` identifies the originating campaign. `config_id` joins to configs.csv and validations.csv. Historical observation IDs join to measurements.csv for exact source paths and full request settings. The twenty-one newly added November 4–5 rows resolve through the appropriate JSON file under canon_additions/ instead; the original full archive is preserved.

## Retrieval use

Parse CSV properly, then index each row as named field/value pairs with the column names retained. Store `record_type`, `model`, `quant`, `gpu`, `gpu_count`, context, concurrency and `config_id` as filterable metadata. Retrieve compatible hardware/model/context/layout configuration records first; compare rates only after checking workload, token lengths, scope and cache state. Retrieve qualitative rules separately as guidance. Keep CANON_GUIDE.md alongside the table as shared interpretation guidance.

For the L40 prototype, filter `gpu=L40` for measured L40 claims. V100 rows can identify configurations worth testing on L40, but do not establish their L40 throughput. The original condensation ran no inference. The November 4 updates add measured V100 and Wright L40 experiment evidence, described below.

Original verification checked 8,532 cells and 190 selected speed pairs. The first November 4 update verified 8,848 cells and eight new selected speed pairs while preserving all 107 historical rows. The second update verified all 9,401 then-current cells and ten further selected pairs while preserving all 111 prior rows. A bounded preview was rendered and inspected. General throughput field terminology is consistent with the [official llama.cpp benchmark documentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/llama-bench/README.md); no outside benchmark results were imported.

## November 4 V100 experiment update

Four rows were added: the production baseline and separate changes to decode threads 4, temperature 0.5, and MTP draft depth 5. The 36 cold fixed-512 speed observations come from baseline/change/baseline sequences on three isolated V100s sharing a host CPU. Baseline observations are grouped into one configuration row; comparisons against each changed setting use its own physical GPU. Six separate short completed-answer checks passed. Warmups and quality checks are excluded from these new rows' speed selection and raw_measurement_count.

The new configuration and observation IDs, full argv, runtime/library identity, source paths and quality evidence resolve through `canon_additions/byteshape-three-knobs-20261104.json`. `CANON_AUDIT.json` lists this supplement, and `build_canon.py` preserves it on rebuild. Short and long examples remain individual lower-middle decode observations, not pooled rates; the experiment report uses pooled same-GPU rates for comparison.

MTP5 improved capped-probe decode, but minimum free VRAM was 827 MiB at the retained 64k context, only 59 MiB above the unchanged guard. Its completed answer generated more tokens and took longer than baseline. These limits are retained in its row and report. Production profiles were restored unchanged.

## November 4 temperature and draft-depth follow-up

Seven additional records cover a fresh 64K baseline, temperature 0/draft 5 at 64K, both draft-9 memory failures at 64K, a matched 32K baseline, and the two successful draft-9 candidates at 32K. Decode threads remained 2; temperature 1/draft 3 was the baseline. The 32K attempts were authorized only after actual 64K memory failures. All model, runtime, quantization and KV settings were preserved.

The 64K failures reached 635 MiB and 521 MiB free VRAM, below the unchanged 768 MiB guard; neither established a valid candidate speed or quality result. Their rows contain `FAILED_MEMORY_GUARD` in `cautions`, `raw_measurement_count=0`, and blank throughput/observation fields. Retain these as feasibility evidence, and exclude them when ranking measured speed. A blank is not zero performance. Successful 32K rows are separate configurations and must not be presented as 64K results.

The supplement `canon_additions/byteshape-temperature-draft-20261104.json` retains 44 cold speed observations, eight completed short-answer checks, full attempt/configuration provenance, failures and comparisons. All eight answer checks passed. Two seeds at temperature 0 are timing repeats, not independent stochastic samples. The experiment report compares both same-context controls and the original 64K baseline, explicitly separating the context change. CANON preserves individual raw representative observations rather than report-level pooled averages. Production was restored at its original 64K settings.

## November 4 single-GPU temperature 0.75 follow-up

Two records were added for an isolated GPU0 production baseline and temperature 0.75/MTP5 candidate. Both retain two decode threads, six prefill threads, 64K context, Q8 KV, the existing ByteShape quantization and runtime, and 150 W. Other GPUs remained unloaded throughout the experiment. Twelve cold speed observations and two successful completed short-answer checks are retained in `canon_additions/byteshape-temp075-draft5-20261104.json`.

The paired report pools before/after controls and shows +14.45% short decode and +11.02% long decode. Natural short-answer wall time improved from 21.474 to 20.693 seconds, with output length changing from 816 to 871 tokens. CANON still selects individual raw examples rather than those pooled rates. Minimum free VRAM was 825 MiB; no context fallback occurred. Original production settings were restored unchanged. Validation checked 9,559 current cells, four new selected speed pairs, and exact preservation of all 118 prior rows.

## November 4 Wright L40 comparison

Three rows were added for default Ollama 0.40.13, the production llama.cpp temperature 1/MTP3 profile, and temperature 0.75/MTP5. They ran sequentially on one Slurm-allocated L40 at 300W, with 12 CPU threads and 64GiB host RAM (job 265070). The model and staged runtimes were reused. Twelve cold 512-output speed probes and three successful completed short-answer checks are retained in `canon_additions/wright-three-configs-20261104.json`. Returned raw files were hash-verified; model processes stopped and Slurm released the allocation.

Ollama retains its resolved defaults: 128 threads within the 12-CPU allocation, 32K context, F16 KV, 1024/1024 batching, FlashAttention and no MTP. Its resolved sampler is temperature 1/top-k 20/top-p 0.95/min-p 0. The two llama.cpp profiles retain 64K context, Q8 KV, 2/6 threads and 2048/512 batching; their only inference-setting differences are temperature and maximum draft tokens. The same user text produces 4078/24156 Ollama input tokens versus 4036/24114 llama.cpp tokens because templates differ. Ollama decode uses n/time; llama.cpp uses (n-1)/time. This is a default-system comparison, not an isolated MTP causal estimate.

The pooled report shows the candidate improving decode over production by 15.00% short and 20.86% long, with prefill changes of -0.76% and -0.66%. Default Ollama had higher long-prompt prefill than either llama.cpp profile. CANON retains individual lower-middle decode observations with their paired prefill, not report-level pooled averages. Quality is limited to one completed short check per configuration. All 120 prior rows were preserved exactly; 9,796 exported cells and six newly selected timing pairs were checked. A GPU-index preflight failure in earlier job 265066 occurred before inference and remains campaign evidence, without a fabricated configuration-performance row.

## November 4 Flash Next on three Wright L40s

Two additional three-GPU rows cover default Ollama and the ordinary V100 production Flash Next profile ported to Wright. The supplement `canon_additions/wright-flash-next-3l40-20261104.json` contains eight uncached 512-output probes, two passing completed short-answer checks, settings, device placement, and raw observation references. Both engines placed the target across all three GPUs. They were measured on different physical trios on n03 after a logging-only production retry. See the campaign report for pooled comparisons and the CSV for individual short/long representative pairs.

## November 5 Muse Glimmer on one Wright L40

Three rows cover default Ollama, the saved production DFlash11/temperature1 profile adapted to one GPU and one slot, and that profile with DFlash15/temperature0.75. All ran sequentially on the same physical L40 in Slurm job 266776, with 12 logical CPUs, 64GiB host RAM and the cluster's 300W limit. The supplement `canon_additions/wright-glimmer-1l40-20261105.json` retains twelve cold fixed-512 speed probes and three completed short final-answer checks. All final-channel JSON answers matched exactly. Raw completions include native reasoning and channel markers, so they require final-channel extraction; the original harness's formatting failures are preserved separately from verified semantic correctness.

Draft 17 was initially requested and prepared, but exceeds this DFlash runtime's effective 15-token cap for the trained 16-position block. The user approved explicit draft15 before execution. No separate draft17 timed run occurred. The candidate records draft_tokens=15 and this history in cautions.

Both llama.cpp runs retain 262,144 context per slot, F16 target/draft KV, 8/12 decode/prefill threads, 4096/512 batch/microbatch, FlashAttention and high reasoning. The exact production source patch was rebuilt for the Wright runtime. Ollama resolved to 32K context, 128/128 threads constrained by the allocation, 1024/1024 batching, F16 KV, temperature0.8/top-k40/top-p0.9, and no DFlash. This is a full-configuration comparison, not a causal isolation of speculative decoding.

The report pools two trials per length: candidate decode was +17.55% short and +4.82% long versus production; long prefill was -5.87%. Long candidate decode ranged from 110.62 to 148.64 t/s, so the small pooled gain is not a reliable general improvement claim. CANON retains individual lower-middle decode examples and their paired prefill, not these pooled rates. Minimum free GPU memory remained at least 23,466MiB and peak temperature was 50C. All 125 previous rows were preserved exactly, six new selected timing pairs were checked, and 10,191 exported cells were verified. The GPU allocation was released.
