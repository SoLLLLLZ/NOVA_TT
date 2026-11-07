# API Contract (v0.1)

This file is the agreement between the **extension (frontend)** and the **backend**.
Both sides build to it. If either side needs a change, edit this file in the same
commit and tell the other person. Do not change a response shape silently.

- Base URL (local / SSH tunnel): `http://localhost:8000`
- Body format: JSON (`Content-Type: application/json`)
- Contract version is returned by `GET /status` as `contract_version`.

---

## Why this contract exists

The extension runs in the browser and cannot do the real work: it can't read the GPU,
restart Ollama, or safely hold the OpenRouter key. The backend can. The two halves talk
only through the endpoints below, so:

1. Each person can build their half against the agreed shapes without waiting.
2. The frontend can run against `mock/mock_server.py` until the real backend exists.
3. If a screen breaks, check whether the backend output matches this file. If yes, the bug
   is in the frontend; if no, it is in the backend.

---

## Conventions

### Auth (pairing code)
On startup the backend prints a pairing code (e.g. `7K4-92X`). The student pastes it into the
extension once. Every request except `GET /health` must send:

```
X-Pairing-Token: <pairing code>
```

Missing or wrong token returns `401` with the standard error body.

### Standard error body (any non-2xx response, and `error` stream events)
```json
{
  "error": {
    "code": "out_of_memory",
    "message": "Model needs 31 GB but only 20 GB is free.",
    "diagnosable": true
  }
}
```
`diagnosable: true` means the frontend may offer a "Fix it" button that calls `POST /diagnose`.

Error codes: `unauthorized`, `bad_request`, `model_not_found`, `out_of_memory`, `gpu_busy`,
`benchmark_failed`, `ai_unavailable`, `internal`.

### Streaming (used by `/optimize`, `/race`, `/chat`)
Streaming endpoints are `POST` and reply with `Content-Type: text/event-stream`.
Each event is one line: `data: <json>` followed by a blank line. The frontend reads it with
`fetch` + `response.body.getReader()` (EventSource cannot send POST bodies).
Every event has a `type` field. A stream always ends with either a `done` or an `error` event.

### Shared enums
| Name | Values |
|---|---|
| `preset` | `fastest`, `balanced`, `quality` |
| `confidence` | `verified` (exact model+GPU in database), `inferred` (similar rows), `experimental` (AI proposed, tested live) |
| `engine` | `ollama`, `llama.cpp` |
| `kv_type` | `f16`, `q8_0`, `q4_0` |
| `step name` | `detect_gpu`, `check_database`, `ask_ai`, `test_configs`, `apply` |
| `step status` | `pending`, `running`, `done`, `failed` |
| `action` (safe actions) | `apply_config`, `revert`, `lower_context`, `switch_quantization`, `run_benchmark` |

### Shared object: `config`
Only fields the tool is allowed to set. Any field may be `null` if not applicable.
```json
{
  "engine": "ollama",
  "threads": 12,
  "context_tokens": 32768,
  "batch_size": 1024,
  "kv_type": "f16",
  "flash_attention": true,
  "quant": "IQ3_S hybrid 3.23bpw",
  "speculative_mode": "none"
}
```

### Shared object: `speed`
```json
{ "decode_tps": 22.5, "prefill_tps": 1327.4 }
```
Units are tokens per second. `decode_tps` = generation speed, `prefill_tps` = prompt reading speed.

---

## 1. `GET /health`
No auth. Used by the extension to check the backend is reachable before asking for the code.

**Response 200**
```json
{ "ok": true }
```

---

## 2. `GET /status`
Called when the widget opens. Fills the GPU pill and the model dropdown.

**Response 200**
```json
{
  "contract_version": "0.1",
  "gpu": {
    "index": 0,
    "label": "L40",
    "name": "NVIDIA L40",
    "memory_total_gb": 48,
    "memory_free_gb": 33.5,
    "busy": false
  },
  "all_gpus": [
    { "index": 0, "label": "L40", "memory_total_gb": 48, "memory_free_gb": 33.5, "busy": false }
  ],
  "models": [
    {
      "id": "qwen3.8-27b",
      "display_name": "Qwen 3.8 27B",
      "installed": true,
      "database_coverage": "verified"
    }
  ],
  "current_config": { "engine": "ollama", "threads": 128, "context_tokens": 32768,
                      "batch_size": 1024, "kv_type": "f16", "flash_attention": true,
                      "quant": "IQ3_S hybrid 3.23bpw", "speculative_mode": "none" },
  "is_tuned": false,
  "contribute_results": false
}
```
`database_coverage` is the confidence the student would get for this model on this GPU, so the
dropdown can show a badge before they click anything. `gpu.label` is the short database label.
If the GPU is unrecognized, `label` is `"unknown"`.

---

## 3. `POST /optimize` (streaming)
Runs the full flow: pick a config, test it against the default, apply it.

**Request**
```json
{
  "model": "qwen3.8-27b",
  "preset": "balanced",
  "constraints": { "min_context_tokens": 32768, "quant": null },
  "gpu_index": 0
}
```
`constraints` and `gpu_index` are optional.

**Events, in order**

Progress for each step (sent when a step starts and again when it finishes):
```json
{ "type": "step", "name": "check_database", "status": "running", "progress": 0.25,
  "detail": "Found 5 matching runs on L40" }
```
`progress` is overall progress from 0 to 1.

The chosen config, with a plain-English explanation for the "Why this config?" panel:
```json
{
  "type": "config",
  "config": { "engine": "ollama", "threads": 12, "context_tokens": 32768, "batch_size": 1024,
              "kv_type": "f16", "flash_attention": true, "quant": "IQ3_S hybrid 3.23bpw",
              "speculative_mode": "none" },
  "changed": [ { "key": "threads", "from": 128, "to": 12 } ],
  "reasoning": "Default uses 128 threads, which slows this GPU. Database shows 12 threads at 54 tok/s.",
  "confidence": "verified",
  "source_rows": 5
}
```

