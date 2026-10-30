"""Protocol-status guard: deterministic, no LLM.

Before any deposit and on every risk tick the agent reads the lending reserve's own on-chain flags. A reserve that is
frozen, paused or inactive gets no new money; money already in a frozen or inactive reserve is withdrawn (a freeze is
the protocol's governance signalling risk or deprecation, and the stablecoin yield is not worth either); a paused
reserve cannot be withdrawn from, so it raises a critical alert. Unknown status (RPC failure) never moves money in;
it also never forces an exit on its own.

Why this exists: on 29 Oct 2026, between ~19:40 and ~22:30 UTC, every Aave v3 Base reserve the agent uses (USDC,
cbBTC, WETH) was frozen. The fork tests caught it (`ReserveFrozen()`); the agent itself had no rule for it.
"""
from __future__ import annotations

import time

from web3 import Web3

POOL_CONFIG_ABI = [{"name": "getConfiguration", "type": "function", "stateMutability": "view",
                    "inputs": [{"name": "asset", "type": "address"}],
                    "outputs": [{"name": "", "type": "tuple", "components": [{"name": "data", "type": "uint256"}]}]}]


def decode_aave_v3_config(data: int) -> dict:
    """Aave v3 ReserveConfiguration bitmap: bit 56 active, 57 frozen, 58 borrowing, 60 paused, bits 116-151 supply cap
    (whole tokens, 0 = no cap)."""
    st = {"active": bool(data >> 56 & 1), "frozen": bool(data >> 57 & 1), "borrowing": bool(data >> 58 & 1),
          "paused": bool(data >> 60 & 1), "supply_cap": (data >> 116) & ((1 << 36) - 1)}
    st["suppliable"] = st["active"] and not st["frozen"] and not st["paused"]
    st["withdrawable"] = st["active"] and not st["paused"]
    return st


class ProtocolStatus:
    """Cached reader of reserve flags. `tokens`: asset -> address; `pools`: protocol -> pool address."""

    def __init__(self, rpc_url: str, tokens: dict[str, str], pools: dict[str, str], ttl_seconds: float = 300,
                 w3: Web3 | None = None):
        self.w3 = w3 or Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 20}))
        self.tokens = {a: Web3.to_checksum_address(x) for a, x in tokens.items()}
        self.pools = {p: self.w3.eth.contract(Web3.to_checksum_address(x), abi=POOL_CONFIG_ABI) for p, x in pools.items()}
        self.ttl = ttl_seconds
        self._cache: dict[tuple[str, str], tuple[float, dict]] = {}

    def status(self, protocol: str, asset: str) -> dict:
        key = (protocol, asset)
        hit = self._cache.get(key)
        if hit and time.time() - hit[0] < self.ttl:
            return hit[1]
        try:
            data = self.pools[protocol].functions.getConfiguration(self.tokens[asset]).call()[0]
            st = {"protocol": protocol, "asset": asset, **decode_aave_v3_config(int(data))}
        except Exception as e:          # unknown status: fail closed for deposits, no forced exit
            st = {"protocol": protocol, "asset": asset, "error": f"{type(e).__name__}: {str(e)[:160]}",
                  "suppliable": False, "withdrawable": None}
        self._cache[key] = (time.time(), st)
        return st


def from_allowlists(rpc_url: str, allow: dict, chain: str = "base", w3: Web3 | None = None, ttl_seconds: float = 300) -> ProtocolStatus:
    tokens = {t["asset"]: t["address"] for t in allow["tokens"][chain].values()}
    pools = {"aave_v3_base": allow["contracts"][chain]["aave_v3_pool"]["address"]}
    return ProtocolStatus(rpc_url, tokens, pools, ttl_seconds=ttl_seconds, w3=w3)
