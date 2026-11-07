# Frontend mock mode

Use the real API schemas and runner with the simulated driver:

```sh
NOVA_MODE=mock NOVA_STATE_DIR=var/mock uv run uvicorn nova_backend.app:app --host 127.0.0.1 --port 8000 --workers 1
```

Read `var/mock/pairing-token` locally. All results are explicitly marked simulated. Mock rates are fixtures and must never be displayed as real hardware measurements.
