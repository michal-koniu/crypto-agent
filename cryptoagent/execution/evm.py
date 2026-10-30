"""On-chain executor for Base (fork mode on Anvil; the same code would run live behind the live gates).

Swaps: Uniswap v3 SwapRouter02.exactInputSingle, after quoting every fee tier with QuoterV2 (an eth_call, so the
quote is the real pool state) and estimating gas. Approvals: exact amount, then revoked to zero after the swap.
Lending: Aave v3 Pool supply / withdraw of USDC. Every transaction is signed by the signer daemon, which re-checks
it against its own allowlist; this module never holds a key.
"""
from __future__ import annotations

import time

from web3 import Web3

from .. import frozen
from ..ledger.store import Ledger
from ..signer.client import SignerClient
from ..types import CostEstimate, Holding, LendIntent, Portfolio, Prices, TradeIntent

ERC20_ABI = [
    {"name": "balanceOf", "type": "function", "stateMutability": "view", "inputs": [{"name": "a", "type": "address"}], "outputs": [{"type": "uint256"}]},
    {"name": "allowance", "type": "function", "stateMutability": "view", "inputs": [{"name": "o", "type": "address"}, {"name": "s", "type": "address"}], "outputs": [{"type": "uint256"}]},
    {"name": "approve", "type": "function", "stateMutability": "nonpayable", "inputs": [{"name": "s", "type": "address"}, {"name": "v", "type": "uint256"}], "outputs": [{"type": "bool"}]},
    {"name": "transfer", "type": "function", "stateMutability": "nonpayable", "inputs": [{"name": "t", "type": "address"}, {"name": "v", "type": "uint256"}], "outputs": [{"type": "bool"}]},
    {"name": "decimals", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint8"}]},
    {"name": "symbol", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "string"}]},
]
QUOTER_ABI = [{"name": "quoteExactInputSingle", "type": "function", "stateMutability": "nonpayable",
               "inputs": [{"name": "p", "type": "tuple", "components": [
                   {"name": "tokenIn", "type": "address"}, {"name": "tokenOut", "type": "address"},
                   {"name": "amountIn", "type": "uint256"}, {"name": "fee", "type": "uint24"},
                   {"name": "sqrtPriceLimitX96", "type": "uint160"}]}],
               "outputs": [{"name": "amountOut", "type": "uint256"}, {"name": "sqrtPriceX96After", "type": "uint160"},
                           {"name": "initializedTicksCrossed", "type": "uint32"}, {"name": "gasEstimate", "type": "uint256"}]}]
ROUTER_ABI = [{"name": "exactInputSingle", "type": "function", "stateMutability": "payable",
               "inputs": [{"name": "p", "type": "tuple", "components": [
                   {"name": "tokenIn", "type": "address"}, {"name": "tokenOut", "type": "address"},
                   {"name": "fee", "type": "uint24"}, {"name": "recipient", "type": "address"},
                   {"name": "amountIn", "type": "uint256"}, {"name": "amountOutMinimum", "type": "uint256"},
                   {"name": "sqrtPriceLimitX96", "type": "uint160"}]}],
               "outputs": [{"name": "amountOut", "type": "uint256"}]}]
POOL_ABI = [
    {"name": "supply", "type": "function", "stateMutability": "nonpayable", "inputs": [{"name": "asset", "type": "address"}, {"name": "amount", "type": "uint256"}, {"name": "onBehalfOf", "type": "address"}, {"name": "referralCode", "type": "uint16"}], "outputs": []},
    {"name": "withdraw", "type": "function", "stateMutability": "nonpayable", "inputs": [{"name": "asset", "type": "address"}, {"name": "amount", "type": "uint256"}, {"name": "to", "type": "address"}], "outputs": [{"type": "uint256"}]},
    {"name": "getReserveData", "type": "function", "stateMutability": "view", "inputs": [{"name": "asset", "type": "address"}], "outputs": [{"name": "d", "type": "tuple", "components": [
        {"name": "configuration", "type": "uint256"}, {"name": "liquidityIndex", "type": "uint128"}, {"name": "currentLiquidityRate", "type": "uint128"},
        {"name": "variableBorrowIndex", "type": "uint128"}, {"name": "currentVariableBorrowRate", "type": "uint128"}, {"name": "currentStableBorrowRate", "type": "uint128"},
        {"name": "lastUpdateTimestamp", "type": "uint40"}, {"name": "id", "type": "uint16"}, {"name": "aTokenAddress", "type": "address"},
        {"name": "stableDebtTokenAddress", "type": "address"}, {"name": "variableDebtTokenAddress", "type": "address"},
        {"name": "interestRateStrategyAddress", "type": "address"}, {"name": "accruedToTreasury", "type": "uint128"},
        {"name": "unbacked", "type": "uint128"}, {"name": "isolationModeTotalDebt", "type": "uint128"}]}]},
]
FEE_TIERS = (100, 500, 3000)


