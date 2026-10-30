"""Live market data and pre-trade cost estimates from public exchange endpoints (no keys).

Prices: OKX (primary) and Kraken (independent second source for the divergence check). Order books are walked to
estimate the fill price and slippage for the actual order size, so every action knows its cost before it happens.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone

import ccxt

from .. import faults

from ..types import CostEstimate, Prices

VENUE_FEES_BPS = {          # entry-tier taker fees (research A, checked 2026-10-29)
    "okx": {"default": 20.0, "stable": 5.0},
    "kraken": {"default": 80.0, "stable": 20.0},
    "paper": {"default": 20.0, "stable": 5.0},     # paper mirrors OKX so paper results are honest
}
STABLES = {"USDC", "USDT"}


@dataclass
class Quote:
    symbol: str
    side: str
    qty_base: float
    avg_price: float
    mid: float
    slippage_bps: float
    spread_bps: float
    depth_ok: bool


class Market:
    def __init__(self, primary: str = "okx", secondary: str = "kraken"):
        self.ex = {primary: getattr(ccxt, primary)({"enableRateLimit": True}),
                   secondary: getattr(ccxt, secondary)({"enableRateLimit": True})}
        self.primary, self.secondary = primary, secondary

    def prices(self, assets=("BTC", "ETH", "SOL")) -> Prices:
        """USD prices (USDC-quoted on OKX; USDC treated as 1.0 unless its own USDC/USDT quote says otherwise)."""
        if faults.active().get("exchange_down"):
            raise faults.InjectedFault("injected fault: exchange_down")
        p = self.ex[self.primary]
        usd = {"USDC": 1.0, "USDT": 1.0}
        tick = p.fetch_tickers([f"{a}/USDC" for a in assets] + ["USDC/USDT"])
        for a in assets:
            t = tick.get(f"{a}/USDC")
            if t and t.get("last"):
                usd[a] = float(t["last"])
        if tick.get("USDC/USDT", {}).get("last"):
            usd["USDT"] = 1.0 / float(tick["USDC/USDT"]["last"])
        second = None
        try:
            k = self.ex[self.secondary].fetch_ticker("BTC/USD")
            second = float(k["last"])
        except Exception:
            second = None
        return Prices(usd=usd, ts=datetime.now(timezone.utc), source=self.primary, second_source_btc_usd=second)

    def quote(self, symbol: str, side: str, qty_base: float, venue: str | None = None) -> Quote:
        if faults.active().get("exchange_down"):
            raise faults.InjectedFault("injected fault: exchange_down")
        ex = self.ex[venue or self.primary]
        ob = ex.fetch_order_book(symbol, limit=50)
        bid, ask = ob["bids"][0][0], ob["asks"][0][0]
        mid = (bid + ask) / 2
        levels = ob["asks"] if side == "buy" else ob["bids"]
        left, cost = qty_base, 0.0
        for lvl in levels:                       # ccxt levels are [price, amount] or [price, amount, count]
            px, sz = float(lvl[0]), float(lvl[1])
            take = min(left, sz)
            cost += take * px
            left -= take
            if left <= 1e-15:
                break
        filled = qty_base - max(left, 0.0)
        avg = cost / filled if filled else mid
        slip = abs(avg - mid) / mid * 1e4
        return Quote(symbol, side, qty_base, avg, mid, slip, (ask - bid) / mid * 1e4, left <= 1e-15)


def cex_cost(venue: str, sell: str, buy: str, q: Quote) -> CostEstimate:
    fees = VENUE_FEES_BPS.get(venue, VENUE_FEES_BPS["okx"])
    fee = fees["stable"] if sell in STABLES and buy in STABLES else fees["default"]
    return CostEstimate(fee_bps=fee, spread_bps=q.spread_bps / 2, slippage_bps=max(q.slippage_bps - q.spread_bps / 2, 0.0),
                        source=f"{venue} order book {time.strftime('%H:%M:%S')}")


def symbol_for(sell: str, buy: str, listed: list[str]) -> tuple[str, str]:
    """Return (symbol, side) for a sell->buy conversion on a venue's listed pairs."""
    if f"{buy}/{sell}" in listed:
        return f"{buy}/{sell}", "buy"
    if f"{sell}/{buy}" in listed:
        return f"{sell}/{buy}", "sell"
    raise ValueError(f"no listed pair for {sell}->{buy}")
