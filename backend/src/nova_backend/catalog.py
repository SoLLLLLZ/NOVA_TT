from __future__ import annotations
import copy, csv, json, math
from .common import ROOT, MODEL, VERSION, Problem, digest
from .schemas import Optimize, Resources, Constraints

MANIFEST = json.loads((ROOT / "configs/profiles/byteshape.json").read_text())
MANIFESTS = {MODEL: MANIFEST}
for _name in ("glimmer", "flash"):
    _manifest = json.loads((ROOT / ("configs/profiles/" + _name + ".json")).read_text())
    MANIFESTS[_manifest["model"]] = _manifest
PROFILES = [p for manifest in MANIFESTS.values() for p in manifest["profiles"]]
BASE = PROFILES[0]["config"]
BASELINE = PROFILES[2]["config"]
# Explicit bounded adapter mappings; everything else is read-only or unsupported.
WRITABLE = {
    "context_tokens": ("integer", 2048, 65536, "--ctx-size"),
    "context_per_slot": ("integer", 2048, 65536, None),
    "draft_tokens": ("integer", 1, 16, "--spec-draft-n-max"),
    "threads_decode": ("integer", 1, 12, "--threads"),
    "threads_prefill": ("integer", 1, 12, "--threads-batch"),
    "batch_size": ("integer", 128, 2048, "--batch-size"),
    "microbatch_size": ("integer", 64, 512, "--ubatch-size"),
    "temperature": ("number", 0, 2, "--temp"),
    "top_p": ("number", 0.01, 1, "--top-p"),
    "top_k": ("integer", 1, 100, "--top-k"),
    "min_p": ("number", 0, 1, "--min-p"),
}
SAMPLING = {"temperature", "top_p", "top_k", "min_p"}
UNSUPPORTED = """context_override fit_target_mib extra_speculation draft_tensor_overrides draft_probability_min cuda_launch_queues force_mmq_runtime load_mode lazy_mode draft_tokens_min draft_probability_split draft_threads_decode draft_threads_prefill draft_backend_sampling cpu_mask cpu_mask_prefill draft_cpu_mask draft_cpu_mask_prefill cpu_range cpu_range_prefill draft_cpu_range draft_cpu_range_prefill cpu_strict cpu_strict_prefill draft_cpu_strict draft_cpu_strict_prefill cpu_priority cpu_priority_prefill draft_cpu_priority draft_cpu_priority_prefill cpu_poll cpu_poll_prefill draft_cpu_poll draft_cpu_poll_prefill numa cpu_moe draft_cpu_moe kv_offload op_offload repack no_host kv_unified swa_full n_cpu_moe draft_n_cpu_moe n_cpu_ffn fit_context_min cache_prompt cache_idle_slots continuous_batching context_shift cache_reuse context_checkpoints swa_checkpoints keep_tokens slot_prompt_similarity sleep_idle_seconds seed frequency_penalty typical_p top_n_sigma dynamic_temperature_range dynamic_temperature_exponent xtc_probability xtc_threshold adaptive_target adaptive_decay mirostat_tau mirostat_eta dry_multiplier dry_base repeat_last_n dry_penalty_last_n dry_allowed_length mirostat samplers dry_sequence_breakers stop logit_bias max_output_tokens ignore_eos reasoning_budget reasoning_budget_message reasoning_preserve skip_chat_parsing prefill_assistant rope_scaling rope_scale rope_freq_base rope_freq_scale yarn_ext_factor yarn_attn_factor yarn_beta_slow yarn_beta_fast yarn_orig_ctx group_attention_n group_attention_w grammar_id json_schema projector_offload projector_device image_min_tokens image_max_tokens multimodal_batch_max_tokens lora_adapters control_vectors http_threads request_timeout_seconds sse_ping_interval_seconds verbosity warmup metrics perf check_tensors runtime_options""".split()
REVISION = "three-models-v1-" + digest({"manifests": MANIFESTS, "writable": WRITABLE})[:12]


def model_check(model):
    if model not in (MODEL, "qwen3.8-flash-next", "muse-glimmer"):
        raise Problem("model_not_found", "Unknown model.", 404)


def manifest_for(model):
    model_check(model)
    return MANIFESTS[model]


def gpu_count(model):
    return manifest_for(model).get("gpu_count", 1)


def profiles_for(model, engine="llama.cpp"):
    return [p for p in manifest_for(model)["profiles"] if p["config"]["engine"] == engine]


def baseline_for(model):
    return copy.deepcopy(profiles_for(model, "ollama")[0]["config"])


