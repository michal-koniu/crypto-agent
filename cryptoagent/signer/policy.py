"""The signer's own policy: a second, independent line of defence below the policy engine.

The policy engine reasons about portfolios and strategies. The signer reasons only about the raw transaction it is
asked to sign, so a bug or a compromise upstream still cannot make it sign something outside these rules:

* `to` must be an allowlisted contract, and the 4-byte selector must be allowlisted for that contract;
* no native-value transfers, ever (value must be 0);
* swaps (Uniswap v3 exactInputSingle): both tokens allowlisted, recipient == our own wallet, amountOutMinimum > 0;
* Aave v3 supply/withdraw: asset allowlisted, onBehalfOf / to == our own wallet;
* ERC-20 approve: token allowlisted, spender allowlisted, amount < 2**128 and <= declared spend x multiple;
* ERC-20 transfer: only while the kill switch is engaged, and only to the human-set safe address;
* while killed: only exits (swaps into BTC or the stable and their exact router approval, withdrawals,
  approve-to-zero, transfer to safe).
"""
from __future__ import annotations

from dataclasses import dataclass

from eth_abi import decode as abi_decode

SEL_EXACT_INPUT_SINGLE = "0x04e45aaf"   # exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))
SEL_SUPPLY = "0x617ba037"               # supply(address,uint256,address,uint16)
SEL_WITHDRAW = "0x69328dec"             # withdraw(address,uint256,address)
SEL_APPROVE = "0x095ea7b3"              # approve(address,uint256)
SEL_TRANSFER = "0xa9059cbb"             # transfer(address,uint256)
UNLIMITED_FLOOR = 2 ** 128


@dataclass
class SignRequest:
    chain: str
    chain_id: int
    to: str
    data: str            # 0x-hex calldata
    value: int = 0
    declared_spend: int | None = None   # for approve: raw token units the next action will spend


def _addr(x: str) -> str:
    return x.lower()


def check_tx(req: SignRequest, wallet: str, allow: dict, limits: dict, killed: bool) -> list[str]:
    v: list[str] = []
    chain_cfg = allow["chains"].get(req.chain)
    if not chain_cfg or chain_cfg["chain_id"] != req.chain_id:
        return [f"chain {req.chain}/{req.chain_id} not allowlisted"]
    if req.value != 0:
        v.append("native value transfers are never signed")
    data = req.data.lower()
    if not data.startswith("0x") or len(data) < 10:
        return v + ["calldata missing a function selector"]
    sel, args = data[:10], bytes.fromhex(data[10:])
    contracts = allow["contracts"].get(req.chain, {})
    tokens = {_addr(t["address"]): (sym, t) for sym, t in allow["tokens"].get(req.chain, {}).items()}
    me = _addr(wallet)
    to = _addr(req.to)

    # ERC-20 calls go to token contracts
    if to in tokens:
        if sel == SEL_APPROVE:
            spender, amount = abi_decode(["address", "uint256"], args)
            spenders = [_addr(s) for s in contracts.get("token_approvals", {}).get("spenders", [])]
            if _addr(spender) not in spenders:
                v.append(f"approve to non-allowlisted spender {spender}")
            if amount >= UNLIMITED_FLOOR:
                v.append("unlimited (or near-unlimited) approval refused")
            if amount > 0:
                swap_router = _addr(contracts.get("uniswap_v3_swap_router02", {}).get("address", ""))
                if killed and _addr(spender) != swap_router:
                    v.append("kill switch engaged: only revokes, or exact approvals to the swap router for exits, are signed")
                mult = limits["approvals"]["max_approval_multiple"]
                if req.declared_spend is None or amount > req.declared_spend * mult:
                    v.append(f"approval {amount} exceeds {mult}x declared spend {req.declared_spend}")
            return v
        if sel == SEL_TRANSFER:
            dest, _amount = abi_decode(["address", "uint256"], args)
            safe = limits["kill_switch"].get("safe_address")
            if not killed:
                v.append("token transfers are only signed during the kill procedure")
            if not safe or _addr(dest) != _addr(safe):
                v.append(f"transfer destination {dest} is not the safe address")
            return v
        return v + [f"selector {sel} not allowed on token contracts"]

    # Allowlisted protocol contracts
    match = [(name, c) for name, c in contracts.items() if c.get("address") and _addr(c["address"]) == to]
    if not match:
        return v + [f"contract {req.to} not allowlisted"]
    name, c = match[0]
    if c.get("read_only"):
        return v + [f"{name} is read-only; nothing to sign"]
    if sel not in c.get("selectors", {}).values():
        return v + [f"selector {sel} not allowlisted on {name}"]

    if sel == SEL_EXACT_INPUT_SINGLE:
        (params,) = abi_decode(["(address,address,uint24,address,uint256,uint256,uint160)"], args)
        token_in, token_out, _fee, recipient, amount_in, min_out, _limit = params
        for t in (token_in, token_out):
            if _addr(t) not in tokens:
                v.append(f"swap token {t} not allowlisted")
        if _addr(recipient) != me:
            v.append(f"swap recipient {recipient} is not our wallet")
        if min_out == 0:
            v.append("swap without amountOutMinimum (no slippage protection)")
        if amount_in == 0:
            v.append("swap of zero")
        if killed and _addr(token_out) in tokens:
            sym = tokens[_addr(token_out)][1]["asset"]
            if sym not in ("BTC", "USDC", "USDT"):
                v.append("kill switch engaged: swaps only into BTC or the stablecoin")
    elif sel == SEL_SUPPLY:
        asset, amount, on_behalf, _ref = abi_decode(["address", "uint256", "address", "uint16"], args)
        if _addr(asset) not in tokens:
            v.append(f"supply of non-allowlisted asset {asset}")
        if _addr(on_behalf) != me:
            v.append(f"supply onBehalfOf {on_behalf} is not our wallet")
        if killed:
            v.append("kill switch engaged: no new deposits")
    elif sel == SEL_WITHDRAW:
        asset, amount, dest = abi_decode(["address", "uint256", "address"], args)
        if _addr(asset) not in tokens:
            v.append(f"withdraw of non-allowlisted asset {asset}")
        if _addr(dest) != me:
            v.append(f"withdraw destination {dest} is not our wallet")
    return v


def check_cex_order(venue: str, symbol: str, side: str, amount: float, notional_usd: float,
                    allow: dict, limits: dict, killed: bool) -> list[str]:
    """CEX orders: pair allowlisted, size capped. The signer exposes no withdrawal endpoint at all."""
    v = []
    if venue not in allow["cex_pairs"]:
        v.append(f"venue {venue} not allowlisted")
    elif symbol not in allow["cex_pairs"][venue]:
        v.append(f"pair {symbol} not allowlisted on {venue}")
    if side not in ("buy", "sell"):
        v.append(f"bad side {side}")
    if amount <= 0:
        v.append("non-positive amount")
    if notional_usd > limits["position"]["max_order_usd"]:
        v.append(f"order ${notional_usd:,.0f} exceeds max ${limits['position']['max_order_usd']:,}")
    if killed:
        base, quote = symbol.split("/")
        into = quote if side == "sell" else base
        if into not in ("BTC", "USDC", "USDT"):
            v.append("kill switch engaged: orders only into BTC or the stablecoin")
    return v
