# F. Verifiable track records: sources, access, and statistical soundness

**Verification date:** 2026-10-29 (all live API calls made 17:37–18:30 UTC that day unless stated).
**Context:** autonomous low-frequency agent. Goal: grow a crypto portfolio **measured in BTC**. Benchmark: hold BTC.
**Owner's rule:** learn only from verifiable evidence: on-chain account histories, exchange-verified records, or our own backtests.

---

## 0. Bottom line (TL;DR)

1. **Verifiable per-account track records exist and can be pulled for free**, best of all on **Hyperliquid**. Its leaderboard lists 48,527 accounts. Per-account PnL, equity, positions, fills, funding and ledger histories are available by address. **GMX v2**, **dYdX v4** and **Polymarket** are also usable. **Aevo** offers only pseudonymous leaderboard names, with no per-account history. **Drift**'s data API was unreachable on the test date.
2. **Histories are short.** Hyperliquid started in 2023, so the longest records are about 2.8–3 years. dYdX v4 dates from late 2023 and GMX v2 from 2023. None covers a full BTC cycle.
3. **The statistics are brutal.** Assume 40,000 accounts with zero true skill, each with a 2-year daily record. The single best of them would show an annualised Sharpe of about **3.0** from luck alone. With 3-year records it would still be about 2.4. To pass a Bonferroni correction over 40k accounts, a true Sharpe of 1 needs about **22 years** of daily data. A Sharpe of 3 needs about 2.5 years. Only accounts with very high Sharpe ratios can be told apart from luck. Those are mostly market makers, HFTs and funding/basis arbitrageurs. Their edge comes from speed and inventory management, so it does not transfer to a low-frequency BTC-timing agent.
4. **Persistence evidence is mixed and mostly short-horizon or non-transferable.** Our own Hyperliquid spot-check (205 accounts) found weak persistence: rank correlation 0.14, p ≈ 0.03. Heavy attrition too: 35% of the prior top decile stopped trading.
   - In Polymarket, skill persists (Gómez-Cram et al. 2026: 44% of "skilled" accounts stay skilled out of sample).
   - Hyperliquid wallets' order flow predicts returns at a **1-second** horizon (Zhai 2026).
   - Day-trader skill is extremely rare (Barber et al. 2014: under 1% predictably profitable net of fees).
   - Social and copy trading tends to underperform and raises risk-taking (Dorfleitner et al. 2018; Apesteguia et al. 2020).
   - No credible paper we found shows that **copying top on-chain BTC traders at low frequency beats holding BTC after costs**.
5. **Aggregate BTC on-chain cohort metrics** split into two groups. Realized cap, MVRV, coin-age supply bands and SOPR are reproducible from a node. Exchange and miner flows depend on opaque, revisable address labels. Because of revision, the free (non-point-in-time) CoinMetrics flow series carry a look-ahead risk. Their predictive evidence also rests on about 4 BTC cycles, so the sample size is tiny.
6. **Recommendation:** do **not** make "follow the verified top traders" a core strategy. If we try it, run it as a cheap, **pre-registered, forward-collected** experiment (section 5). Treat the "skilled cohort net BTC positioning" signal as guilty until proven innocent, and accept it only on a deflated-Sharpe / White-Reality-Check basis against hold-BTC. Default posture: hold BTC, and let any signal only *tilt* exposure.

---

## 1. Fully on-chain venues with public per-account history

### 1.1 Hyperliquid (best source, tested live)

Base: `POST https://api.hyperliquid.xyz/info` (JSON body, no auth). Stats CDN: `https://stats-data.hyperliquid.xyz/Mainnet/...`.

| Endpoint (tested 2026-10-29) | What it returned | Notes |
|---|---|---|
| `GET stats-data.hyperliquid.xyz/Mainnet/leaderboard` | 40 MB JSON, **48,527 rows**: `ethAddress`, `accountValue`, `windowPerformances` {day, week, month, allTime} × {pnl, roi, vlm}, `displayName` | This is the **enumeration source**. Includes 0-equity (dead) accounts, so it is not purely survivors. The exact inclusion rule is undocumented (median lifetime volume about $19.8M). |
| `GET stats-data.hyperliquid.xyz/Mainnet/vaults` | 14 MB, **9,478 vaults** with `summary` {name, vaultAddress, leader, tvl, isClosed, createTimeMillis}, `apr`, `pnls` per window | Vault enumeration. |
| `{"type":"vaultDetails","vaultAddress":...}` | portfolio (equity/PnL history), followers, leaderFraction, leaderCommission, isClosed | Example: Growi HF vault, history 2024-07-10 → today, 70 points. |
| `{"type":"portfolio","user":...}` | windows `day/week/month/allTime` and `perpDay…perpAllTime`, each with `accountValueHistory`, `pnlHistory`, `vlm` | **allTime is coarse: about 90–100 irregular points** from account start. The earliest seen was 2023-12-20. **Use `perpAllTime`** to exclude spot (HYPE airdrop) PnL. |
| `{"type":"clearinghouseState","user":...}` | current perp positions (`szi`, `entryPx`, leverage, liquidationPx, cumFunding) | **Weight 2**, so it is cheap. This is the building block for an "aggregate BTC positioning" snapshot. |
| `{"type":"userFills"}` / `{"type":"userFillsByTime","startTime","endTime"}` | ≤2000 fills per call | **Only the 10,000 most recent fills are reachable.** For two high-turnover top accounts, a 2024 window returned **0 fills** and the latest 2000 fills were all from today. For three lower-activity accounts, fills went back to 2023-12 / 2024-12. |
| `{"type":"historicalOrders"}` | ≤2000 most recent orders | |
| `{"type":"userFunding","startTime"}` | funding payments (500 per page), back to Jan 2024 for the tested account | |
| `{"type":"userNonFundingLedgerUpdates","startTime"}` | deposits, withdrawals, transfers (2000 per page) | Needed to compute **flow-adjusted (time-weighted) returns**. |

