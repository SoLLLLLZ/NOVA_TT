import json
import pytest

from nova_backend.agent import Agent
from nova_backend.catalog import evidence, gpu_count, profiles_for, resolve, rows
from nova_backend.common import ROOT, digest
from nova_backend.schemas import Optimize


CAMPAIGNS = [
    ("byteshape", "qwen3.8-27b", 15, ("A2",)),
    ("glimmer", "muse-glimmer", 20, ("A3", "D3", "B3")),
    ("flash", "qwen3.8-flash-next", 15, ("A5", "C5")),
]


@pytest.mark.parametrize("name,model,count,selected", CAMPAIGNS)
async def test_recent_evidence_and_complete_profiles_reach_astra(monkeypatch, name, model, count, selected):
    records = json.loads((ROOT / f"data/canon/experiments/wright-{name}-industrial-20261107.json").read_text())["records"]
    source_ids = {r["config_id"] for r in records}
    assert len(source_ids) == count
    canon = {r["config_id"]: r for r in rows()}
    registered = {p["config"]["profile_id"]: p for p in profiles_for(model)}
    for record in records:
        if record["id"] not in selected:
            continue
        config = record["config"]
        profile = registered[config["profile_id"]]
        # Exact receipt equality prevents mixing independent winning tracks.
        assert profile["config"] == config
        assert record["config_id"] in profile["source_config_ids"]
        assert config["profile_id"] == "profile_" + digest({k: v for k, v in config.items() if k != "profile_id"})[:24]
        assert resolve(Optimize(model=model, resources={"gpu_count": gpu_count(model)}, profile_id=config["profile_id"])) == config
        assert canon[record["config_id"]] in evidence(config)["source_rows"]

    async def completion(messages, deadline, tools):
        payload = json.loads(messages[-1]["content"])
        assert source_ids <= {r["config_id"] for r in payload["canon"]}
        assert "lesson_019" in {r["config_id"] for r in payload["canon"]}
        sent = {p["config"]["profile_id"] for p in payload["profiles"]}
        allowed = tools[0]["function"]["parameters"]["properties"]["profile_id"]["enum"]
        assert set(allowed) == sent
        for r in records:
            if r["id"] in selected:
                assert r["config"]["profile_id"] in sent
        instructions = messages[0]["content"]
        assert "Do not browse or search the web" in instructions
        assert "prefer the faster recorded ByteShape MTP5" not in instructions
        assert "prefer the compatible CANON-backed short-decode candidate" not in instructions
        chosen = next(r["config"]["profile_id"] for r in records if r["id"] == selected[0])
        return {"tool_calls": [{"function": {"name": "select_configuration", "arguments": json.dumps({"profile_id": chosen, "reason": "Matched essay evidence", "lesson_ids": []})}}]}

    agent = Agent()
    monkeypatch.setattr(agent, "completion", completion)
    config, _ = await agent.select(Optimize(model=model, resources={"gpu_count": gpu_count(model)}), 9999999999)
    assert config == next(r["config"] for r in records if r["id"] == selected[0])


async def test_sampling_lock_excludes_new_lower_temperature_candidates(monkeypatch):
    async def completion(messages, deadline, tools):
        payload = json.loads(messages[-1]["content"])
        assert all(p["config"]["settings"]["temperature"] == 1 for p in payload["profiles"])
        chosen = payload["profiles"][0]["config"]["profile_id"]
        return {"tool_calls": [{"function": {"name": "select_configuration", "arguments": json.dumps({"profile_id": chosen, "reason": "Sampling locked", "lesson_ids": []})}}]}
    agent = Agent()
    monkeypatch.setattr(agent, "completion", completion)
    config, _ = await agent.select(Optimize(model="qwen3.8-27b", constraints={"allow_sampling_change": False}), 9999999999)
    assert config["settings"]["temperature"] == 1
