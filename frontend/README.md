# Frontend

Owner: partner. Future UI/API-client code goes in `src/`; static assets go in `assets/`. Adapt these placeholders if the chosen macOS widget/browser-extension framework needs a different layout.

Use the [API v2 contract](../docs/api/endpoint.md) and [demo model catalog](../docs/demo/DEMO_MODELS.md). Show model/GPU selection, readiness, real progress, decode performance and failures. Keep advanced settings in an expandable detail view; the backend owns capability validation and GPU execution.

Use the pairing token for backend requests; never embed or request the OpenRouter key in the frontend. Use [tests/mocks](../tests/mocks/) for a future contract-compatible mock server and clearly label mock data.

No frontend framework or runnable UI has been added yet. Add actual build/run commands here after implementation.
