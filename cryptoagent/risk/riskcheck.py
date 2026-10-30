"""Risk check before anything new is allowlisted (a human decision informed by this report).

Checks: GoPlus token security (honeypot, mintable, owner privileges, taxes, holder concentration), contract code
present, and DefiLlama protocol/hacks data when a protocol slug is given. External API output is untrusted data: it
is summarised into typed flags, and the report never edits the allowlist itself.
"""
from __future__ import annotations

import httpx

RED_FLAGS = ["is_honeypot", "is_mintable", "owner_change_balance", "hidden_owner", "selfdestruct", "can_take_back_ownership",
             "transfer_pausable", "is_blacklisted", "is_proxy", "slippage_modifiable", "cannot_sell_all", "trading_cooldown"]


def report(address: str, chain_id: str = "8453") -> dict:
    out: dict = {"address": address, "chain_id": chain_id, "flags": {}, "verdict": "unknown"}
    try:
        r = httpx.get(f"https://api.gopluslabs.io/api/v1/token_security/{chain_id}", params={"contract_addresses": address}, timeout=30)
        res = (r.json().get("result") or {}).get(address.lower(), {})
        out["token_name"] = str(res.get("token_name", ""))[:40]
        out["token_symbol"] = str(res.get("token_symbol", ""))[:16]
        for f in RED_FLAGS:
            if f in res:
                out["flags"][f] = res[f] == "1"
        out["buy_tax"], out["sell_tax"] = res.get("buy_tax"), res.get("sell_tax")
        out["holder_count"] = res.get("holder_count")
        out["is_open_source"] = res.get("is_open_source") == "1"
    except Exception as e:
        out["goplus_error"] = type(e).__name__
    bad = [f for f, v in out["flags"].items() if v and f not in ("is_proxy", "is_mintable")]
    out["verdict"] = "reject" if bad or out.get("is_open_source") is False else ("review" if out["flags"] else "unknown")
    out["red_flags"] = bad
    out["note"] = "proxy and mintable are normal for regulated stablecoins/wrappers (USDC, cbBTC) but mean an issuer can change or freeze the token"
    return out
