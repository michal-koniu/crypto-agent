"""Paper executor: real-time prices and order books, simulated fills, the same ledger records as live.

Fills walk the live OKX order book for the exact size (so slippage is realistic), pay the OKX entry-tier taker
fee, and are recorded as `fill` events with every tax field. Lending accrues the configured APY on deposits.
The portfolio is rebuilt from the ledger on start-up (the ledger is the source of truth).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..ledger.store import Ledger
from ..types import CostEstimate, Holding, LendIntent, Portfolio, Prices, TradeIntent
from .market import Market, cex_cost, symbol_for

PAPER_PAIRS = ["BTC/USDC", "ETH/USDC", "ETH/BTC", "SOL/USDC", "USDC/USDT"]


class PaperExecutor:
    venue = "paper"

    def __init__(self, ledger: Ledger, market: Market | None, state_dir: str | Path, mode: str = "paper",
                 lend_apy: dict[str, float] | None = None):
        self.ledger, self.market, self.mode = ledger, market, mode
        self.state_file = Path(state_dir) / "paper_portfolio.json"
        self.lend_apy = lend_apy or {"aave_v3_base": 0.05}
        self.pf = self._rebuild()

    # ------------------------------------------------------------------ portfolio from the ledger
    def _rebuild(self) -> Portfolio:
        bal: dict[tuple[str, str | None], float] = {}
        for e in self.ledger.events():
            p = e.payload
            if e.kind == "deposit" and p.get("venue") == self.venue:
                k = (p["asset"], None)
                bal[k] = bal.get(k, 0.0) + float(p["qty"])
            elif e.kind == "fill" and p.get("venue") == self.venue:
                bal[(p["sell_asset"], None)] = bal.get((p["sell_asset"], None), 0.0) - float(p["sell_qty"])
                bal[(p["buy_asset"], None)] = bal.get((p["buy_asset"], None), 0.0) + float(p["buy_qty"])
            elif e.kind == "lend" and p.get("executor") == self.venue:
                sign = 1 if p["action"] == "supply" else -1
                bal[(p["asset"], None)] = bal.get((p["asset"], None), 0.0) - sign * float(p["qty"])
                bal[(p["asset"], p["venue"])] = bal.get((p["asset"], p["venue"]), 0.0) + sign * float(p["qty"])
            elif e.kind == "interest" and p.get("executor") == self.venue:
                bal[(p["asset"], p["venue"])] = bal.get((p["asset"], p["venue"]), 0.0) + float(p["qty"])
        hs = [Holding(venue=self.venue, asset=a, qty=q, protocol=prot) for (a, prot), q in bal.items() if abs(q) > 1e-12]
        pf = Portfolio(holdings=hs)
        self._save(pf)
        return pf

    def _save(self, pf: Portfolio):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(pf.model_dump_json(indent=1))

    def portfolio(self) -> Portfolio:
        return self.pf

    def deposit(self, asset: str, qty: float, note: str = "initial paper capital"):
        self.ledger.append("deposit", {"venue": self.venue, "asset": asset, "qty": qty, "mode": self.mode, "note": note})
        self.pf = self._rebuild()

    # ------------------------------------------------------------------ trading
    def estimate(self, intent: TradeIntent, prices: Prices) -> tuple[CostEstimate, dict]:
        sym, side = symbol_for(intent.sell_asset, intent.buy_asset, PAPER_PAIRS)
        base = sym.split("/")[0]
        qty_base = intent.sell_qty if side == "sell" else intent.sell_qty / prices.usd[base] * prices.usd[intent.sell_asset]
        q = self.market.quote(sym, side, qty_base)
        return cex_cost("paper", intent.sell_asset, intent.buy_asset, q), {"symbol": sym, "side": side, "qty_base": qty_base,
                                                                          "avg_price": q.avg_price, "mid": q.mid, "depth_ok": q.depth_ok}

    def execute(self, intent: TradeIntent, prices: Prices, quote: dict, cost: CostEstimate) -> dict:
        sym, side, avg = quote["symbol"], quote["side"], quote["avg_price"]
        fee_rate = cost.fee_bps / 1e4
        if side == "sell":                       # selling base for quote
            gross = intent.sell_qty * avg
            buy_qty = gross * (1 - fee_rate)
            fee_asset, fee_qty = intent.buy_asset, gross * fee_rate
        else:                                    # buying base with quote
            base_qty = intent.sell_qty / avg
            buy_qty = base_qty * (1 - fee_rate)
            fee_asset, fee_qty = intent.buy_asset, base_qty * fee_rate
        value_usd = intent.sell_qty * prices.usd[intent.sell_asset]
        fill = {"mode": self.mode, "venue": self.venue, "chain": None, "order_id": f"paper-{datetime.now(timezone.utc).timestamp():.6f}",
                "symbol": sym, "side": side, "sell_asset": intent.sell_asset, "sell_qty": intent.sell_qty,
                "buy_asset": intent.buy_asset, "buy_qty": buy_qty, "price": avg, "price_quote": sym.split("/")[1],
                "mid": quote["mid"], "fee_asset": fee_asset, "fee_qty": fee_qty,
                "fee_usd": fee_qty * prices.usd.get(fee_asset, 0.0), "gas_native": 0.0, "gas_usd": 0.0,
                "slippage_bps": abs(avg - quote["mid"]) / quote["mid"] * 1e4, "value_usd": value_usd,
                "price_btc_usd": prices.usd["BTC"], "strategy_id": intent.strategy_id,
                "strategy_version": intent.strategy_version, "decision_id": intent.decision_id,
                "reason_code": intent.reason_code, "expected_cost_bps": cost.total_bps(value_usd)}
        self.ledger.append("fill", fill)
        self.pf = self._rebuild()
        return fill

    # ------------------------------------------------------------------ lending
    def lend(self, intent: LendIntent) -> dict:
        rec = {"executor": self.venue, "mode": self.mode, "venue": intent.venue, "action": intent.action,
               "asset": intent.asset, "qty": intent.qty, "expected_apy": intent.expected_apy,
               "decision_id": intent.decision_id, "strategy_version": intent.strategy_version}
        self.ledger.append("lend", rec)
        self.pf = self._rebuild()
        return rec

    def accrue_interest(self, days: float):
        for h in self.pf.holdings:
            if h.protocol and h.qty > 0:
                apy = self.lend_apy.get(h.protocol, 0.0)
                q = h.qty * ((1 + apy) ** (days / 365) - 1)
                if q > 0:
                    self.ledger.append("interest", {"executor": self.venue, "venue": h.protocol, "asset": h.asset,
                                                    "qty": q, "apy": apy, "days": days, "mode": self.mode})
        self.pf = self._rebuild()

    def snapshot(self) -> str:
        return json.dumps(self.pf.model_dump(), default=str)
