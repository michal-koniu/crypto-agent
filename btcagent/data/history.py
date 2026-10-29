"""Historical data: download raw series from verifiable public sources and build one daily panel.

Sources (all free, no key; checked 2026-10-29, see docs/RESEARCH.md):
  CoinMetrics community API  BTC price/market cap/MVRV/supply/hash rate since 2010; alt prices and caps
  data.binance.vision        spot klines (daily and hourly) since 2017 for BTC/USDT and ALT/BTC pairs
  OKX public REST            recent daily candles (fills the gap after the last monthly Binance file)
  US Treasury                daily par yield curve (3M, 2Y, 10Y) since 1990
  NY Fed markets API         effective fed funds rate (EFFR) since 2000
  alternative.me             Fear & Greed index since 2018
  DefiLlama                  total stablecoin supply
  Yahoo (yfinance)           DXY, S&P 500 (secondary source; rate-limited)

Everything lands as CSV in the data directory; `panel()` joins it into one daily DataFrame indexed by UTC date.
"""
from __future__ import annotations

import io
import time
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import pandas as pd

UA = {"User-Agent": "btc-agent/0.1 (research; personal use)"}
CM_URL = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
CM_BTC_METRICS = ["PriceUSD", "CapMrktCurUSD", "CapMVRVCur", "SplyCur", "HashRate", "IssTotUSD", "FlowInExUSD", "FlowOutExUSD"]
CM_ALTS = ["eth", "bnb", "xrp", "ada", "doge", "ltc", "link", "avax", "dot", "trx"]
CM_STABLES = ["usdt", "usdc"]
BINANCE_PAIRS = ["BTCUSDT", "ETHBTC", "SOLBTC", "BNBBTC", "XRPBTC", "ADABTC", "LINKBTC", "DOGEBTC", "LTCBTC"]


def _get(client: httpx.Client, url: str, **kw) -> httpx.Response:
    for attempt in range(4):
        r = client.get(url, timeout=60, **kw)
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(5 * (attempt + 1))
            continue
        return r
    return r


def fetch_coinmetrics(client: httpx.Client, asset: str, metrics: list[str]) -> pd.DataFrame:
    rows, url = [], CM_URL
    params = {"assets": asset, "metrics": ",".join(metrics), "frequency": "1d", "page_size": 10000, "start_time": "2009-01-01"}
    while url:
        r = _get(client, url, params=params)
        r.raise_for_status()
        j = r.json()
        rows += j["data"]
        url, params = j.get("next_page_url"), None
        time.sleep(0.6)
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["time"]).dt.tz_convert(None).dt.normalize()
    keep = ["date"] + [m for m in metrics if m in df.columns]
    out = df[keep].copy()
    for m in keep[1:]:
        out[m] = pd.to_numeric(out[m], errors="coerce")
    return out


