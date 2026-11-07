# Frontend: TuneIt widget

Owner: partner. Chrome Manifest V3 extension. Clicking the toolbar icon opens a small standalone 400×820 window that stays open while you run the model in a terminal. Built with Vite, React and TypeScript against [API contract v2.1](../docs/api/endpoint.md) and the [demo model catalog](../docs/demo/DEMO_MODELS.md).

Flow: pair → choose cluster, GPU and model (the car changes with the model) → **PITSTOP · OPTIMIZE** (spin → drive → service animation with the live step checklist) → **SETUP OPTIMIZED** (changed settings only, no speeds) → the student runs the model in a terminal → **LIVE SPEED** gauge from `GET /live`. **REVERT TO DEFAULTS** is available on both tuned screens.

## Run

Requires Node 22+.

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173/widget.html in a normal tab
npm test             # vitest: SSE parser, gauge scale, change rows, checklist, state machine
npm run build        # typecheck + build the extension into frontend/dist
```

Load the extension: open `chrome://extensions`, enable Developer mode, choose **Load unpacked** and select `frontend/dist`. Click the toolbar bolt to pop the widget open; clicking again focuses the existing window.

Without the real backend, start the [mock](../tests/mocks/README.md) first and pair with the code it prints (`7K4-92X` by default).

## Layout

| Path | Purpose |
| --- | --- |
| `src/App.tsx` | Side effects: connect/pair, optimize stream + run polling, `/live` subscription, revert |
| `src/state/machine.ts` | Pure reducer for every screen state (unit tested) |
| `src/state/steps.ts` | Maps contract step names onto the five checklist rows |
| `src/api/` | Contract types, fetch client with pairing/idempotency headers, SSE parser |
| `src/lib/changes.ts` | Turns `changes` into readable rows (merges decode/prompt threads and K/V cache) |
| `src/lib/gauge.ts` | Speedometer scale `0 10 20 40 80 120 160 200`; 20 at top centre, 200 far right |
| `src/screens/`, `src/components/` | UI; styles in `src/styles/` |
| `src/models.ts` | Per-model names, captions, car sprites and colours |
| `src/background.ts`, `public/manifest.json` | Toolbar button → pop-out window |
| `assets/design/` | Source mockup and car sheet supplied for the design |
| `scripts/extract-cars.mjs` | Cuts the car sheet into transparent sprites (`npm run assets`, needs `sharp`) |

The product name is a placeholder in `src/config.ts` (`APP_NAME`) and `public/manifest.json`. The backend URL defaults to `http://localhost:8000` and must match the manifest's `host_permissions`.

## Behaviour notes

- Optimize sends `mode: "verify_only"` with `allow_sampling_change: true`. Success requires `applied: true` and a passed validation. The changed-settings list comes from the backend's `changes` (falling back to a config diff), so values such as temperature 1 → 0.75 are shown explicitly.
- No speed is shown until `/live` reports a real request. Historical CANON numbers are never displayed.
- Idempotency keys are kept per click. A dropped stream or a replayed key switches to polling `GET /runs/{id}` instead of re-posting. Reopening the widget resumes an active run or a tuned result.
- Cluster list: Wright is supported. Babel, Bridges-2 and FLAME are listed but disabled until the backend advertises them.
- `prefers-reduced-motion` replaces the pitstop sequence with the service scene and disables the tweens.
