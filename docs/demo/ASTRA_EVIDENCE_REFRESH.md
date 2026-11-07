# Astra evidence refresh — November 7, 2026

The new CANON rows were already sent to Astra, but its system instructions still favored the older MTP5/0.75 and DFlash15/0.75 configurations, and the registered selection menu excluded most newly measured settings. Both instructions now prioritize matching Industrial Revolution evidence. Six complete, unchanged experiment configurations are registered: ByteShape A2; Glimmer A3/D3/B3; Flash A5/C5. Existing profiles also cite matching campaign control observations. All 50 recent observations remain available as evidence; unrelated track winners are not combined.

Three real OpenRouter calls to GPT-6 Astra, high reasoning, returned priority-tier selections:

| Model | Selected settings | Selection time | Campaign source |
| --- | --- | ---: | --- |
| Qwen3.8 27B | MTP3, temperature 0.75 | 6.581 s | A2, cfg_8f6054cbe8f82879 |
| Muse Glimmer | DFlash15, temperature 0.25 | 7.185 s | B3, cfg_e53e9357cdad567e |
| Qwen3.8 Flash Next | MTP2, temperature 0.5 | 11.545 s | A5, cfg_a29eda3be71d4808 |

These were selection-only calls, not new GPU tests or end-to-end Optimize validations. Historical speeds are single observations, not promised live rates. Smaller drafts are favored only where measured evidence supports them; higher temperature remains a conditional preference when it does not reduce decode. Explicit sampling locks, required context, runtime identity and resource requirements remain enforced. Web search remains disabled. Every production Optimize must still apply the selected configuration, pass the completed correctness check, collect live timings, and repair or fail honestly.

Validation: 74 backend tests passed, including full campaign evidence delivery, exact configuration equality with experiment receipts, profile IDs, source lineage and sampling locks. All 12 shell blocks in the demo guide passed syntax checks; both launchers' help interfaces and the app path were verified. The existing authenticated Wright master and read-only Slurm job query succeeded, with no jobs shown. No Ollama baseline was rerun.

The Google Doc was edited in place and read back: replaced the removed `scripts/tuneit` command with `scripts/cmutuneit`, corrected the app name/path to CMUTuneIt, matched the `Qwen3.8 27B` picker label, and identified the older rehearsal as historical. Other commands were checked against the current launcher and driver implementation. Its formatting and section structure were preserved. The repository copy is [DEMO_COMMANDS.md](DEMO_COMMANDS.md).

See the [selection and validation receipt](astra-evidence-refresh-20261107.json) for effective settings, returned selection explanations, source IDs and input hashes.
