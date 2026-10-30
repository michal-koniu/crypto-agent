"""Performance metrics (FROZEN: part of the measurement layer; the agent cannot change how it is scored).

Primary metric: BTC multiple = NAV in BTC at the end / NAV in BTC at the start. Holding BTC scores exactly 1.0.
Secondary: drawdown in BTC and USD terms, fees, trade count, time in BTC, win rate of round trips, and the same
numbers per halving epoch ("cycle"), because there are only a handful of independent cycles in BTC's history and a
result that comes from one of them is not evidence.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

CYCLES = [  # halving epochs: fixed a priori, not chosen by results
    ("pre-2012", "2010-07-18", "2012-11-27"),
    ("2012-2016", "2012-11-28", "2016-07-08"),
    ("2016-2020", "2016-07-09", "2020-05-10"),
    ("2020-2024", "2020-05-11", "2024-04-19"),
    ("2024-now", "2024-04-20", "2099-01-01"),
]


def max_drawdown(x: pd.Series) -> float:
    peak = x.cummax()
    return float((x / peak - 1).min()) if len(x) else 0.0


def btc_multiple(nav_btc: pd.Series) -> float:
    return float(nav_btc.iloc[-1] / nav_btc.iloc[0]) if len(nav_btc) > 1 else 1.0


def round_trips(trades: list[dict]) -> list[dict]:
    """Pair each move out of BTC with the move back; a 'win' ends with more BTC than it started with."""
    out, open_ = [], {}
    for t in trades:
        leg = t["leg"]
        if t["side"] == "buy" and leg not in open_:
            open_[leg] = t
        elif t["side"] == "sell" and leg in open_:
            o = open_.pop(leg)
            if leg == "STABLE":
                gain = o["btc_usd"] / t["btc_usd"] - 1          # BTC regained per BTC sold, before fees
            else:
                gain = t["eth_btc"] / o["eth_btc"] - 1 if o.get("eth_btc") else 0.0
            out.append({"leg": leg, "open": o["date"], "close": t["date"], "gain_btc_pct": gain,
                        "fees_btc": o["fee_btc"] + t["fee_btc"]})
    return out


def summarize(nav: pd.DataFrame, trades: list[dict]) -> dict:
    n = nav["nav_btc"]
    years = max((n.index[-1] - n.index[0]).days / 365.25, 1e-9)
    mult = btc_multiple(n)
    lr = np.log(n).diff().dropna()
    rt = round_trips(trades)
    wins = [r for r in rt if r["gain_btc_pct"] > 0]
    return {
        "start": str(n.index[0].date()), "end": str(n.index[-1].date()), "years": round(years, 2),
        "btc_multiple": round(mult, 4),
        "btc_cagr": round(mult ** (1 / years) - 1, 4),
        "max_dd_btc": round(max_drawdown(n), 4),
        "max_dd_usd": round(max_drawdown(nav["nav_usd"]), 4),
        "hodl_max_dd_usd": round(max_drawdown(nav["btc_usd"]), 4) if "btc_usd" in nav else None,
        "usd_multiple": round(float(nav["nav_usd"].iloc[-1] / nav["nav_usd"].iloc[0]), 3),
        "hodl_usd_multiple": round(float(nav["btc_usd"].iloc[-1] / nav["btc_usd"].iloc[0]), 3) if "btc_usd" in nav else None,
        "ann_vol_excess": round(float(lr.std() * math.sqrt(365)), 4) if len(lr) > 2 else 0.0,
        "sharpe_excess": round(float(lr.mean() / lr.std() * math.sqrt(365)), 3) if len(lr) > 2 and lr.std() > 0 else 0.0,
        "n_trades": len(trades),
        "fees_btc": round(sum(t["fee_btc"] for t in trades), 6),
        "time_in_btc": round(float(1 - nav.get("w_stable", 0).mean() - nav.get("w_eth", 0).mean()), 3) if "w_stable" in nav else 1.0,
        "round_trips": len(rt), "win_rate": round(len(wins) / len(rt), 3) if rt else None,
        "avg_round_trip_gain_btc": round(float(np.mean([r["gain_btc_pct"] for r in rt])), 4) if rt else None,
    }


def per_cycle(nav: pd.DataFrame) -> dict[str, float]:
    out = {}
    for name, a, b in CYCLES:
        s = nav["nav_btc"].loc[a:b]
        if len(s) > 30:
            out[name] = round(btc_multiple(s), 4)
    return out


def yearly_log_excess(nav: pd.DataFrame) -> pd.Series:
    """Log change of NAV-in-BTC per calendar year (excess over holding BTC)."""
    n = nav["nav_btc"]
    return np.log(n.groupby(n.index.year).last() / n.groupby(n.index.year).first())
