# Menu-bar and terminal demo

The CMUTuneIt Electron widget connects to the real local Python backend, which calls OpenRouter Astra high and deploys a verified llama.cpp profile under Slurm on Wright. Default Ollama is **outside the tool** for all three models.

For the complete copy-paste terminal sequence, including SSH recovery and verbose timing, see [Demo commands](DEMO_COMMANDS.md).

## Start the widget

From the repository root, prepare dependencies once:

```sh
uv sync --locked
cd frontend
npm ci
npm run desktop:bundle
```

Open `frontend/release/CMUTuneIt.app`. This local bundle points to this checkout; rebuild it after moving the checkout or changing frontend code. It starts the backend on loopback port 8000 when needed and reads the private local pairing token. The frontend never reads the OpenRouter key. Keep the existing authenticated Wright SSH connection open.

The bolt in the macOS menu bar and **Option+Space** show/hide the floating widget. Hiding keeps the backend and retained model alive. **Revert setup** unloads this demo's model; quitting stops the backend child owned by the app. An existing external backend is reused and is not stopped by the widget.

## 1. Demonstrate default Ollama in Terminal

Open Terminal and change into the repo root. Run:

```sh
./scripts/ollama-wright serve
```

This is an explicitly labeled Wright launcher: it starts the **real `ollama serve` binary on an allocated L40**, checks the installed model/runtime, and prints the Slurm job and remote command. A bare `ollama serve` on the Mac would run locally instead. The launcher changes no sampling/thread/context settings; its private loopback server and model store isolate the demo.

Wait for **READY**. In a second terminal, from the repo root:

```sh
./scripts/ollama-wright run qwen3.8-27b --verbose
```

At `>>>`, type:

```text
Write a short essay explaining the causes of the Industrial Revolution
```

The answer and native decode rate print in Terminal; a private receipt is saved under `var/ollama-demo/`. The only inference override is a 2048-token output cap. **After completion, press Ctrl+C in the serve terminal and wait for “Owned Slurm allocation released.”**

## 2. Optimize in the widget

1. Open CMUTuneIt from the menu bar or Option+Space.
2. Select Wright, L40 and ByteShape Qwen3.8 27B.
3. Click **PITSTOP · OPTIMIZE**.
4. Wait for **SETUP OPTIMIZED** and the verified settings. The tested candidate changes draft maximum 3 → 5 and temperature 1 → 0.75. Astra chooses the compatible profile; no Ollama step runs.

The changed settings compare against the registered native reference, not an automatically measured Ollama configuration. Verification includes a short completed arithmetic check; it is not a broad model-quality guarantee. Astra has no web-search tool.

## 3. Select the optimized model and type the prompt in Terminal

```sh
./scripts/cmutuneit run qwen3.8-27b --verbose
```

This prints the actual model, engine, profile, draft/temperature and Wright job before the `>>>` prompt. Type the same Industrial Revolution prompt. It streams the final answer through the real `/generate` endpoint while the widget receives `/live` timing updates. The terminal and widget final decode rates must agree (the widget rounds to an integer). Receipts are saved under `var/terminal/`.

The widget displays **Completed** when generation ends. Click **REVERT SETUP** when finished to release the allocation. Leave the app running if you want its menu-bar item available for the next rehearsal.

## Observed integration rehearsal — November 7

- Standalone Ollama: **27.14 tokens/s**, 278 output tokens, natural completion, job 268037.
- Widget-selected native MTP5 / temperature 0.75: **70.10 tokens/s**, 764 output tokens, natural completion, job 268038.
- Observed decode ratio: **2.58×**. This is one whole-configuration comparison with different contexts, sampling, tokenized prompts and output lengths, not a universal speedup or an isolated MTP effect.
- The widget displayed actual progress, verified settings, live **Generating**, and final **70 tok/s / Completed**. No historical CANON rate was inserted into the speedometer.
- Computer use performed the native widget interactions. macOS Terminal was explicitly unavailable to computer use, so the terminal portions were performed with the terminal execution tool using interactive prompts. This was not a GUI-automated Terminal rehearsal.

See [the machine-readable receipt](widget-integration-validation-20261107.json) for measurement, configuration, baseline lineage and checks.
