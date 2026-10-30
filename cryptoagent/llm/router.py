"""Model router: per-role model choice, fallbacks, budgets, structured output, and an audit trail.

Thin on purpose (research C: no agent framework needed; LiteLLM had malicious PyPI releases in March 2026, so it
is not a dependency). Two wire formats cover every provider in config/models.yaml:
  * OpenAI-compatible chat completions (rig llama-swap, OpenAI, DeepSeek, Qwen, Kimi, GLM, OpenRouter);
  * Anthropic Messages (structured output through a forced tool call).

Every call is written to the ledger as a `model_call` event: role, requested model, the model name the server
reports, tokens, latency, cost estimate, fallback reason. That is the evidence trail that a live model served it.
Output is always validated against a Pydantic schema in code; an invalid answer after retries is a failure, and
the caller treats a failure as "no LLM input" (rules only), never as a default action.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Type

import httpx
import yaml
from pydantic import BaseModel, ValidationError

from .. import faults
from ..ledger.store import Ledger

ENV_RE = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


def _expand(s: str) -> str:
    return ENV_RE.sub(lambda m: os.environ.get(m.group(1), m.group(2) or ""), s)


def load_config(path: str | Path) -> dict:
    cfg = yaml.safe_load(Path(path).read_text())
    for p in cfg["providers"].values():
        p["base_url"] = _expand(p["base_url"])
    return cfg


class LLMError(RuntimeError):
    pass


@dataclass
class CallResult:
    data: BaseModel
    model_ref: str
    served_model: str
    tokens_in: int
    tokens_out: int
    latency_s: float
    attempts: list[dict]


def _strip_thinking(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    return text.strip()


def _extract_json(text: str) -> Any:
    text = _strip_thinking(text)
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.S)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("no JSON object in the answer")
    return json.loads(text[start:end + 1])


class Router:
    def __init__(self, config: dict | str | Path, ledger: Ledger | None = None, transport: httpx.BaseTransport | None = None):
        self.cfg = load_config(config) if not isinstance(config, dict) else config
        self.ledger = ledger
        self.client = httpx.Client(transport=transport, timeout=None)
        self._usage: dict[tuple[str, str], int] = {}      # (day, role) -> tokens
        self._spend: dict[tuple[str, str], float] = {}    # (day, provider) -> usd

    # ------------------------------------------------------------------ budgets
    def _day(self) -> str:
        return datetime.now(timezone.utc).date().isoformat()

    def _budget_ok(self, role: str, provider: str) -> tuple[bool, str]:
        b = self.cfg.get("budgets", {})
        tok_cap = b.get("per_role_daily_tokens", {}).get(role)
        if tok_cap is not None and self._usage.get((self._day(), role), 0) >= tok_cap:
            return False, f"role {role} daily token budget {tok_cap} exhausted"
        usd_cap = b.get("per_provider_daily_usd", {}).get(provider)
        if usd_cap is not None and self._spend.get((self._day(), provider), 0.0) >= usd_cap:
            return False, f"provider {provider} daily budget ${usd_cap} exhausted"
        return True, "ok"

    def _account(self, role: str, provider: str, tin: int, tout: int) -> float:
        price = self.cfg["providers"][provider].get("price_per_mtok", {"in": 0, "out": 0})
        usd = tin / 1e6 * price["in"] + tout / 1e6 * price["out"]
        k = (self._day(), role)
        self._usage[k] = self._usage.get(k, 0) + tin + tout
        kp = (self._day(), provider)
        self._spend[kp] = self._spend.get(kp, 0.0) + usd
        return usd

    # ------------------------------------------------------------------ wire formats
    def _call_openai(self, prov: dict, model: str, system: str, user: str, schema: dict, rc: dict) -> tuple[str, str, int, int]:
        key = os.environ.get(prov["api_key_env"]) if prov.get("api_key_env") else "local"
        if prov.get("api_key_env") and not key:
            raise LLMError(f"missing API key env {prov['api_key_env']}")
        body = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "temperature": rc.get("temperature", 0.2), "max_tokens": rc.get("max_tokens", 2000),
                "response_format": {"type": "json_schema", "json_schema": {"name": "answer", "schema": schema,
                                                                          "strict": bool(rc.get("json_strict", False))}}}
        body.update(rc.get("extra_body") or {})          # e.g. chat_template_kwargs: {enable_thinking: false}
        url = prov["base_url"].rstrip("/") + "/chat/completions"
        h = {"Authorization": f"Bearer {key}"}
        r = self.client.post(url, json=body, headers=h, timeout=rc.get("timeout_s", 300))
        if r.status_code == 400 and "response_format" in r.text:
            body["response_format"] = {"type": "json_object"}
            r = self.client.post(url, json=body, headers=h, timeout=rc.get("timeout_s", 300))
        if r.status_code >= 400:
            raise LLMError(f"HTTP {r.status_code}: {r.text[:200]}")
        j = r.json()
        msg = j["choices"][0]["message"]
        u = j.get("usage") or {}
        text = msg.get("content") or ""
        if "{" not in text:          # thinking models may leave content empty and put the answer in the reasoning field
            text = (msg.get("reasoning_content") or msg.get("reasoning") or "") + "\n" + text
        return text, j.get("model", model), int(u.get("prompt_tokens", 0)), int(u.get("completion_tokens", 0))

    def _call_anthropic(self, prov: dict, model: str, system: str, user: str, schema: dict, rc: dict) -> tuple[str, str, int, int]:
        key = os.environ.get(prov["api_key_env"] or "")
        if not key:
            raise LLMError(f"missing API key env {prov['api_key_env']}")
        body = {"model": model, "system": system, "max_tokens": rc.get("max_tokens", 2000),
                "temperature": rc.get("temperature", 0.2), "messages": [{"role": "user", "content": user}],
                "tools": [{"name": "answer", "description": "Return the answer.", "input_schema": schema}],
                "tool_choice": {"type": "tool", "name": "answer"}}
        r = self.client.post(prov["base_url"].rstrip("/") + "/v1/messages", json=body, timeout=rc.get("timeout_s", 300),
                             headers={"x-api-key": key, "anthropic-version": "2023-06-01"})
        if r.status_code >= 400:
            raise LLMError(f"HTTP {r.status_code}: {r.text[:200]}")
        j = r.json()
        block = next((b for b in j["content"] if b["type"] == "tool_use"), None)
        text = json.dumps(block["input"]) if block else "".join(b.get("text", "") for b in j["content"])
        u = j.get("usage") or {}
        return text, j.get("model", model), int(u.get("input_tokens", 0)), int(u.get("output_tokens", 0))

    # ------------------------------------------------------------------ public
    def chain(self, role: str) -> list[str]:
        rc = self.cfg["roles"][role]
        return [rc["model"]] + list(rc.get("fallbacks", []))

    def call(self, role: str, system: str, user: str, schema_model: Type[BaseModel], context_id: str | None = None,
             retries: int = 2) -> CallResult:
        rc = self.cfg["roles"][role]
        schema = schema_model.model_json_schema()
        attempts: list[dict] = []
        req_hash = hashlib.sha256((system + "\n" + user).encode()).hexdigest()[:16]
        for ref in self.chain(role):
            provider, model = ref.split(":", 1)
            prov = self.cfg["providers"][provider]
            ok, why = self._budget_ok(role, provider)
            if not ok:
                attempts.append({"model": ref, "error": why})
                continue
            msg_user = user
            for attempt in range(retries + 1):
                t0 = time.time()
                try:
                    if provider in (faults.active().get("llm_down") or []):
                        raise LLMError(f"injected fault: provider {provider} down")
                    fn = self._call_anthropic if prov["kind"] == "anthropic" else self._call_openai
                    text, served, tin, tout = fn(prov, model, system, msg_user, schema, rc)
                    usd = self._account(role, provider, tin, tout)
                    data = schema_model.model_validate(_extract_json(text))
                    lat = time.time() - t0
                    attempts.append({"model": ref, "served": served, "ok": True, "latency_s": round(lat, 2)})
                    self._log(role, ref, served, tin, tout, usd, lat, attempts, req_hash, context_id, True)
                    return CallResult(data, ref, served, tin, tout, lat, attempts)
                except (ValidationError, ValueError, json.JSONDecodeError) as e:
                    attempts.append({"model": ref, "error": f"invalid output: {str(e)[:160]}"})
                    msg_user = user + "\n\nYour previous answer was not valid JSON for the schema. Error: " + str(e)[:300] + \
                        "\nAnswer again with ONLY the JSON object."
                except (httpx.HTTPError, LLMError, KeyError) as e:
                    attempts.append({"model": ref, "error": f"{type(e).__name__}: {str(e)[:160]}"})
                    break          # transport/server failure -> next model in the chain
        self._log(role, None, None, 0, 0, 0.0, 0.0, attempts, req_hash, context_id, False)
        raise LLMError(f"all models failed for role {role}: {attempts}")

    def _log(self, role, ref, served, tin, tout, usd, lat, attempts, req_hash, context_id, ok):
        if self.ledger:
            self.ledger.append("model_call", {"role": role, "model": ref, "served_model": served, "tokens_in": tin,
                                              "tokens_out": tout, "usd": round(usd, 6), "latency_s": round(lat, 2),
                                              "attempts": attempts, "request_hash": req_hash, "context_id": context_id, "ok": ok})
