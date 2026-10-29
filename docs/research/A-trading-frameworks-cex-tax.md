# Research A: trading frameworks, centralized exchanges and Polish crypto tax

*Prepared 2026-10-29 for the design of a low-frequency, BTC-benchmarked autonomous crypto agent (LLM proposes, deterministic Python policy engine approves; staged backtest -> paper -> tiny live; Polish tax resident; Ubuntu 24/7).*

**How things were verified.** Repository facts (stars, open issues, licence, last push, last commit, last release) come from the GitHub REST API (`gh api repos/...`), and PyPI release dates from `pypi.org/pypi/<pkg>/json`, all queried on **2026-10-29**. The MiCA status of every exchange was checked against the **ESMA interim MiCA register of CASPs** (`CASPS.csv`, downloaded 2026-10-29, 387 entries), including whether the authorisation is passported to Poland. Tax rules come from the Ministry of Finance (podatki.gov.pl), the official *Broszura do PIT-38 za 2025 r.*, and published KIS interpretations. Where only secondary sources (law-firm blogs, news) were available, the text says so. "Not verified" means exactly that.

---

## 0. Executive summary

| Area | Recommendation | One-line reason |
|---|---|---|
| Exchange I/O | **Reuse `ccxt` fully** (MIT) | Released daily (v4.5.91 on 2026-10-29), unified spot plus stop-loss and trigger params, and WebSocket ("Pro") is now free. It covers every candidate exchange. |
| Backtest | **Build a small custom BTC-numeraire simulator**, optionally on **vectorbt OSS** (v1.2.0, 2026-10-19) | No mainstream framework except LEAN treats BTC as the account currency natively. Pricing every asset in BTC turns any single-currency engine into a BTC-numeraire one. |
| Paper/live engine | **Build a thin custom engine** (state machine + ledger + ccxt). Keep **NautilusTrader** as a "graduate to" option once 2.0 is stable. | The agent makes only a few decisions a month, so a framework's strategy-class loop adds friction for an external LLM decision maker. Nautilus is the only framework with stable OKX/Kraken/Bybit/Coinbase adapters, multi-currency accounts and a sandbox (paper) mode, but it is in a 2.0 release-candidate cycle. |
| Avoid | backtrader (dead since 2023), Hummingbot (market-making centric), OctoBot (opinionated GPL bot), freqtrade as the core (single stake currency, so it cannot hold "BTC or stablecoin" with BTC accounting) | See section 1. |
| Exchange | **OKX Europe (MFSA Malta, ccxt `myokx`)** as primary; **Kraken (Payward Europe, CBI Ireland)** as secondary | OKX: MiCA, passported to PL; lowest fees (0.10/0.20, ~0 on stablecoin pairs); OCO/trailing/trigger; the only official EEA demo env; PLN+BLIK. Kraken: 31 BTC-quoted pairs for alt/BTC rotations, granular keys. Exclude Binance (withdraw-only in PL since 1.07.2026, API trading revoked) and Bitget (no MiCA). |
| Stablecoin | Plan around **USDC (or EURC)**, not USDT | Tether has no MiCA authorisation, and USDT is no longer tradable on MiCA-licensed EEA venues after 1 July 2026. The "100 USDT" starting capital has to be converted. |
| Tax | Crypto-to-crypto (incl. BTC <-> USDT/USDC) is **tax-neutral** under PIT. Only fiat/goods/services disposals are taxed (19%, PIT-38). Costs are pooled (no FIFO) and carried forward. The NBP mid rate from the day before (D-1) applies. **USDC (an EMT) carries residual classification risk.** Treatment of staking/Earn rewards is unsettled. | See section 3. The tax log design is in section 3.8. |

---

## 1. Trading bot, backtesting and execution frameworks

### 1.1 Live maintenance snapshot (GitHub API, verified 2026-10-29)

