# Developer and demo scripts

- `generate.py --model <id>` sends a prompt through the already optimized Wright service, driving `/live` without another agent call or model load. Default prompt: `Write a short essay explaining the causes of the Industrial Revolution`. Default output cap: 2048, with natural stopping.
- `check_live_models.py --model <id>` runs a standalone Ollama comparison, stops it, then calls the real production OpenRouter/Astra `/optimize` path and tests `/generate` plus `/live`. No explicit profile override. It releases the owned allocation and saves private receipts under `var/production-<model>-<timestamp>/`. Model IDs: `qwen3.8-27b`, `muse-glimmer`, `qwen3.8-flash-next`.
- `live_byteshape.py` wraps the preceding test for ByteShape. Historical race/profile-only flags no longer apply.
- `check_live_byteshape.py` retains the explicit-profile ByteShape `/live` transport test; it does not call OpenRouter.

GPU tests are opt-in. Ollama runs only in these separate developer/demo comparisons, never in any production optimization pipeline. Prepare large Flash artifacts before the presentation timer. Reused standalone baseline receipts are explicitly identified; they are not fresh measurements.

## Live menu-bar demo

Use `./scripts/ollama-wright serve` and `./scripts/ollama-wright run qwen3.8-27b` for the standalone default baseline. Stop serve with Ctrl+C before optimizing in CMUTuneIt. Then `./scripts/cmutuneit run qwen3.8-27b` selects the retained optimized model and asks for a prompt. See [WIDGET_DEMO.md](../docs/demo/WIDGET_DEMO.md).