**Rate limits** (docs, [rate limits page](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits)):
- REST is **1200 weight/min per IP**. `clearinghouseState`, `allMids`, `l2Book` etc. weigh 2. `userRole` weighs 60. Most other info calls weigh 20.
- `userFills*` adds extra weight per 20 items returned.
- In practice: about 60 `portfolio` calls/min, or about 600 `clearinghouseState` calls/min. A full daily positioning snapshot of the ~38k "active" leaderboard accounts therefore takes about 1 hour from one IP.
- No rate-limit headers are returned (only CloudFront headers).

**Deep history beyond 10k fills** ([historical data docs](https://hyperliquid.gitbook.io/hyperliquid-docs/historical-data)):
- `s3://hl-mainnet-node-data`: `node_fills`, `node_fills_by_block`, `node_trades`, `explorer_blocks`, `replica_cmds`, `misc_events_by_block`.
- `s3://hyperliquid-archive` (requester pays): L2 snapshots and asset contexts.
- The docs say there is "no guarantee of timely updates and data may be missing". Third-party archives exist (e.g. Hydromancer's "Reservoir", used by arXiv 2606.15715).
- **Only the S3 fills give a survivorship-free universe**, meaning every address that ever traded, not just those on today's leaderboard.

**Live numbers from the leaderboard snapshot (2026-10-29):**
- Positive all-time PnL: 50.6% of all 48,527 rows. Many rows are spot/HYPE holders with near-zero perp volume.
- Accounts with lifetime volume ≥ $10M: 38,106. Of these, **only 40.1% have positive all-time PnL**.
- Accounts with current equity > $100k: 15,464. Of these, **84.5% are positive**. This is survivorship by construction: selecting on *current* size selects winners.
- The top all-time PnL accounts are dominated by addresses with ~0 trading volume (spot/HYPE appreciation) and by protocol vaults. HLP (`0xdfc2…f303`) shows +$139M. The top "trader" by PnL with real volume is `0xecb6…2b00`: +$216M all-time on **$316B volume**, i.e. a market-maker profile (2000 fills inside about 9 minutes today).

**Vault survivorship (computed from the vault list):**
- 9,478 vaults, of which 6,408 are closed.
- 8,569 are older than 1 year. **Only 1,918 (22.4%) of those have positive all-time PnL.**
- Only **45** are open, older than 1 year, with TVL > $100k. 34 of those are positive.
- The surviving visible set is a heavily filtered remnant. Note also that vault PnL is in **USD**: a "long BTC" vault looks skilled in USD whenever BTC rose.

**Persistence spot-check (our own test, section 4.5):**
- On 205 accounts, the rank correlation of normalised perp PnL between the period before and after 2025-10-29 is 0.14 (p ≈ 0.03).
- 35% of the prior top decile stopped trading.

### 1.2 GMX v2 (Arbitrum/Avalanche) (tested live)

- Subsquid GraphQL: `POST https://gmx.squids.live/gmx-synthetics-arbitrum:prod/api/graphql`.
- Introspection lists `accountStats`, `accountPnlRankMetrics`, `positions`, `positionChanges`, `prices`, `markets`, etc.
- The live count was **1,349,812 accounts** in `accountStats` and **5,652,272 `positionChanges`**.
- `accountStats(orderBy: realizedPnl_DESC)` works. Fields include `volume, realizedPnl, wins, losses, closedCount, maxCapital, netCapital, deposits`. USD values are scaled by 1e30. The top account showed about $10.4M realized PnL, 34 closed positions, 24 wins.
- **Strength:** every position change is an on-chain event, so it can be fully reproduced from Arbitrum logs.
- **Weakness:** oracle-priced, so execution differs from CEX. Closed-position counts per account are small (tens), so per-account statistical power is low. Many accounts are hedging legs of off-chain books.
- REST: `https://arbitrum-api.gmxinfra.io/markets/info` works and gives market metadata.

### 1.3 dYdX v4 (Cosmos app-chain) (tested live)

- Indexer: `https://indexer.dydx.trade/v4/...`. `/height` returned 111,624,623 at 2026-10-29T17:39Z.
- `/perpetualMarkets?ticker=BTC-USD` showed BTC 24h volume of about $6.8M, so activity is now small.
- `/trades/perpetualMarket/BTC-USD` returns trades **without addresses**.
- Per account:
  - `/historical-pnl?address=&subaccountNumber=` gives equity, totalPnl and netTransfers, roughly hourly.
  - `/fills?address=&subaccountNumber=`.
  - The Megavault history is at `/v4/vault/v1/megavault/historicalPnl` (works). `/v4/megavault/...` and `/v4/leaderboard/...` return 404.
- **Enumeration:** there is no leaderboard endpoint, but the chain lists all subaccounts. `https://dydx-rest.publicnode.com/dydxprotocol/subaccounts/subaccount?pagination.limit=…` works, with key pagination.
- History starts with v4 mainnet (late 2023). Liquidity has migrated away, so dYdX is a weak source today.

### 1.4 Drift (Solana): not usable at test time

- `https://data.api.drift.trade/*` failed (proxy CONNECT returned 502) on 2026-10-29.
- DefiLlama's hack list shows a Drift exploit dated **2026-04-01 (~$295M)**, and 30-day perp volume is tiny (search snippet, not independently verified).
- Drift's historical per-user trade records (S3 by user account) were the classic source. Treat the venue as unreliable now. Raw Solana program logs remain a fallback (e.g. Shyft GraphQL).

### 1.5 Aevo: leaderboard only

- `GET https://api.aevo.xyz/leaderboard` works. It returns daily/weekly/… rankings with `pnl`, `perp_volume`, `options_volume` and **random pseudonymous usernames** (e.g. "Magenta-Literate-Volcker").
- Account history endpoints require API keys for the account owner.
- **Not verifiable per account by a third party** (off-chain order book, rollup settlement), so it does not meet the owner's rule.

### 1.6 Polymarket: calibration and forecasting records (tested live)

- `GET https://data-api.polymarket.com/v1/leaderboard?timePeriod=all&orderBy=PNL&limit=&offset=` works and paginates past rank 10,000.
- `/v2/leaderboard?window=all` also works. The old `lb-api.polymarket.com` returns **410 (retired)**.
- Per wallet:
  - `/activity?user=&sortDirection=ASC` gave the top account's first trade on 2024-10-14.
  - `/closed-positions?user=` gives realizedPnl and avgPrice per market.
  - `/positions?user=`.
- All of it is reproducible from Polygon CTF-exchange logs.
- **BTC relevance:**
  - Gamma (`https://gamma-api.polymarket.com/public-search?q=bitcoin up or down`) lists **"Bitcoin Up or Down" markets at 5-minute (and longer) horizons, resolved on Chainlink BTC/USD streams**.
  - It also lists long-dated BTC threshold markets, e.g. "Will Bitcoin hit $60k or $80k first?" with about $1.97M volume, ending 2027-01-01.
  - These give (a) a market-implied, **verifiable-calibration** probability for BTC paths and (b) per-wallet BTC-directional forecasting records.
- **Caveat:** short-horizon up/down markets measure microstructure skill, not low-frequency skill.

**Answer to "can we enumerate multi-year, large-sample, risk-adjusted profitable accounts on BTC directional calls?"**
- Enumeration: yes on Hyperliquid, GMX, dYdX and Polymarket.
- **Multi-year:** at most about 3 years.
- **Large-sample for low-frequency BTC directional calls:** essentially no. A swing trader making 1–4 BTC calls per month has 30–100 independent bets over the whole history of these venues. That is far too few after correcting for tens of thousands of candidates (section 4).
- Accounts with enough independent observations to be significant are high-turnover ones, whose edge is not low-frequency.

---

## 2. "Smart money" vendors: what is free, what is verifiable

| Vendor | Free access | Verifiable? | Label opacity |
|---|---|---|---|
| **Nansen** | Limited free tier. The API is credit-based (free tier reportedly 100 trial credits; free tier consumes 10× credits vs Pro per [Nansen docs](https://docs.nansen.ai/getting-started/credits)). Pricing consolidated to a single Pro plan (~$49–69/mo per third-party sources, Sep 2025 onward). | The **underlying transactions** are verifiable. **"Smart Money" membership is not**: it is a proprietary, retroactive, PnL-based label with rolling windows and heuristics plus manual research. | **Opaque.** Selection on past PnL across a huge wallet universe is exactly the multiple-testing problem in section 4, and Nansen does not publish its false-discovery control or out-of-sample performance of the label. Treat it as a candidate list at best. |
| **Arkham** | Free web app. API through AWS Marketplace (usage-billed) and paid tiers. | Entity attributions (exchange or fund X owns address Y) come from heuristics, clustering and a paid **bounty "Intel Exchange"**, so they cannot be checked from the chain alone. | **Opaque / crowd-sourced**, with occasional stale or disputed labels. Useful for *exchange-wallet* identification; never treat as ground truth. |
| **Dune** | Free tier with SQL queries and API credits. | **Most verifiable**: the SQL is visible, decoded tables derive from raw logs, and you can re-run it. | Community label tables (`labels.*`) are user-submitted. Check the provenance of each label used. |
| **DeBank** | Web is free. Cloud API is paid (compute units; per a competitor's blog, no free tier). | Balances are verifiable. "Whale" or "smart" rankings are not. | Medium. |
| **Zerion** | Developer API is free (10 rps, 2,000 req/day per Zerion FAQ). | Wallet balances and history are verifiable. | Low: portfolio data, no "smart" labels. |

**Rule for the agent:** use vendors only as **address discovery**. Recompute every metric (returns, Sharpe, drawdown, skill tests) ourselves from raw venue or chain data. Never ingest a vendor's "smart money" flag as a feature without re-deriving it point-in-time, because the label is assigned *after* the performance it is supposed to predict.

---

## 3. Aggregate BTC on-chain cohort behaviour: reproducible or opaque?

**Tested live:** CoinMetrics Community API (`https://community-api.coinmetrics.io/v4`).
- Catalog: `/catalog-all-v2/asset-metrics?assets=btc` lists 1,324 BTC metrics. The old `/catalog-asset-metrics` path returns 404.
- Rate limit header: `x-ratelimit-limit: 6000;w=20` (6000 per 20 s sliding window), plan "download".

| Metric family | Free on community API (tested)? | Reproducible from a full node? |
|---|---|---|
| `PriceUSD`, `ReferenceRateUSD`, `CapMrktCurUSD`, `SplyCur`, `IssTotNtv/USD`, `FeeTotNtv`, `HashRate`, `TxCnt`, `AdrActCnt`, `BlkCnt` | **Free** | Yes (price is an external but public input) |
| `CapMVRVCur` (MVRV) | **Free** (so realized cap = market cap / MVRV is derivable for free) | **Yes**: realized cap = Σ UTXO value × price when created. Needs a UTXO-age index plus a price history. |
| `CapRealUSD`, `SplyAct1yr/180d/2yr/5yr/10yr/Ever` (coin-age bands, the basis of LTH/STH), `VelCur1yr`, `SER`, `NVTAdj`, `TxTfrValAdjUSD`, `SplyFF`, `RevNtv/USD`, `DiffMean`, `CapMVRVFF`, address-balance bands (`AdrBalNtv1KCnt`, `SplyAdrBalNtv1K`, `SplyAdrTop1Pct`) | **Paid** (forbidden on community key) | **Yes.** All are deterministic functions of the UTXO set plus price. "Adjusted" variants rely on change-output heuristics and are less clean. |
| `FlowInExNtv/USD`, `FlowOutExNtv`, `SplyExNtv` (exchange flows and balances) | **Free, but flagged `status: flash`** (revisable) | **No.** Requires exchange address labels and clustering. Labels are backfilled when new exchange wallets are discovered, so history changes. |
| `FlowInExPitNtv` etc. (point-in-time exchange flows) | **Paid** | No. PIT versions exist precisely because the non-PIT history has look-ahead. |
| Miner flows/supply: `SplyMiner0HopAllNtv`, `FlowMinerOut1HopAllNtv`, `FlowMinerOut0HopAllNtv` | **Paid** | 0-hop (coinbase outputs) is **yes**, deterministic. 1-hop and pool attribution are **heuristic**. |

**Self-hosted option:**
- [Bitcoin Research Kit (brk)](https://github.com/bitcoinresearchkit/mono) is MIT-licensed and OpenSats-funded.
- It computes realized cap, MVRV, SOPR, cohort (age and size) metrics and more from a Bitcoin Core node. It needs about 400 GB of disk and 12 GB+ of RAM ([docs.rs/brk](https://docs.rs/brk)).
- This is the cleanest "verifiable from raw chain" path for LTH/STH supply and realized price.
- **Our definitions must be pinned and published.** Glassnode's LTH/STH split uses a 155-day coin-age threshold with smoothing. CoinMetrics uses fixed bands (180d, 1y, …). The exact choice is a free parameter that can be overfit.

**Statistical caveat for cohort metrics:**
- Every widely quoted "rule" (MVRV > ~3.5 = top, price < realized price = bottom, LTH distribution = late cycle) is fitted on about **3–4 BTC cycles**, i.e. 3–4 independent events.
- Daily data creates an illusion of large n. The effective sample for cycle-timing claims is single digits.
- These metrics are fine as **regime descriptors and risk limits** (e.g. reduce leverage when MVRV is extreme). They are not statistically validated return predictors.

---

## 4. Statistics: can learning from leaderboards be sound?

### 4.1 Luck among many accounts: expected maximum Sharpe under the null

From Bailey & López de Prado's "False Strategy Theorem":
E[max SR] ≈ σ(SR̂)·[(1−γ)Φ⁻¹(1−1/N) + γΦ⁻¹(1−1/(Ne))], with γ = Euler–Mascheroni and σ(SR̂) ≈ √(1/T).

Our computation for iid daily returns, true SR = 0, annualised:

| Record length | N = 100 | N = 1,000 | N = 10,000 | N = 40,000 |
|---|---|---|---|---|
| 1 year | 2.53 | 3.26 | 3.86 | 4.19 |
| 2 years | 1.79 | 2.30 | 2.73 | **2.96** |
| 3 years | 1.46 | 1.88 | 2.23 | 2.42 |

Hyperliquid alone has about 38k accounts with ≥$10M volume. **A top-of-leaderboard Sharpe of 3 over 2 years is what pure luck produces.** Fat tails, negative skew (martingale or short-vol traders that look smooth until liquidated) and autocorrelation (illiquid marks) make this worse.

### 4.2 Probabilistic / Deflated Sharpe ratio and minimum track record length

- **PSR**: PSR(SR*) = Φ[(SR̂−SR*)·√(T−1) / √(1 − γ₃SR̂ + (γ₄−1)/4·SR̂²)].
- **DSR** = PSR with SR* set to the expected maximum above. N is the number of *effectively independent* trials. The papers suggest clustering correlated accounts or strategies to estimate N.
- **MinTRL** (one-sided α = 5%, vs SR* = 0) is about **990 days for SR = 1** and about 250 days for SR = 2. That is *before* any multiple-testing correction.
- To survive **Bonferroni over 40k accounts** (z = 4.71), the required days of daily data are:
  - SR 1: about 8,100 days (22 years)
  - SR 2: about 2,000 days (5.5 years)
  - SR 3: about 900 days (2.5 years)
- No low-frequency BTC directional trader can be certified on any venue that exists today. Only Sharpe ≥ 3 accounts (MM/HFT/arb) are even detectable.

### 4.3 False discovery control (better than Bonferroni)

- **Benjamini–Hochberg FDR** on per-account p-values from a stationary block bootstrap or sign-randomisation, with the **BY** variant for dependence.
- **Barras, Scaillet & Wermers (2010)** estimate the proportion of truly skilled (π⁺) and unskilled funds, and the FDR among those selected. Applied to mutual funds, they find about 0.6% truly skilled.
- **White's Reality Check (2000)**, **Hansen's SPA (2005)** and **Romano–Wolf StepM (2005)** test whether the *best* of many strategies beats the benchmark.
- **Harvey, Liu & Zhu (2016)** argue that new factors need t > 3.0.
- **Probability of Backtest Overfitting (PBO)** via combinatorially symmetric cross-validation (Bailey, Borwein, López de Prado & Zhu 2017) should be applied to *our selection rule itself* (which accounts we choose and how we weight them).

### 4.4 Empirical evidence on following top performers

| Study | Setting | Finding relevant to us |
|---|---|---|
| Barber, Lee, Liu & Odean (2014), *J. Financial Markets* 18:1–24, "The cross-section of speculator skill: Evidence from day trading" | Full Taiwan day-trader population | Some persistence, but **<1% of day traders are predictably profitable net of fees**. |
| Chague, De-Losso & Giovannetti (2019), "Day Trading for a Living?" SSRN 3423101 | Brazilian futures day traders | 97% of those who persisted more than 300 days lost money. |
| Fama & French (2010), *JF* 65(5); Kosowski, Timmermann, Wermers & White (2006), *JF*; Barras, Scaillet & Wermers (2010), *JF* 65(1) | Mutual funds, bootstrap luck vs skill | Very few true positive-alpha managers. Top-ranked funds mostly reflect luck. |
| Dorfleitner et al. (2018), *QREF* 70:160–171, "To follow or not to follow" | wikifolio, ayondo social trading | Returns to followers / signal providers are negative or unattractive on average (per AAII summary). |
| Oehler, Horn & Wendt (2016), *IRFA* 46:202–210 | wikifolio certificates | Underperform benchmarks after fees. |
| Apesteguia, Oechssler & Weidenholzer (2020), *Management Science* 66(12):5608–5622, "Copy Trading" | Lab experiment | Seeing others' success, and the option to copy, **increase risk-taking**. Success is partly luck plus risk. |
| Joseph, Riedl, Pentland & Moro (2025), arXiv 2507.01817 | Large social trading platform (eToro-like) | Followers pick by **popularity**, which is weakly related to returns. Widespread underperformance. Those who frequently switch whom they copy do better. |
| Pan, Altshuler & Pentland (eToro 2011–13; arXiv 1406.7729 "Popularity and Performance") | eToro | "Guided copying" helped vs manual trading. This is a platform-affiliated MIT study, not a net-of-cost out-of-sample test vs a passive benchmark. |
| YieldFund (Oct 2025, industry, not peer-reviewed), 100k copy outcomes on Binance/Bybit/MEXC over 90 days | CEX copy trading | 97% of lead traders had positive personal PnL, but **only 43.6% delivered positive returns to followers**. 48.5% of followers were profitable. Shows the execution and timing gap. |
| Zhai (2026), arXiv 2608.04373, "Public Trader Identity: Adverse Selection and Return Predictability" | Public-wallet DEX (147k wallets, $84B taker notional) | Wallet informativeness persists (rank correlation 0.52 across 10-day windows) and improves **1-second** return prediction (OOS R² 12.3%). No after-cost P&L. **The horizon is irrelevant to a low-frequency agent.** |
| Gómez-Cram, Guo, Kung & Jensen (2026), SSRN 6617059 (Polymarket, 1.72M accounts, 2023–2025) | Prediction market | Sign-randomisation test classifies 3.14% as skilled. **44% stay skilled out of sample** (vs about 10% for mutual funds). 60% of "lucky winners" revert. Only 12% of top earners are "skilled". Top earners ≠ skilled. |
| Reichenbach & Walther, SSRN 5910522 (Polymarket) | Prediction market | Under a third of traders profit, and profits are persistent. |
| Chernoff & Jagtiani (2024/2025), Philadelphia Fed WP 24-14, "Beneath the Crypto Currents" | ETH holder cohorts | Large ETH holders increase holdings before price rises while small holders reduce. This is a cohort-level association, not a tested trading strategy. |

**Synthesis:**
- Skill exists, and in some venues persists, but it is concentrated in **a few percent of accounts**, **short horizons** and **microstructure or information edges**.
- "Top by PnL" is a poor proxy for skill: in the Polymarket study only 12% of top earners were skilled.
- Copying adds latency, slippage and capacity problems, plus survivorship and crowding (public wallets get front-run or hunted).
- There is **no credible peer-reviewed evidence that following verified top performers at low frequency produces out-of-sample excess returns after costs**, and none at all against a hold-BTC benchmark.

### 4.5 Our own persistence spot-check on Hyperliquid (live, 2026-10-29)

**Method** (scripts: `scratchpad/scripts/hl_persist_fetch.py`, `hl_persist_analyze.py`):
- Sampled 450 random leaderboard accounts with ≥$10M lifetime volume.
- Called `portfolio` for each. 415 succeeded; 35 failed with truncated HTTP reads, not rate-limit errors.
- Kept the 205 accounts whose perp history started ≥6 months before the split date.
- Period A = account start → 2025-10-29. Period B = 2025-10-29 → 2026-10-29.
- Metric = perp PnL in the period ÷ median account equity in the period (floored at $1k).

**Results:**
- **Spearman rank correlation A→B = 0.136** (one-sided permutation p = 0.027, n = 205). This is weak but non-zero persistence.
- Base rate of positive PnL in period B: **18.5%**. Period B was a falling BTC year: BTC fell from about $110k to about $81k.
- Top decile in A that were positive in B: **35%** (median normalised B PnL = 0, because many stopped trading). Bottom decile: 10%.
- **Attrition:** 29% of all accounts, and **35% of the top decile**, had essentially zero PnL in B, i.e. they stopped trading. Among the 145 still active in B, 26% were positive. Among active accounts in the top decile of A, 50% were positive (n = 14, so the confidence interval is huge).
- Of 63 accounts positive in A, 22 (35%) were also positive in B.

**Interpretation:**
- There is a little relative persistence, mostly "losers keep losing" plus "winners lose less".
- Winners frequently **quit**. Same pattern as the Polymarket attrition finding: past winners leave the sample, so "follow the top list" constantly loses its members.
- This is a *USD perp-PnL* test: crude, not risk-adjusted, not BTC-denominated, and with no multiple-testing correction because it is a single pre-specified test.
- It neither supports nor kills the idea. It shows that the data supports a proper test (section 5).

---

## 5. Recommended pipeline (if we do it at all)

### 5.0 Verdict first

- **Expected value is low.** The plausible edge, if any, is a weak, noisy tilt signal. The infrastructure is cheap (free APIs, one machine).
- The real risk is **self-deception**: a beautiful but overfit backtest.
- **Recommendation:** build it as a **research and forward-test track** with strict pre-registration. Do not deploy capital on it until it passes the forward gate in 5.4.
- Keep "hold BTC" as the default. The signal may only **tilt** BTC exposure within a bounded band, e.g. 70–100% BTC with the rest in USD stablecoin, never levered, never into alts on the basis of this signal.

### 5.1 (a) Pull verifiable account histories

1. **Universe (survivorship-free):**
   - Preferred: every address that ever traded HL perps, from `s3://hl-mainnet-node-data/node_fills*` (requester pays, about tens of GB) or from replaying `replica_cmds` on a non-validating node.
   - Fallback: union of daily leaderboard snapshots, **starting now**, stored with the snapshot date. The leaderboard keeps dead accounts but its inclusion rule is unknown.
2. **Per address, store raw:**
   - `portfolio` (perpAllTime pnlHistory and accountValueHistory)
   - `userNonFundingLedgerUpdates` (deposits and withdrawals)
   - `userFunding`
   - `userFillsByTime`, paged (≤10k most recent; older fills from S3)
   - Respect 1200 weight/min/IP: about 60 portfolio or fill calls per minute.
3. **Daily positioning snapshot** (forward, point-in-time): `clearinghouseState` (weight 2) for the candidate set. Save BTC `szi`, entryPx, leverage, equity and the timestamp. Store everything append-only with fetch timestamps. This is the PIT record we cannot reconstruct cheaply later.
4. **Add GMX v2** (squid `positionChanges`, BTC markets) and **Polymarket** (BTC threshold markets' prices and wallet records) as secondary universes. Treat dYdX as optional (low activity). Exclude Aevo and Drift.

### 5.2 (b) Select accounts with significant skill after multiple-testing correction

1. **Build daily, flow-adjusted returns:**
   - Time-weighted, removing deposits and withdrawals: r_t = (E_t − E_{t−1} − netFlow_t) / E_{t−1}.
   - Convert to **BTC terms**: r_t^BTC = (1 + r_t^USD)/(1 + r_t^BTCUSD) − 1, since the objective is BTC.
2. **Exclusions:**
   - Vaults and protocol accounts (HLP).
   - Accounts with HFT/MM signatures: fills per day above a threshold, median holding period under 1 hour. Their edge is not ours.
   - Accounts whose BTC-perp exposure is a hedge: near-zero net delta across coins, or large spot holdings.
   - Accounts with fewer than 365 days of history or fewer than N_min independent BTC position flips.
3. **Skill statistic per account:**
   - Alpha vs BTC: regress r^USD on BTC return and keep the intercept.
   - Plus **timing skill**: correlation between the account's BTC net delta at t and the BTC return over [t, t+k] for k = 7 and 30 days.
   - Use non-overlapping windows or Newey–West standard errors.
4. **p-values** by stationary block bootstrap (e.g. 10-day blocks) or **sign-randomisation of position direction** (as in Gómez-Cram et al.).
5. **Multiple-testing control** across *all* accounts tested (record N honestly, including every variant tried):
   - BH/BY FDR at q = 10%.
   - Report the Barras–Scaillet–Wermers π⁺ estimate.
   - Compute **DSR** with N equal to the number of effectively independent accounts.
6. **Expect the selected set to be empty or tiny.** That is a valid result. If it is empty, stop (section 5.0).

### 5.3 (c) Turn aggregate positioning into a candidate signal

- **Signal S_t** = equity-weighted (or equal-weighted, which is more robust) net BTC delta of the selected cohort, as a fraction of their equity. It is measured from the **daily PIT snapshot taken before our decision time**.
- **Contrast signal:** the same quantity for the *whole* universe, or for the bottom-skill cohort. Literature on retail flows suggests a **contrarian** reading may work better. Pre-register both and correct for both.
- **Map to exposure:** BTC weight w_t = clip(0.85 + 0.15·z(S_t), 0.70, 1.00). Rebalance weekly with a hysteresis band to limit costs.
- **Pre-register all of the following before looking at forward results:** selection thresholds, horizon k, the mapping, and the rebalance rule.

### 5.4 (d) Backtest honestly

1. **Point-in-time:**
   - The skill selection at date t may use only data ≤ t (walk-forward re-selection, e.g. monthly).
   - Positions come from snapshots stamped ≤ t.
   - Historical reconstruction of positions from fills (S3) must use fill timestamps, not later-revised leaderboard data.
   - **Never** use the current leaderboard to choose accounts for a past period. That is the classic survivorship / look-ahead error.
2. **Survivorship-free:** the universe at t is every address active by t, including those later liquidated or gone to zero.
3. **Costs:** spot taker fees plus spread on BTC/USDC rebalances, a 1-day decision lag, and stablecoin yield (or none).
4. **Evaluation vs hold-BTC, in BTC terms:**
   - Excess log-growth of BTC holdings.
   - **DSR** using the true count of variants tried.
   - **PBO** via CSCV over the variant grid.
   - **White Reality Check / SPA** vs the benchmark.
   - Bootstrap confidence interval on excess return.
   - Report MinTRL: how long until the result could be significant.
5. **Forward gate:**
   - Because history is short (≤3 years, one partial cycle), any in-sample result is weak.
   - Require **≥12 months of live paper-trading** on frozen rules. Deploy only if forward DSR > 0.95 *and* turnover-adjusted excess return > 0.
   - Otherwise, archive the result as a negative finding (that is also valuable "verifiable evidence").

### 5.5 Cost estimate

- Daily snapshots of about 2–5k candidates take about 10 minutes per day.
- Full backfill of portfolio histories for 38k accounts takes about 11 hours at 60 calls/min. Polite fetching over 2 nights is fine.
- S3 node fills cost requester-pays egress, single-digit to tens of USD.
- Storage is a few GB.

---

## 6. Additional caveats specific to the BTC-denominated objective

- **USD PnL leaderboards are mostly BTC beta.** In a rising year, long-BTC accounts look skilled in USD while adding nothing vs holding BTC. Always evaluate in BTC terms.
- **Entity ≠ address:**
  - One trader may use many addresses and sub-accounts.
  - Vault leaders trade on others' capital.
  - Delta-neutral funding farmers carry large *short* BTC perp positions that are hedged elsewhere.
  - Naive aggregation of net BTC delta therefore mixes views with hedges.
- **Reflexivity and adversarial behaviour:** big public wallets are tracked by bots and influencers. They can deliberately signal, and their positions get hunted. Public, famous wallets are the *least* likely to carry an exploitable, uncrowded signal.
- **Venue risk:** Drift's 2026 incident and dYdX's liquidity migration show that the venue itself may not survive the track record.

---

## 7. Sources

**APIs tested (2026-10-29):**
- api.hyperliquid.xyz/info: types `meta`, `portfolio`, `clearinghouseState`, `userFills`, `userFillsByTime`, `userFunding`, `historicalOrders`, `userNonFundingLedgerUpdates`, `vaultDetails`, `allMids`
- stats-data.hyperliquid.xyz/Mainnet/leaderboard and /vaults
- gmx.squids.live/gmx-synthetics-arbitrum:prod/api/graphql
- arbitrum-api.gmxinfra.io/markets/info
- indexer.dydx.trade/v4: height, perpetualMarkets, trades, historical-pnl, fills, vault/v1/megavault/historicalPnl
- dydx-rest.publicnode.com/dydxprotocol/subaccounts/subaccount
- api.aevo.xyz/leaderboard and /statistics
- data.api.drift.trade: unreachable
- data-api.polymarket.com: v1/leaderboard, v2/leaderboard, activity, closed-positions
- lb-api.polymarket.com: 410 retired
- gamma-api.polymarket.com: events, public-search
- community-api.coinmetrics.io/v4: catalog-all-v2/asset-metrics, timeseries/asset-metrics

**Docs:**
- Hyperliquid rate limits: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits
- Hyperliquid info endpoint: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint
- Hyperliquid historical data: https://hyperliquid.gitbook.io/hyperliquid-docs/historical-data
- Nansen credits: https://docs.nansen.ai/getting-started/credits
- Zerion pricing: https://developers.zerion.io/pricing
- BRK: https://github.com/bitcoinresearchkit/mono , https://docs.rs/brk , https://opensats.org/projects/bitcoinresearchkit
- DefiLlama Drift: https://defillama.com/protocol/drift

**Papers:**
- Bailey & López de Prado (2014), "The Deflated Sharpe Ratio", *J. Portfolio Management* 40(5). https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551
- Bailey, Borwein, López de Prado & Zhu (2017), "The Probability of Backtest Overfitting", *J. Computational Finance* 20(4). https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253
- Bailey & López de Prado (2012), "The Sharpe Ratio Efficient Frontier" (PSR, MinTRL), *J. Risk* 15(2). https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1821643
- Harvey, Liu & Zhu (2016), "…and the Cross-Section of Expected Returns", *RFS* 29(1).
- Harvey & Liu (2015), "Backtesting", *JPM* 42(1).
- White (2000), "A Reality Check for Data Snooping", *Econometrica* 68(5).
- Hansen (2005), SPA test, *JBES* 23(4).
- Romano & Wolf (2005), *Econometrica* 73(4).
- Benjamini & Hochberg (1995), *JRSS-B* 57(1).
- Benjamini & Yekutieli (2001), *Ann. Stat.* 29(4).
- Barras, Scaillet & Wermers (2010), "False Discoveries in Mutual Fund Performance", *JF* 65(1).
- Fama & French (2010), "Luck versus Skill…", *JF* 65(5).
- Kosowski, Timmermann, Wermers & White (2006), *JF* 61(6).
- Barber, Lee, Liu & Odean (2014), *J. Financial Markets* 18.
- Chague, De-Losso & Giovannetti (2019), SSRN 3423101.
- Dorfleitner et al. (2018), *QREF* 70:160–171. https://ideas.repec.org/a/eee/quaeco/v70y2018icp160-171.html
- Oehler, Horn & Wendt (2016), *IRFA* 46.
- Apesteguia, Oechssler & Weidenholzer (2020), *Management Science* 66(12):5608–5622, doi:10.1287/mnsc.2019.3508. https://bse.eu/research/publications/copy-trading
- Joseph, Riedl, Pentland & Moro (2025), arXiv 2507.01817. https://arxiv.org/abs/2507.01817
- Pan, Altshuler & Pentland, "Popularity and Performance", arXiv 1406.7729. https://arxiv.org/pdf/1406.7729
- Zhai (2026), arXiv 2608.04373. https://arxiv.org/abs/2608.04373
- arXiv 2606.15715, "Trading in the Sunshine or in the Shade: Market Impact and Adverse Selection on Hyperliquid". https://arxiv.org/pdf/2606.15715
- Gómez-Cram, Guo, Kung & Jensen (2026), SSRN 6617059 (via The Block coverage): https://www.theblock.co/post/398902/skilled-polymarket-traders-are-a-3-minority-and-everyone-else-funds-their-gains-study
- Reichenbach & Walther, SSRN 5910522. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5910522
- Chernoff & Jagtiani, Philadelphia Fed WP 24-14. https://www.philadelphiafed.org/-/media/frbp/assets/working-papers/2024/wp24-14.pdf
- YieldFund copy-trading study (industry): https://www.yieldfund.com/news/is-copy-trading-profitable-a-90-day-multi-exchange-study
- Kogan, Makarov, Niessner & Schoar (2024), "Are Cryptos Different? Evidence from Retail Trading", *JFE*.

**Verification notes:**
- Paper details marked "per summary" come from secondary coverage. We read the abstracts directly for Zhai (2026), Joseph et al. (2025) and Chernoff & Jagtiani; the rest are from memory or search snippets.
- Classic references (Bailey/López de Prado, Harvey, White, Barras et al., Fama–French, Barber et al.) are cited from standard bibliographic knowledge and were not re-fetched.
- Medium and blog analyses found in search ("86% of HL traders lose", the "43 whale addresses" study) were **excluded as evidence** under the owner's rule.
