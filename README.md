# NOVA

A simple model/GPU setup tool that uses CANON evidence and an OpenRouter agent to select a conservative inference configuration, verify it, and show live decode performance. Default Ollama is a separate demo baseline, outside all production optimization pipelines. The demo targets Wright L40 GPUs with ByteShape Qwen 3.8 27B, Qwen 3.8 Flash Next Q4 and Muse Glimmer Q4.

Shared repository: https://github.com/SoLLLLLZ/NOVA_TT

**Current status:** The Python FastAPI backend, explicit frontend mock mode, registered profiles for all three models and Wright Slurm worker are implemented. Start with [backend setup and usage](backend/README.md). All three models are enabled; Glimmer uses one L40 and its patched runtime, and Flash requires three L40s on one node.

[Latest hardware validation](docs/demo/GLIMMER_FLASH_VALIDATION.md): Glimmer and Flash both passed the real Astra production path, generation and live feed. Flash decoded at 71.33 tokens/s versus the reused standalone Ollama baseline of 15.18 tokens/s (4.70×); see the report for configuration and allocation differences.

The widget frontend (floating desktop widget and Chrome extension) is in [frontend/](frontend/README.md); a standalone stdlib mock for frontend work is in [tests/mocks/](tests/mocks/README.md).

## Start here

1. Read the [API v2 contract](docs/api/endpoint.md) before connecting frontend and backend.
2. Use the [three demo models](docs/demo/DEMO_MODELS.md) for names, IDs, resource requirements and config examples.
3. Read the [optimizer instructions](backend/prompts/OPTIMIZER_AGENT.md) and [CANON guide](data/canon/CANON_GUIDE.md) before implementing selection.
4. Run `uv sync --locked`, then follow the backend README to launch real or explicitly simulated mode.

## Repository layout

```text
NOVA_TT/
├── README.md
├── .gitignore
├── backend/
│   ├── README.md
│   ├── src/                     # API, OpenRouter selection, runtime adapter and run control
│   └── prompts/
│       └── OPTIMIZER_AGENT.md
├── frontend/
│   ├── README.md
│   ├── src/                     # Future widget/extension UI and API client
│   └── assets/                  # Icons and other static UI assets
├── docs/
│   ├── api/endpoint.md          # Authoritative frontend/backend contract
│   └── demo/DEMO_MODELS.md      # Demo catalog and profile reference
├── data/
│   └── canon/                  # CSV, interpretation guide, validation and lessons
├── configs/
│   └── profiles/               # Pinned model/runtime configurations
├── scripts/                    # Terminal generation and standalone comparison tests
├── deploy/
│   └── wright/                 # Private Slurm worker
├── tests/
│   ├── README.md
│   ├── fixtures/               # Future small, sanitized test cases
│   └── mocks/                  # Same-API simulated frontend mode
└── var/                        # Local run state/cache/logs; ignored except its README
```

Frontend placeholders remain for the partner's implementation. Backend package and locked dependencies are defined by `pyproject.toml` and `uv.lock`.

## Ownership and shared boundaries

| Area | Owner / purpose |
| --- | --- |
| backend, prompts, profiles, Wright deployment | Taeho: selection, OpenRouter, execution, benchmarking and lifecycle |
| frontend | Partner: model/GPU selection, progress, live speed, default-vs-tuned comparison, error states and API client |
| API contract and integration mocks | Shared: both sides must use contract version 2.1 |
| CANON evidence | Shared source of truth; preserve provenance and keep measured hardware distinct |

Keep the normal UI simple. The backend applies the complete supported configuration and reports effective settings; the frontend displays them. Update the API contract, affected examples and implementations together when changing shapes. Match mocks to the same version and label simulated results.

## Data and local state

- [CANON.csv](data/canon/CANON.csv) is the curated evidence table. Keep its [guide](data/canon/CANON_GUIDE.md), [validation receipt](data/canon/CANON_VALIDATION.json) and [lessons](data/canon/qualitative_lessons.json) alongside it.
- Historical raw-record paths inside the evidence refer to the original P100 Project research workspace. This repository is not a copy of the complete experiment archive.
- Deployable profiles belong in `configs/profiles/`; CANON rows and documentation examples are not complete executable profiles.
- Put local run manifests, benchmark output, caches and logs under `var/`. Put small sanitized test fixtures under `tests/fixtures/`.
- Keep model weights on Wright or outside Git. The repo's `.gitignore` excludes common weight formats, credentials, environment secrets and generated files. It is a convenience, not a guarantee that a file contains no secrets.
- Store the OpenRouter key in macOS Keychain or backend secret storage. Never put it in a committed file, prompt, fixture or frontend bundle. Never store SSH passwords/private keys here.

## Paths moved during organization

| Previous root path | Current path |
| --- | --- |
| `endpoint.md` | `docs/api/endpoint.md` |
| `DEMO_MODELS.md` | `docs/demo/DEMO_MODELS.md` |
| `OPTIMIZER_AGENT.md` | `backend/prompts/OPTIMIZER_AGENT.md` |
| `CANON.csv`, `CANON_GUIDE.md`, `CANON_VALIDATION.json`, `qualitative_lessons.json` | `data/canon/` with the same filenames |

Update local references after pulling this change. The four CANON evidence files were moved without changing their contents. No GPU job or application is launched by this reorganization.
