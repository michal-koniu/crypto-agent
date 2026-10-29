"""Point-in-time features on weekly closes (Sunday 00:00 UTC week end, like TradingView weekly bars).

Every feature at week t uses only data available at the close of week t. Expanding fits (log regression, risk
metric normalisation) are refit each week on the data so far; nothing is normalised over the full sample.

The features follow Benjamin Cowen's *verifiable* tools (research E, labelled (a)/(b)); his proprietary metrics are
replaced by documented approximations:
  sma20w, ema21w (bull market support band), sma50w, sma100w, sma200w, sma200d
  logreg_fair, logreg_resid_pct   log10(price) vs log10(days since genesis), expanding OLS; residual percentile
  risk                            ln(price / 400D SMA) * time de-trend, expanding min/max -> 0..1  (approximation)
  mvrv, price_to_realized         on-chain cost basis (CoinMetrics)
  days_since_ath, ath_recent_13w  cycle clock (top known only in hindsight -> use running ATH)
  days_since_halving, midterm_h1  calendar
  ff_minus_2y, ust2y_chg13w, curve_10y_2y, dxy_vs_sma50w   macro regime
  ethbtc_vs_sma20w, dom_vs_sma20w  BTC vs alts
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .history import halvings, us_midterm_years

GENESIS = pd.Timestamp("2009-01-03")


def weekly(daily: pd.DataFrame) -> pd.DataFrame:
    """Weekly bars ending Sunday (label = the Sunday). Prices: last close; flows: last value."""
    return daily.resample("W-SUN").last()


def _expanding_logreg(price: pd.Series, min_points: int = 104) -> tuple[pd.Series, pd.Series]:
    """Expanding OLS of log10(P) on log10(days since genesis); returns fair value and residual percentile."""
    days = (price.index - GENESIS).days.values.astype(float)
    x = np.log10(days)
    y = np.log10(price.values.astype(float))
    fair = np.full(len(price), np.nan)
    pct = np.full(len(price), np.nan)
    sx = sy = sxx = sxy = 0.0
    resid_hist: list[float] = []
    n = 0
    for i in range(len(price)):
        if not np.isfinite(y[i]):
            continue
        n += 1
        sx += x[i]; sy += y[i]; sxx += x[i] * x[i]; sxy += x[i] * y[i]
        if n < min_points:
            continue
        b = (n * sxy - sx * sy) / (n * sxx - sx * sx)
        a = (sy - b * sx) / n
        fair[i] = 10 ** (a + b * x[i])
        r = y[i] - (a + b * x[i])
        resid_hist.append(r)
        pct[i] = (np.searchsorted(np.sort(resid_hist), r, side="right")) / len(resid_hist)
    return pd.Series(fair, price.index), pd.Series(pct, price.index)


def _risk_metric(daily_price: pd.Series, k: float = 0.395) -> pd.Series:
    """Approximation of a cycle 'risk' oscillator: ln(P / 400D SMA), scaled up with time so that later, smaller
    cycles are comparable (diminishing returns), normalised with an expanding min/max (no look-ahead).
    The exponent k is fixed a priori (not fitted on returns); documented as an approximation, not Cowen's formula."""
    sma400 = daily_price.rolling(400, min_periods=400).mean()
    days = (daily_price.index - GENESIS).days.astype(float)
    raw = np.log(daily_price / sma400) * np.power(days / 1000.0, k)
    lo = raw.expanding(min_periods=200).min()
    hi = raw.expanding(min_periods=200).max()
    return ((raw - lo) / (hi - lo)).clip(0, 1)