class EvmExecutor:
    def __init__(self, rpc_url: str, signer: SignerClient, ledger: Ledger, chain: str = "base", mode: str = "fork"):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 60}))
        self.signer, self.ledger, self.chain, self.mode = signer, ledger, chain, mode
        allow = frozen.allowlists()
        self.chain_id = allow["chains"][chain]["chain_id"]
        self.tokens = {t["asset"]: {**t, "symbol": sym, "address": Web3.to_checksum_address(t["address"])}
                       for sym, t in allow["tokens"][chain].items()}
        c = allow["contracts"][chain]
        self.router = self.w3.eth.contract(Web3.to_checksum_address(c["uniswap_v3_swap_router02"]["address"]), abi=ROUTER_ABI)
        self.quoter = self.w3.eth.contract(Web3.to_checksum_address(c["uniswap_v3_quoter_v2"]["address"]), abi=QUOTER_ABI)
        self.pool = self.w3.eth.contract(Web3.to_checksum_address(c["aave_v3_pool"]["address"]), abi=POOL_ABI)
        self.me = Web3.to_checksum_address(signer.address)
        self.venue = "uniswap_v3_base"

    # ------------------------------------------------------------------ verification and state
    def verify_allowlist(self) -> list[str]:
        """Start-up check: every allowlisted address has code and the expected decimals."""
        problems = []
        for a, t in self.tokens.items():
            if not self.w3.eth.get_code(t["address"]):
                problems.append(f"{t['symbol']}: no code at {t['address']}")
                continue
            d = self.erc20(a).functions.decimals().call()
            if d != t["decimals"]:
                problems.append(f"{t['symbol']}: decimals {d} != allowlist {t['decimals']}")
        for name, ct in (("router", self.router), ("quoter", self.quoter), ("aave pool", self.pool)):
            if not self.w3.eth.get_code(ct.address):
                problems.append(f"{name}: no code at {ct.address}")
        return problems

    def erc20(self, asset: str):
        return self.w3.eth.contract(self.tokens[asset]["address"], abi=ERC20_ABI)

    def atoken(self, asset: str):
        rd = self.pool.functions.getReserveData(self.tokens[asset]["address"]).call()
        return self.w3.eth.contract(rd[8], abi=ERC20_ABI)

    def raw(self, asset: str, qty: float) -> int:
        return int(round(qty * 10 ** self.tokens[asset]["decimals"]))

    def human(self, asset: str, raw: int) -> float:
        return raw / 10 ** self.tokens[asset]["decimals"]

    def portfolio(self) -> Portfolio:
        hs = []
        for a in self.tokens:
            q = self.human(a, self.erc20(a).functions.balanceOf(self.me).call())
            if q > 0:
                hs.append(Holding(venue=self.venue, asset=a, qty=q, chain=self.chain))
        try:
            q = self.human("USDC", self.atoken("USDC").functions.balanceOf(self.me).call())
            if q > 0:
                hs.append(Holding(venue=self.venue, asset="USDC", qty=q, chain=self.chain, protocol="aave_v3_base"))
        except Exception:
            pass
        return Portfolio(holdings=hs)

    # ------------------------------------------------------------------ costs before acting
    def _gas_price(self) -> tuple[int, int]:
        base = self.w3.eth.get_block("latest")["baseFeePerGas"]
        prio = max(int(0.001e9), 1)
        return base * 2 + prio, prio

    def estimate(self, intent: TradeIntent, prices: Prices) -> tuple[CostEstimate, dict]:
        tin, tout = self.tokens[intent.sell_asset]["address"], self.tokens[intent.buy_asset]["address"]
        amt = self.raw(intent.sell_asset, intent.sell_qty)
        best = None
        for fee in FEE_TIERS:
            try:
                out, _, _, gas = self.quoter.functions.quoteExactInputSingle((tin, tout, amt, fee, 0)).call()
            except Exception:
                continue
            if out and (best is None or out > best[1]):
                best = (fee, out, gas)
        if not best:
            raise RuntimeError(f"no Uniswap v3 pool quote for {intent.sell_asset}->{intent.buy_asset}")
        fee, out, gas_q = best
        out_h = self.human(intent.buy_asset, out)
        ref = intent.sell_qty * prices.usd[intent.sell_asset] / prices.usd[intent.buy_asset]   # oracle-implied amount
        impact_bps = max((ref - out_h) / ref * 1e4, 0.0)
        max_fee, _ = self._gas_price()
        gas_units = 3 * 60_000 + int(gas_q) + 60_000       # approve + swap + revoke, conservative
        gas_usd = gas_units * max_fee / 1e18 * prices.usd.get("ETH", 0.0)
        cost = CostEstimate(fee_bps=fee / 100, slippage_bps=max(impact_bps - fee / 100, 0.0), gas_usd=gas_usd,
                            source=f"uniswap v3 quoter fee {fee}")
        return cost, {"fee_tier": fee, "amount_out_raw": out, "amount_out": out_h, "reference_out": ref}

    # ------------------------------------------------------------------ transactions
    def _send(self, to: str, data: str, declared_spend: int | None = None) -> dict:
        nonce = self.w3.eth.get_transaction_count(self.me)
        max_fee, prio = self._gas_price()
        gas = int(self.w3.eth.estimate_gas({"from": self.me, "to": to, "data": data}) * 1.3)
        signed = self.signer.sign_tx(chain=self.chain, chain_id=self.chain_id, to=to, data=data, value=0, nonce=nonce,
                                     gas=gas, max_fee_per_gas=max_fee, max_priority_fee_per_gas=prio, declared_spend=declared_spend)
        h = self.w3.eth.send_raw_transaction(signed["raw_tx"])
        rc = self.w3.eth.wait_for_transaction_receipt(h, timeout=120)
        if rc["status"] != 1:
            raise RuntimeError(f"tx {h.hex()} reverted")
        return {"tx_hash": "0x" + h.hex().removeprefix("0x"), "gas_used": rc["gasUsed"], "eff_gas_price": rc["effectiveGasPrice"]}

    def _approve(self, asset: str, spender: str, amount: int) -> dict:
        data = self.erc20(asset).encode_abi("approve", args=[spender, amount])
        return self._send(self.tokens[asset]["address"], data, declared_spend=amount)

    def execute(self, intent: TradeIntent, prices: Prices, quote: dict, cost: CostEstimate) -> dict:
        tin, tout = self.tokens[intent.sell_asset]["address"], self.tokens[intent.buy_asset]["address"]
        amt = self.raw(intent.sell_asset, intent.sell_qty)
        min_out = int(quote["amount_out_raw"] * (1 - intent.max_slippage_bps / 1e4))
        before = self.erc20(intent.buy_asset).functions.balanceOf(self.me).call()
        txs = [self._approve(intent.sell_asset, self.router.address, amt)]
        data = self.router.encode_abi("exactInputSingle", args=[(tin, tout, quote["fee_tier"], self.me, amt, min_out, 0)])
        txs.append(self._send(self.router.address, data))
        if self.erc20(intent.sell_asset).functions.allowance(self.me, self.router.address).call() > 0:
            txs.append(self._approve(intent.sell_asset, self.router.address, 0))      # revoke leftovers
        got = self.human(intent.buy_asset, self.erc20(intent.buy_asset).functions.balanceOf(self.me).call() - before)
        gas_native = sum(t["gas_used"] * t["eff_gas_price"] for t in txs) / 1e18
        price = (intent.sell_qty * prices.usd[intent.sell_asset]) / got / prices.usd[intent.buy_asset] if got else None
        fill = {"mode": self.mode, "venue": self.venue, "chain": self.chain, "tx_hash": txs[1]["tx_hash"],
                "approval_txs": [t["tx_hash"] for t in txs[:1] + txs[2:]], "side": "swap",
                "sell_asset": intent.sell_asset, "sell_qty": intent.sell_qty, "buy_asset": intent.buy_asset, "buy_qty": got,
                "price": got / intent.sell_qty if intent.sell_qty else None, "price_quote": f"{intent.buy_asset} per {intent.sell_asset}",
                "fee_asset": intent.sell_asset, "fee_qty": intent.sell_qty * quote["fee_tier"] / 1e6,
                "fee_usd": intent.sell_qty * quote["fee_tier"] / 1e6 * prices.usd[intent.sell_asset],
                "gas_native": gas_native, "gas_usd": gas_native * prices.usd.get("ETH", 0.0),
                "slippage_bps": max((quote["reference_out"] - got) / quote["reference_out"] * 1e4, 0.0),
                "value_usd": intent.sell_qty * prices.usd[intent.sell_asset], "price_btc_usd": prices.usd["BTC"],
                "strategy_id": intent.strategy_id, "strategy_version": intent.strategy_version,
                "decision_id": intent.decision_id, "reason_code": intent.reason_code, "fill_vs_oracle": price}
        self.ledger.append("fill", fill)
        return fill

    def lend(self, intent: LendIntent) -> dict:
        asset = self.tokens[intent.asset]["address"]
        amt = self.raw(intent.asset, intent.qty)
        txs = []
        if intent.action == "supply":
            txs.append(self._approve(intent.asset, self.pool.address, amt))
            txs.append(self._send(self.pool.address, self.pool.encode_abi("supply", args=[asset, amt, self.me, 0])))
        else:
            txs.append(self._send(self.pool.address, self.pool.encode_abi("withdraw", args=[asset, amt, self.me])))
        rec = {"executor": self.venue, "mode": self.mode, "venue": intent.venue, "chain": self.chain, "action": intent.action,
               "asset": intent.asset, "qty": intent.qty, "txs": [t["tx_hash"] for t in txs],
               "gas_native": sum(t["gas_used"] * t["eff_gas_price"] for t in txs) / 1e18, "decision_id": intent.decision_id}
        self.ledger.append("lend", rec)
        return rec

    def transfer(self, asset: str, qty: float, to: str) -> dict:
        data = self.erc20(asset).encode_abi("transfer", args=[Web3.to_checksum_address(to), self.raw(asset, qty)])
        tx = self._send(self.tokens[asset]["address"], data)
        rec = {"chain": self.chain, "asset": asset, "qty": qty, "to": to, "tx_hash": tx["tx_hash"], "mode": self.mode}
        self.ledger.append("transfer", rec)
        return rec

    def wait_block(self, seconds: float = 2.0):
        time.sleep(seconds)
