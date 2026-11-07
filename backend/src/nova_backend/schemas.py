from typing import Literal, Annotated, Any
from pydantic import BaseModel, ConfigDict, Field, model_validator

Pos = Annotated[int, Field(strict=True, gt=0)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Budget(Strict):
    deadline_seconds: Annotated[int, Field(ge=15, le=300)] = 180
    max_repair_attempts: Annotated[int, Field(ge=0, le=2)] = 2


class Resources(Strict):
    target_id: Literal["wright"] = "wright"
    allocation_id: str | None = None
    gpu_type: Literal["L40"] = "L40"
    gpu_count: Annotated[int, Field(ge=1, le=2)] = 1
    gpu_ids: list[str] | None = None
    same_node: bool = True
    replica_gpu_groups: list[list[str]] | None = None
    cpus_per_task: Annotated[int, Field(ge=12, le=24)] = 12
    host_memory_mib: Annotated[int, Field(ge=65536, le=131072)] = 65536
    wall_time_seconds: Annotated[int, Field(ge=300, le=7200)] = 3600
    account: Literal["cmist"] = "cmist"
    partition: Literal["cmist"] = "cmist"
    qos: Literal["cmist_priority"] = "cmist_priority"
    power_limit_w: float | None = None

    @model_validator(mode="after")
    def selection(self):
        if self.gpu_ids is not None and not self.allocation_id:
            raise ValueError("gpu_ids require allocation_id")
        if self.power_limit_w is not None:
            raise ValueError("Wright power limits are read-only")
        if self.replica_gpu_groups is not None:
            raise ValueError(
                "Replica groups are not supported by the ByteShape adapter"
            )
        if not self.same_node:
            raise ValueError("The demo adapter requires one node")
        return self


class Constraints(Strict):
    min_context_tokens: Pos | None = None
    quant: str | None = None
    allow_quant_change: bool = False
    allow_sampling_change: bool = True
    allow_experimental: bool = False
    fixed_settings: dict[str, Any] = Field(default_factory=dict)
    min_free_gpu_memory_mib: Annotated[int, Field(ge=1024, le=16384)] = 1024
    max_gpu_count: Pos | None = None
    runtime_requirements: dict[str, bool] = Field(default_factory=dict)
    allow_cpu_offload: bool = False


class Overrides(Strict):
    artifact_id: str | None = None
    quant: str | None = None
    engine: Literal["llama.cpp", "ollama"] | None = None
    runtime_id: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def nulls(cls, v):
        if isinstance(v, dict) and any(x is None for x in v.values()):
            raise ValueError(
                "Omit overrides to preserve defaults; null is not an override"
            )
        return v


class Optimize(Strict):
    model: str
    objective: Literal["decode"] = "decode"
    preset: Literal["fastest"] = "fastest"
    workload: Literal["short", "long"] = "short"
    mode: Literal["verify_only", "sequential_compare"] = "verify_only"
    resources: Resources = Field(default_factory=Resources)
    constraints: Constraints = Field(default_factory=Constraints)
    profile_id: str | None = None
    overrides: Overrides = Field(default_factory=Overrides)
    budget: Budget = Field(default_factory=Budget)
    baseline_run_id: str | None = None
    capabilities_revision: str | None = None


class Race(Strict):
    model: str
    prompt: Annotated[str, Field(min_length=1, max_length=12000)]
    mode: Literal["simultaneous", "sequential"] = "simultaneous"
    max_tokens: Annotated[int, Field(ge=1, le=4096)] = 256
    tuned_profile_id: str | None = None
    resources: Resources = Field(default_factory=Resources)
    budget: Budget = Field(default_factory=Budget)
    seed: int | None = None


class Revert(Strict):
    rollback_id: str
    budget: Budget = Field(default_factory=Budget)


class Chat(Strict):
    message: Annotated[str, Field(min_length=1, max_length=8000)]
    history: list[dict[str, str]] = Field(default_factory=list, max_length=20)
    model: str | None = None
    run_id: str | None = None


class Diagnose(Strict):
    model: str
    run_id: str | None = None
    error_code: str | None = None
    log_tail: Annotated[str, Field(max_length=8000)] | None = None


class Action(Strict):
    action: Literal[
        "apply_config",
        "revert",
        "lower_context",
        "switch_quantization",
        "run_benchmark",
    ]
    params: dict[str, Any]
    budget: Budget = Field(default_factory=Budget)
    capabilities_revision: str | None = None


class Benchmark(Strict):
    budget: Budget = Field(default_factory=Budget)
    model: str
    profile_id: str | None = None
    resources: Resources = Field(default_factory=Resources)
    workload: Literal["short", "long"] = "short"
    purpose: Literal["throughput", "quality", "warmup"] = "throughput"
    max_tokens: Annotated[int, Field(ge=1, le=4096)] = 256
    seed: int = 71430


class Empty(Strict):
    pass
