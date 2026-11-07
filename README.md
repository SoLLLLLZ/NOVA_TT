# NOVA

A simple model/GPU setup tool that uses CANON evidence and an OpenRouter agent to select a conservative inference configuration, verify it, and show decode performance against default Ollama. The demo targets Wright L40 GPUs with ByteShape Qwen 3.8 27B, Qwen 3.8 Flash Next Q4 and Muse Glimmer Q4.

Shared repository: https://github.com/SoLLLLLZ/NOVA_TT

**Current status:** API v2.1 contract, agent instructions and inference evidence are available. The widget frontend ([frontend/](frontend/README.md)) and a contract mock server ([tests/mocks/](tests/mocks/README.md)) run locally. Backend and deployment code are not implemented yet; their folders are placeholders.

## Start here

1. Read the [API v2 contract](docs/api/endpoint.md) before connecting frontend and backend.
2. Use the [three demo models](docs/demo/DEMO_MODELS.md) for names, IDs, resource requirements and config examples.
3. Read the [optimizer instructions](backend/prompts/OPTIMIZER_AGENT.md) and [CANON guide](data/canon/CANON_GUIDE.md) before implementing selection.
4. Put implementation code in the folders below and add actual install/run commands when choosing the stack. No language or framework is imposed by these placeholders.

## Repository layout

```text
NOVA_TT/
├── README.md
├── .gitignore
├── backend/
│   ├── README.md
│   ├── src/                     # Future API, agent tools, runtime adapters and run control
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
│   └── profiles/               # Future registered model/runtime configurations
├── scripts/                    # Future developer and preparation commands
├── deploy/
│   └── wright/                 # Future Slurm jobs and private service launchers
├── tests/
│   ├── README.md
│   ├── fixtures/               # Future small, sanitized test cases
│   └── mocks/                  # Future frontend mock server
└── var/                        # Local run state/cache/logs; ignored except its README
```

Folders with no implementation contain a README or `.gitkeep` so Git tracks them. These files do not select a package layout; adapt `src/` to the chosen framework when implementation starts.

## Ownership and shared boundaries

| Area | Owner / purpose |
| --- | --- |
| backend, prompts, profiles, Wright deployment | Taeho: selection, OpenRouter, execution, benchmarking and lifecycle |
| frontend | Partner: model/GPU selection, progress, comparison, error states and API client |
| API contract and integration mocks | Shared: both sides must use contract version 2.1 |
| CANON evidence | Shared source of truth; preserve provenance and keep measured hardware distinct |

Keep the normal UI simple. The backend applies the complete supported configuration and reports effective settings; the frontend displays them. Update the API contract, affected examples and implementations together when changing shapes. Match mocks to the same version and label simulated results.

## Data and local state

- [CANON.csv](data/canon/CANON.csv) is the curated evidence table. Keep its [guide](data/canon/CANON_GUIDE.md), [validation receipt](data/canon/CANON_VALIDATION.json) and [lessons](data/canon/qualitative_lessons.json) alongside it.
- Historical raw-record paths inside the evidence refer to the original P100 Project research workspace. This repository is not a copy of the complete experiment archive.
- Future deployable profiles belong in `configs/profiles/`; CANON rows and documentation examples are not complete executable profiles.
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
