# Backend validation

Run `uv run pytest -q`. Tests cover authentication, strict model-specific settings, profile/evidence isolation, no-Ollama production paths for all three models, idempotency, context/sampling constraints, quality failures, resource locks, cancellation, rollback, model-channel parsing and native live telemetry. Mock measurements are explicitly simulated, not performance evidence.

`scripts/check_live_models.py --model <id>` performs opt-in Wright tests with a separate Ollama reference and the real OpenRouter/Astra production pipeline. Private receipts go under ignored `var/`; sanitized hardware validation belongs in `docs/demo/`. The former in-tool baseline/race features are intentionally disabled and regression-tested as rejected requests.
