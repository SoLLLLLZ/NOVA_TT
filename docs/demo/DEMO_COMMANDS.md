# CMUTuneIt live demo commands

Google Doc: https://docs.google.com/document/d/1xQQXhorkL4drHkqtOYHXWrzy1S2fI5zRfhqcTU6Lprw/edit?tab=t.0

Repository: https://github.com/SoLLLLLZ/NOVA_TT

Run these commands in macOS Terminal on Taeho's demo Mac. The launchers send inference to Wright L40 GPUs through Slurm. A bare `ollama serve` on the Mac would serve locally. Default Ollama remains separate from CMUTuneIt; the same prompt is typed interactively in each run. Do not paste the `>>>` prompt marker itself.

## 0. Prepare the connection and widget

In each terminal you will use, enter the repository:

```sh
cd "/Users/taeholee/Documents/ChatGPT/P100 Project/tmp/nova-canon-publish-20261107"
```

Check the existing authenticated Wright connection:

```sh
ssh -S /tmp/wright-glimmer-20261105-501/control -O check taeholee@wright.hss.cmu.edu
```

If it prints `Master running`, continue. If the connection has expired, run the following in a separate connection terminal. Complete the normal Wright login there and leave that terminal open:

```sh
mkdir -p /tmp/wright-glimmer-20261105-501
chmod 700 /tmp/wright-glimmer-20261105-501
ssh -M -S /tmp/wright-glimmer-20261105-501/control \
  -o ControlMaster=auto -o ControlPersist=12h \
  -o ServerAliveInterval=30 -o ServerAliveCountMax=10 \
  -o TCPKeepAlive=yes -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=/tmp/wright-access-check-20261103-known_hosts \
  taeholee@wright.hss.cmu.edu
```

These paths match this Mac's configured backend and existing trusted host-key file. Keepalives help maintain an idle connection; they cannot guarantee survival through sleep, network loss or server policy. Run the remaining commands in Mac terminals, not inside the remote Wright shell.

Open the prepared widget:

```sh
open frontend/release/CMUTuneIt.app
```

Option+Space shows or hides CMUTuneIt. If a previous optimized model is still loaded, click REVERT SETUP before beginning the baseline.

## 1. Terminal A: start default Ollama on Wright

```sh
cd "/Users/taeholee/Documents/ChatGPT/P100 Project/tmp/nova-canon-publish-20261107"
./scripts/ollama-wright serve qwen3.8-27b
```

Wait for READY. Leave this terminal running. The launcher prints the actual remote `ollama serve` executable and Slurm job; the GPU work runs on Wright. Do not proceed while weights are still loading.

## 2. Terminal B: run the verbose Ollama baseline

```sh
cd "/Users/taeholee/Documents/ChatGPT/P100 Project/tmp/nova-canon-publish-20261107"
./scripts/ollama-wright run qwen3.8-27b --verbose
```

At `>>>`, type this prompt and press Return:

```text
Write a short essay explaining the causes of the Industrial Revolution
```

The essay streams in Terminal. At completion, show the judges the Default Ollama decode line in tokens/s. Verbose output also prints prefill speed, token counts, phase durations, timing convention and the saved receipt path. This launcher reports Ollama's own native timing measurements; its only inference override is the 2048-token output cap. It returns to the shell after one prompt.

## 3. Stop the baseline, then optimize

In Terminal A, press Control+C once. Wait for:

```text
Ollama stopped. Owned Slurm allocation released.
```

Open CMUTuneIt with Option+Space. Select Wright / L40 / Qwen3.8 27B, then click PITSTOP · OPTIMIZE. Wait for SETUP OPTIMIZED. Scroll the Model settings panel to show the 20 key applied settings. Arrows identify changed values; other rows show their current value. CMUTuneIt calls Astra through OpenRouter and verifies the selected configuration. This does not launch Ollama.

## 4. Terminal B: select the optimized model and run the prompt

```sh
./scripts/cmutuneit run qwen3.8-27b --verbose
```

The terminal prints the model, engine, profile, draft size, temperature and Wright job. At `>>>`, type the same prompt and press Return:

```text
Write a short essay explaining the causes of the Industrial Revolution
```

The answer streams in Terminal while CMUTuneIt's live speedometer updates. Show the final Decode line and compare it with the earlier Ollama number. The widget rounds the final rate to a whole number. Verbose output includes prefill speed and native timing details. Repeat the command for another prompt; it reuses the retained optimized model.

## 5. Finish and release the GPU

Click REVERT SETUP in CMUTuneIt. It returns to model selection and releases its owned allocation. Leave CMUTuneIt open if you want the menu-bar icon available for another demo.

Optional read-only check from a Mac terminal:

```sh
ssh -S /tmp/wright-glimmer-20261105-501/control \
  -o BatchMode=yes -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=/tmp/wright-access-check-20261103-known_hosts \
  taeholee@wright.hss.cmu.edu 'squeue -u taeholee'
```

This lists your jobs; unrelated jobs may remain. Do not cancel unrelated allocations.

## Other model selections

Use only one model at a time. Stop the baseline before optimizing, and revert the current CMUTuneIt setup before switching models. Flash Next needs three L40 GPUs; Glimmer needs one.

Glimmer baseline (serve in Terminal A, run in Terminal B):

```sh
./scripts/ollama-wright serve muse-glimmer
./scripts/ollama-wright run muse-glimmer --verbose
```

After selecting and optimizing Glimmer in CMUTuneIt:

```sh
./scripts/cmutuneit run muse-glimmer --verbose
```

Flash Next baseline (serve in Terminal A, run in Terminal B):

```sh
./scripts/ollama-wright serve qwen3.8-flash-next
./scripts/ollama-wright run qwen3.8-flash-next --verbose
```

After selecting and optimizing Flash Next in CMUTuneIt:

```sh
./scripts/cmutuneit run qwen3.8-flash-next --verbose
```

## Reading the numbers

Decode is generation speed; prefill is prompt-processing speed. Compare the two final decode lines. An earlier ByteShape rehearsal measured 27.14 tokens/s for Ollama and 70.10 tokens/s for the optimized profile (2.58×). These are recorded results, not promised live rates. Settings, contexts, prompt tokenization and answer lengths differ, so this is a whole-configuration demo rather than an isolated MTP comparison. Source: docs/demo/widget-integration-validation-20261107.json.

Private raw receipts are under var/ollama-demo/ and var/terminal/. They are excluded from Git. No API key needs to be copied into these commands.
