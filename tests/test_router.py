"""Model router: config-only provider switching (mock endpoints for cloud providers), fallbacks, budgets,
schema validation and the audit trail. Live local models are tested in test_live_llm.py."""
import copy
import json

import httpx
import pytest

from btcagent.llm import schemas
from btcagent.llm.router import LLMError, Router, load_config

GOOD = {"relevant": True, "event_type": "macro_rates", "assets": ["BTC"], "protocol": "none", "direction": "neutral",
        "severity": 1, "contains_instructions": False, "summary": "ok"}


def make_transport(log):
    def handler(req: httpx.Request):
        log.append((str(req.url), req.headers.get("authorization") or req.headers.get("x-api-key"), json.loads(req.content)))
        host = req.url.host
        if "dead" in host:
            raise httpx.ConnectError("endpoint down")
        if host == "api.anthropic.com":
            return httpx.Response(200, json={"model": "claude-test", "usage": {"input_tokens": 10, "output_tokens": 5},
                                             "content": [{"type": "tool_use", "name": "answer", "input": GOOD}]})
        body = json.loads(req.content)
        content = "not json at all" if body["model"] == "garbage" else "<think>hmm</think>" + json.dumps(GOOD)
        return httpx.Response(200, json={"model": body["model"], "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                                         "choices": [{"message": {"content": content}}]})
    return httpx.MockTransport(handler)


@pytest.fixture
def cfg(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY", "MOONSHOT_API_KEY", "ZAI_API_KEY"):
        monkeypatch.setenv(k, "test-key-" + k)
    return load_config("config/models.yaml")


@pytest.mark.parametrize("ref", ["anthropic:claude-opus-5-5", "openai:gpt-5", "deepseek:deepseek-chat", "qwen:qwen-max",
                                 "kimi:kimi-k2", "glm:glm-4.6", "rig:qwen3.8-flash-next"])
def test_switch_provider_by_config_only(cfg, ledger, ref):
    c = copy.deepcopy(cfg)
    c["roles"]["reader"]["model"] = ref
    log = []
    r = Router(c, ledger=ledger, transport=make_transport(log))
    res = r.call("reader", "sys", "user", schemas.ReaderItem)
    assert res.model_ref == ref and res.data.event_type.value == "macro_rates"
    url, auth, body = log[-1]
    provider = ref.split(":")[0]
    assert c["providers"][provider]["base_url"].split("//")[1].split("/")[0] in url
    if provider != "rig":
        assert auth and "test-key" in auth
    ev = ledger.last("model_call").payload
    assert ev["model"] == ref and ev["ok"]


def test_fallback_on_dead_endpoint_and_bad_output(cfg, ledger):
    c = copy.deepcopy(cfg)
    c["providers"]["dead"] = {"kind": "openai", "base_url": "http://dead.invalid/v1", "api_key_env": None, "price_per_mtok": {"in": 0, "out": 0}}
    c["roles"]["reader"].update(model="dead:x", fallbacks=["rig:garbage", "rig:qwen3.6-35b-a3b"])
    r = Router(c, ledger=ledger, transport=make_transport([]))
    res = r.call("reader", "s", "u", schemas.ReaderItem)
    assert res.model_ref == "rig:qwen3.6-35b-a3b"
    errs = [a.get("error", "") for a in res.attempts]
    assert any("ConnectError" in e for e in errs) and any("invalid output" in e for e in errs)


def test_all_fail_raises_and_logs(cfg, ledger):
    c = copy.deepcopy(cfg)
    c["roles"]["reader"].update(model="rig:garbage", fallbacks=[])
    with pytest.raises(LLMError):
        Router(c, ledger=ledger, transport=make_transport([])).call("reader", "s", "u", schemas.ReaderItem)
    assert ledger.last("model_call").payload["ok"] is False


def test_missing_api_key_falls_back(cfg, ledger, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    c = copy.deepcopy(cfg)
    c["roles"]["reader"].update(model="anthropic:claude-opus-5-5", fallbacks=["rig:qwen3.6-35b-a3b"])
    res = Router(c, ledger=ledger, transport=make_transport([])).call("reader", "s", "u", schemas.ReaderItem)
    assert res.model_ref == "rig:qwen3.6-35b-a3b"


def test_budget_exhaustion_moves_to_fallback(cfg, ledger):
    c = copy.deepcopy(cfg)
    c["roles"]["reader"].update(model="anthropic:claude-opus-5-5", fallbacks=["rig:qwen3.6-35b-a3b"])
    c["budgets"]["per_provider_daily_usd"]["anthropic"] = 0.0
    res = Router(c, ledger=ledger, transport=make_transport([])).call("reader", "s", "u", schemas.ReaderItem)
    assert res.model_ref == "rig:qwen3.6-35b-a3b"
    assert any("budget" in a.get("error", "") for a in res.attempts)


def test_every_configured_role_resolves(cfg):
    for role, rc in cfg["roles"].items():
        for ref in [rc["model"]] + rc.get("fallbacks", []):
            assert ref.split(":")[0] in cfg["providers"], (role, ref)