def writable_for(model):
    result = dict(WRITABLE)
    maximum = {MODEL: 65536, "muse-glimmer": 262144, "qwen3.8-flash-next": 131072}[model]
    for key in ("context_tokens", "context_per_slot"):
        t, lo, _, flag = result[key]
        result[key] = (t, lo, maximum, flag)
    result["draft_tokens"] = ("integer", 1, {MODEL: WRITABLE["draft_tokens"][2], "muse-glimmer": 15, "qwen3.8-flash-next": 2}[model], "--spec-draft-n-max")
    if model == "muse-glimmer":
        result["batch_size"] = ("integer", 128, 4096, "--batch-size")
    if model == "qwen3.8-flash-next":
        result["microbatch_size"] = ("integer", 64, 1024, "--ubatch-size")
    return result


def profile(pid):
    for p in PROFILES:
        if p["config"]["profile_id"] == pid:
            return copy.deepcopy(p["config"])
    raise Problem("not_found", "Unknown registered profile.", 404)


def rows():
    with (ROOT / "data/canon/CANON.csv").open(newline="") as f:
        return list(csv.DictReader(f))


def evidence(c):
    exact = next((p for p in PROFILES if p["config"] == c), None)
    source = exact or profiles_for(c["model"])[0]
    return {
        "confidence": "verified" if exact else "inferred",
        "source_config_ids": source["source_config_ids"],
        "lesson_ids": [],
        "source_rows": [
            r for r in rows() if r["config_id"] in source["source_config_ids"]
        ],
        "match": {
            "model": True,
            "quant": True,
            "gpu_type": True,
            "gpu_count": True,
            "context": c["settings"]["context_per_slot"]
            == source["config"]["settings"]["context_per_slot"],
            "concurrency": True,
            "runtime": c["runtime_id"] == source["config"]["runtime_id"],
        },
        "deviations": []
        if exact
        else ["Settings differ from the cited historical profile."],
        "cautions": [
            "Historical L40 results are not today's measurements; one short completed check is not broad quality certification."
        ],
    }


def resolve(req: Optimize, selected=None, reference=None):
    model_check(req.model)
    manifest = manifest_for(req.model)
    base = profiles_for(req.model)[0]["config"]
    writable = writable_for(req.model)
    required = gpu_count(req.model)
    if req.resources.gpu_count != required:
        raise Problem("allocation_unavailable", f"{req.model} requires {required} L40s per engine on one node.", 409)
    if req.capabilities_revision and req.capabilities_revision != REVISION:
        raise Problem(
            "constraint_violation", "Capabilities changed; refresh them.", 409
        )
    c = (
        copy.deepcopy(selected)
        if selected and (not req.profile_id or selected["profile_id"] == req.profile_id)
        else profile(req.profile_id)
        if req.profile_id
        else copy.deepcopy(base)
    )
    if c["model"] != req.model:
        raise Problem("constraint_violation", "Profile belongs to another model.")
    if c["engine"] != "llama.cpp":
        raise Problem(
            "unsupported_setting", "Optimize requires a registered llama.cpp profile."
        )
    original = copy.deepcopy(c)
    for key, value in req.overrides.model_dump(exclude_unset=True).items():
        if key == "settings":
            continue
        if value != c[key]:
            raise Problem(
                "unsupported_setting",
                f"{key} cannot change in this model adapter.",
                field=key,
            )
    changes = dict(req.constraints.fixed_settings)
    for k, v in req.overrides.settings.items():
        if k in changes and changes[k] != v:
            raise Problem("constraint_violation", f"Override conflicts with fixed {k}.")
        changes[k] = v
    for key, value in changes.items():
        if key not in writable:
            if (
                key not in c["settings"]
                or value != c["settings"][key]
                or type(value) is not type(c["settings"][key])
            ):
                raise Problem(
                    "unsupported_setting",
                    f"{key} is not writable.",
                    field="settings." + key,
                )
            continue
        typ, lo, hi, _ = writable[key]
        valid = type(value) is int if typ == "integer" else type(value) in (int, float)
        if (
            not valid
            or not lo <= value <= hi
            or (type(value) is float and not math.isfinite(value))
        ):
            raise Problem(
                "bad_request",
                f"{key} must be {typ} in [{lo},{hi}].",
                400,
                field="settings." + key,
            )
        c["settings"][key] = value
    s = c["settings"]
    q = req.constraints
    if s["context_tokens"] != s["context_per_slot"]:
        raise Problem(
            "constraint_violation",
            "One slot requires equal context_tokens and context_per_slot.",
        )
    minimum = (
        q.min_context_tokens
        if q.min_context_tokens is not None
        else original["settings"]["context_per_slot"]
    )
    if s["context_per_slot"] < minimum:
        raise Problem(
            "constraint_violation", "Requested context is below the promised minimum."
        )
    if s["microbatch_size"] > s["batch_size"]:
        raise Problem("constraint_violation", "Microbatch cannot exceed batch size.")
    if not q.allow_sampling_change and any(
        s[k] != (reference if reference and reference["model"] == req.model else base)["settings"][k] for k in SAMPLING
    ):
        raise Problem(
            "constraint_violation",
            "Changing sampling requires allow_sampling_change=true.",
        )
    if q.quant and q.quant != c["quant"]:
        raise Problem("constraint_violation", "Requested quant is not installed.")
    if q.max_gpu_count and req.resources.gpu_count > q.max_gpu_count:
        raise Problem("constraint_violation", "GPU count exceeds constraint.")
    for k, v in q.runtime_requirements.items():
        if (
            k not in manifest["runtime_features"]
            or manifest["runtime_features"][k] != v
        ):
            raise Problem(
                "runtime_unavailable",
                "No installed build satisfies runtime requirements.",
            )
    changed = any(s[k] != original["settings"][k] for k in s)
    if changed and not q.allow_experimental:
        matching = any(p["config"]["settings"] == s for p in PROFILES)
        # Explicit context lowering is a supported operation, but remains separately verified.
        context_only = all(
            k in ("context_tokens", "context_per_slot")
            or s[k] == original["settings"][k]
            for k in s
        )
        if not matching and not context_only:
            raise Problem(
                "constraint_violation",
                "Untested combination requires allow_experimental=true.",
            )
    c.pop("profile_id", None)
    c["profile_id"] = "profile_" + digest(c)[:24]
    return c


