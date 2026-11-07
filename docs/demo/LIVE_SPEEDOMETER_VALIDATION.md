# ByteShape live speedometer validation

Verified November 7, 2026 on Wright, one owned Slurm L40 allocation (`268027`), using the pinned ByteShape Qwen3.8 27B IQ3_S artifact and registered MTP5 / temperature 0.75 profile. This test selected the profile explicitly; it did not make another OpenRouter call. Glimmer and Flash were not tested.

The real FastAPI server received two authenticated `/generate` requests while one authenticated `/live?model=qwen3.8-27b` connection remained open. Both used exactly:

> Write a short essay explaining the causes of the Industrial Revolution

| Request | Native decode | Output tokens | Live samples | Delivered updates/sec | Median interval | Maximum interval |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 69.80 tok/s | 764 | 55 | 4.92 | 201 ms | 248 ms |
| 2 | 69.25 tok/s | 764 | 54 | 4.85 | 201 ms | 321 ms |

Both answers ended naturally (`eos`) below the 2048-token cap. Rates include reasoning tokens. Each final decode rate is `(predicted_n - 1) / native decode seconds`; the final `/live` measurement exactly matched the `/generate` result. Prefill was 78.66 and 77.04 tokens/sec with 21 prompt tokens and zero cached tokens. The speedometer shows a running native request average, not a rolling estimate from text chunks.

The target is five updates per second. The worker obtains native per-token timings, a persistent private SSH channel forwards new samples, and each observer delivers the newest sample on a 200 ms cadence. Network/runtime timing can reduce actual frequency; no samples are interpolated or repeated to fill gaps. The initial implementation delivered about 3 Hz; the cadence was corrected before this final test.

Validated: initial waiting event, two started/done pairs, native metrics during generation, contiguous per-connection sequence numbers, no Optimize measurements on `/live`, terminal error on revert, and 404 after release. The test allocation was released and the subsequent scheduler read showed no jobs for the test user. Local tests also cover authentication, unknown models, reconnect snapshots, bounded observers, rate limiting, native timing validation, partial transport lines, idempotency, cancellation and failure recovery.

After Optimize, run `uv run python scripts/generate.py` on the Mac to drive the widget. Direct calls to private llama.cpp ports are not instrumented. Frontend rendering itself was not exercised in this backend test; the event shapes match the partner's v2.1 branch, with the requested cadence increased from four to five updates/sec.

Sanitized receipt: [live-speedometer-validation-20261107.json](live-speedometer-validation-20261107.json). Private full receipts remain under `var/live-speedometer-1794074278388363000/`; native raw responses remain in the private per-job Wright directory.
