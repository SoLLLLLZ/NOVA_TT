# Developer scripts

`live_byteshape.py` runs the actual API against Wright: default Ollama, an OpenRouter-selected optimized profile, sequential race, and rollback/release. It writes private receipts under `var/live-byteshape/`. `--profile-only` bypasses OpenRouter and requests the registered MTP5 profile explicitly. Run only when GPU work is intended; see `backend/README.md`.