def capabilities(model):
    model_check(model)
    manifest = manifest_for(model)
    base = profiles_for(model)[0]["config"]
    fields = {}
    for k, v in base["settings"].items():
        fields["settings." + k] = {
            "schema": {"const": v},
            "support": "supported",
            "access": "read_only",
            "apply": "observe_only",
            "evidence": "tested",
            "reason": "Pinned registered profile value.",
            "default": v,
            "ui_group": "advanced",
            "advanced": True,
            "runtime_mapping": None,
        }
    for k, (t, lo, hi, flag) in writable_for(model).items():
        fields["settings." + k] = {
            "schema": {"type": t, "minimum": lo, "maximum": hi},
            "support": "supported",
            "access": "writable",
            "apply": "restart",
            "evidence": "tested"
            if k in ("draft_tokens", "temperature")
            else "source_declared",
            "reason": "Capability bounds do not establish quality for every combination.",
            "default": base["settings"][k],
            "ui_group": "sampling" if k in SAMPLING else "runtime",
            "advanced": True,
            "runtime_mapping": flag,
        }
    for k in UNSUPPORTED:
        if k in base["settings"]:
            continue
        fields["settings." + k] = {
            "schema": {},
            "support": "unsupported",
            "access": "read_only",
            "apply": "observe_only",
            "evidence": "unverified",
            "reason": "No enabled mapping in this model adapter.",
            "ui_group": "advanced",
            "advanced": True,
            "runtime_mapping": None,
        }
    for prefix, model_schema in [
        ("resources", Resources),
        ("constraints", Constraints),
    ]:
        for key, schema in model_schema.model_json_schema()["properties"].items():
            readonly = key == "power_limit_w"
            fields[prefix + "." + key] = {
                "schema": schema,
                "support": "supported",
                "access": "read_only" if readonly else "writable",
                "apply": "observe_only"
                if readonly
                else "reallocate"
                if prefix == "resources"
                else "request",
                "evidence": "source_declared",
                "reason": "Validated against owned allocation and adapter policy.",
                "ui_group": prefix,
                "advanced": True,
                "runtime_mapping": None,
            }
    return {
        "contract_version": VERSION,
        "capabilities_revision": REVISION,
        "model": model,
        "target_id": "wright",
        "runtime_id": base["runtime_id"],
        "fields": fields,
        "constraints": [
            {
                "code": "sampling_policy",
                "paths": ["constraints.allow_sampling_change"],
                "message": "Sampling changes are allowed by default; explicit locks are honored.",
            },
            {
                "code": "single_slot",
                "paths": ["settings.context_tokens", "settings.context_per_slot"],
                "message": "Single slot; equal total and per-slot context.",
            },
            {
                "code": "experimental_policy",
                "paths": ["constraints.allow_experimental"],
                "message": "Unrecorded combinations require allow_experimental.",
            },
            {
                "code": "cluster_policy",
                "paths": ["resources.power_limit_w", "settings.mps"],
                "message": "Wright power and MPS are read-only.",
            },
        ],
        "artifacts": [
            dict(
                manifest["artifact"],
                installed=None,
                files=[dict(f, verified=None) for f in manifest["artifact"]["files"]],
            )
        ],
        "runtimes": [
            {
                "runtime_id": base["runtime_id"],
                "build_features": manifest["runtime_features"],
                "source_commit": "74a7c897f049c17e7080423aa2111776eff6ebbf",
                "identity_verification": "Worker hashes binaries and libraries before use.",
            }
        ],
        "resource_options": {
            "gpu_type": "L40",
            "gpu_counts": [gpu_count(model)],
            "cleanup_deadline_seconds": 60,
            "default_deadline_seconds": 180,
            "max_deadline_seconds": 300,
            "race_enabled": False,
        },
    }