def build(daily: pd.DataFrame) -> pd.DataFrame:
    d = daily.copy()
    d["sma200d"] = d["btc"].rolling(200, min_periods=200).mean()
    d["risk"] = _risk_metric(d["btc"].dropna()).reindex(d.index)
    w = weekly(d)
    p = w["btc"]
    f = pd.DataFrame(index=w.index)
    f["btc"] = p
    f["sma20w"] = p.rolling(20, min_periods=20).mean()
    f["ema21w"] = p.ewm(span=21, adjust=False, min_periods=21).mean()
    f["bmsb_low"] = f[["sma20w", "ema21w"]].min(axis=1)
    f["sma50w"] = p.rolling(50, min_periods=50).mean()
    f["sma100w"] = p.rolling(100, min_periods=100).mean()
    f["sma200w"] = p.rolling(200, min_periods=200).mean()
    f["sma200d"] = w["sma200d"]
    f["below_50w"] = (p < f["sma50w"]).astype(int)
    f["weeks_below_50w"] = f["below_50w"].groupby((f["below_50w"] == 0).cumsum()).cumsum()
    f["weeks_above_50w"] = (1 - f["below_50w"]).groupby((f["below_50w"] == 1).cumsum()).cumsum()
    f["below_bmsb"] = (p < f["bmsb_low"]).astype(int)
    fair, pct = _expanding_logreg(p.dropna())
    f["logreg_fair"] = fair.reindex(f.index)
    f["logreg_resid_pct"] = pct.reindex(f.index)
    f["risk"] = w["risk"]
    f["mvrv"] = w.get("mvrv")
    f["realized_price"] = w.get("realized_price")
    f["price_to_realized"] = p / f["realized_price"]
    ath = d["btc"].cummax()
    last_ath = pd.Series(np.where(d["btc"] >= ath, d.index, pd.NaT), index=d.index).ffill()
    days_since_ath = (d.index.to_series() - pd.to_datetime(last_ath)).dt.days
    f["days_since_ath"] = days_since_ath.resample("W-SUN").last()
    f["drawdown_from_ath"] = (p / ath.resample("W-SUN").last()) - 1
    f["ath_recent_13w"] = (f["days_since_ath"] <= 91).astype(int)
    hv = halvings()
    f["days_since_halving"] = [min(((t - h).days for h in hv if h <= t), default=np.nan) for t in f.index]
    f["midterm_h1"] = [int(t.year in us_midterm_years() and t.month <= 6) for t in f.index]
    if "ust2y" in w:
        f["ust2y"] = w["ust2y"]
        f["ust10y"] = w.get("ust10y")
        f["curve_10y_2y"] = w["ust10y"] - w["ust2y"]
        f["ust2y_chg13w"] = w["ust2y"] - w["ust2y"].shift(13)
    if "effr" in w:
        f["effr"] = w["effr"]
        f["ff_minus_2y"] = w["effr"] - w.get("ust2y")
        f["ff_chg26w"] = w["effr"] - w["effr"].shift(26)
    if "ust3m" in w:
        f["tbill3m"] = w["ust3m"]
    if "dxy" in w:
        f["dxy"] = w["dxy"]
        f["dxy_vs_sma50w"] = w["dxy"] / w["dxy"].rolling(50, min_periods=50).mean() - 1
    if "eth_btc" in w:
        f["eth_btc"] = w["eth_btc"]
        f["ethbtc_vs_sma20w"] = w["eth_btc"] / w["eth_btc"].rolling(20, min_periods=20).mean() - 1
    if "btc_dom_proxy" in w:
        f["btc_dom"] = w["btc_dom_proxy"]
        f["dom_vs_sma20w"] = w["btc_dom_proxy"] / w["btc_dom_proxy"].rolling(20, min_periods=20).mean() - 1
    if "fng" in w:
        f["fng"] = w["fng"]
    if "stable_mcap" in w:
        f["stable_mcap_chg13w"] = w["stable_mcap"] / w["stable_mcap"].shift(13) - 1
    f["ret_1w"] = p.pct_change()
    return f.dropna(subset=["btc"])


def snapshot(f: pd.DataFrame, t: pd.Timestamp | None = None) -> dict:
    """The feature row at (or before) t as a plain dict with rounded floats - what the LLM sees."""
    row = f.loc[:t].iloc[-1] if t is not None else f.iloc[-1]
    out = {"week": str(row.name.date())}
    for k, v in row.items():
        if isinstance(v, (float, np.floating)):
            out[k] = None if not np.isfinite(v) else round(float(v), 6 if abs(v) < 10 else 2)
        else:
            out[k] = v.item() if hasattr(v, "item") else v
    return out
