# Developer scripts

`live_byteshape.py` runs the actual API against Wright: default Ollama, an OpenRouter-selected optimized profile, sequential race, and rollback/release. It writes private receipts under `var/live-byteshape/`. `--profile-only` bypasses OpenRouter and requests the registered MTP5 profile explicitly. Run only when GPU work is intended; see `backend/README.md`.

The default speed probe and rehearsal race use the exact demo prompt: `Write a short essay explaining the causes of the Industrial Revolution`. Optimize measures a capped 256-token probe; the rehearsal race permits natural completion up to 2048 tokens, including reasoning. The separate arithmetic check verifies basic runtime correctness. The workload selection does not repeat or change the demo prompt. Use `--output-dir var/live-industrial-revolution` to preserve earlier receipts; `--simultaneous` allocates two L40s for the race.
