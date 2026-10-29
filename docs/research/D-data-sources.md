# D. Data sources for a BTC-denominated, low-frequency crypto agent

**Research date:** 2026-10-29. **Method:** I sent live HTTP probes from the research machine (macOS, behind a filtering proxy) and read official pricing and docs pages. Each claim is tagged with how it was checked:

- **[LIVE]**: I called the endpoint on 2026-10-29 and looked at the response (status code, payload, rate-limit headers, history depth).
- **[DOC]**: taken from the vendor's own pricing or docs page on 2026-10-29.
- **[3P]**: from third-party sources only, or the sources disagreed. Verify before you depend on it.
- **[UNVERIFIED]**: I couldn't confirm it (blocked or unreachable from the test box, or no official page found).

Live snapshot used as a sanity check: on 2026-10-28 BTC was about $81.2k (CoinMetrics), CoinMetrics MVRV was about 1.50, Binance funding was about 0.005–0.01% per 8h, and the Fear & Greed index was 51 (Neutral).

---

## 0. TL;DR: recommended stack

| Need | Primary (free) | Fallback / upgrade |
|---|---|---|
| Macro rates and liquidity | **FRED API** (free key) | Treasury FiscalData (daily TGA), ALFRED for revisions |
| Dollar | FRED `DTWEXBGS` (broad index, public domain) | Yahoo `DX-Y.NYB` via yfinance (unofficial) |
| Equities and VIX | FRED `SP500` (10 years only), `NASDAQCOM`, `VIXCLS` | yfinance `^GSPC`, `^IXIC`, `^VIX` for longer history |
| Global M2 | Build it yourself: FRED `M2SL` + ECB BSI + BoJ API + DBnomics/IMF for China, converted with FRED FX | BGeometrics Advanced (includes M2), paid |
| Economic calendar | Fed FOMC page + BLS `.ics` + FRED `release/dates` | none needed |
| BTC daily price 2010→ | **CoinMetrics Community** `PriceUSD` (from 2010-07-18) | blockchain.info `market-price` (from 2009), Bitstamp OHLC (from 2011) |
| Backtest OHLCV | **data.binance.vision** (spot from 2017-08, perps, funding, OI metrics) | Bybit `public.bybit.com`, OKX REST, ccxt |
| Dominance / TOTAL / TOTAL2 / TOTAL3 | CoinMarketCap Basic, free (1 year of daily global metrics) + your own daily snapshots | **One month of CMC Startup at $79** to backfill to 2013, then cancel |
| ALT/BTC | Binance `XXXBTC` klines (ETHBTC from 2017-07) | CoinGecko Demo `vs_currency=btc` (365 days) |
| Stablecoin supply | **DefiLlama** `stablecoins.llama.fi` (from 2017-11) | none needed |
| Funding / OI | Binance, Bybit and OKX public REST + Binance bulk `metrics` files (OI from 2020-09) | CoinGlass Hobbyist $29/mo (aggregated across exchanges) |
| Liquidations | No good free history; collect from exchange WebSocket streams yourself | CoinGlass Hobbyist; Tardis (expensive) |
| ETF flows | Farside / bitbo (HTML; Farside sits behind Cloudflare) | CoinGlass Hobbyist ETF endpoints |
| Fear & Greed | **alternative.me** (from 2018-02-01) | none needed |
| On-chain (MVRV, NUPL, Puell, realized price, hash rate) | **CoinMetrics Community** (derive from full history) + mempool.space | **BGeometrics** for SOPR and supply-in-profit (free: 4 years, 7-day delay, 15 requests/day) |
| DeFi / protocol risk | **DefiLlama** (TVL, yields, hacks) + **L2Beat** summary JSON | rekt.news RSS, Solodit |
| News and regulation | RSS: CoinDesk, The Block, Decrypt, Cointelegraph, SEC, Fed, CFTC, ESMA | CryptoPanic (no free tier any more) |

