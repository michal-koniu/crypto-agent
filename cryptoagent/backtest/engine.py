"""Backtester with BTC as the unit of account.

Decisions happen at the weekly close (Sunday UTC) from point-in-time features; trades execute at that close plus
costs. Between weekly decisions, stops are checked on every daily close (a stop in BTC terms: for stablecoins, BTC
rising enough; for ETH, ETH/BTC falling enough). Idle stablecoins earn max(3M T-bill - haircut, 0) per year, a
documented proxy for on-chain/CEX lending yield (research B: USDC lending ~4-6 % in 2026).

Costs per side default to 20 bps: OKX entry-tier spot taker fee (research A) plus slippage for small orders are
inside that; the policy engine checks the real, quoted cost before any live or paper order.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .book import Book


@dataclass
class BacktestResult:
    nav: pd.DataFrame                       # daily: nav_btc, nav_usd, w_stable, w_eth, btc_usd
    trades: list[dict] = field(default_factory=list)
    decisions: list[dict] = field(default_factory=list)
    params: dict = field(default_factory=dict)


def run(feat: pd.DataFrame, daily: pd.DataFrame, params: dict, start: str | None = None, end: str | None = None,
        cost_bps: float = 20.0, keep_decisions: bool = False) -> BacktestResult:
    f = feat.loc[start:end] if (start or end) else feat
    f = f[f["sma50w"].notna()]
    days = daily.loc[f.index[0]:f.index[-1] + pd.Timedelta(days=6)]
    btc_px = days["btc"].ffill()
    eth_btc = days["eth_btc"].ffill() if "eth_btc" in days else pd.Series(np.nan, index=days.index)
    tbill = days["ust3m"].ffill() if "ust3m" in days else pd.Series(np.nan, index=days.index)
    book = Book(params=params, cost_bps=cost_bps)
    weeks = {d: i for i, d in enumerate(f.index)}
    decisions, rows = [], []
    for day in days.index:
        px = float(btc_px.loc[day])
        eb = float(eth_btc.loc[day]) if pd.notna(eth_btc.loc[day]) else None
        tb = float(tbill.loc[day]) if pd.notna(tbill.loc[day]) else None
        book.on_day(day.date(), px, eb, tb)
        if day in weeks:
            row = f.iloc[weeks[day]].to_dict()
            row["btc"] = px
            t = book.on_week(day.date(), row)
            if keep_decisions:
                decisions.append({"date": day, "stable": t.stable, "eth": t.eth, "rules": t.rules})
        ws, we = book.weights(px, eb)
        n = book.nav(px, eb)
        rows.append({"date": day, "nav_btc": n, "nav_usd": n * px, "w_stable": ws, "w_eth": we, "btc_usd": px})
    trades = [{**t, "date": pd.Timestamp(t["date"])} for t in book.trades]
    return BacktestResult(pd.DataFrame(rows).set_index("date"), trades, decisions, params)


def hodl(daily: pd.DataFrame, start, end) -> pd.DataFrame:
    d = daily.loc[start:end, ["btc"]].ffill()
    return pd.DataFrame({"nav_btc": 1.0, "nav_usd": d["btc"], "btc_usd": d["btc"]}, index=d.index)
