# Frontend mock mode

There are two ways to run the API without GPUs. Both label every rate as simulated; never display mock rates as real hardware measurements.

## Backend mock mode (real schemas and runner)

Use the real API schemas and runner with the simulated driver:

```sh
NOVA_MODE=mock NOVA_STATE_DIR=var/mock uv run uvicorn nova_backend.app:app --host 127.0.0.1 --port 8000 --workers 1
```

Read `var/mock/pairing-token` locally. All results are explicitly marked simulated. Mock rates are fixtures and must never be displayed as real hardware measurements.

## Standalone stdlib mock (frontend development)

`mock_server.py` implements [API contract v2.1](../../docs/api/endpoint.md) for the three [demo models](../../docs/demo/DEMO_MODELS.md). It uses only the Python standard library. Profiles and changes mirror DEMO_MODELS. Every rate it emits is simulated, and its measurements carry the warning `mock fixture: not a real measurement`. It runs no inference and touches no GPU, Slurm or OpenRouter.

```bash
python3 tests/mocks/mock_server.py              # http://127.0.0.1:8000, pairing code 7K4-92X
python3 tests/mocks/simulate_terminal.py        # pretend the student ran the tuned model → /live events
python3 -m unittest tests/mocks/test_mock_server.py
```

Environment switches:

| Variable | Values | Effect |
| --- | --- | --- |
| `NOVA_PAIRING_CODE` | any string | Pairing code to accept (default `7K4-92X`) |
| `MOCK_SCENARIO` | `success`, `repair`, `fail` | Normal run; out-of-memory then fallback profile; terminal `out_of_memory` error |
| `MOCK_ALLOCATION` | `running`, `none` | Existing 3×L40 allocation, or none (optimize "requests" one) |
| `MOCK_SPEED` | number | Multiplies step delays (tests use `0.01`) |
| `MOCK_AUTO_INFERENCE_SECONDS` | number | Fake a terminal request N seconds after a successful optimize |
| `MOCK_QUIET` | `1` | Silence request logs |

Covered: health, status, capabilities, profiles, optimize (verify_only and sequential_compare), runs, cancel, revert, action, chat, diagnose and live. Also covered: idempotent replay and conflicts, one active operation at a time, unknown-field rejection, and 401 without a pairing token.

`POST /mock/inference {"model": "<id>"}` is mock-only and not part of the contract. It stands in for the real backend noticing a request on the retained tuned service.

Default Ollama is outside the tool. `apply_default` is rejected, matching the production backend. Use the standalone Wright terminal launcher for actual baseline demonstrations.