**Suggested paid add-ons, if any:** (1) a one-off month of **CoinMarketCap Startup at $79** to backfill dominance and total market cap from 2013; (2) **CoinGlass Hobbyist at $29/mo** if you want aggregated OI, liquidations and ETF flows; (3) **BGeometrics Advanced** if SOPR or supply-in-profit turn out to matter in backtests (the price wasn't shown on the page). Everything else can run free.

---

## 1. Macro

### 1.1 FRED API (St. Louis Fed)
- **Endpoint:** `https://api.stlouisfed.org/fred/series/observations?series_id=…&api_key=…&file_type=json`. There's also an API v2 for bulk pulls of whole releases [DOC].
- **Key:** required. **[LIVE]** A call without a key returns `400 "Variable api_key is not set"`. The key is free.
- **Rate limit:** the official terms only say the Fed "may set or change bandwidth and transaction limits". **[3P]** Many sources agree on **120 requests per minute per key**. That's ample for daily jobs.
- **Licence [DOC]:** FRED terms of use. Third-party series (notes say "Copyright", tag "Copyrighted: Pre-Approval Required") are **fine for your own personal use**; anything beyond that needs permission from the data owner. Apps must show "This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis."
- **Keyless CSV** (`fred.stlouisfed.org/graph/fredgraph.csv?id=…`): **[LIVE] failed from the test box** (HTTP/2 stream reset, i.e. bot protection). Don't rely on it. This also affects keyless `pandas-datareader` FRED reads. Use the API with a key.

**Core series (all verified on FRED series pages, updated 2026-10-26 to 2026-10-29 [DOC]):**

| Use | Series | Freq / units | Notes |
|---|---|---|---|
| Fed funds | `DFF` (effective, daily), `FEDFUNDS` (monthly), `DFEDTARU`/`DFEDTARL` (target range) | % | public domain |
| 2y / 10y | `DGS2`, `DGS10`, curve `T10Y2Y` | daily % | public domain |
| Real yield / breakeven | `DFII10`, `T10YIE` | daily | useful for the liquidity regime |
| Fed balance sheet | `WALCL` | weekly (Wed), **$ millions** | |
| TGA | `WTREGEN` | weekly (Wed), **$ millions** | latest observation 2026-10-21 |
| Reverse repo | `RRPONTSYD` | daily, **$ billions** | latest observation 2026-10-28 |
| M2 | `M2SL` (monthly SA), `WM2NS` (weekly NSA) | $ billions | |
| Dollar | `DTWEXBGS` (nominal broad USD index, H.10) | daily, Jan 2006 = 100 | **public domain**, weekly release lag (latest 2026-10-23, next 2026-11-02) |
| FX legs for a synthetic DXY | `DEXUSEU`, `DEXJPUS`, `DEXUSUK`, `DEXCAUS`, `DEXSDUS`, `DEXSZUS` | daily | apply the ICE DXY weights to get a free DXY replica |
| S&P 500 | `SP500` | daily | **only 10 years of history** under the S&P DJI licence; copyrighted |
| Nasdaq Composite | `NASDAQCOM` | daily | copyrighted (Nasdaq), personal use OK |
| VIX | `VIXCLS` | daily (CBOE) | copyrighted, "reprinted with permission" |
| CPI | `CPIAUCSL`, `CPILFESL` | monthly | BLS |
| HY spread (risk appetite) | `BAMLH0A0HYM2` | daily | **[3P/DOC] since April 2026, ICE BofA series on FRED keep only about 3 years** (older vintages via ALFRED). Store history locally. |

**Net liquidity** (the common Fed liquidity proxy): `WALCL/1000 − WTREGEN/1000 − RRPONTSYD` in $ billions. Mind the units: two of the series are in millions and one in billions. Forward-fill the weekly series to daily and use **point-in-time (ALFRED vintages, or at least the release date) in backtests** to avoid look-ahead bias. WALCL and WTREGEN are published on Thursday afternoon for Wednesday.

**Daily TGA alternative:** US Treasury FiscalData Daily Treasury Statement, `https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/operating_cash_balance` (free, no key). **[UNVERIFIED]** The connection failed from the test box (network-level), so I couldn't check it.

### 1.2 DXY and free proxies
- **FRED `DTWEXBGS`**: public domain, the official broad dollar index. Not the same basket as DXY, but highly correlated. Recommended as the primary signal.
- **Synthetic DXY** from FRED FX series (formula: `50.14348112 × EURUSD^-0.576 × USDJPY^0.136 × GBPUSD^-0.119 × USDCAD^0.091 × USDSEK^0.042 × USDCHF^0.036`).
- **Yahoo `DX-Y.NYB`** **[LIVE]**: the v8 chart endpoint answered 200 with ICE data. It's unofficial, and Yahoo's terms are personal-use only. Use it as a cross-check.
- **Stooq**: **[LIVE] now serves a JavaScript proof-of-work bot wall**, so it's not usable headless. Dropped.

### 1.3 Equities and risk sentiment
- FRED `SP500` (10 years), `NASDAQCOM`, `VIXCLS` are enough for a daily agent.
- Longer S&P history: yfinance `^GSPC` (from 1927). See section 7 on reliability.
- Optional: HY OAS (`BAMLH0A0HYM2`, now only about 3 years on FRED), the `T10Y2Y` curve, and the `NFCI` financial-conditions index (Chicago Fed, weekly, public domain).

### 1.4 Global M2
There's no free official aggregate. **[3P]** TradingView-style "global M2" indices are built from commercial feeds. To build it yourself (all free):

| Economy | Source | Status |
|---|---|---|
| US | FRED `M2SL` | [DOC] |
| Euro area | ECB Data Portal `https://data-api.ecb.europa.eu/service/data/BSI/M.U2.Y.V.M20.X.1.U2.2300.Z01.E?format=csvdata` | **[UNVERIFIED]**: 503 / connection failure from the test box; ECB documents it as a public API |
| Japan | **BoJ Time-Series Data Search API** (launched 2026-02-18, no key), e.g. `https://www.stat-search.boj.or.jp/api/v1/getDataCode?format=json&lang=en&db=MD02&code=MAM1NAM2M2MO` | **[LIVE]** 200, "Successfully completed" |
| China, UK, others | DBnomics (`api.db.nomics.world`, providers include IMF, BOE, BIS, NBS, OECD) | **[LIVE]** API up; check each series for freshness |
| FX conversion | FRED `DEXCHUS`, `DEXJPUS`, `DEXUSEU`, `DEXUSUK` | [DOC] |

Paid shortcut: **BGeometrics Advanced and above include "M2"** [DOC]. M2 is monthly and published with a lag of 3–6 weeks, so model it with release lags.

### 1.5 ISM PMI
- ISM PMI is **not on FRED** (licence pulled years ago).
- **DBnomics `ISM/pmi`** **[LIVE]** exists, but its **last observation is 2025-12 (indexed 2026-01-07), so it's stale**. Don't depend on it.
- Free substitutes: the regional Fed manufacturing surveys on FRED, e.g. Philly Fed `GACDFSA066MSFRBPHI` and Empire `GACDINA066MSFRBNY`, plus `NFCI`. Or scrape the ISM headline from the monthly ISM press release (manual, terms unclear). I'd treat PMI as optional.

### 1.6 Economic calendar
- **FOMC:** `https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm` **[LIVE]**. Parsed dates: 2026: Jan 27–28, Mar 17–18*, Apr 28–29, Jun 16–17*, Jul 28–29, Sep 15–16*, Oct 27–28, **Dec 8–9***. 2027: Jan 26–27, Mar 16–17*, Apr 27–28, Jun 8–9*, Jul 27–28, Sep 14–15*, Oct 26–27, Dec 7–8* (* = with SEP projections). Also the Fed press RSS `https://www.federalreserve.gov/feeds/press_all.xml` **[LIVE]**.
- **CPI and all BLS releases:** an iCalendar file at `https://www.bls.gov/schedule/news_release/bls.ics` **[LIVE]** (313 events). Upcoming CPI dates: **2026-11-10, 2026-12-10**.
- **FRED release calendar:** `fred/releases/dates` and `fred/release/dates?release_id=…` (with a key) cover CPI, H.4.1, H.10 and other release dates.

---

## 2. Crypto market structure

| What | Endpoint | History | Cost / limits | Licence | Status |
|---|---|---|---|---|---|
| **Dominance and total market cap (current)** | CoinGecko `GET /api/v3/global` | current snapshot only | Demo plan: free, 10k calls/month, 100/min (keyless public access also works) | attribution required | **[LIVE]** 200 |
| Dominance history (CoinGecko) | `/global/market_cap_chart` | — | **[LIVE] paid only** ("limited to PRO API subscribers"). Analyst plan $129/mo: history from 2013 | | |
| **Dominance and total market cap history (CMC)** | `GET /v1/global-metrics/quotes/historical` | **Basic (free): 1 year daily**; Builder $29: 3 years; **Startup $79: from 2013** | Basic: 15k credits/month, 50/min | CMC licence: commercial use allowed for one product, **no redistribution** | [DOC] |
| Current snapshot fallbacks | CoinPaprika `/v1/global` (dominance 57.22%), CoinLore `/api/global/` (btc_d 60.57%) | current only | free, no key | — | **[LIVE]** Note how much providers disagree on "dominance" (57–61%). **Pick one source and stay with it.** |
| TOTAL2 / TOTAL3 | Derive: TOTAL − BTC mcap (− ETH mcap) from the same provider's history | | | | method |
| **ALT/BTC prices** | Binance klines `ETHBTC`, `SOLBTC`, … (`data.binance.vision`, ETHBTC from 2017-07) | 2017→ | free | Binance terms | **[LIVE]** |
| ALT/BTC (aggregated) | CoinGecko `/coins/{id}/market_chart?vs_currency=btc&days=365` | **365 days only** on free/public | Demo free | attribution | **[LIVE]** 366 points; `days=max` → error 10012 |
| **Stablecoin supply** | DefiLlama `https://stablecoins.llama.fi/stablecoincharts/all` (also `/stablecoins`, `/stablecoincharts/{chain}`) | **2017-11-29→** | free, no key | open API; credit DefiLlama | **[LIVE]** |
| **Funding rates** | Binance `fapi/v1/fundingRate`, Bybit `v5/market/funding/history`, OKX `api/v5/public/funding-rate-history`; Binance bulk `data/futures/um/monthly/fundingRate/BTCUSDT/` | Binance bulk from 2020-01 | free, no key | exchange terms | **[LIVE]** all three 200 |
| **Open interest** | Binance REST `futures/data/openInterestHist` = **last 30 days only** (`startTime` older → error -1130). **Binance bulk `data/futures/um/daily/metrics/BTCUSDT/`**: 5-minute OI, OI value, top-trader and global long/short ratios, taker buy/sell ratio, **from 2020-09-01, latest 2026-10-28** | 2020-09→ | free | | **[LIVE]**. This is the best free OI history. |
| Liquidations | Binance `forceOrder` WebSocket (live only); `liquidationSnapshot` bulk dataset **no longer listed** | none free | — | | **[LIVE]**. Collect your own or pay. |
| Aggregated derivatives (OI, liquidations, ETF, long/short) | **CoinGlass API** | daily: all-time | **Hobbyist $29/mo (30/min, 80+ endpoints, personal use only)**, Startup $79, Standard $299 (commercial). **No free tier.** | personal use for Hobbyist and Startup | [DOC] |
| **ETF flows** | Farside `farside.co.uk/btc/` | from Jan 2024 | free HTML | **[LIVE] 403 Cloudflare challenge**; the terms page is also 403. Don't scrape. | |
| ETF flows alternatives | bitbo.io `/treasuries/etf-flows` (HTML, **[LIVE]** 200); CoinGlass ETF endpoints (paid); SoSoValue (widely cited; **[UNVERIFIED]** I couldn't find official API docs) | | | read each site's terms | |
| **Fear & Greed** | `https://api.alternative.me/fng/?limit=0&format=json` | **2018-02-01→** (3,189 daily points) | free, no key | attribution requested | **[LIVE]** |

---

## 3. Historical OHLCV for backtests

| Source | Endpoint | History | Cost / limits | Licence | Status |
|---|---|---|---|---|---|
| **Binance public data** | `https://data.binance.vision/` (S3 listing `s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data/spot/monthly/klines/BTCUSDT/1d/`) | BTCUSDT 1d **2017-08→2026-09** monthly zips (+ daily zips for the current month), with `.CHECKSUM` files; spot, USDⓈ-M and COIN-M futures, aggTrades, mark/index/premium klines, funding, metrics | free, no key | Binance terms (personal use is fine) | **[LIVE]** |
| Binance REST | `api/v3/klines` (1000 rows/request; weight-based limit of about 6000/min) | 2017→ | free | | **[LIVE]** |
| Bybit | `https://public.bybit.com/` (trading/ = tick trades for 2,106 symbols; `kline_for_metatrader4/` 2020–2024); REST `v5/market/kline` | 2019/2020→ | free | | **[LIVE]** |
| OKX | REST `api/v5/market/history-candles`, funding history; CSV "historical data" download page | 2018→ (REST paginated) | free, 20 req/2 s typical | | **[LIVE]** (funding) |
| **ccxt** | unified wrapper over all of the above | — | MIT | | v4.5.91 released **2026-10-29** |
| **BTC daily back to 2010** | **CoinMetrics Community** `PriceUSD` (`paging_from=start`) | **2010-07-18→** | free, no key; **10 requests / 6 s per IP** [DOC]; response header shows a 6000/20 s "download" plan | **CC BY-NC 4.0** (personal and non-commercial use OK, attribution) | **[LIVE]** |
| BTC price from 2009 | blockchain.info `https://api.blockchain.info/charts/market-price?timespan=all&format=json&sampled=false` | 2009-01-03→ (zeros until mid-2010) | free | blockchain.com terms | **[LIVE]** |
| Bitstamp OHLC | `https://www.bitstamp.net/api/v2/ohlc/btcusd/?step=86400&start=…&limit=1000` | **2011-09→** (real exchange OHLC) | free | | **[LIVE]** |
| CryptoCompare / **CoinDesk Data** | `min-api.cryptocompare.com`, `data-api.coindesk.com` | from 2010 | **[LIVE] both return 401 "API key required".** **[3P]** The free tier was retired on 2026-05-21; paid plans are sales-only. **Not recommended.** | | |
| Kaiko | institutional, sales-only | | $$$$ | | not recommended |
| Tardis.dev | tick, order book, `derivative_ticker` (funding, OI), liquidations | 2019→ | **[DOC] the first day of each month is free without a key**; Solo plan $700–900/mo | | good for validating intraday microstructure, overkill for daily decisions |

**Backtest guidance:** use Binance spot klines as the "tradeable" price from 2017 onward. Use CoinMetrics `PriceUSD` (reference rate) for BTC regime and cycle work from 2010. For alt universes, include **delisted pairs** (Binance bulk keeps them) to avoid survivorship bias.

---

## 4. On-chain BTC metrics

| Source | What you get free | History | Limits | Licence | Status |
|---|---|---|---|---|---|
| **CoinMetrics Community API** `community-api.coinmetrics.io/v4/timeseries/asset-metrics` | 31 BTC metrics: `PriceUSD`, `CapMrktCurUSD`, **`CapMVRVCur`**, `SplyCur`, **`HashRate`**, **`IssTotUSD`/`IssTotNtv`**, `FeeTotNtv`, `AdrActCnt`, `AdrBalCnt`, `TxCnt`, `FlowInExUSD`/`FlowOutExUSD`, `SplyExNtv` (exchange supply), `ROI1yr`, `ReferenceRate*`, … | **2010-07-18→ (updated daily, T-1)** | 10 req / 6 s per IP, no key | **CC BY-NC 4.0** | **[LIVE]** (MVRV 1.50 on 2026-10-28) |
| → derived for free | **Realized cap** = `CapMrktCurUSD / CapMVRVCur`; **realized price** = realized cap / `SplyCur`; **NUPL** = 1 − 1/MVRV; **Puell multiple** = `IssTotUSD` / 365-day mean of `IssTotUSD`; **MVRV Z-score** ≈ (mcap − realized cap) / std(mcap) | full | | | method |
| **BGeometrics** (`bitcoin-data.com/v1/{metric}`, e.g. `mvrv`, `sopr`, `nupl`, `puell-multiple`, `realized-price`, `supply-in-profit` …) | **SOPR, STH/LTH variants, supply in profit**, plus all the classics | **free: last 4 years (from 2022-10-29); the last 7 days are withheld** (`"delayed":true`) | **free: 10 requests/hour, 15/day** (`X-RateLimit-*` headers); Advanced 200/hour, 300/day; Premium 500/1000; Business 6000/10000. Prices weren't shown on the page. | **no redistribution**; the commercial publishing add-on allows charts and values only | **[LIVE]** + [DOC] |
| **mempool.space** `api/v1/mining/hashrate/{1m,3m,6m,1y,2y,3y,all}`, `difficulty-adjustments`, fees | hash rate, difficulty, fees | full | rate-limited (HTTP 429, bans on abuse); self-hostable (open source) | AGPL software, data open | **[LIVE]** |
| blockchain.info charts | hash-rate, difficulty, miners-revenue, n-transactions, market-price | 2009→ | free | | **[LIVE]** |
| Glassnode | Studio: Advanced $49/mo (24h resolution, 4 years, **no API**), Professional from $584/mo with **API as a paid add-on**; "API Light" = 14 days, daily resolution, 50 calls/day | — | **[DOC] no free plan listed on the pricing page** | | not worth it for this budget |
| CryptoQuant | **Basic (free): 10,000 API credits/month** [DOC], with metric coverage limited on free; Advanced 300k, Pro 500k credits | varies | credit-metered; free plan can't buy top-ups | | worth a free key as a cross-check (exchange flows, miner flows) |
| Look Into Bitcoin (formerly Bitcoin Magazine Pro) | API only with the **Professional plan** ([3P] about $99/mo billed annually), 200+ metrics, **personal use only** | | | | [DOC] / [3P] |

**Recommendation:** use CoinMetrics Community as the backbone (deep, free, stable schema, a fully maintained Python client `coinmetrics-api-client` 2026.10.23). Add a once-a-day BGeometrics pull of 5–10 metrics to cover SOPR and supply-in-profit; 15 requests/day is enough if you cache and pull incrementally. Add mempool.space for hash rate and difficulty and miner stress. CC BY-NC is fine for a personal agent, but **re-check the licence if this ever goes commercial**.

---

## 5. DeFi and protocol risk

| Source | Endpoint | Notes | Status |
|---|---|---|---|
| **DefiLlama TVL** | `api.llama.fi/protocols` (8,874 protocols incl. `audits`, `audit_links`, `category`, `chainTvls`), `/protocol/{slug}`, `/v2/historicalChainTvl` (from 2017-09), `/v2/chains` | free, no key. **[3P]** Free limits are informal (sources say 10–300/min). Pro API (`pro-api.llama.fi`): 1,000/min, 1M calls/month, $0.60 per extra 1k calls; price [3P] about $300/mo. Not needed. | **[LIVE]** |
| DefiLlama stablecoins | `stablecoins.llama.fi/stablecoins`, `/stablecoincharts/all` | peg and depeg monitoring via `/stablecoinprices` | **[LIVE]** |
| DefiLlama yields | `yields.llama.fi/pools` (15,929 pools), `/chart/{pool}` | APY and TVL, outlier flags | **[LIVE]** |
| **DefiLlama hacks** | `api.llama.fi/hacks` | 1,328 incidents, 2011-06 → **2026-10-28**, fields: classification, technique, amount, chain, bridgeHack, targetType, returnedFunds | **[LIVE]** (free) |
| **L2Beat** | `https://l2beat.com/api/scaling/summary` (no key): per-project `stage` (Stage 0/1/2), `risks[]` (sequencer failure, state validation, DA, exit window, proposer failure), TVS | Official `api.l2beat.com` **requires an apiKey** ("Unauthorized. Use apiKey query parameter"). The public summary JSON is an undocumented website endpoint, so pin a schema check. | **[LIVE]** |
| rekt.news | `https://rekt.news/rss/feed.xml` | post-mortems, narrative only | **[LIVE]** RSS 200 |
| Audit trackers | DefiLlama `audits` / `audit_links` per protocol; **Solodit** (`solodit.cyfrin.io`, searchable audit findings, web only); De.Fi REKT database (web) | none has a free stable API. Use them for manual or agent look-ups, not as a time series. | **[LIVE]** pages up |

How to turn this into a risk signal: treat a bridge or protocol you're exposed to as "red" if any of these hold: TVL drops more than 20% in 24h, a stablecoin trades below $0.98, a `hacks` entry appears for the protocol or chain, or the L2Beat stage gets downgraded. For a BTC-benchmarked portfolio, it's mainly relevant to wrapped-BTC (WBTC, cbBTC, tBTC), stablecoin parking and any alt you hold.

---

## 6. News and regulation feeds

| Feed | URL | Status |
|---|---|---|
| CoinDesk | `https://www.coindesk.com/arc/outboundfeeds/rss/` (25 items) | **[LIVE]** |
| The Block | `https://www.theblock.co/rss.xml` | **[LIVE]** |
| Decrypt | `https://decrypt.co/feed` | **[LIVE]** |
| Cointelegraph | `https://cointelegraph.com/rss` | **[LIVE]** |
| SEC press releases | `https://www.sec.gov/news/pressreleases.rss` (the SEC requires a descriptive User-Agent with contact info and caps traffic at ≤10 req/s) | **[LIVE]** |
| Fed press releases | `https://www.federalreserve.gov/feeds/press_all.xml` | **[LIVE]** |
| CFTC | `https://www.cftc.gov/RSS/RSSGP/rssgp.xml` | **[LIVE]** |
| ESMA | `https://www.esma.europa.eu/rss.xml` (MiCA notices) | **[LIVE]** |
| KNF (Poland) | no RSS found; public warnings list at `knf.gov.pl/dla_konsumenta/ostrzezenia_publiczne`, news under "komunikaty" | **[UNVERIFIED]**: the site didn't connect from the test box; plan on HTML polling |
| **CryptoPanic** | `/api/{growth|growth_weekly|enterprise}/v2/posts/` | **[LIVE]** the server says valid plans are growth, growth_weekly and enterprise. **The free "developer" tier is gone.** Prices weren't retrievable (Cloudflare). Skip it. |

### Treating news as untrusted input (prompt-injection hygiene)
1. **Allowlist fetchers.** Code, not the LLM, decides which URLs get fetched. No following links found inside articles.
2. **Strip and normalise.** Parse with `feedparser` (BSD-2, v6.0.14, 2026-07) and keep only title, link, published date, source and a truncated summary. Strip HTML, scripts, zero-width and bidi characters. Cap the length.
3. **Wrap as data.** Pass items inside clearly delimited blocks, e.g. `<untrusted_news source=… id=…>…</untrusted_news>`. The system prompt states that content inside them is never instructions.
4. **Least privilege.** The news-reading step **has no tool access** (no trading, no fetching). It only outputs a fixed JSON schema (`{event_type, assets, direction, severity 0–3, confidence, source_ids}`), which is validated with pydantic or jsonschema.
5. **Corroboration rule.** A severity ≥2 regulatory or hack event changes allocation only if **two independent sources** report it, or one primary source does (sec.gov, federalreserve.gov, esma.europa.eu, a DefiLlama hack entry, an exchange status page).
6. **Hard limits outside the LLM.** Position-size and turnover limits are enforced in code no matter what the news says. Log the raw items for audit.
7. **Dedup and replay.** Hash the canonical URL and title, and store with fetch time so backtests can replay "what the agent knew when".

---

## 7. Python libraries (PyPI checked 2026-10-29) [LIVE]

| Library | Latest | Released | Licence | Verdict |
|---|---|---|---|---|
| **ccxt** | 4.5.91 | 2026-10-29 | MIT | Very active. Use it for exchange REST (OHLCV, funding, OI) across Binance, Bybit and OKX. |
| **coinmetrics-api-client** | 2026.10.23.19 | 2026-10-23 | MIT | Official; handles paging and the Community endpoint. |
| fredapi | 0.5.2 | 2024-05-05 | Apache-2.0 (per repo) | Stale but works (thin wrapper). OK to use. |
| fedfred | 3.0.0 | 2025-11-18 | MIT | Modern FRED client (async, caching). A newer alternative. |
| pandas-datareader | 0.11.1 | 2026-06-24 | BSD-3 | Maintained again, but keyless FRED goes through `fredgraph.csv`, which was blocked from the test box. Prefer the keyed API. |
| **yfinance** | 1.7.0 | 2026-08-26 | Apache-2.0 | Actively released (1.x line in 2026). **[3P]** Recurring `YFRateLimitError` / 429 issues and cloud-IP blocks are reported; unofficial Yahoo API, personal use. **[LIVE]** the v8 chart endpoint worked. Use it for ^GSPC, ^IXIC, ^VIX, DX-Y.NYB as a **secondary** source, with caching and retry/back-off, one batched daily call. |
| python-binance | 1.0.37 | 2026-06-08 | MIT | Fine, but ccxt plus raw `data.binance.vision` downloads is enough. |
| defillama (unofficial) | 2.3.0 | 2024-05-09 | Apache-2.0 | Stale. The API is simple REST: use `httpx`/`requests` directly. |
| defillama-sdk | 0.1.4 | 2026-02-10 | n/a | Provenance unverified. Prefer raw REST. |
| pycoingecko | 3.2.0 | 2024-11-13 | MIT | Usable; raw REST is just as easy. |
| feedparser | 6.0.14 | 2026-07-30 | BSD-2 | RSS ingestion. |

Also useful: `httpx` + `tenacity` (retries), `requests-cache` / `diskcache`, `duckdb` + Parquet for local storage, `pandera` for schema checks on vendor payloads.

---

## 8. Master table: recommended sources

| # | What | Endpoint | History | Cost | Limits | Licence (personal use) | Reliability |
|---|---|---|---|---|---|---|---|
| 1 | US rates, Fed balance sheet, TGA, RRP, M2, CPI, broad USD, VIX, Nasdaq | FRED API `api.stlouisfed.org/fred/series/observations` | decades (SP500 10 years; ICE BofA about 3 years) | free key | about 120/min [3P] | public domain or "personal use OK" for copyrighted series; attribution notice | High (official) |
| 2 | Daily TGA | Treasury FiscalData DTS | 2005→ | free | generous | public domain | High [UNVERIFIED from the test box] |
| 3 | JP M2 | BoJ API `stat-search.boj.or.jp/api/v1` | 2003→ (new series) | free, no key | n/a | BoJ terms | High (new in 2026) |
| 4 | EZ M2 | ECB Data Portal `data-api.ecb.europa.eu` | 1980→ | free | n/a | ECB reuse policy (attribution) | High [UNVERIFIED from the test box] |
| 5 | Other M2, misc. macro | DBnomics `api.db.nomics.world/v22` | varies | free | n/a | per provider | Medium (check freshness: ISM stale since 2025-12) |
| 6 | FOMC / CPI calendar | federalreserve.gov FOMC page; BLS `bls.ics` | through 2027 | free | — | public | High |
| 7 | Index and DXY cross-check | yfinance / Yahoo v8 chart | 1927→ (^GSPC) | free | unofficial throttling | Yahoo terms: personal only | Medium-low |
| 8 | BTC daily 2010→ and core on-chain | CoinMetrics Community API | 2010-07-18→ | free | 10 req / 6 s per IP | CC BY-NC 4.0 | High |
| 9 | SOPR, supply in profit, etc. | BGeometrics `bitcoin-data.com/v1` | free: 4 years, T-7 days | free / paid | free: 10/hour, 15/day | no redistribution | Medium-high |
| 10 | Hash rate, difficulty, fees | mempool.space API | full | free | 429 on abuse | open | High (self-hostable) |
| 11 | Spot and perp OHLCV, funding, OI | data.binance.vision + Binance, Bybit, OKX REST via ccxt | 2017→ (spot), 2020→ (perps, metrics) | free | weight-based | exchange terms | High |
| 12 | Dominance, TOTAL history | CoinMarketCap `/v1/global-metrics/quotes/historical` | free: 1 year; $79 Startup: 2013→ | free / $79 | 50–600/min | commercial OK, no redistribution | High |
| 13 | Dominance and global snapshot | CoinGecko `/global` (Demo key) | current | free | 10k/month, 100/min | attribution | High |
| 14 | ALT/BTC | Binance `*BTC` klines; CoinGecko `vs_currency=btc` | 2017→ / 365 days | free | — | — | High |
| 15 | Stablecoin supply | DefiLlama `stablecoins.llama.fi` | 2017-11→ | free | informal | open | High |
| 16 | Fear & Greed | alternative.me `/fng/?limit=0` | 2018-02→ | free | — | attribution | Medium (single methodology owner) |
| 17 | Aggregated OI, liquidations, ETF flows | CoinGlass API | daily all-time | $29/mo | 30/min | personal only (Hobbyist) | High (paid) |
| 18 | ETF flows (free) | Farside / bitbo HTML | 2024-01→ | free | Cloudflare (Farside) | site terms; no scraping | Low (fragile) |
| 19 | TVL, yields, hacks | DefiLlama `api.llama.fi`, `yields.llama.fi` | 2017→ | free | informal | open | High |
| 20 | L2 risk and stage | L2Beat `l2beat.com/api/scaling/summary` | current (+ chart) | free | — | open source project | Medium (undocumented) |
| 21 | News and regulators | RSS (CoinDesk, The Block, Decrypt, Cointelegraph, SEC, Fed, CFTC, ESMA, rekt.news) | rolling | free | polite polling | publisher terms (headline use) | High for regulators; Medium for media |

### Not recommended or dropped
- **CryptoCompare / CoinDesk Data:** keyless access now returns 401; free tier retired ([3P] 2026-05-21).
- **CryptoPanic:** no free tier; only growth, growth_weekly and enterprise plans exist.
- **Glassnode:** no free plan on the pricing page; API only as a Professional add-on (≥$584/mo).
- **Stooq:** JavaScript proof-of-work wall.
- **Keyless FRED CSV:** blocked from the test box.
- **DBnomics ISM:** stale.
- **Kaiko / Tardis:** priced for institutions; overkill for daily or weekly decisions.

---

## 9. Source URLs (accessed 2026-10-29)

- FRED API docs: https://fred.stlouisfed.org/docs/api/fred/ · Terms: https://fred.stlouisfed.org/docs/api/terms_of_use.html
- FRED series pages (checked 2026-10-29): https://fred.stlouisfed.org/series/SP500 · /NASDAQCOM · /VIXCLS · /DTWEXBGS · /WTREGEN · /RRPONTSYD
- FRED rate-limit consensus [3P]: https://apis.io/rate-limits/fred/fred-rate-limits/
- ICE BofA 3-year limit on FRED: https://alfred.stlouisfed.org/series?seid=BAMLC4A0C710YEY ; S&P 10-year: https://fred.stlouisfed.org/series/SP500
- BoJ API launch notice: https://www.boj.or.jp/en/statistics/outline/notice_2026/not260218a.htm
- FOMC calendar: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm · BLS ICS: https://www.bls.gov/schedule/news_release/bls.ics
- DBnomics: https://db.nomics.world/ (API `https://api.db.nomics.world/v22/`)
- CoinGecko pricing: https://www.coingecko.com/en/api/pricing
- CoinMarketCap API pricing: https://coinmarketcap.com/api/pricing/
- CoinGlass pricing: https://www.coinglass.com/pricing
- Binance public data: https://data.binance.vision/ · https://github.com/binance/binance-public-data
- Bybit public data: https://public.bybit.com/
- CoinDesk Data free-tier retirement [3P]: https://coinmarketcap.com/api/resources/coindesk-api-alternatives-7-crypto-data-feeds-compared-in-2026 , https://coingecko.com/learn/coindesk-api-alternatives
- Tardis.dev: https://tardis.dev/ · free first day of the month: https://docs.tardis.dev/api/http-api-reference
- CoinMetrics Community docs: https://gitbook-docs.coinmetrics.io/access-our-data (CC BY-NC 4.0; 10 req / 6 s)
- BGeometrics pricing: https://bitcoin-data.com/bguser/pricing
- Glassnode pricing: https://studio.glassnode.com/pricing · API docs: https://docs.glassnode.com/basic-api/api
- CryptoQuant API credits: https://docs.cryptoquant.com/guides/api-credits
- Look Into Bitcoin (formerly BM Pro) API: https://www.lookintobitcoin.com/api/
- mempool.space API: https://mempool.space/docs/api/rest
- DefiLlama API docs: https://api-docs.defillama.com/ (free list: https://api-docs.defillama.com/llms-free.txt) · Pro: https://defillama.com/pro-api
- L2Beat: https://l2beat.com/api/scaling/summary · https://api.l2beat.com/docs/
- alternative.me Fear & Greed: https://alternative.me/crypto/fear-and-greed-index/
- Farside: https://farside.co.uk/btc/ · bitbo: https://bitbo.io/treasuries/etf-flows
- rekt.news RSS: https://rekt.news/rss/feed.xml · Solodit: https://solodit.cyfrin.io/
- SEC EDGAR fair access: https://www.sec.gov/os/accessing-edgar-data
- yfinance rate-limit reports [3P]: https://github.com/ranaroussi/yfinance/issues/2422
- PyPI JSON (versions): https://pypi.org/pypi/{package}/json