def fetch_binance_daily(client: httpx.Client, sym: str, start=(2017, 7)) -> pd.DataFrame:
    frames, (y, m) = [], start
    today = date.today()
    while (y, m) < (today.year, today.month):
        u = f"https://data.binance.vision/data/spot/monthly/klines/{sym}/1d/{sym}-1d-{y}-{m:02d}.zip"
        r = _get(client, u)
        if r.status_code == 200:
            z = zipfile.ZipFile(io.BytesIO(r.content))
            frames.append(pd.read_csv(z.open(z.namelist()[0]), header=None).iloc[:, :6])
        m += 1
        if m == 13:
            y, m = y + 1, 1
    df = pd.concat(frames)
    df.columns = ["open_time", "open", "high", "low", "close", "volume"]
    t = df["open_time"].astype("int64")
    t = t.where(t < 10**14, t // 1000)   # files from 2025 on are in microseconds
    df["date"] = pd.to_datetime(t, unit="ms").dt.normalize()
    return df[["date", "open", "high", "low", "close", "volume"]].drop_duplicates("date")


def fetch_okx_daily(client: httpx.Client, inst: str, limit: int = 100) -> pd.DataFrame:
    """Recent daily candles from OKX public REST (UTC days). inst like BTC-USDT."""
    r = _get(client, "https://www.okx.com/api/v5/market/history-candles", params={"instId": inst, "bar": "1Dutc", "limit": limit})
    r.raise_for_status()
    rows = [{"date": pd.to_datetime(int(c[0]), unit="ms").normalize(), "open": float(c[1]), "high": float(c[2]),
             "low": float(c[3]), "close": float(c[4]), "volume": float(c[5])} for c in r.json()["data"] if c[8] == "1"]
    return pd.DataFrame(rows).sort_values("date")


def fetch_treasury_yields(client: httpx.Client, start_year: int = 2009) -> pd.DataFrame:
    frames = []
    for y in range(start_year, date.today().year + 1):
        u = (f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{y}/all"
             f"?type=daily_treasury_yield_curve&field_tdr_date_value={y}&page&_format=csv")
        r = _get(client, u)
        if r.status_code == 200 and r.text.startswith("Date"):
            frames.append(pd.read_csv(io.StringIO(r.text)))
        time.sleep(0.5)
    df = pd.concat(frames)
    df["date"] = pd.to_datetime(df["Date"], format="%m/%d/%Y")
    return df.rename(columns={"3 Mo": "ust3m", "2 Yr": "ust2y", "10 Yr": "ust10y"})[["date", "ust3m", "ust2y", "ust10y"]].sort_values("date")


def fetch_effr(client: httpx.Client, start: str = "2009-01-01") -> pd.DataFrame:
    r = _get(client, "https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json",
             params={"startDate": start, "endDate": date.today().isoformat()})
    r.raise_for_status()
    rows = [{"date": pd.to_datetime(x["effectiveDate"]), "effr": x["percentRate"],
             "ff_upper": x.get("targetRateTo")} for x in r.json()["refRates"]]
    return pd.DataFrame(rows).sort_values("date")


def fetch_fear_greed(client: httpx.Client) -> pd.DataFrame:
    j = _get(client, "https://api.alternative.me/fng/", params={"limit": 0, "format": "json"}).json()["data"]
    return pd.DataFrame([{"date": pd.to_datetime(int(d["timestamp"]), unit="s").normalize(), "fng": int(d["value"])}
                         for d in j]).sort_values("date")


def fetch_stablecoins(client: httpx.Client) -> pd.DataFrame:
    j = _get(client, "https://stablecoins.llama.fi/stablecoincharts/all").json()
    return pd.DataFrame([{"date": pd.to_datetime(int(d["date"]), unit="s").normalize(),
                          "stable_mcap": d["totalCirculatingUSD"].get("peggedUSD")} for d in j])


def fetch_yahoo(ticker: str, name: str) -> pd.DataFrame:
    import yfinance as yf  # optional dependency
    d = yf.download(ticker, start="2010-01-01", progress=False, auto_adjust=True)
    d.columns = [c[0] if isinstance(c, tuple) else c for c in d.columns]
    d = d.reset_index()[["Date", "Close"]].rename(columns={"Date": "date", "Close": name})
    d["date"] = pd.to_datetime(d["date"]).dt.tz_localize(None)
    return d


def download_all(data_dir: str | Path, log=print, include_yahoo: bool = True) -> dict[str, int]:
    """Refresh every raw CSV. Idempotent; failures are logged and skipped (the panel uses what exists)."""
    d = Path(data_dir)
    d.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    with httpx.Client(headers=UA, follow_redirects=True) as c:
        jobs = [("cm_btc", lambda: fetch_coinmetrics(c, "btc", CM_BTC_METRICS))]
        jobs += [(f"cm_{a}", lambda a=a: fetch_coinmetrics(c, a, ["PriceUSD", "CapMrktCurUSD"])) for a in CM_ALTS + CM_STABLES]
        jobs += [(f"binance_{s}_1d", lambda s=s: fetch_binance_daily(c, s)) for s in BINANCE_PAIRS]
        jobs += [("okx_BTC-USDT_1d", lambda: fetch_okx_daily(c, "BTC-USDT")), ("okx_ETH-BTC_1d", lambda: fetch_okx_daily(c, "ETH-BTC")),
                 ("treasury", lambda: fetch_treasury_yields(c)), ("effr", lambda: fetch_effr(c)),
                 ("fear_greed", lambda: fetch_fear_greed(c)), ("stablecoins", lambda: fetch_stablecoins(c))]
        if include_yahoo:
            jobs += [("yf_dxy", lambda: fetch_yahoo("DX-Y.NYB", "dxy")), ("yf_spx", lambda: fetch_yahoo("^GSPC", "spx"))]
        for name, fn in jobs:
            try:
                df = fn()
                df.to_csv(d / f"{name}.csv", index=False)
                counts[name] = len(df)
                log(f"data: {name} {len(df)} rows")
            except Exception as e:  # keep going: one dead source must not stop the others
                log(f"data: {name} FAILED {type(e).__name__}: {str(e)[:160]}")
    return counts


def _read(d: Path, name: str) -> pd.DataFrame | None:
    p = d / f"{name}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    df["date"] = pd.to_datetime(df["date"], utc=False, format="mixed").dt.tz_localize(None).dt.normalize()
    return df.drop_duplicates("date").set_index("date").sort_index()


def panel(data_dir: str | Path) -> pd.DataFrame:
    """One daily panel. Columns: btc, btc_mcap, mvrv, realized_price, supply, hashrate, <alt>_btc, <alt>_mcap,
    stable_mcap_cm, btc_dom_proxy, ust3m, ust2y, ust10y, effr, ff_upper, fng, stable_mcap, dxy, spx."""
    d = Path(data_dir)
    b = _read(d, "cm_btc")
    if b is None:
        raise FileNotFoundError(f"{d}/cm_btc.csv missing - run `btcagent data refresh` first")
    out = pd.DataFrame(index=b.index)
    out["btc"] = b["PriceUSD"]
    out["btc_mcap"] = b["CapMrktCurUSD"]
    out["mvrv"] = b["CapMVRVCur"]
    out["realized_price"] = b["CapMrktCurUSD"] / b["CapMVRVCur"] / b["SplyCur"]
    out["supply"] = b["SplyCur"]
    out["hashrate"] = b.get("HashRate")
    # recent BTC closes from Binance/OKX where CoinMetrics lags by a day
    for name in ("binance_BTCUSDT_1d", "okx_BTC-USDT_1d"):
        x = _read(d, name)
        if x is not None:
            out = out.reindex(out.index.union(x.index))
            out["btc"] = out["btc"].fillna(x["close"])
    alt_caps = []
    for a in CM_ALTS:
        x = _read(d, f"cm_{a}")
        if x is None:
            continue
        if "PriceUSD" in x:
            out[f"{a}_usd"] = x["PriceUSD"]
        if "CapMrktCurUSD" in x:
            out[f"{a}_mcap"] = x["CapMrktCurUSD"]
            alt_caps.append(f"{a}_mcap")
    for s in CM_STABLES:
        x = _read(d, f"cm_{s}")
        if x is not None and "CapMrktCurUSD" in x:
            out[f"{s}_mcap"] = x["CapMrktCurUSD"]
    # ALT/BTC: prefer exchange pairs (direct quotes), fall back to USD cross rates
    for sym in BINANCE_PAIRS[1:]:
        x = _read(d, f"binance_{sym}_1d")
        if x is not None:
            out[f"{sym[:-3].lower()}_btc"] = x["close"]
    if "eth_btc" not in out and "eth_usd" in out:
        out["eth_btc"] = out["eth_usd"] / out["btc"]
    if "eth_usd" in out:
        out["eth_btc"] = out["eth_btc"].fillna(out["eth_usd"] / out["btc"])
    # Dominance proxy: BTC cap / (BTC + tracked large alts), ex-stablecoins. Tracked set is a top-cap sample,
    # so this overstates true dominance; only its trend is used.
    if alt_caps:
        out["btc_dom_proxy"] = out["btc_mcap"] / (out["btc_mcap"] + out[alt_caps].fillna(0).sum(axis=1))
    t = _read(d, "treasury")
    if t is not None:
        out = out.join(t[["ust3m", "ust2y", "ust10y"]], how="left")
    e = _read(d, "effr")
    if e is not None:
        out = out.join(e[["effr", "ff_upper"]], how="left")
    for name, col in (("fear_greed", "fng"), ("stablecoins", "stable_mcap"), ("yf_dxy", "dxy"), ("yf_spx", "spx")):
        x = _read(d, name)
        if x is not None and col in x:
            out[col] = x[col]
    macro = [c for c in ("ust3m", "ust2y", "ust10y", "effr", "ff_upper", "dxy", "spx") if c in out]
    out[macro] = out[macro].ffill()          # weekends/holidays carry the last published value forward
    return out.sort_index()


def halvings() -> list[pd.Timestamp]:
    return [pd.Timestamp(x) for x in ("2012-11-28", "2016-07-09", "2020-05-11", "2024-04-20", "2028-04-15")]


def us_midterm_years() -> set[int]:
    return {2014, 2018, 2022, 2026, 2030}


def utc_today() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(timezone.utc).date())
