"""Historical market for replay runs: prices and quotes come from the daily panel at a simulated date.

Used by `cryptoagent replay` (end-to-end and self-improvement tests on real history with live LLMs). Quotes use a
fixed spread and a size-dependent slippage, so costs stay realistic without an order book.
Note: an LLM replaying the past may know what happened next (training data), so replay results test the mechanics,
not the analyst's skill. Performance evidence comes from backtests of the rules and from forward paper trading.
"""
from __future__ import annotations

from datetime import datetime, time, timezone

import pandas as pd

from ..types import Prices
from .market import Quote


class HistoricalMarket:
    def __init__(self, daily: pd.DataFrame):
        self.daily = daily
        self.now: pd.Timestamp = daily.index[0]

    def set_date(self, d: pd.Timestamp):
        self.now = pd.Timestamp(d).normalize()

    def _row(self):
        return self.daily.loc[:self.now].iloc[-1]

    def prices(self, assets=("BTC", "ETH", "SOL")) -> Prices:
        r = self._row()
        usd = {"USDC": 1.0, "USDT": 1.0, "BTC": float(r["btc"])}
        if pd.notna(r.get("eth_btc")):
            usd["ETH"] = float(r["eth_btc"]) * usd["BTC"]
        ts = datetime.combine(self.now.date(), time(23, 59), tzinfo=timezone.utc)
        return Prices(usd=usd, ts=ts, source="history", second_source_btc_usd=usd["BTC"] * 1.0005)

    def quote(self, symbol: str, side: str, qty_base: float, venue: str | None = None) -> Quote:
        base = symbol.split("/")[0]
        p = self.prices()
        mid = p.usd[base] / p.usd[symbol.split("/")[1]]
        notional_usd = qty_base * p.usd[base]
        spread_bps = 2.0
        slip_bps = spread_bps / 2 + min(notional_usd / 1e6 * 5, 50)      # 5 bps per $1M, capped
        avg = mid * (1 + slip_bps / 1e4) if side == "buy" else mid * (1 - slip_bps / 1e4)
        return Quote(symbol, side, qty_base, avg, mid, slip_bps, spread_bps, True)