One event per benchmark run:
```json
{ "type": "benchmark", "label": "default", "decode_tps": 22.5, "prefill_tps": 1327.4 }
{ "type": "benchmark", "label": "tuned",   "decode_tps": 54.2, "prefill_tps": 2192.3 }
```
`label` is `default` or `tuned`.

Final event on success:
```json
{
  "type": "done",
  "before": { "decode_tps": 22.5, "prefill_tps": 1327.4 },
  "after":  { "decode_tps": 54.2, "prefill_tps": 2192.3 },
  "speedup": 2.4,
  "reason": "Default uses 128 threads, which slows this GPU. Tuned to 12.",
  "confidence": "verified",
  "applied": true,
  "repro_command": "OLLAMA_HOST=127.0.0.1:11500 ollama serve  # then num_thread=12"
}
```
`speedup` is `after.decode_tps / before.decode_tps`, rounded to one decimal.
`repro_command` powers the "Copy command" button.

On failure, the stream ends with `{ "type": "error", ...standard error fields... }`.

---

## 4. `POST /race` (streaming)
Sends one prompt to the default setup and the tuned setup at the same time.

**Request**
```json
{ "model": "qwen3.8-27b", "prompt": "Explain how a hash table works.", "max_tokens": 256 }
```

**Events**
```json
{ "type": "start", "lanes": ["default", "tuned"] }
{ "type": "token", "lane": "default", "text": "A hash", "tokens": 3, "tps": 21.9 }
{ "type": "token", "lane": "tuned",   "text": "A hash", "tokens": 3, "tps": 53.8 }
{ "type": "lane_done", "lane": "tuned", "total_tokens": 256, "seconds": 4.7, "decode_tps": 54.0 }
{ "type": "done", "winner": "tuned", "speedup": 2.4 }
```
`token` events for both lanes are interleaved as they arrive. `tps` is the running speed so far.
The frontend uses them to move the speedometer and the progress bars.

---

## 5. `POST /revert`
Restores the settings that were active before the last `/optimize`.

**Request:** `{}`

**Response 200**
```json
{ "ok": true, "restored_config": { "engine": "ollama", "threads": 128, "context_tokens": 32768,
                                    "batch_size": 1024, "kv_type": "f16", "flash_attention": true,
                                    "quant": "IQ3_S hybrid 3.23bpw", "speculative_mode": "none" } }
```

---

## 6. `POST /chat` (streaming)
The "Ask" assistant. The backend adds GPU, model, current settings, latest results and
relevant database rows to the prompt itself; the frontend only sends the conversation.

**Request**
```json
{
  "message": "Why is this faster?",
  "history": [
    { "role": "user", "content": "What does context length mean?" },
    { "role": "assistant", "content": "It's how much text the model can remember at once..." }
  ]
}
```
`history` is optional; the frontend keeps it and trims it to the last ~10 messages.

**Events**
```json
{ "type": "delta", "text": "Your model was using 128 threads, " }
{ "type": "delta", "text": "which ..." }
{ "type": "done", "suggested_questions": ["What if I need a longer context?", "Is quality affected?"] }
```
If OpenRouter is unreachable the stream ends with an `error` event, code `ai_unavailable`, and the
frontend shows "Chat is offline".

---

## 7. `POST /diagnose`
Turns a failure into a plain-English explanation and, when possible, one safe fix.

**Request**
```json
{ "model": "qwen3.8-27b", "error_code": "out_of_memory", "log_tail": "CUDA error: out of memory ..." }
```
`log_tail` is optional; the backend uses its own captured logs if it is omitted.

**Response 200**
```json
{
  "explanation": "The model needs 31 GB but only 20 GB is free because another job is using this GPU.",
  "suggested_action": {
    "action": "lower_context",
    "params": { "context_tokens": 16384 },
    "label": "Lower context to 16k and retry"
  }
}
```
`suggested_action` may be `null` if there is no safe fix. The AI can only choose from the safe
`action` list. The backend validates it, and nothing is applied until the student clicks.

---

## 8. `POST /action`
Runs one safe action, used by the "Fix it" button.

**Request**
```json
{ "action": "lower_context", "params": { "context_tokens": 16384 } }
```

**Response 200**
```json
{ "ok": true, "applied_config": { "engine": "ollama", "threads": 12, "context_tokens": 16384,
                                   "batch_size": 1024, "kv_type": "f16", "flash_attention": true,
                                   "quant": "IQ3_S hybrid 3.23bpw", "speculative_mode": "none" } }
```
Unknown actions or out-of-range params return `400` with `code: "bad_request"`.

---

## Who owns what

| Endpoint | Frontend uses it for | Backend does |
|---|---|---|
| `/health` | Connection check | Returns ok |
| `/status` | GPU pill, model dropdown, coverage badges | `nvidia-smi`, Ollama model list, database lookup |
| `/optimize` | Progress steps, knobs, result card | Shortlist, OpenRouter call, validate, benchmark, apply |
| `/race` | Two streaming columns, live gauge | Run two setups at once, stream tokens |
| `/revert` | Revert button | Restore previous settings |
| `/chat` | Ask assistant panel | Build context prompt, call OpenRouter, stream |
| `/diagnose` | Error banner | Explain failure, propose a safe action |
| `/action` | "Fix it" button | Validate and run one allowed action |

## Changing this file
1. Edit the file and bump the version at the top and in `/status`.
2. Message the other person before pushing.
3. Update `mock/mock_server.py` in the same commit.