| Project | Stars | Open issues | Licence | Last commit | Last release | Python? | Status |
|---|---|---|---|---|---|---|---|
| [freqtrade/freqtrade](https://github.com/freqtrade/freqtrade) | 56,137 | 26 | GPL-3.0 | 2026-10-29 | 2026.9 (2026-09-29) | Yes | Very active, monthly releases |
| [hummingbot/hummingbot](https://github.com/hummingbot/hummingbot) | 20,792 | 184 | Apache-2.0 | 2026-09-22 (master), pushed 2026-10-20 | v2.17.0 (2026-09-22); PyPI 20260922 (2026-10-07) | Yes (+Cython) | Active, monthly |
| [jesse-ai/jesse](https://github.com/jesse-ai/jesse) | 8,738 | 13 | MIT (core) | 2026-10-29 | tag v3.5.3; PyPI 3.5.3 (2026-10-26) | Yes (Rust indicators) | Active. Live-trading plugin is a paid add-on |
| [nautechsystems/nautilus_trader](https://github.com/nautechsystems/nautilus_trader) | 31,034 | 155 | LGPL-3.0 | 2026-10-29 | stable v1.231.0 (2026-08-02); **v2.0.0rc8 (2026-10-29)** | Python API on Rust core | Very active. Major 2.0 transition in progress |
| [polakowo/vectorbt](https://github.com/polakowo/vectorbt) (OSS) | 9,585 | 128 | Apache-2.0 **+ Commons Clause** | 2026-10-28 | v1.2.0 (2026-10-19) | Yes | Active again (2026 releases) |
| vectorbt PRO ([vectorbt.pro](https://vectorbt.pro/)) | private | – | Proprietary, all rights reserved | – | v2026.10.5 shown on site | Yes + Rust crate | Active. Paid membership: from $25/mo, $240/yr, $500 lifetime |
| [kernc/backtesting.py](https://github.com/kernc/backtesting.py) | 9,160 | 103 | AGPL-3.0 | 2026-08-05 | tag 0.6.6; PyPI 0.6.6 (2026-07-22) | Yes | Maintained, slow cadence |
| [mementum/backtrader](https://github.com/mementum/backtrader) | 23,617 | 64 | GPL-3.0 | **2023-04-19** | 1.9.78.123 (2023-04-19) | Yes | **Unmaintained** |
| [QuantConnect/Lean](https://github.com/QuantConnect/Lean) | 22,295 | 281 | Apache-2.0 | 2026-10-29 | GitHub "release" stale (2017). Shipped via LEAN CLI/Docker | C# engine, Python algos | Very active |
| [Drakkar-Software/OctoBot](https://github.com/Drakkar-Software/OctoBot) | 6,873 | 192 | GPL-3.0 | 2026-10-07 | 3.0.0-beta3 (2026-10-08); PyPI 2.1.1 (2026-03-29) | Yes | Active, 3.0 in beta ("node mode") |
| [ccxt/ccxt](https://github.com/ccxt/ccxt) | 44,620 | 716 | MIT | 2026-10-29 | v4.5.91 (2026-10-29) | Yes (also JS/TS/PHP/C#/Go) | Extremely active, near-daily releases |

**Newer / LLM-oriented contenders (verified 2026-10-29):**

| Project | Stars | Licence | Last push | What it is |
|---|---|---|---|---|
| [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) | 118,223 | Apache-2.0 | 2026-10-27 | Multi-agent LLM *analysis/decision* framework (analyst, researcher, trader and risk roles). Equity-oriented, with no execution layer. Useful for prompt and role design, not for execution. |
| [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) | 64,349 | MIT | 2026-10-27 | Educational multi-agent "hedge fund". No production execution. |
| [hummingbot/condor](https://github.com/hummingbot/condor) | 246 | MIT | 2026-10-29 | "Open source harness for trading agents" (announced 2026-04-21) that connects LLMs to Hummingbot API across 50+ venues. Young. |
| [hummingbot/hummingbot-api](https://github.com/hummingbot/hummingbot-api) | 152 | MIT | 2026-10-20 | FastAPI backend to orchestrate Hummingbot bots (what Condor drives). |
| [NoFxAiOS/nofx](https://github.com/NoFxAiOS/nofx) | 13,168 | AGPL-3.0 | 2026-10-21 | "AI trading terminal". 515 open issues. Perps-heavy. |
| [Lumiwealth/lumibot](https://github.com/Lumiwealth/lumibot) | 2,184 | GPL-3.0 | 2026-10-29 | Python backtest/paper/live framework with "AI agents that place the trade". Crypto via ccxt. PyPI 4.6.32 (2026-10-28). |
| [nkaz001/hftbacktest](https://github.com/nkaz001/hftbacktest) | 5,022 | MIT | 2025-12-23 | HFT/market-making. Irrelevant for daily/weekly. |
| [pmorissette/bt](https://github.com/pmorissette/bt) | 3,012 | MIT | 2026-10-25 | Portfolio-level (allocation/rebalancing) backtester. Conceptually a good fit for "weights across BTC/stable/alts". |

Also relevant: Jesse ships an **MCP server** for AI-assisted strategy development (its README), and vectorbt PRO advertises an MCP server, CLI and agent tooling. Both target *development-time* assistance, not runtime decision making.

### 1.2 Capability comparison for this use case

Legend: ✅ native / good · ◐ possible with work / partial · ❌ not supported / poor fit.

| | BTC (non-USD) numeraire accounting | Fee & slippage model | Paper trading | Exchange-native stop-loss | Drivable by external LLM | Daily/weekly MTF |
|---|---|---|---|---|---|---|
| **freqtrade** | ◐ `stake_currency` can be BTC (trade XXX/BTC pairs), but it is a *single* stake currency and spot is long-only. "Rotate BTC -> stablecoin" cannot be expressed while accounting in BTC (it would need a USDC/BTC base/quote pair, which venues do not list). | ✅ exchange fees. Slippage is not modelled in backtest (fills at candle open/limit). | ✅ `dry_run` | ✅ `stoploss_on_exchange`: OKX, Kraken, Bitget (market+limit), Binance (limit). **Bybit spot not supported.** ([docs](https://www.freqtrade.io/en/stable/stoploss/)) | ◐ REST API `/forceenter`, `/forceexit`, `/pause` (requires `force_entry_enable`) ([docs](https://www.freqtrade.io/en/stable/rest-api/)). Workable but fights the strategy-centric design. | ✅ informative pairs/timeframes |
| **Hummingbot** | ❌ quote-asset per connector. No portfolio numeraire. | ◐ | ✅ paper connectors | ◐ via V2 executors (bot-managed rather than resting exchange stops on many connectors) | ◐ Hummingbot API + Condor are designed for LLM control (2026) | ❌ geared to market making/HF. Backtesting via quants-lab (last push 2025-11). |
| **Jesse** | ❌ USD(T)-centric | ✅ fees. Slippage limited. | ✅ (live plugin) | ◐ via plugin | ❌ strategy-class centric | ✅ multi-timeframe |
| **NautilusTrader** | ✅ multi-currency `CASH` accounts. Venue `base_currency` can be set (or left None for multi-currency). Exact `Money` types. | ✅ pluggable fee, fill and latency models (Python-subclassable in 2.0 rc) | ✅ **sandbox** execution clients on live data | ✅ STOP_MARKET/STOP_LIMIT etc. routed natively where supported. OKX, Bybit, Kraken, Coinbase, Binance adapters all "Stable" ([integrations](https://nautilustrader.io/docs/latest/integrations/)). Bitget not listed. | ◐ An Actor/Strategy can consume external messages (2.0 adds native external MessageBus requests). More plumbing. | ✅ any bar type |
| **vectorbt (OSS)** | ◐ single cash currency, but prices can be expressed in BTC (see 1.3) | ✅ fees, fixed fees, slippage per order | ❌ | ❌ | ✅ the simplest kind: feed it an order/weight array produced by the LLM/policy | ✅ resampling |
| **vectorbt PRO** | ◐ same, plus richer simulation | ✅ | ❌ (research) | ❌ | ✅ | ✅ |
| **backtesting.py** | ◐ single instrument. Works for BTC<->USDC using BTC-denominated price. | ✅ commission, spread | ❌ | ❌ | ◐ | ◐ manual resample |
| **backtrader** | ◐ | ✅ | ◐ (stale broker integrations) | ❌ | ◐ | ✅ | 
| **LEAN** | ✅ **`SetAccountCurrency("BTC")`** is first-class ([docs](https://www.quantconnect.com/docs/v2/writing-algorithms/initialization)), with automatic conversion feeds via the CashBook. Edge cases reported for custom brokerages ([forum](https://www.quantconnect.com/forum/discussion/19044/problem-with-btcusdt-conversion-with-custom-unsupported-brokerage/)). | ✅ brokerage fee models (Kraken, Coinbase, Bybit, Binance), slippage models | ✅ paper brokerage | ✅ stop market/limit/trailing per brokerage model | ◐ heavy (C# engine, Docker, LEAN CLI) | ✅ |
| **OctoBot** | ❌ reference market is configurable (can be BTC) but the bot is opinionated | ◐ | ✅ simulator | ◐ | ◐ has a ChatGPT/Ollama trading mode, but you cannot plug a custom policy engine in front of it cleanly | ◐ |
| **ccxt** | n/a (I/O library) | n/a | ◐ via exchange sandbox/demo where the venue offers one (`set_sandbox_mode`) | ✅ unified `stopLossPrice`/`triggerPrice`/`takeProfitPrice` params, `has['createStopLossOrder']`, trailing where the venue supports it | ✅ just a library | ✅ `fetch_ohlcv('1d'/'1w')` |
| **bt** | ◐ (BTC-denominated prices) | ✅ commissions | ❌ | ❌ | ✅ weights in, results out | ✅ |

ccxt facts: CCXT Pro (WebSocket) is "a free part of CCXT" ([pro manual](https://docs.ccxt.com/docs/pro-manual)). OKX, Bybit, Bitget and Binance are **"CCXT Certified"** in the README. Kraken and Coinbase are supported (with Pro/WebSocket) but not certified (README read 2026-10-29).

### 1.3 Key design insight: the BTC numeraire

The benchmark is "hold BTC", so performance should be measured as **portfolio value in BTC**. The only framework found that does this natively is LEAN (`SetAccountCurrency("BTC")`). Nautilus supports it through multi-currency accounts.

A cheap, robust trick works in *any* single-currency engine (vectorbt, bt, backtesting.py or a custom loop): **express every asset's price in BTC** and treat BTC as cash.
- A stablecoin position has BTC price `1 / BTCUSD`.
- An altcoin has its `ALT/BTC` price (native pair, or a synthetic `ALTUSD / BTCUSD`).
- Fees apply as a percentage of BTC notional. For a two-leg route (ALT -> USDC -> BTC), charge both legs.
- The equity curve is then directly "BTC multiple vs HODL" (HODL = flat line at 1.0).

**Caveat on backtesting an LLM:** LLM proposals cannot be honestly backtested over periods inside the model's training data (look-ahead/knowledge leakage). Backtest the *deterministic signals and policy-engine rules*. Evaluate the LLM layer in forward paper trading, or with point-in-time replay using a model whose training cutoff predates the test window.

### 1.4 Reuse vs build recommendation

- **Reuse fully: `ccxt`** (sync or asyncio) for market data (`fetch_ohlcv` daily/weekly), balances, orders, native stop orders, Earn endpoints where unified (otherwise `privateGet/Post*` raw endpoints). Pin the version, since it ships almost daily. MIT licence.
- **Reuse for research: `vectorbt` OSS** (Apache-2.0 + Commons Clause, which is fine for personal non-commercial use) or `bt` for portfolio-weight backtests in BTC terms. vectorbt PRO (from $25/mo) is optional and not needed at this frequency.
- **Build:**
  - a small **event-driven daily/weekly simulator and ledger** in BTC numeraire. This becomes the paper broker *and* the reconciliation ledger. With a handful of trades per month this is a few hundred lines, and one code path serves backtest, paper and live.
  - the **policy engine** (planned).
  - an **order manager** (idempotent client order IDs, place native stop after entry fill, reconcile on restart).
  - a **tax ledger** (section 3.8).
- **Keep as an upgrade path: NautilusTrader**, if the agent later needs intraday precision, many instruments, or a single production-grade engine across backtest, sandbox and live. Wait for **2.0 final**: as of 2026-10-29 it is at rc8, so expect API churn. LGPL-3.0 is fine.
- **freqtrade** is worth it only if you accept USDC as the accounting currency and compute BTC-relative performance outside the bot. Its dry-run, freqUI and `stoploss_on_exchange` are excellent, but the single-stake-currency model clashes with "BTC or stables" rotation.
- **Do not use:** backtrader (no commits since 2023-04), Hummingbot (market-making/HF focus; Condor is 6 months old), OctoBot (opinionated; 3.0 beta), Jesse (live trading is a paid plugin and USD-centric).
- **Borrow ideas, not code:** TradingAgents (role decomposition: analyst/bull-bear debate/risk manager) for the LLM proposer prompt architecture.

---

## 2. Centralized exchanges for a Polish resident (late 2026)

### 2.1 Regulatory baseline (verified 2026-10-29)
- **MiCA transitional period ended 1 July 2026.** Since then only CASPs authorised under MiCA (in any EU state, passported) may serve Polish residents. Poland has **no** MiCA implementing act (presidential vetoes, the third on 11 June 2026) and no national competent authority designated. That does not affect passported foreign licences. ([UKNF stance PDF](https://www.knf.gov.pl/knf/pl/komponenty/img/Stanowisko_UKNF_nadzor_nad_kryptoaktywami_97115.pdf); [SII](https://www.sii.org.pl/18828/analizy/newsroom/wojna-o-ustawe-o-rynku-kryptoaktywow-trwa-prezydent-wetuje-minister-krytykuje-a-sadny-1-lipca-coraz-blizej.html))
- **ESMA interim MiCA CASP register** (`https://www.esma.europa.eu/sites/default/files/2024-12/CASPS.csv`, downloaded 2026-10-29), with "PL" checked in the passport column:

| Brand | Authorised entity | Home NCA | Authorised | Passported to PL |
|---|---|---|---|---|
| OKX | OKX Europe Limited | MFSA (MT) | 2025-01-27 | ✅ |
| Bybit | Bybit EU GmbH | FMA (AT) | 2025-05-28 | ✅ |
| Kraken | Payward Europe Solutions Ltd | CBI (IE) | 2025-06-25 | ✅ |
| Coinbase | Coinbase Luxembourg S.A. | CSSF (LU) | 2025-06-20 | ✅ |
| Bitstamp | Bitstamp Europe S.A. | CSSF (LU) | 2025-05-15 | ✅ |
| Bitvavo | Bitvavo B.V. | AFM (NL) | 2025-06-26 | ✅ |
| Crypto.com | Foris DAX MT Ltd | MFSA (MT) | 2025-01-27 | ✅ |
| Gemini | Gemini Intergalactic EU Ltd | MFSA (MT) | 2025-08-21 | ✅ |
| Gate | Gate Technology Ltd | MFSA (MT) | 2025-09-29 | ✅ |
| KuCoin | KuCoin EU Exchange GmbH | FMA (AT) | 2025-11-27 | ✅ |
| Revolut | Revolut Digital Assets (Europe) Ltd | CySEC (CY) | 2025-10-20 | ✅ |
| Kanga | SIA AlphaRoute | Latvijas Banka (LV) | 2026-06-18 | ✅ |
| **Binance** | – | – | **not in register** | ❌ |
| **Bitget** | – (Bitget EU applied to FMA, confirmed 2026-07-02) | – | **not in register** | ❌ |

- **Binance (Poland): effectively withdraw-only since 1 July 2026.** No new spot orders, open orders cancelled, bots disabled, Earn/staking closed, **API permissions for new spot/margin orders revoked**. Conversions are allowed only into PLN/EUR/USDC, and withdrawals still work ([Parkiet, 26.06.2026, updated 29.10.2026](https://www.parkiet.com/kryptowaluty/art44706221-binance-polska-mica-ograniczone-uslugi)). The Greek MiCA application was withdrawn 24.06.2026, with no new authorisation as of 26.10.2026 ([casptracker](https://casptracker.eu/exchange/binance/)). **Exclude.**
- **Bitget:** not authorised. The FMA application is pending ([Bitget notice 2.07.2026](https://www.bitget.com/support/articles/12560603885949)), and spot access for PL users after 1 July is unclear. **Exclude** until it appears in the ESMA register.
- **Zondacrypto (ex-BitBay):** the Estonian licence was revoked 29.06.2026 and the company was declared bankrupt (reported 27.08.2026) ([Kancelaria Skarbiec](https://kancelaria-skarbiec.pl/en/bb-trade-estonia-zondacrypto-insolvency/)). **Do not use.**
- **USDT is not tradable on MiCA-licensed EEA venues.** Tether never sought EMT authorisation. Kraken went sell-only for EEA users on 24.03.2025, Coinbase delisted it for the EEA in Dec 2024, OKX Europe offers USDC/USDG instead ([OKX guide](https://www.okx.com/en-us/learn/usdt-not-tradeable-okx-europe-stablecoin-guide)), and Bybit EU lists no USDT pairs (live API). **Design the agent around USDC (and/or EURC/EUR).** Holding USDT in self-custody stays legal.

### 2.2 Comparison (EEA entity as seen by a Polish retail user; checked 2026-10-29)

| | **OKX Europe** (my.okx.com / eea.okx.com) | **Kraken** (Payward Europe) | **Bybit EU** (bybit.eu) | **Coinbase Advanced** (Coinbase Lux.) | Bitvavo / Bitstamp (alternatives) |
|---|---|---|---|---|---|
| **API** | V5 REST `https://eea.okx.com`, WS `wss://wseea.okx.com`. ccxt id **`myokx`** (ccxt Pro, certified family) ([docs](https://my.okx.com/docs-v5/en/), [ccxt myokx.ts](https://raw.githubusercontent.com/ccxt/ccxt/master/ts/src/myokx.ts)) | REST + WS v2 + FIX. ccxt id `kraken` ([docs](https://docs.kraken.com/api/docs/rest-api/add-order)) | V5 REST/WS `https://api.bybit.eu`. **Retail API trading only since 2 Sep 2026** ([announcement](https://announcements.bybit.eu/en-EU/article/api-trading-power-your-tools-and-ai-with-deep-liquidity-and-low-latency--art639fafc104c9/)). ccxt id **`bybiteu`** | Advanced Trade REST + WS (CDP keys). ccxt id `coinbase` (`coinbaseadvanced` removed) | Bitvavo: good REST/WS, ccxt `bitvavo`. Bitstamp: REST/WS, ccxt `bitstamp` |
| **Key permissions** | Read / Trade / Withdraw. Up to 20 IPs. A Trade key **without an IP binding expires after 14 days of inactivity**. EEA API withdrawals to private wallets are blocked anyway (Travel Rule). | Very granular (funds query/deposit/withdraw split, order query/modify/cancel, ledger/export, WS). IP whitelist. **Key expiry setting.** ([support](https://support.kraken.com/hc/en-us/articles/360000919966-How-to-create-an-API-key)) | Read-only / Read-Write. **No withdraw permission exists** for API. Up to 100 IPs. A key without IP expires after 90 days. Symbol whitelist. ([guide](https://www.bybit.eu/en-EU/learn/bybit-guide/what-is-api-trading-and-how-to-set-it-up-on-bybit-eu)) | Scopes view / trade / transfer (omit transfer = no withdrawals). IP allowlist (secondary). Key tied to one portfolio. | Bitvavo/Bitstamp: trade-only keys + IP whitelist (not individually re-verified) |
| **Subaccounts** | ✅ up to 5 (standard). Subaccounts cannot withdraw. ([FAQ](https://www.okx.com/en-eu/help/subaccounts-account-mode-and-api-connections-faq)) | ✅ via API `CreateSubaccount`, framed for "institutional/pro". Retail eligibility **unverified**. | ✅ (count unverified) | ✅ "Portfolios" (retail), one key per portfolio | – |
| **Native spot conditional orders** | ✅ trigger, **OCO**, TP/SL, **trailing** (`move_order_stop`), TWAP via `order-algo`. Trailing-on-spot not explicitly confirmed. | ✅ stop-loss, stop-loss-limit, take-profit(-limit), **trailing-stop(-limit)**, conditional close attached to entry. **No OCO.** | ✅ TP/SL & stop orders on spot (`orderFilter`). OCO/trailing not documented for spot. | ✅ stop-limit, **trigger_bracket** (TP+SL, OCO-like). **No trailing, no stop-market.** | Bitvavo: stopLoss/stopLossLimit/takeProfit on spot ✅. Bitstamp: stops **derivatives-only** ❌ |
| **BTC-quoted pairs** | Global list: only **ETH-BTC, SOL-BTC, OKB-BTC** (live API). EEA tradability **unverified** (needs authenticated `account/instruments`). | **31 BTC-quoted pairs** (live API: ETH, SOL, ADA, DOT, LINK, LTC, XRP, AAVE, UNI, ATOM, …). Some may be geo-restricted. | **None** (live API: 128 pairs = 107 USDC, 17 EUR, 4 PLN) | **19 BTC-quoted pairs** (live API) | Bitvavo: none (EUR + 11 USDC). Bitstamp: 3 (ETH, LTC, XRP) |
| **Stablecoins / fiat pairs** | USDC, USDG, EURC. **BTC-PLN, ETH-PLN, USDC-PLN**, EUR pairs | USDC (XBT/USDC, USDC/EUR), EUR | USDC, EURC, **BTCPLN, ETHPLN, SOLPLN, USDCPLN**, EUR pairs | USDC, EUR pairs (BTC-USDC, USDC-EUR) | EUR, USDC |
| **Earn: BTC** | Flexible lending rate ~0.5% (public endpoint, may be global). OKX EEA guide says BTC Earn is **VIP-only** ([guide](https://www.okx.com/en-eu/learn/crypto-earn)) | Flexible **0.1%**, bonded 30-day **0.15%** (PL page). BTC Vaults "up to 2.5%" (secondary, unverified for EEA). ([PL page](https://www.kraken.com/en-pl/features/auto-earn/bitcoin)) | Flexible Savings **1.2%** (max 1 BTC), no lock (live `v5/earn/product`) | None | Bitvavo/Bitstamp lending exists. Rates/PL eligibility unverified. Bitvavo states staking/lending are **not MiCA-regulated**. |
| **Earn: USDC** | Flexible ~1%–3.5% (guide range; public rate ~3.5%) | **Not available in EEA** (Opt-in rewards excluded) ([USDC page](https://www.kraken.com/en-pl/features/auto-earn/usdc)) | Flexible **1.02%** (live) | **Ended for EEA 1 Dec 2024** ([Decrypt](https://decrypt.co/294033/coinbase-ends-usdc-rewards-in-europe-as-mica-deadline-looms)) | as above |
| **Spot fees (entry tier)** | **0.10% maker / 0.20% taker**. Stablecoin pairs **0.00% / 0.05%** (from 25.09.2026; [notice](https://www.okx.com/en-eu/help/important-notice-upcoming-spot-fee-adjustment-eea), from snippets) | **0.40% / 0.80%** (0.30/0.60 from $2.5k vol.). Stablecoin/FX pairs 0.20%/0.20% ([fees](https://www.kraken.com/features/fee-schedule)) | **0.25% flat** (no maker/taker split, from 5.10.2026) ([fees](https://www.bybit.eu/en-EU/help-center/article/Trading-Fee-Structure)) | ~0.25% / 0.50% after 16.09.2026 restructure (**secondary, unverified**) | Bitvavo 0.15/0.25 (USDC pairs 0.05/0.05). Bitstamp ~0.30/0.40 (secondary) |
| **Fiat on-ramp** | **PLN pairs**, **BLIK via ZEN.COM**, PayPal. EUR SEPA not re-verified. | EUR SEPA/SEPA Instant (free). **No PLN, no BLIK.** ([support](https://support.kraken.com/hc/en-us/articles/360000381846)) | **PLN via BLIK** (≤850 PLN/order, 5k lifetime), Zen, SWIFT. EUR SEPA. PayPal. | **BLIK (PLN) for purchases** since Dec 2025. Holding/withdrawing PLN unverified. | EUR SEPA. No PLN. |
| **Demo / paper** | ✅ **Official EEA demo trading**: REST `eea.okx.com` + header `x-simulated-trading: 1`, WS `wss://wseeapap.okx.com`. ccxt `myokx.set_sandbox_mode(True)`. No earn/withdraw in demo. | Spot UAT **by request only** (account manager). Futures demo is self-service. ([quickstart](https://docs.kraken.com/home/guides/quickstart)) | `api-testnet.bybit.eu` / `api-demo.bybit.eu` respond, but EU account eligibility is **unverified** | Sandbox = **static mocked responses** only | Bitstamp: sandbox exists. Bitvavo: none |
| **freqtrade `stoploss_on_exchange` (spot)** | ✅ | ✅ | ❌ (Bybit spot) | – | – |
| **Nautilus adapter** | Stable (OKX) – EEA host config not verified | Stable | Stable (Bybit) – EU host not verified | Stable | – |

### 2.3 Recommendation

1. **Primary: OKX Europe (my.okx.com / `eea.okx.com`, ccxt `myokx`).**
   - MiCA-authorised and passported to PL.
   - Lowest fees of the set (0.10/0.20, ~0 on stablecoin pairs, which matters for frequent BTC<->USDC rotation).
   - The richest native spot order set (trigger/OCO/TP-SL/trailing).
   - **The only official, self-service EEA demo environment**, which fits the paper-trading stage and lets you test real order flows incl. stop orders.
   - PLN pairs + BLIK, subaccounts, and USDC flexible Earn (~1–3.5%).
   - Weaknesses:
     - very few BTC-quoted pairs (ETH-BTC, SOL-BTC; EEA availability to confirm), so alt/BTC rotations route via USDC (two legs, two fees);
     - BTC Earn in EEA appears VIP-only;
     - API keys without an IP binding lapse after 14 days idle, so **bind the Ubuntu box's static IP**.
2. **Secondary: Kraken (Payward Europe, CBI).**
   - Best for **alt/BTC rotations** (31 native BTC-quoted pairs).
   - Most granular API permissions incl. key expiry, and native trailing stops.
   - Strong security reputation; also gives counterparty diversification.
   - Weaknesses:
     - expensive at low volume (0.40/0.80);
     - no USDC yield in EEA, BTC yield only 0.1–0.15%;
     - EUR only (no PLN);
     - no self-service spot sandbox, so paper trading must use your own simulator on Kraken live data.
- **Runner-up / alternative: Bybit EU.**
  - Good if idle-asset yield matters: BTC 1.2% flexible up to 1 BTC, and a PLN BLIK on-ramp.
  - There is **no API withdraw permission at all** (a nice safety property).
  - Against it: no BTC-quoted pairs, a 0.25% flat fee, and retail API trading only since 2 Sep 2026 (young).
- **Coinbase Advanced** is viable (19 BTC pairs, OCO-like brackets), but EU fees are unverified, there is no USDC yield, and the sandbox is mocked.
- **Bitvavo** has good spot stop orders but no BTC-quoted pairs. **Bitstamp** has no spot stops via API.
- **Earn caveat:** under MiCA, lending/"Earn" is generally **outside MiCA protection**. Kraken's Earn is run by Payward Commercial (not CBI-regulated), and Bitvavo says the same of its lending. Treat yield as unsecured counterparty risk and cap it in the policy engine.
- **Operational note for 100 USDT:** convert to USDC (or EUR) before or after deposit. USDT deposits on MiCA venues may be auto-converted or rejected. Verify each venue's handling before sending.

---

## 3. Polish tax rules for crypto (status 2026)

> Not tax advice. Primary sources are the PIT Act (ustawa o PIT), the MF portal podatki.gov.pl and the official PIT-38 brochure for 2025 (read 2026-10-29). Interpretations (KIS) bind only the applicant. Where commentary differs, both positions are given.

### 3.1 Form, rate and deadline
- Income from **odpłatne zbycie walut wirtualnych** goes on **PIT-38** (section E for 2025: poz. 36 revenue, poz. 37 costs of the year, poz. 38 costs carried from prior years, poz. 39 income, poz. 40 costs to carry forward). It is taxed at a flat **19%** (art. 30b ust. 1a). ([Broszura PIT-38 za 2025](https://www.podatki.gov.pl/media/g5ebnm2e/broszura-do-pit-38-za-2025-r.pdf); [podatki.gov.pl – Zbycie kryptowalut](https://podatki.gov.pl/podatki-osobiste/pit/informacje-podstawowe/co-jest-opodatkowane/zbycie-kryptowalut), both read 2026-10-29)
- Filing window: **15 Feb – 30 Apr** of the following year, so the return for 2026 is due **30 Apr 2027**.
- **You must file even with zero revenue if you had acquisition costs** (e.g., bought crypto with PLN/EUR in 2026), so that the costs are recorded and carried forward. (podatki.gov.pl)
- Crypto income is a separate basket. It cannot be netted against shares/derivatives (section C), and a KIS ruling in early 2026 reportedly confirmed that crypto futures losses (section C) cannot offset spot crypto (section E) ([bithub.pl summary](https://bithub.pl/kryptowaluty/interpretacje-podatkowe-dotyczace-krypto-co-ustalil-fiskus-na-poczatku-2026-roku/), secondary).
- Exchanges have no obligation to issue PIT-8C. You self-compute. (podatki.gov.pl)

### 3.2 What is a taxable event
- Art. 17 ust. 1f: *"przez odpłatne zbycie waluty wirtualnej rozumie się wymianę waluty wirtualnej na prawny środek płatniczy, towar, usługę lub prawo majątkowe inne niż waluta wirtualna lub regulowanie innych zobowiązań walutą wirtualną"* (quoted in the 2025 brochure).
- **Crypto-to-crypto is not taxed:** *"Wymiana pomiędzy walutami wirtualnymi, niezależnie od tego, czy jest dokonywana na giełdzie, czy jednostkowo, nie podlega opodatkowaniu"* (podatki.gov.pl).
- **But fees on crypto-to-crypto swaps are not deductible** (art. 23 ust. 1 pkt 38d; summarised on podatki.gov.pl and in [poradnikprzedsiebiorcy.pl](https://poradnikprzedsiebiorcy.pl/-rozliczanie-kosztow-nabycia-walut-wirtualnych)).

### 3.3 Stablecoins (USDT / USDC): is BTC <-> stablecoin neutral?
- **USDT:** treated as *waluta wirtualna* in the AML-act sense, so BTC <-> USDT is neutral. Commentators broadly agree.
- **USDC / EURC (MiCA e-money tokens):** this is the grey zone. The PIT Act relies on the AML-act definition of *waluta wirtualna* (art. 2 ust. 2 pkt 26 ustawy AML), which **excludes electronic money** within the meaning of the Payment Services Act. MiCA art. 48(2) deems EMTs to be e-money. Read literally, BTC -> USDC could therefore be a disposal for "e-money" (taxable).
  - The Polish MiCA implementing act, which would have clarified the tax definitions, was **vetoed three times** (latest 11 June 2026; override failed in Sept 2026 per secondary sources). So the law is unchanged. ([SII](https://www.sii.org.pl/18828/analizy/newsroom/wojna-o-ustawe-o-rynku-kryptoaktywow-trwa-prezydent-wetuje-minister-krytykuje-a-sadny-1-lipca-coraz-blizej.html); [Kancelaria Macura](https://www.kancelariamacura.pl/aktualnosci/trzecie-weto-wobec-ustawy-o-rynku-kryptoaktywow-zwieksza-ryzyko-dla-ciaglosci-uslug-od-1-lipca-2026-r/); [mddp](https://www.mddp.pl/weto-dla-ustawy-o-rynku-kryptoaktywow-oby-korzystne-zmiany-podatkowe-wrocily-w-nowej-wersji-przepisow/))
  - **Most relevant ruling found:** individual interpretation **DKIS 27.02.2026, sygn. 0114-KDIP2-2.4010.579.2025.2.IN** ([Inforlex full text](https://www.inforlex.pl/dok/tresc,FOB0000000000007535930,Interpretacja-indywidualna-z-dnia-27-lutego-2026-r-Dyrektor-Krajowej-Informacji-Skarbowej-sygn-0114-KDIP2-2.4010.579.2025.2.IN.html), read 2026-10-29). **This is a CIT ruling** (an S.A. applicant), not PIT. KIS accepted that exchanging crypto for stablecoins *including EMTs* is neutral. Its reasoning: MiCA *"nie reguluje kwestii podatkowych"*, the e-money notion is applied "w znaczeniu obowiązującym przed wejściem do stosowania Rozporządzenia MICA", and the assessment of each stablecoin is case-by-case (*"Nie jest więc uzasadnione by a priori dokonywać ogólnej kwalifikacji stablecoinów"*). The CIT and PIT definitions use the same AML-act reference, so it is persuasive for PIT but **not binding** on the owner.
  - **Practical implication:** USDT is the "cleanest" stablecoin for tax but is unavailable on MiCA venues (section 2). USDC is what you can trade. Mitigations:
    - log every stablecoin leg with an `asset_class` flag, so a different classification can be recomputed later;
    - consider an **individual interpretation (interpretacja indywidualna, fee 40 PLN)** covering BTC <-> USDC and Earn on USDC before the size grows to 5,000;
    - EUR-quoted trading (BTC/EUR) is the unambiguous alternative, but every BTC -> EUR is then a taxable disposal.

### 3.4 Cost basis: pooled, not FIFO
- Art. 22 ust. 14: costs are *"udokumentowane wydatki bezpośrednio poniesione na nabycie waluty wirtualnej oraz koszty związane ze zbyciem waluty wirtualnej, w tym udokumentowane wydatki poniesione na rzecz podmiotów, o których mowa w art. 2 ust. 1 pkt 12 ustawy [AML]"* (i.e., exchange fees on fiat legs).
- Costs are recognised **in the year incurred**, not matched to the specific coins sold (art. 22 ust. 15–16). Any excess of costs over revenue carries forward to the next year (poz. 38/40) with no time limit. *"Przy odpłatnym zbyciu kryptowaluty nigdy nie wystąpi strata"* (podatki.gov.pl).
- **No FIFO/LIFO lot tracking is legally needed** for the PIT-38 crypto basket. The annual calculation is (sum of fiat-equivalent proceeds) − (sum of fiat acquisition costs and fees in the year + unused prior costs). Lot tracking is still useful for internal BTC-performance analytics.
- Not deductible: financing costs, mining hardware/energy, crypto-to-crypto swap costs.

### 3.5 Exchange-rate rule (NBP D-1)
- Art. 11a: amounts in foreign currencies (revenue, costs, fees) are converted *"według kursu średniego walut obcych ogłaszanego przez Narodowy Bank Polski z ostatniego dnia roboczego poprzedzającego dzień uzyskania przychodu, poniesienia kosztu"* (2025 brochure, p. 1).
- Use **NBP Table A mid rate**, last business day **before** the transaction date. API: `https://api.nbp.pl/api/exchangerates/rates/a/{eur|usd}/{date}/?format=json` (tested 2026-10-29; e.g., USD mid 2026-10-28 = 3.9624, table 210/A/NBP/2026). Store the **table number** with each conversion.
- USDT/USDC are not currencies in NBP tables. When a crypto is sold for EUR, convert the EUR at EUR D-1. Crypto-to-crypto legs are neutral, so they need no PLN rate (still log a PLN reference value for internal and DAC8 reconciliation).

### 3.6 Staking, lending/Earn interest, airdrops (unsettled)
- **Staking/Earn rewards – two positions:**
  1. **KIS (historically and in some recent rulings):** a reward is revenue **on receipt** at market value. Older practice was "other sources" at the progressive scale (PIT-36). Later rulings treat its value as a cost on later sale. In the **CIT** ruling of 27.02.2026 (above), KIS again held that staking rewards are revenue at receipt.
  2. **WSA Wrocław, I SA/Wr 413/23** and much practitioner commentary: receipt **does not create revenue**. Tax arises only when the reward is disposed of for fiat/goods/services, with **cost = 0** ([Infor, 30.11.2025](https://ksiegowosc.infor.pl/podatki/pit/pit/rozliczenia/7468930,staking-kryptowalut-a-pit-kiedy-naprawde-trzeba-zaplacic-podatek.html)).
  - For **CeFi Earn interest paid in USDC/BTC** (lending-like), no specific 2026 PIT ruling was found. The same split applies. Some commentators treat it as interest/"other sources". **Not verified with a primary source.**
  - Separately, a **VAT** interpretation of 3.03.2026 (0114-KDIP4-3.4012.702.2025.4.IG) treated staking as a VAT-able service, a controversial result aimed at validators ([Inforlex](https://www.inforlex.pl/dok/tresc,FOB0000000000007535970,Interpretacja-indywidualna-z-dnia-3-marca-2026-r-Dyrektor-Krajowej-Informacji-Skarbowej-sygn-0114-KDIP4-3.4012.702.2025.4.IG.html)). It is irrelevant for passive CeFi Earn by a consumer, but it shows the authorities' direction.
  - **Design consequence:** record every reward with its timestamp, quantity and PLN fair value at receipt (D-1 NBP plus a market price source). Either treatment can then be filed. Given the small amounts, an individual interpretation or adviser call is worth it before scaling.
- **Airdrops:** commentary is split between "revenue on receipt (free benefit)" and "neutral until disposal, cost 0" ([Divly](https://divly.com/pl/przewodniki/staking-i-airdropy-podatek), [beatcoin](https://beatcoin.pl/poradniki/airdropy-a-podatek-dochodowy-jak-i-kiedy-rozliczyc-darmowe-tokeny/), both secondary). This is irrelevant if the agent does not pursue airdrops. Log them with the same fields as rewards.

### 3.7 DAC8 (crypto reporting to tax authorities) from 2026
- **EU:** Directive (EU) 2023/2226 (DAC8) applies from **1 Jan 2026**. Reporting crypto-asset service providers report annually per user: identity, tax residence, **TIN (PESEL/NIP for PL)**, and per-asset aggregates of crypto<->fiat, crypto<->crypto and transfers. The data goes to the user's residence state (Poland: KAS) via automatic exchange. First reports cover calendar year 2026 and are due in 2027. National deadlines vary: e.g. Cyprus set 30 June 2027 ([Bloomberg Tax](https://news.bloombergtax.com/daily-tax-report-international/cyprus-tax-agency-announces-entry-into-force-of-dac8-amendment-law)). The exact directive deadline wording (Art. 8ad) could not be retrieved from EUR-Lex (empty fetch) and is **not verified**.
- **Poland:** the implementing act (amendment of *ustawa o wymianie informacji podatkowych z innymi państwami*, DAC8 + DAC9) was **signed by the President on 11 March 2026**. Its reporting covers transactions **from 1 January 2026** ([Infor, 19.03.2026](https://www.infor.pl/twoje-pieniadze/podatki/7538305,koniec-z-ukrywaniem-kryptowalut-przed-skarbowka-prezydent-podpisal-ustawe-ktora-implementuje-dyrektywy-unijne-dac8-i-dac9-wymiana-informacji-podatkowych-miedzy-panstwami-raje-podatkowe.html); [podatki.biz](https://www.podatki.biz/artykuly/ustawa-o-wymianie-informacji-podatkowych-z-innymi-panstwami-z-podpisem-prezydenta-rp_16_61489.htm)). Per commentary on the act, a CASP must **block reportable transactions 60 days after a user fails to provide the self-certification/TIN** ([pit.pl](https://www.pit.pl/aktualnosci/nowe-obowiazki-podatkowe-implementacja-dyrektyw-dac8-i-dac9); [dudkowiak](https://www.dudkowiak.com/blog/dac8-new-tax-obligations-for-casps-from-2026-and-automatic-transaction-blocking-after-60-days/)). The Dz.U. item number and the exact Polish first-report date were **not verified**.
- **Implication:** KAS will receive exchange-level aggregates for 2026 in 2027. The agent's ledger must reconcile with what the exchange reports (same units, same transaction categories). Make sure the self-certification (tax residence + PESEL) is completed on the exchange, or the API account may be blocked.

### 3.8 Records to keep and the tax-log schema
- **Retention:** a tax liability expires 5 years from the end of the year in which the payment deadline fell (Ordynacja podatkowa art. 70 §1). For 2026 trades (deadline 30.04.2027) that means **until 31.12.2032**. Acquisition-cost evidence must be kept **as long as any of those costs are still being carried forward**, plus 5 years. Keep raw exchange exports (CSV/PDF statements), bank statements for fiat legs, and the computed ledger.
- **Minimum fields per ledger row** (one row per fill/fee/reward/transfer):

| Field | Why |
|---|---|
| `event_id` (UUID), `exchange`, `account/subaccount`, `exchange_order_id`, `exchange_trade_id`, `client_order_id` | Uniqueness, audit trail, reconciliation with exchange exports and DAC8 data |
| `ts_utc`, `date_local_warsaw` | The tax date is the local transaction date, which drives D-1 |
| `event_type` ∈ {fiat_buy, fiat_sell, crypto_swap, fee, deposit_fiat, withdraw_fiat, deposit_crypto, withdraw_crypto, internal_transfer, earn_subscribe, earn_redeem, reward_interest, reward_staking, airdrop, other} | Tax classification |
| `base_asset`, `base_qty`, `quote_asset`, `quote_qty`, `price` | Economic substance |
| `fee_asset`, `fee_qty` | Fee deductibility depends on the leg type |
| `fiat_currency` (PLN/EUR/USD/null), `fiat_amount` | Only fiat legs create revenue/cost |
| `nbp_table_no`, `nbp_rate_date` (D-1), `nbp_mid` | Art. 11a evidence |
| `pln_amount` | Converted revenue or cost |
| `tax_treatment` ∈ {revenue_17_1f, cost_22_14, neutral_crypto_crypto, nondeductible_23_1_38d, reward_pending_classification, transfer_nontaxable} | Directly maps to PIT-38 poz. 36/37 |
| `stablecoin_class` ∈ {none, VC_non_EMT (USDT), EMT (USDC/EURC)} | Allows re-computation if EMTs are later treated as e-money |
| `fair_value_pln_at_receipt`, `price_source` | For rewards/airdrops (either tax position) |
| `btc_value_at_event`, `btc_price_source` | Not tax: agent performance vs HODL |
| `source_doc` (export filename + SHA-256), `bank_tx_ref` | Documentation ("udokumentowane wydatki") |
| `tax_year`, `carried_forward_cost_pln` (year-level table) | Poz. 38/40 carry-forward |

- **Year-end job:** sum `pln_amount` for `revenue_17_1f` (poz. 36) and `cost_22_14` (poz. 37), take prior-year poz. 40 as poz. 38, then compute poz. 39/40. Export the computation alongside the raw files.

---

## 4. Could not verify / open items
- The exact DAC8 first-report deadline in Polish law and its Dz.U. citation, and the precise Art. 8ad wording of the directive (the EUR-Lex fetch returned empty).
- A specific 2026 **PIT** (not CIT) ruling on BTC <-> USDC (EMT) neutrality, and any PIT ruling specific to CeFi "Earn" interest.
- The secondary-source claim that the Sejm failed to override the third veto in Sept 2026 and that a fourth government draft was announced in Oct 2026 (single blog source, [radcakowalski.pl](https://radcakowalski.pl/czy-kryptowaluty-sa-legalne-w-polsce-przewodnik-po-regulacjach/)).
- Jesse live-plugin pricing (jesse.trade returned 403).
- OKX EEA: whether ETH-BTC/SOL-BTC are tradable for EEA accounts (the public instrument list is global; needs authenticated `GET /api/v5/account/instruments`), whether trailing stop works on spot, locked Earn products/APYs, and full official fee table (snippets only).
- Bybit EU: whether EU accounts can obtain testnet/demo keys, and the max subaccount count.
- Kraken: whether retail accounts can create subaccounts via API, and BTC Vaults availability in the EEA.
- Coinbase: EU fee tiers after 16.09.2026, PLN balance/withdrawal and BLIK in Advanced, IP allowlist/key expiry (help center returned 403).
- Bitget: whether PL users can still trade spot after 1 July 2026. Binance: any new MiCA filing (France AMF rumours only).
- Kanga: API and PLN rails for PL users after July 2026, despite its Latvian MiCA licence passported to PL.
- Earn APYs are point-in-time (2026-10-29) and float daily.
