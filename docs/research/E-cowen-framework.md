# E — Benjamin Cowen ("Into The Cryptoverse") framework: deep analysis → testable rules

Research date: **2026-10-29**. Purpose: pre-design input for an autonomous agent whose objective is to **grow a portfolio measured in BTC** (benchmark = buy-and-hold 1 BTC).

> **Sourcing caveats (read first).**
> - Cowen's core indicators (risk metric, social risk, composite risks, liquidity/recession models) are **proprietary** (behind ITC Premium). Public detail comes from his free YouTube videos, his research memos on benjamincowen.com, X posts, and **secondary news write-ups** (Benzinga, The Daily Hodl / Informer Post reprints, BeInCrypto, Cointelegraph, CoinMarketCap). The secondary sources paraphrase him, sometimes wrongly.
> - Video "summaries" quoted here (rosetta.to, readray/lilys.ai) come from **auto-generated captions** and contain transcription errors (e.g. "having" for "halving", "congressional" for "logarithmic").
> - Several outlets (benzinga.com, beincrypto.com, cryptorank.io, x.com) blocked direct fetching. Their content is reported via search-result snippets or syndicated copies, and is marked as such.
> - Where I computed something myself from public price history (cycle day counts, ROI multiples), it is labelled **[computed]**.
>
> **Evidence standard (applied throughout; see §2.11 and §4).**
> - **(a) VERIFIED.** The claim can be checked against market data, and I checked it. Data used: CoinMetrics community API daily BTC/ETH reference price (`PriceUSD`) and `CapMVRVCur` (realized price = price / MVRV), 2010-07-18 → 2026-10-28; Binance ETHBTC weekly klines 2017-07 → 2026-10; FRED (`DFEDTARU`, `DFF`, `DGS2`, `DGS10`, `WALCL`, `UNRATE`, `DTWEXBGS`) to 2026-10-27; CoinGecko `/global` dominance snapshot on 2026-10-29. Weekly close = CoinMetrics Sunday daily close. Scripts: `/private/tmp/claude-501/pxscripts/verify.py`, `verify2.py`. Close-based numbers can differ by a few % from the intraday figures quoted in the media.
> - **(b) VERIFIABLE, NOT YET CHECKED.** I state the data that would check it. This is mainly dominance history (I had no free historical TOTAL/BTC.D series) and the exact content of videos I only know by title.
> - **(c) UNVERIFIABLE OPINION / PROPRIETARY.** Narratives, probabilities, and proprietary indicators whose formula is not public.
> - **Source tiers** for each call: **P1** = his own dated words (YouTube upload date and title from the YouTube page, his X post with timestamp decoded from the ID, his dated memo on benjamincowen.com). **P2** = transcript-derived summary of his own video (rosetta.to, readray.ai), which are his words but via auto-captions. **S** = mainstream third-party paraphrase (Cointelegraph, CoinMarketCap Academy, BeInCrypto, Benzinga, Forklog, 24/7 Wall St). **S-low** = aggregator/SEO/syndication (The Informer Post / Daily Hodl reprints, datawallet, KuCoin flash, MEXC, CoinTurk, COINOTAG, altcoinbuzz). **Claims that rest only on S-low are flagged ⚠.**

---

## 0. Executive summary

1. **What the framework is.** Cowen stacks six layers: (a) a **cycle clock** (4-year cycle, Q4 post-halving-year tops, Q4 midterm-year lows, about 1 year of bear market); (b) **long-run valuation** (log-regression "fair value" bands, a 0–1 "risk metric", and since May 2026 an asymmetric quantile model); (c) **trend filters** (Bull Market Support Band = 20W SMA + 21W EMA, the 50W SMA, and the sequence 50W→100W→200W); (d) **rotation** (BTC dominance with and without stablecoins, ALT/BTC pairs, ETH/BTC); (e) **macro/liquidity** (QT/balance sheet, Fed funds vs the 2Y yield as a "neutral" proxy, labour market, yield curve, DXY, inflation, the S&P 500, and a recession composite); (f) **sentiment** (a "social risk" index built from YouTube views, subscriber counts, X followers, Coinbase app rank and Google Trends).
2. **His strongest and most durable thesis, and the most relevant to a BTC-denominated agent:** *"Altcoins are oscillators at best against Bitcoin"*. BTC dominance rises during QT and tight policy, and **alt seasons need loose liquidity plus a new BTC all-time high**. This held through 2022–2026. ETH/BTC fell from 0.086 (Sep 2022) to **0.01766 (week of 2025-04-21)**, and was 0.029 on 2026-10-26 (verified, Binance). The 2025 cycle topped "on apathy" with no alt rotation. A rule of "default 100% BTC, alts only under a strict liquidity-and-trend gate" is the main transferable lesson.
3. **Cycle-timing record (checked against price data).** The **top** timing worked: he called Q4 2025, and BTC topped on 2025-10-06 (close $124.8k, intraday ≈ $126k), 1,062 days after the 2022 low vs 1,067 and 1,059 in the prior cycles **(a) VERIFIED**. His **bear-market** call (base-case low Oct 2026, near $60k) was right on price and early on timing **(a)**. The 2026 low so far is a $58.5k close on 2026-06-30, only 267 days after the top vs 364–406 days in earlier cycles. BTC has **not** yet gone below its realized price, which it did at every prior cycle low (MVRV min 0.56 / 0.69 / 0.75 vs 1.10 in 2026) **(a)**. Tactical macro calls were his weak spot: Q4 2023 and September 2026 (*"Bitcoin Breaks the May High (I Was Wrong)"*, P1 video 2026-09-21).
4. **Current view (2026-10-29).** Bear-leaning, "bottom-watch". After admitting in September that the breakout above the May high and the 50W SMA invalidated his bear memo, he flipped back. Two weekly closes below **$83k** (Oct 18 and Oct 25) are, in his words, a "fakeout confirmed". He posted a stepwise Q4 bearish roadmap on X (2026-10-24), which becomes **void if BTC reclaims and holds above $83k**. Step 3 (the Fed held on 10-28, with 2 dissents for a hike) is confirmed, and hot PCE (10-29) is the next step. Coverage cites $72–76k downside. He notes that the realized price (~$53k) has not been lost and that the cycle-bottom drops in 2014, 2018 and 2022 came *after* midterm elections (the 2026 midterm is Nov 3). He stays constructive on 2027.
5. **What can be reproduced.** The cycle clock, BMSB/50W rules, the dominance and ALT/BTC trend gates, the log-regression bands, the quantile bands, realized price/MVRV, and most macro inputs can all be rebuilt from public data. The proprietary risk, social and liquidity models can only be approximated. The biggest backtest danger is **n = 3–4 cycles**, which is a very small sample.
6. **Transcripts.** Channel **@benjaminjcowen** (ID `UCRvqjQPSeaWn-uEx-w0XOIg`) has about **3.1–3.2k videos** and 1.02M subscribers. English auto-captions (ASR) exist on recent uploads. Bulk extraction works with `yt-dlp --skip-download --write-auto-subs` or `youtube-transcript-api`. The highest-value playlists are *Bitcoin* (1,434), *Ethereum* (361), *Macroeconomics* (169), *Bitcoin: The Beauty of Mathematics* (73) and *On-Chain Analysis* (49), plus title-based series ("Bitcoin Dominance", "Bitcoin: Bull Market Support Band", "Bitcoin: Social Risk", "Bitcoin Risk Metric", "ETH/BTC", "Bitcoin: Dubious Speculation", the monthly macro data videos).

---

## 1. Who he is and where the material lives

| Item | Detail | Source |
|---|---|---|
| Background | BS in math (NC State), PhD in nuclear engineering (UNM, MD simulations of radiation damage in ceramics), postdoc at Sandia. Founded ITC in 2019, paid platform since 2021 (BC Analytics LLC) | datawallet profile (upd. 2026-08-27) https://www.datawallet.com/crypto/who-is-ben-cowen ; Cointelegraph Magazine 2026-03-06 https://cointelegraph.com/magazine/bitcoin-four-year-cycle-dead-debate-bear-market-2026-benjamin-cowen |
| YouTube | @benjaminjcowen, channel ID UCRvqjQPSeaWn-uEx-w0XOIg, **1.02M subs, "3.1K videos"** (channel header, 2026-10-29). vidIQ: 3,184 videos, 178.7M views | https://www.youtube.com/@benjaminjcowen ; https://vidiq.com/youtube-stats/channel/UCRvqjQPSeaWn-uEx-w0XOIg |
| Premium platform | intothecryptoverse.com, with charts incl. Log Regression Bands, Long Term Moving Averages, MVRV Z, ROI After Bottom, Short Term Bubble Risk, Bitcoin Dominance Analysis, US Inflation & Interest Rates, Flippening Index; tools: Macro Recession Risk, DCA simulation, Exit Strategies, Risk Portfolio Tester, MPT simulator, no-code "Workbench" | https://intothecryptoverse.com/ |
| Research memos (free, monthly in 2026) | benjamincowen.com/reports: Crypto Macro Risk Memos Jan–Sep 2026, "Asymmetric Tail Curvature in Bitcoin Price Quantiles" (2026-05-29), Bitcoin/Ethereum Letters (2020) | https://benjamincowen.com/reports |
| X | @benjamincowen (also @intocryptoverse) | https://x.com/benjamincowen |
| Other | Free monthly newsletter; newsletter.intothecryptoverse.com; Telegram t.me/intocryptoverse; "Investing Through the Cycles" conference, Miami, 2026-11-21 | video descriptions |

Video summaries with timestamps up to mid-June 2026 are at **rosetta.to/u/intothecryptoverse** (2,385 items). This is a useful secondary index: https://rosetta.to/u/intothecryptoverse

---

## 2. The tools and metrics, and how they are computed

### 2.1 BTC "risk metric" (price risk), 0–1 scale
- **What he says publicly.** It is a proprietary metric "first presented in 2019" that **"accounts for diminishing returns to assess instantaneous risk"**, displayed on 0 (blue, low risk) to 1 (red, high risk). Recurring videos: "Bitcoin Risk Metric" (e.g. 2021-11-30), "Sticking to Your Risk Metric", "Bitcoin Risk Metric & Finding Your Unique Risk Tolerance". ITC calls it the "flagship" metric and supports DCA in/out by risk bands (0.1-wide bands). He also publishes risk metrics for ETH/BTC ("ETH/BTC Risk Strategy", "Risk metric for moving between Ethereum and Bitcoin"), TOTAL market cap, XRP, the S&P 500 (data back to the 1920s), and gold. Sources: rosetta topic page https://rosetta.to/u/intothecryptoverse/topic/computer-science ; ITC homepage.
- **Formula: not public.** Community reconstructions (explicitly "definitely not correct, rough estimate"):
  - OrionAlgo "Cowen Risk Index": price / 400-period SMA → oscillator, × an exponentially increasing time factor to offset diminishing returns, then normalised. https://www.tradingview.com/scripts/benjamin/
  - "Bitcoin Risk Metric II" (TradingView): average of normalised terms that include ln(price / 20W MA), (price − 4-year MA)/σ, and **50D MA / 50W MA**. https://www.tradingview.com/script/8HsNtCbh-Bitcoin-Risk-Metric-II
  - jacdr "Benjamin Cowen's Simplified Risk Metric" (2022-04-02) https://www.tradingview.com/script/H4iCbDci-Benjamin-Cowen-s-Simplified-Risk-Metric
  - His own video titles ("Complete MA Division", inspired by Cowen) point to a **ratio of short to long moving averages**, de-trended for time.
- **Reproducible approximation for the agent:**
  `raw_t = ln(P_t / SMA_L(P)_t) · f(t)`, where L ≈ 350–400 days and `f(t) = (days since 2010)^k` (k fitted so that cycle peaks of `raw` are about equal). Then `risk_t = (raw_t − min_{≤t}) / (max_{≤t} − min_{≤t})` **using expanding-window min/max only**. Static min/max over the full history is look-ahead bias, and most public versions do this.
- **Composite variants he references:** "Total Indicator Risk" / "Total Risk" (2023 videos), "Bitcoin On-Chain Risk", and a "composite on-chain risk" (0.181 in the Aug-2026 memo). In July 2026 he wrote that "risk readings sitting in a 'low zone' historically marked accumulation".

### 2.2 Logarithmic regression bands / "fair value"
- **Concept (his words):** "The red line is what's called the fair value logarithmic regression trendline… the fair value of the asset class increases monotonically with time and we sort of oscillate around that fair value." Two fits:
  1. **All-data fit:** fair value ≈ **$33–34k** with a band of ~$28–41k (Feb 2022).
  2. **Non-bubble fit** ("green band"; bubble periods excluded by his own choice): fair value **≈ $19–20k** (Feb 2022). BTC subsequently bottomed at about $15.5k in Nov 2022.
  Source: "Bitcoin: What Is The Fair Value?" (2022-01-24/02-15) https://rosetta.to/u/intothecryptoverse/bitcoin-what-is-the-fair-value
- **Rules of thumb he stated:** each cycle top lands lower in band terms (often quoted as "about 2.5 regression bands below the previous one"), and each bear market bottoms about **one band lower** than the prior one. Later he generalised this as "each cycle's peaks fall short of the upper bands and lows drift lower". Sources: The Informer Post/Daily Hodl reprints (https://theinformerpost.beehiiv.com/p/10000-bitcoin-is-a-pipe-dream-for-bears-says-crypto-analyst-benjamin-cowen-heres-why), rosetta quantile video (2026-05-30).
- **Applied to TOTAL crypto market cap.** In "Beauty of Mathematics Part 70" (2026-05-07), TOTAL was about **$2.7T, "well below" the fair-value trendline (undervaluation regime)**. He expects undervaluation to persist through 2026 and possibly flip in 2027–28, with a long-run total market cap of about $10T. https://rosetta.to/u/intothecryptoverse/bitcoin-the-beauty-of-mathematics-part-70
- **(a) VERIFIED:** an OLS power-law fit `log10(P) = a + b·log10(days since 2009-01-03)` on CoinMetrics data up to 2022-02-15 gives a fair value of **$33,847** on that date (slope b ≈ 5.9). This exactly reproduces his "$33–34k" all-data fair value, so the method is the standard log-log regression. The "non-bubble ≈ $20k" variant depends on his subjective exclusion of bubble periods: **(b)**, reproducible only if those periods are defined.
- **Reproducible form:** `log10(P) = a + b·log10(days since 2009-01-03)` by OLS (equivalently a + b·ln(t)). Bands are residual quantiles or ±kσ in log space. The non-bubble fit drops days whose residual exceeds a threshold, which is a subjective choice and an overfitting risk.

### 2.3 Asymmetric quantile model (new, 2026-05-29)
- **Paper:** "Asymmetric Tail Curvature in Bitcoin Price Quantiles", a full-sample (~15 years, 4 halvings) quantile regression in which the **upper tail bends inward over time** (significant under block bootstrap) and the **lower tail stays close to a straight power law**. He calls it "descriptive, not predictive; not a forecast, floor or loss-risk measure". Out of sample, power-law and stock-to-flow variants show optimistic biases of roughly +32%, +295% and +1,699%. https://benjamincowen.com/reports/asymmetric-tail-curvature-in-bitcoin-price-quantiles (PDF linked there)
- **Numbers from the video (2026-05-30):** BTC sat at about the **9.4th percentile**. **Q1 (1st percentile) ≈ $62k**. The **2019 and 2025 tops both reached only about the 75th percentile** (not the 95th–99th). Gaps between Q1 visits were 238 → 139 → ~185 weeks. He treats Q1 as an **accumulation "golden pocket"** and warns the model "could easily break" in a global recession. https://rosetta.to/u/intothecryptoverse/bitcoin-asymmetric-tail-curvature-in-bitcoin-price-quantiles
- **Agent use:** this gives *a priori* valuation bands with an explicit statistical procedure, so it is more reproducible than the hand-drawn 2020 bands.

### 2.4 Trend filters: Bull Market Support Band (BMSB), 50W SMA, MA cascade
- **BMSB = 20-week SMA + 21-week EMA** (weekly closes). Above the band it acts as support in bull markets. A weekly close below it "can take several months" to recover. In bear markets he renames it the **"Bear Market Resistance Band"** (many 2026 titles: "Bitcoin Rallies to / Rejected off / Closes Below the Bear Market Resistance Band"). Sources: Coin Bureau https://coinbureau.com/news/bitcoin-never-below-40000-ever-again-why-its-possible ; channel search results (latest: "Bitcoin Bull Market Support Band", 2026-10-22, id KZ1Jro92t48).
- **50W SMA as the bull/bear line (this cycle).** In Oct 2025 he said the real support this cycle "has been the 50-week moving average". His explicit rule in "Altcoins and the end of QT" (2025-10-15): **two consecutive weekly closes below the 50W SMA mean the cycle is likely over, "and I would exit"**. In the bear phase, a **sustained weekly reclaim of the 50W SMA** is the invalidation of the bear thesis (July 2026 memo: 50W ≈ $86.5k). https://rosetta.to/u/intothecryptoverse/altcoins-and-the-end-of-qt ; https://benjamincowen.com/reports/bitcoin-cycle-memo-july-2026 ; X 2025-11-19: "If Bitcoin can back above the 50W SMA within the next week then I'll take the bear goggles off" https://x.com/intocryptoverse/status/1991250695232651378
- **MA cascade:** once BTC is below the 50W, "it's usually only a matter of time" before it loses the 100W and then the 200W. Each bear cycle loses them in sequence. In 2026 BTC broke below the 200W SMA in June ("Bitcoin Falls to the 200W Moving Average", 2026-06-05), then reclaimed it.
- **200-day MA:** in bear years, rallies that stall at the 200D are a classic bear-market-rally signature (2014, 2018, 2022, 2026: "Bitcoin Rejected off the 200D", 2026-05-19).

### 2.5 The cycle clock: 4-year cycle, halving, midterm year
- **Tops** come in **Q4 of the post-halving year** (Q4 2013, Q4 2017, Q4 2021, Q4 2025). **Lows** come in the **midterm year, usually Q4** (late 2014/Jan 2015, Dec 2018, Nov 2022, and his 2026 base case). "The four-year cycle tells you **when** the bottoms tend to occur", not the price. https://rosetta.to/u/intothecryptoverse/bitcoin-the-four-year-cycle-is-not-dead (2026-05-26)
- **Day counts (bottom→top):** he cites days 1,059 and 1,068 for prior cycles and ~1,062 for 2025 ("topped within one week of when it historically tops"). **(a) VERIFIED on CoinMetrics daily closes:** 2015-01-14→2017-12-16 = **1,067 d**; 2018-12-15→2021-11-08 = **1,059 d**; 2022-11-09→2025-10-06 = **1,062 d**. His numbers reproduce exactly on close data. Top→bottom: 406 / 364 / 366 d → projected 2026 low window **2026-10-05 to 2026-11-16**. Low→low: 1,431 / 1,425 d → **2026-10-04 to 2026-10-10**. The actual 2026 close low so far (2026-06-30) is at **day 267** after the top and **day 1,329** after the 2022 low, about 100 days early. If June holds as the low, the bottom-timing half of the clock missed by about a quarter. His Aug-2026 video uses "cycles typically 1,430–1,440 days" and "average bear bottom around day 406 from peak". https://readray.ai/notes/en/bitcoin-20260813/bitcoin-where-in-cycle
- **Midterm-year seasonality ("window of weakness"):** fade H1 of the midterm year. Typical path: Feb low, April higher/lower low, **June low, July rally, final Q4 low**. "Seasonality is only right like 70% of the time." "Usually the way to be successful at Bitcoin is to ignore it for the first half of the midterm year." Rallies in midterm years lasted 15–25 weeks (2014: 25; 2018: 19 and 21; 2022: 21). He also uses midterm YTD ROI within ±1σ of prior midterm years. https://rosetta.to/u/intothecryptoverse/bitcoin-the-window-of-weakness (2026-05-29)
- **Presidential-cycle and equity analogues:** S&P 1962–1982 lows every ~4 years, "topping on apathy doesn't mean you don't have a bear market"; returns by political party (2026-05-13).
- **Midterm Fed-hike analogue (Sept 2026 memo):** in prior midterm hike years BTC held near its hike-day level for about 7 weeks, then broke lower, which points to early November 2026. https://benjamincowen.com/reports/the-triple-squeeze-september-2026

### 2.6 Lengthening cycles vs. diminishing returns
- **2020–2021:** he and his team explored two separate hypotheses: **diminishing returns** (each cycle's ROI is smaller) and **lengthening cycles** (each bottom-to-top lasts longer). "Bitcoin: Measuring valley to valley" (2020-06-09) reported about 166 and 200 weeks between bottoms and a *projected* 270 weeks. Early 2021 coverage: "won't have a parabolic 2021… expects BTC to stretch its bull cycle into 2022". Titles from 2021–22: "Market Cycle Has Now *Unofficially* Lengthened From The Market Cycle Bottom", "Lengthening Cycle Theory Strikes Back – Or Does It?", "Market Cycle Theory (No Lengthening Cycles)".
- **Outcome:** lengthening cycles was **falsified**. The 2021 top came on the 4-year schedule (Nov 2021), and the low-to-low gap was ~1,437 days, not 270 weeks. He has since reverted fully to the 4-year clock. **Diminishing returns survived. (a) VERIFIED on daily closes:** bottom→top multiples were 112× (2015–17), 21× (2018–21), 7.9× (2022–25). Top-to-top ratios were 3.4× (2021/2017) and 1.85× (2025/2021). Peak-to-trough drawdowns were 84.5% (2013–15), 83.8% (2017–18), 76.7% (2021–22), and **53.1% so far (2025-10-06 → 2026-06-30)**, which fits his "diminishing gains *and* diminishing losses" comment. A plain full-sample power-law fit (log10 P on log10 days since genesis) puts the cycle tops at residual percentiles 98.5 → 91.5 → 66.5, and the lows at 26 → 5.7 → 5.5 (2026 low). This corroborates his "tops reach lower quantiles, lows hold near the lower band" finding **(a)**.
- **Lengthening-cycle record from his own dated titles (P1):** "Lengthening Cycle Theory Strikes Back – Or Does It?" (2021-05-16); "Bitcoin: How Long Could The Market Cycle Last?" (2021-11-13); "Bitcoin Market Cycle Has Now *Unofficially* Lengthened From The Market Cycle Bottom" (**2021-11-19**, eleven days after the actual cycle-top close of 2021-11-08); "Bitcoin Lengthening Cycles" (2021-12-24); "Bitcoin: Market Cycle Theory (No Lengthening Cycles)" (2022-05-07). The titles show he still entertained an extended cycle *after* the top, and dropped it by May 2022. The exact wording inside the videos is (b): check the transcripts.

### 2.7 Dominance and ALT/BTC
- **BTC.D measured two ways.** **Including stablecoins** (TradingView BTC.D): ~58% (Feb 2026), 60.66% (Apr 2026). **Excluding stablecoins**: ~66–67% (Feb 2026), ~70% peak; the Aug-2026 memo cites "Bitcoin dominance 67%". He argues the headline number is depressed by stablecoin growth (a "flight to safety"), so he prefers the ex-stables series for the trend. "Bitcoin Dominance" (2026-02-15) https://rosetta.to/u/intothecryptoverse/bitcoin-dominance
- **Flight-to-safety gauge:** **BTC.D + USDT.D**, which was ~63% in Aug 2024 (similar to June 2019, before the first Fed cut). https://cointelegraph.com/news/bitcoin-dominance-trading-altcoin-season-benjamin-cowen-crypto-trader
- **Alt basket:** **TOTAL2 ex-USDT ÷ BTC**, plus ETH/BTC, SOL/BTC, BNB/BTC, and an **advance-decline line of the top 100 coins**, which has trended down since 2021 ("Why Alt Season Never Happened", 2026-02-20).
- **Key aphorisms:** "**Altcoins are oscillators at best against Bitcoin.**" "**All Bitcoin pairs bottom first, all USD pairs bottom next.**" "btc.d goes up regardless during QT" (X, Nov 2025). "**The only way you're going to get alt season is if Bitcoin goes back up to new all-time highs**" (2025-10-15). Why he cares (X, 2024-10-15): "you can just keep your portfolio #BTC heavy throughout a BTC dominance uptrend and outperform a majority of the altcoin market." https://x.com/benjamincowen/status/1846250939965231387
- **ETH/BTC:** he flagged a long bleed in 2022–23. In Sept 2023 he gave a target of about 0.032, which was hit and exceeded. In Sept 2024 he said "the low… is September 2024… could go a little lower" with a bottom of 0.03–0.04, which was **wrong on depth**: ETH/BTC fell to ~0.018 in April 2025 [approx.]. In Oct 2025 he said the ETH/BTC low was probably in (April 2025), with a higher low expected. ETH/BTC risk metric videos have run since 2020.
- **"The final rotation" series (2024–25):** "Bitcoin Dominance: The Final Rotation is About To Begin / Continues / The Grueling Final Rotation", and "The Bitcoin Dominance Train (To 66%?)".

### 2.8 Macro: Fed, liquidity, labour, curve, dollar, inflation, equities, business cycle
- **QT and balance sheet.** BTC topped about 2 months before QT ended in both 2019 and 2025 (QT ended 2025-12-01), and before the balance sheet resumed growth. "Last cycle altcoins collectively bottomed against Bitcoin when quantitative tightening ended." The QT period means **rising BTC.D** ("Bitcoin Dominance and Monetary Policy").
- **Policy stance vs. neutral.** He uses **Fed funds − 2Y Treasury yield** as a restrictiveness gauge (the 2Y is his proxy for neutral). Durable alt rallies happened when the gap went **below zero**. That had not happened this cycle as of Feb 2026, which in his view explains rising ex-stables dominance. https://rosetta.to/u/intothecryptoverse/bitcoin-dominance
- **Liquidity risk model (proprietary):** policy rates, yield curve, dollar strength, central-bank liquidity, funding-stress proxies. He says M2 is a poor gauge and prefers "global net liquidity". An alt season needs this model "back near its lows" (very loose). https://rosetta.to/u/intothecryptoverse/why-alt-season-never-happened
- **Rate cuts.** Cuts are "typically not the most bullish thing for risk assets" because the Fed cuts into weakness. BTC topped before the first cut in 2019. "The market will tend to bottom out close to the last rate cut." Three cuts came around the top in both 2019 and 2025. In Aug 2024 he said about 200 bp of cuts might be needed to break BTC's downtrend.
- **"The Fed pivots when something breaks" / labour market.** Tight policy persists until labour data or financial stress forces a pivot. He tracks the unemployment rate, claims, JOLTS openings per unemployed and payroll revisions. "A Fed forced to tighten into stalling payrolls is the policy error that has historically shortened late cycles" (Aug 2026 memo). Older series: "Unemployment, Recessions, and Stock Market Bottoms", "Macroeconomics: Yield Curve, Inflation, Unemployment, Stocks, and Recessions".
- **Yield curve and the 10Y.** Recessions follow inversion and then un-inversion ("Recessions and The Yield Curve", "S&P 500 ROI After Yield Curve Inversion"). "Bitcoin finds the bottom when the 10-year yield tops." In Sept 2026 he highlighted **bear steepening** (10Y 5.29%, 30Y 5.64%).
- **Dollar (DXY).** A rising dollar means tighter liquidity and is bad for alts. He watches DXY breakouts (Sept 2026: invalidation if DXY breaks above 101.8). His Sept 2026 error was assuming a hike plus a stronger dollar would immediately sink BTC. In fact BTC rose with the dollar.
- **Inflation:** CPI/PCE prints are each covered in a video. Energy/oil is treated as the inflation swing factor in 2026 (Hormuz).
- **Equities / business cycle.** "Historically, the cycle low has formed during the equity correction, not ahead of it." A 10–20% S&P correction could be the catalyst for BTC < $60k. He calls 2026 "late business cycle" ("Bitcoin in a Late Business Cycle Environment", 2026-03-27). Rotation chain under tight liquidity: alts → BTC → S&P → gold. ISM appears only occasionally on the free channel (a channel search for "ISM" returned just 4 videos), so do not over-weight it as "his" indicator.
- **Recession composite:** "Macro Recession Risk" on ITC. The Aug-2026 memo gives **0.024** ("the recession cluster has not formed") and scenario weights of 65% late-cycle / 20% policy-error correction / 15% recession. https://benjamincowen.com/reports/the-balance-of-risks-august-2026

### 2.9 On-chain
**Realized price** (cost basis; ~$53k in 2026). "Every prior midterm-year bear market bottomed below that line." He also uses **balanced price** (~$37.7k; prior lows printed beneath it), **MVRV Z-score** ("bouncing rather than resetting below zero" means an incomplete reset), **% supply in profit/loss** (the crossover marks entry into a bottoming window), the **Puell Multiple** (~0.3 at prior bottoms vs 0.375 in Nov 2022), and **ETF holdings** (rolled over in 2026). Sources: July 2026 memo; Forklog 2022-11-28 https://forklog.com/en/news/analyst-outlines-timing-for-bitcoins-bottom ; Mitrade/BeInCrypto 2026-09-08 https://www.mitrade.com/insights/news/live-news/article-3-2067088-20260908

### 2.10 Social risk (sentiment)
"Bitcoin: An Improved Social Risk Metric" (2026-03-31) gives the inputs: **X/Twitter follower counts** (L1s, exchanges, analysts), **YouTube total daily views and subscriber counts across a set of crypto channels** (~500k views/day now vs **3–4M/day in 2021**), **Coinbase app-store rank** (new), and **Google Trends "Bitcoin"** (new). Normalisation and weights are not disclosed. It has trended down since Nov 2024. Falling social interest coincides with rising BTC.D. "This is not about calling exact tops or bottoms." He colour-codes price by social interest to show that the 2025 top came **on apathy**. https://rosetta.to/u/intothecryptoverse/bitcoin-an-improved-social-risk-metric ; "Bitcoin Social Risk: Why Retail Never Returned" (2025).

### 2.11 Evidence classification of the tools and structural claims

| Claim / tool | Label | How checked, or what would check it | Source tier |
|---|---|---|---|
| BTC tops in Q4 of the post-halving year (2013, 2017, 2021, 2025) | **(a) VERIFIED** | Daily-close maxima: 2013-12-04, 2017-12-16, 2021-11-08, 2025-10-06. All in Q4 | P2 (2026-05-26 video), S |
| Bottom→top ≈ 1,060–1,068 days | **(a) VERIFIED** | 1,067 / 1,059 / 1,062 d (CoinMetrics closes) | S (CMC), P2 |
| Bear market ≈ 1 year; low ≈ 364–406 d after top | **(a) VERIFIED for 2014/2018/2022** (406/364/366 d); **2026 so far deviates** (267 d to the Jun-30 close low) | CoinMetrics closes | P2, S |
| Cycle lows fall in the midterm year's 2nd half, after the November election (2014→Jan-2015, 2018-12, 2022-11) | **(a) VERIFIED** for history (2014-11-04→2015-01-14; 2018-11-06→2018-12-15; 2022-11-08→2022-11-09 close low). 2026 ⏳ | CoinMetrics closes + election dates | S (Benzinga 2026-10-29 snippet) |
| Midterm-year H1 is weak ("ignore Bitcoin in H1 of the midterm year") | **(a) VERIFIED 4/4**: H1 return 2014 −12%, 2018 −54%, 2022 −58%, 2026 −33% | CoinMetrics | P2 (2026-05-29) |
| June low → July rally in midterm years | **(a) partly**: July +21% (2018), +21% (2022), +7% (2026), but −9% (2014) → 3/4 | CoinMetrics | P2 |
| Final Q4 low in midterm years | **(a) VERIFIED 3/3 historically**: from Sep-30, Q4/Jan min was −55% (2014), −52% (2018), −19% (2022). 2026 ⏳ | CoinMetrics | P1 memo, P2 |
| "BTC fell 15–18% in every prior midterm August" (July-2026 memo) | **(a) FALSE as stated**: Aug 2014 −17.8%, **Aug 2018 −9.1%**, Aug 2022 −14.3%; Aug 2026 **+24.9%** | CoinMetrics | ⚠ S-low only (datawallet paraphrase of the memo) |
| Every prior cycle low printed below realized price | **(a) VERIFIED**: min MVRV 0.56 (2015), 0.69 (2018), 0.75 (2022). 2026 min 1.10 (never below). Realized price at the 2026 low ≈ $53.1k, now ≈ $54.1k | CoinMetrics CapMVRVCur | P1 memo, S |
| 50W SMA ≈ $86.5k in mid-July 2026 (invalidation level) | **(a) VERIFIED**: computed 50W SMA on 2026-07-19 = $86,513 | CoinMetrics weekly closes | P1 memo |
| BMSB = 20W SMA + 21W EMA; BTC "loses then regains" it | Definition **(a)** reproducible. Current state (2026-10-25 close $80.0k vs 20W $72.4k / 21W-EMA $76.5k / 50W $76.0k): **BTC is above all three** | CoinMetrics | P1 titles, S (Coin Bureau) |
| Rule: 2 consecutive weekly closes < 50W SMA ⇒ cycle over | **(a) backtested on 4 tops**: triggered 2014-08-24 ($508; top $1,135, low $176), 2018-06-03 ($7,702; top $19.6k, low $3.2k), 2022-01-09 ($41.9k; top $67.5k, low $15.8k), **2025-11-23 ($86.9k; top $124.8k, low so far $58.5k)**. Always exited well above the eventual low, but late (−38% to −61% below the top) | CoinMetrics | P2 (2025-10-14 video) |
| Log-regression all-data fair value ≈ $33–34k (Feb 2022) | **(a) VERIFIED** ($33,847) | Own OLS fit | P2 |
| Non-bubble fair value ≈ $20k (Feb 2022) | **(b)** | Needs his bubble-exclusion rule | P2 |
| Diminishing returns (ROI per cycle shrinking, shallower drawdowns) | **(a) VERIFIED** (112×→21×→7.9×; −84.5%→−83.8%→−76.7%→−53.1%) | CoinMetrics | P1 report 2020, P2 |
| Lengthening cycles | **(a) FALSIFIED** (low-to-low 1,431 then 1,425 d, i.e. not lengthening) | CoinMetrics | P1 titles 2020–22 |
| Asymmetric quantile model (Q1 ≈ $62k in May 2026; tops at ~75th pct) | **(b)**: needs his PDF spec. My simpler power-law residuals put tops at 98.5/91.5/66.5 pct, consistent in direction | Re-fit quantile regression | P1 report, P2 |
| BTC topped ~2 months before QT ended / balance sheet began growing (2019, 2025) | **(a) VERIFIED for 2025**: top 2025-10-06; Fed announced QT end 2025-10-29 (P1 video "The Fed Announces QT Will End in December", 2025-10-30); WALCL trough 2025-12-03 then rising. 2019 leg is **(b)** (needs WALCL 2019; QT ended Aug-2019, top 2019-06-26) | FRED WALCL | P2, S |
| Three Fed cuts around the 2025 top | **(a) VERIFIED**: upper bound 4.50→4.25 (2025-09-18), →4.00 (10-30), →3.75 (12-11) | FRED DFEDTARU | P2 |
| Fed hiked Sep 2026; held Oct 28 | **(a) VERIFIED**: upper bound →4.00 on 2026-09-17; unchanged to 2026-10-29 | FRED | P1 memo, S |
| 10Y ≈ 5.29% (Sep 30 2026) | **(a) VERIFIED** (5.29; 2026 max 5.31 on 10-05; 4.99 on 10-27) | FRED DGS10 | P1 memo |
| "BTC rose alongside the dollar" (his Sep-2026 error) | **(a) VERIFIED with a proxy**: broad USD index (DTWEXBGS) 118.9→121.0 and BTC $76.1k→$83.6k between 2026-09-16 and 09-30. DXY itself **(b)** (ICE data) | FRED, CoinMetrics | S-low ⚠ (KuCoin flash) + P1 title "Where I Went Wrong" |
| Fed funds above 2Y = restrictive; FF−2Y had not gone < 0 this cycle (Feb 2026) | **(a) VERIFIED**: FF−2Y = +0.24 on 2026-02-16 (−0.09/−0.10 in 2020–21). **Caveat:** by Jun–Oct 2026 FF−2Y turned **negative (−0.43, −0.82)** because the 2Y priced *hikes*, so the sign alone is ambiguous as a "loose policy" signal | FRED DFF, DGS2 | P2 |
| BTC dominance ≈ 59–60% incl. stables, ≈ 65–67% ex-stables | **(a) VERIFIED today**: CoinGecko 2026-10-29: BTC 59.46%; ex-USDT/USDC 65.5%. History (60% by late 2024, ~65–66% mid-2025, "ex-stables uptrend intact") **(b)**: needs daily TOTAL & stablecoin caps (CoinGecko Pro / CMC historical / TradingView CRYPTOCAP:BTC.D, USDT.D) | CoinGecko | P1 X, P2, S |
| ETH/BTC "ongoing collapse" from 2023 | **(a) VERIFIED**: weekly close 0.0626 (2023-09-18 wk) → 0.0498 (Dec 2023) → 0.0319 (Nov 2024) → **0.01766 low (week of 2025-04-21)** | Binance ETHBTC | P1 titles 2023-07-05, 2023-09-19 |
| "Alts bottom vs BTC around the end of QT" (2019 precedent) | **(a) partly**: ETH/BTC 2019 low = week of 2019-09-02 (0.0162), about one month after QT ended (Aug 2019). In 2025, ETH/BTC low was Apr 2025 (before QT end), with a higher low 0.0253 (Jun 2026), so far ✓ | Binance | P2 (2025-10-14) |
| Alt seasons need loose liquidity + BTC ATH + euphoria | **(c)** as causal theory. Partly testable **(b)**: needs TOTAL2/BTC history vs FF−2Y, WALCL, social data | — | P2 |
| Risk metric, social risk, liquidity risk model, Macro Recession Risk composite | **(c) proprietary**, with approximations possible. Social inputs are listed (P2) but weights are not | — | P2, ITC site |
| Narrative analogues ("2026 rhymes with late 2018"), scenario probabilities (65/20/15; "65% low ahead") | **(c) unverifiable opinion**. Only scorable after the fact | — | P1 memos, S |

---

## 3. Recurring theses (BTC vs alts, tops and bottoms)

1. **Dominance rises during QT and restrictive policy, whatever BTC/USD does.** "btc.d goes up regardless during QT." Under tight liquidity, leadership narrows and moves up the quality ladder (alts→BTC→large-cap equities→gold).
2. **Alt seasons need (a) loose liquidity (QE or near-zero real policy gap), (b) BTC at new ATHs, (c) retail euphoria (social risk high).** Without euphoria "there's no one left to sell the altcoins to". 2021 had all three. 2024–25 had only (b), so alt season never came.
3. **ALT/BTC pairs bottom around the end of QT** (2019 precedent) and then retest for a year or more. BTC pairs bottom before USD pairs.
4. **BTC tops in Q4 of the post-halving year and bottoms about a year later** (Q4 of the midterm year). Bear markets last about a year. Cycle-bottom crashes historically came *after* the midterm elections.
5. **Topping on apathy (2019, 2025) still produces a bear market.** A "time-based capitulation" can substitute for a deep "price-based" one.
6. **Diminishing returns on both sides:** lower ROI per cycle, shallower drawdowns, tops reaching lower quantiles (the 75th, not the 99th).
7. **Rate cuts are not automatically bullish:** cuts come into weakness, and markets bottom near the last cut. Hikes are not immediately bearish either; he learned this in Sept 2026.
8. **Bitcoin needs a macro catalyst (actual liquidity) more than narratives.** ETFs, corporate treasuries and a strategic reserve did not prevent the 2026 bear market.
9. **Process over prediction:** DCA, risk bands, reacting to weekly closes; "you don't have to predict what happens; reacting is better".

---

## 4. Track record (2018–2026): dated calls scored against market data

Verdict key: ✅ hit · ◐ partial (right direction; wrong magnitude or timing) · ❌ miss · ⏳ open. **Evidence:** (a) verified against data (how) / (b) checkable but not checked (what data) / (c) unverifiable. **Tier:** P1 / P2 / S / S-low (⚠ = only S-low support). Prices are CoinMetrics daily closes unless stated otherwise.

| Date (tier) | Call | Outcome vs data | Verdict | Evidence |
|---|---|---|---|---|
| 2020-06-09 (P2) | Valley-to-valley ~166→200 weeks; next ~270 weeks (lengthening) | Next low-to-low = 1,425 d ≈ 204 weeks | ❌ | (a) CoinMetrics |
| 2021-05-16 → 2021-12-24 (P1 titles) | Lengthening-cycle theory; "Market Cycle Has Now *Unofficially* Lengthened" (**2021-11-19**) | Cycle top close 2021-11-08 ($67.5k); 2022 = bear market (−76.7%) | ❌ (titles only; exact claim inside the video is (b)) | (a) price; (b) transcript |
| Early 2021 (⚠ S-low) | "No parabolic 2021; bull cycle extends into 2022" | As above | ❌ | (a) price; source quality low |
| 2021-04-11 (P1 title) | "Bitcoin: The Pi Cycle Top Has Signaled" | 2021-04-13 close $63.4k → 2021-07-20 $29.8k (−53%), but not the cycle top (Nov) | ◐ (good local de-risk signal) | (a) price; (b) what he concluded |
| 2022-01/02 (P2) | Log-regression fair value $33–34k; non-bubble FV ≈ $20k | All-data FV reproduced ($33,847). Bear low $15.8k, below the non-bubble FV, as his band logic implies | ✅ (method) / ◐ (as a target) | (a) own fit + price |
| Jan 2022 (⚠ S-low, Benzinga snippet) | Likely bottom ~$30k, "worst case" ~$20k | Low $15.8k | ❌ (depth) | (a) price |
| 2022-05-07 (P1 title) | "Market Cycle Theory (No Lengthening Cycles)": returns to the 4-year clock | Low 2022-11-09, 1,425 d after the 2018 low | ✅ (correction) | (a) |
| 2022-05-18 (P1 title) | "Bitcoin Dominance – Altcoins Remain High Risk" | ETH/BTC 0.067 (May) → 0.049 (Jun) → 0.086 (Sep, Merge) → 0.072 (Dec): whipsaw | ◐ | (a) Binance ETHBTC |
| 2022-11-28 (S, Forklog) | Bottom ≈ Dec 25–27, 2022; ~1-year bear; Puell ≈ 0.3 at bottoms | Close low 2022-11-09 (≈ 7 weeks earlier); never undercut | ◐ (window right, date early) | (a) price; Puell (b) |
| 2023-07-05 & 2023-09-19 (P1 titles) | "ETH/BTC: The Coming Collapse?" / "Ongoing Collapse"; ~0.032 target (S) | 0.064 → 0.0319 (Nov 2024) → 0.0177 (Apr 2025) | ✅ | (a) Binance |
| 2023 H2 (S, Cointelegraph quoting him) | 2019 analogue: BTC stalls < $35k, sideways into 2024. **His self-declared biggest miss** | Sep-30-2023 $27.0k → Dec-31 $42.2k → Mar-2024 $73.1k | ❌ | (a) price |
| Repeated 2023–25 (P2/S) | Cycle top in Q4 2025 | Top close 2025-10-06 ($124.8k), day 1,062 | ✅ | (a) |
| Apr 2024 (⚠ S-low) | Summer correction | 2024-03-13 $73.1k → 2024-09-06 $53.8k (−26%) | ✅ | (a) price |
| 2024-08-17 (S, Cointelegraph quoting interview) | BTC.D "final move" to ~60% by Sep/Dec 2024; not back to 70% | Today 59.5% (incl. stables), 65.5% ex-stables. History of 60% in late 2024 / ~66% mid-2025: **not checked** | ◐/⏳ | (b) needs BTC.D daily history |
| 2024-09-23, 2024-10-30, 2024-11-08 (P1 titles "Finding the Bottom", "When Will ETH/BTC Bottom", "Is the Bottom In?"); S: floor 0.03–0.04 | ETH/BTC bottoming at 0.03–0.04 | Went to **0.0177** (Apr 2025), −55% below the floor | ❌ | (a) Binance |
| 2024-10-15 (P1 X) | Keep the portfolio BTC-heavy through the dominance uptrend; BTC.D tops ~60% | BTC-heavy beat alts: ETH/BTC 0.0388 (Sep-30-2024) → 0.0290 (Oct-2026) | ✅ (strategy) / ◐ (the 60% cap was exceeded ex-stables) | (a) ETH/BTC; (b) BTC.D |
| 2025-02-24 (P1 title) | "The Bitcoin Dominance Train (To 66%?)" | Ex-stables 65.5% today; mid-2025 peak not checked | ⏳/(b) | (b) BTC.D history |
| 2025-03-10 (P1 title) | "Bitcoin Falls Below The Bull Market Support Band" | Low 2025-04-08 $76.4k, then a new ATH in Oct 2025: the BMSB break was a mid-cycle shakeout | ◐ (signal whipsawed) | (a) |
| Sep 2025 (⚠ S-low/Benzinga headline) | "Final act in Q4 could lift BTC beyond $130k" | Peak close $124.8k (intraday ≈ $126k) | ◐ (timing ✓, level ✗) | (a) |
| 2025-10-14 (P2) | Rule: two weekly closes < 50W ⇒ exit; BTC.D up either way; ETH/BTC low likely Apr 2025 | Triggered 2025-11-23 at $86.9k (top $124.8k; later low $58.5k). ETH/BTC higher low 0.0253 (Jun 2026) > 0.0177 | ✅ | (a) |
| Oct 2025 (⚠ S-low, datawallet) | ETH ≥ $5,300 | ETH max close $4,831 (2025-08-22); $2,357 now | ❌ | (a) CoinMetrics ETH |
| 2025-11-03/04 (S-low Daily Hodl quoting X) | "Alts will bleed to BTC" (−30% more) | ETH/BTC 0.0367 (Oct-13-2025) → 0.0253 (Jun 2026, −31%) | ✅ | (a) Binance |
| 2025-11-19 (P1 X) | Bear goggles on unless the 50W SMA is reclaimed within a week | Not reclaimed until 2026-09-20 | ✅ | (a) |
| 2025-12-05 / 12-15 (P1 titles "A Different Kind of Bear Market?", "The Bear Market Blues") | 2026 is a bear year; bottom ~Oct 2026 (S) | Low (so far) 2026-06-30 $58.5k; drawdown −53% | ✅ (bear) / ◐ (timing) | (a) |
| 2026-02-13 (P1 title "Where Bitcoin Will Bottom"); Feb–May (S) | Rally to the May high is counter-trend; Feb low will break | Feb-05 $63.5k → May-10 $82.3k (+30%) → Jun-30 $58.5k (new low) | ✅ | (a) |
| 2026-05-26/27 (P2; S CMC/247wallst) | Revisit ~$60k; base-case low Oct 2026 | $58.5k reached on 2026-06-30 | ◐ (price ✓, month ✗ so far) | (a) |
| 2026-05-29 (P2) | H1 weak; June low; July rally; final Q4 low | H1 −33% ✓; June low ✓; July +7% ✓; Q4 ⏳ | ✅/⏳ | (a) |
| 2026-07-15 (P1 memo) | Bottom-watch; patience; invalidation = sustained weekly reclaim of 50W (~$86.5k) | 50W verified at $86.5k. BTC reclaimed the falling 50W on 2026-09-20 ($81.2k vs 50W $78.8k) → thesis invalidated by his own rule | ❌ | (a) |
| Jul 2026 (⚠ S-low only) | "BTC fell 15–18% in every prior midterm August"; ~$44k floor | The premise is false for 2018 (−9%); Aug 2026 +25% | ❌ | (a) |
| 2026-08-15 (P1 memo) | 65/20/15 scenario weights; bottom-watch near $63k | — | (c) | unverifiable probabilities |
| 2026-09-08 (S, BeInCrypto via Mitrade) | "65% chance the low is in the future"; realized price ~$53k | Realized price verified ($53–54k). BTC broke the May high on 2026-09-21 | ⏳ (probabilistic) | (a) level; (c) probability |
| 2026-09-21/22 (P1 titles "Bitcoin Breaks the May High (I Was Wrong)", "Bitcoin: Where I Went Wrong") | Admits the bear call failed; "burden of proof shifted to bears" | Weekly closes $81.2k (09-20) → $84.4k → $86.5k (10-04) | (honest correction) | (a) |
| 2026-09-25 (P1 X) | Acceptance back below the May high = "massive fakeout" before Q4 weakness | Weekly closes $83.6k (10-11), **$81.9k (10-18), $80.0k (10-25)**: two closes below $83k ✓. The Q4 weakness itself ⏳ | ⏳ | (a) |
| 2026-10-24/26 (P1 X roadmap) | Fakeout → Fed no hike (10-28) → hot PCE (10-29) → oil ~$120 → 10Y back to 5.3% → … ; void above $83k | Steps 1–2 ✓ (FRED: upper bound unchanged at 4.00). 10Y now 4.99% (not 5.3%). PCE/oil ⏳ | ⏳ | (a) for the completed steps |

**Scorecard of the dated, data-checkable calls above (my tally, excluding ⏳ and (c)):** **12 hits, 6 partial, 9 misses** (rows with a split verdict are counted at their first verdict; the two lengthening-cycle rows overlap). This is not a random sample: it is the calls that the media and I could find. Hits cluster in **structural/relative** calls (cycle-top timing, BTC > alts, ETH/BTC bleed, diminishing returns, 50W exit, midterm H1 weakness). Misses cluster in **levels** (2022 depth, ETH/BTC floor, ETH $5.3k) and **macro-narrative tactics** (Q4 2023, lengthening cycles, Aug–Sep 2026).

**Claims I could only find in S-low sources (treat as unconfirmed):** the "15–18% every midterm August" stat (and it is wrong on the data); "ETH ≥ $5,300"; "Altseason index 37 / dominance 60.66% in Apr 2026"; "$44k floor" (also in S BeInCrypto); "early 2021: no parabolic 2021"; the "Apr 2024 summer correction" date; Benzinga Jan-2022 "$30k bottom / $20k worst case" (snippet only); "BTC rose with the dollar" (KuCoin flash; but corroborated by his own P1 video title and by FRED/price data).

**Assessment.**
- **Strengths.** Multi-year *structural* calls: Q4-2025 top timing, BTC > alts through QT, ETH/BTC bleed, about a 1-year bear market, diminishing returns, the 50W exit rule. These are mostly **rules about relative performance and regime**, exactly what a BTC-denominated agent needs.
- **Weaknesses.** (a) Depth and level targets (the 2022 low, the ETH/BTC floor, ETH $5.3k, BTC $130k+). (b) Intra-year macro narrative calls (Q4 2023; Aug–Sep 2026, when the hike→dollar→BTC-down chain was wrong). (c) Abandoned hypotheses (lengthening cycles). (d) He sometimes gives probabilities that he revises quickly (65% bear on 9-08, "I was wrong" on 9-21, bear again on 10-25), which makes scoring hard. Treat his **regime rules** as signals and his **point forecasts** as noise.
- **Incentive note.** He runs a paid platform and a conference (Miami, 2026-11-21). The cycle narrative is also his brand, so expect some status-quo bias toward the 4-year cycle. To his credit, he publicly owns misses ("Bitcoin: Where I Went Wrong").

---

## 5. Current view (as of 2026-10-29)

- **Market context (a: verified on CoinMetrics/FRED/CoinGecko unless noted):** BTC close $81.2k (10-28); weekly closes $81.9k (10-18) and $80.0k (10-25); ATH close $124.8k (2025-10-06, intraday ≈ $126k per media); 2026 close low $58.5k (06-30); realized price $54.1k (MVRV 1.50). Price is **above** the 50W SMA ($76.0k) and the BMSB (20W $72.4k / 21W-EMA $76.5k), so his trend filters read *bullish* while his roadmap reads *bearish*. The bearish read rests on the failed May-high/$83k retest. BTC.D 59.5% (ex-USDT/USDC 65.5%). FF upper bound 4.00%; 2Y 4.70%; 10Y 4.99%; UNRATE 4.2% (Sep). Fed: QT ended 2025-12-01; cut 3× in late 2025 to 3.50–3.75%; Powell stepped down (May 2026); **hiked 25 bp on 2026-09-16 to 3.75–4.00%**; **held on 2026-10-28 (10-2, two dissents for a hike)**; markets price a December hike at about 82% (Polymarket per coverage). 10Y ≈ 5.3%, DXY ≈ 101, WTI $90+ with Hormuz risk, S&P near records with weak breadth. BTC.D ≈ 60–61% headline / ~67% ex-stables.
- **His stance:** after the Sept 21 mea culpa, he set **$83k** as the line. Two weekly closes below it mean "fakeout confirmed" ("Bitcoin: Bears Regaining Control", 2026-10-25). The 10-24 roadmap is a sequence (fakeout → Fed no hike → hot PCE → oil spike → long-end yields up → …), "void if Bitcoin gets and holds back above $83k". He emphasises that the 2014/2018/2022 cycle-bottom drops came after midterm elections (Nov 3, 2026), and that the realized price has not been broken. His low-to-low clock points to **late Oct–Nov 2026**. Latest uploads: "Bitcoin: Post-FOMC" (2026-10-28), "NFA Live! Bitcoin Losing Momentum? Fed Fallout & Midterm Market Risks" (2026-10-29).
- **Macro base case (Sept 30 memo):** "2026 rhymes more with late 2018 than with 2022". Any correction is a growth scare within an intact business cycle, not a recession. A Q4 BTC drawdown is a risk to watch rather than the memo's base case. He has been constructive on **2027** ("early 2027 likely to be strong", CoinTurk 2026-09-25).
- **BTC vs alts now:** no alt season while policy is restrictive and DXY firm. The ex-stables dominance uptrend is "intact". He expects dominance to fade only once loose liquidity returns, perhaps 2027–29, and after BTC makes new highs. ETH/BTC low likely April 2025, but alts remain "oscillators at best".

---

## 6. Quantitative and reproducible vs. discretionary

| Component | Reproducible? | Public data needed | Notes |
|---|---|---|---|
| Cycle clock (halving dates, top/bottom day counts, midterm calendar) | **Yes** | BTC daily OHLC 2010→ (CoinMetrics community, Bitstamp/Coinbase, Yahoo BTC-USD from 2014), halving dates, US election calendar | Only 3–4 cycles; date of "the low" depends on the exchange |
| BMSB (20W SMA / 21W EMA), 50W/100W/200W SMA, 200D, weekly-close rules | **Yes** | Weekly closes (Sunday 00:00 UTC, as TradingView) | Specify the weekly-close convention exactly |
| Log-regression bands / fair value | **Yes (approx.)** | BTC daily history from 2010 | Non-bubble data selection is subjective |
| Asymmetric quantile bands | **Yes (approx.)** | Same, plus quantile regression (statsmodels QuantReg) | Full method in his PDF |
| Risk metric (0–1) | **Approximation only** | Price, MAs | Must use expanding normalisation; his exact formula is proprietary |
| Dominance incl./excl. stables, USDT.D, TOTAL2/TOTAL3, ALT/BTC | **Yes** | CoinGecko `/global` and historical market caps; CoinMarketCap historical; TradingView CRYPTOCAP:BTC.D, USDT.D, TOTAL2, TOTAL3 | Definitions changed over time (stablecoins); survivorship in alt baskets |
| Top-100 advance/decline | Yes (effort) | Point-in-time top-100 constituents (CoinGecko historical snapshots) | Survivorship risk |
| Realized price, MVRV-Z, % supply in profit, Puell | **Yes** | CoinMetrics community (CapRealUSD, CapMVRVCur), Glassnode/LookIntoBitcoin/BGeometrics, bitcoin-data.com | |
| Fed funds, 2Y, 10Y, curve, UNRATE, claims, JOLTS, CPI/PCE, Fed balance sheet (WALCL), RRP, TGA, DXY, ISM | **Yes** | FRED (+ **ALFRED vintages** for point-in-time data), ICE DXY (or FRED DTWEXBGS), ISM PMI | Use release dates, not reference periods |
| Social risk | **Partial** | Google Trends (pytrends), YouTube Data API channel stats (views and subs over time only going forward, history via Social Blade), Coinbase app rank (paid: Sensor Tower / appfigures) | Historical YouTube view series hard to reconstruct |
| Liquidity risk model, Macro Recession Risk, composite on-chain risk | **No (proprietary)** | Build own: z-scores of (FF−2Y), curve, DXY trend, net liquidity (WALCL−RRP−TGA), credit spreads (BAA10Y / HY OAS) | Weights unknown |
| "Which analogue year are we in" (2018 vs 2019 vs 2022), scenario probabilities, narrative chains | **Discretionary** | none | His main source of misses |

---

## 7. Candidate rules and signals for a BTC-denominated agent

**Common backtest protocol.** Run the equity curve in **BTC units** (start = 1 BTC). Assets: BTC, a USD stablecoin (USDC; pre-2018 use USD cash as proxy), ETH, and an alt basket (point-in-time top-N ex-stables, rebalanced monthly, survivorship-free). Weekly decision cadence at the Sunday close; execute next open; fees 10–20 bp plus slippage. Report BTC-denominated CAGR, max drawdown in BTC terms, time in market, turnover, and the **number of independent cycle events** behind each result. Validation: **leave-one-cycle-out** (2013–15, 2017–18, 2021–22, 2025–26) plus walk-forward. Parameters are fixed a priori from Cowen's stated values; only small neighbourhoods are swept, as a robustness check, never for optimisation. Macro data must be point-in-time (ALFRED).

Note: in BTC terms, **holding stablecoins is a short-BTC position**. Rules that move to stables gain BTC only if they re-enter lower. Every "exit" rule therefore needs an explicit re-entry rule.

| # | Rule (draft) | Data | How to backtest | Overfitting risk |
|---|---|---|---|---|
| R1 | **Default: 100% BTC, zero alts.** Alts allowed only when the **Alt Gate** is open (R2). | — | Baseline vs HODL BTC, by construction ≈ benchmark | None |
| R2 | **Alt Gate** (all required): (a) BTC made a new ATH within the last 13 weeks; (b) policy loose: [Fed funds − 2Y ≤ 0 **and** 2Y 13-week change ≤ 0, so that a negative gap caused by hikes being priced in, as in Jun–Oct 2026, does not count] **or** balance sheet growing (WALCL 13-wk Δ > 0), **and** no hike in last 6 months; (c) BTC.D ex-stables below its 20W SMA **and** TOTAL2exStables/BTC above its 20W SMA; (d) DXY below its 50W SMA. Max alt weight 25–35%, ETH first. | FRED (DFF, DGS2, WALCL), DXY, CoinGecko caps | Gate open/closed timeline 2013–2026; compare BTC-denominated returns of gate-on alt exposure vs always-BTC. Expect gate open ≈ H1 2017, late 2017–Jan 2018, 2020-Q4–2021 | **Medium-high**: only 2–3 alt seasons in history; conditions partly chosen with hindsight (2021). Keep thresholds coarse |
| R3 | **Alt exit:** close all alts (into BTC) on 2 consecutive weekly closes of TOTAL2exStables/BTC below its 20W SMA, **or** BTC.D ex-stables reclaiming its 20W SMA, **or** any Fed hike / QT start | Same | Measure BTC-denominated alt drawdown avoided vs alts held | Medium |
| R4 | **"BTC pairs bottom first":** never buy an alt whose ALT/BTC has not made a higher weekly low above its 20W SMA, even if ALT/USD looks cheap | ALT/BTC weekly | Event study on ALT/BTC vs ALT/USD bottoms 2015–2026 | Low-medium |
| R5 | **QT / hiking regime veto:** during QT or a hiking cycle (or FF − 2Y > +0.5pp), alt weight = 0 regardless of other signals | FRED | Count alt/BTC performance by regime | Low (economically motivated, many sub-periods) but regime n is small |
| R6-evidence | Quick check already done (§2.11): the plain "2 weekly closes < 50W" exit fired at $508 / $7,702 / $41.9k / $86.9k after the 2013/2017/2021/2025 tops, every time well above the subsequent low ($176 / $3.2k / $15.8k / $58.5k so far). That is a BTC-unit gain *if* re-entry happened near the low. With re-entry on "weekly reclaim of the 50W", the 2025–26 round trip was exit $86.9k → re-enter $81.2k (2026-09-20), only about +7% in BTC terms. Re-entry design dominates the result | | | |
| R6 | **Bear-regime de-risk (to stables):** in the **post-halving year Q4 or later**, two consecutive weekly closes below the **50W SMA** (or below BMSB *and* BMSB slope < 0) mean moving X% (e.g. 50–100%) of BTC to stables | BTC weekly | Backtest every cycle top (2013, 2017, 2021, 2025); also check false signals in mid-cycle drawdowns (2019, 2021 May–Jul, 2024 Aug) | **Medium**: 2021 mid-cycle would have whipsawed; the calendar condition reduces whipsaws but is itself fitted to 4 tops |
| R7 | **Re-entry ladder (stables → BTC):** buy back in tranches when ≥2 of: (a) cycle-clock window (≥ 300 days after the top, or within the 1,400–1,460-day low-to-low window); (b) price ≤ 200W SMA or ≤ realized price or ≤ quantile Q1 band; (c) MVRV-Z ≤ 0 / supply-in-profit < 50%; (d) risk metric (R9) < 0.2. **Force full re-entry** on a weekly reclaim of the 50W SMA after a 2-week hold, or by day 450 after the top | BTC, CoinMetrics, own quantile fit | Tranches of 25%; measure BTC gained vs HODL; sensitivity to tranche timing | **High** for (a) (n=3); lower for (b)/(c), which have more bottom observations. The forced re-entry caps the damage of a missed bottom (e.g. 2026 June low vs October base case) |
| R8 | **Midterm-year H1 rule:** in a midterm year, no *new* BTC buys from stables between Jan and June unless R7(b)+(c) both trigger; do the main accumulation in H2/Q4 | Calendar + R7 | Compare 2014/2018/2022/2026 | **High** (4 observations; he says it works ~70%) |
| R9 | **Risk-metric bands (approx.):** reconstructed 0–1 risk with expanding normalisation; risk > 0.8 → sell 10% of BTC per 0.05 increment into stables; risk < 0.3 → buy back. Only applies to the share not already governed by R6/R7 | BTC daily | Walk-forward with expanding min/max; compare static-normalised version to quantify look-ahead | **High** if exponent/normalisation is fitted on the full sample; mitigate with an expanding window and a fixed exponent |
| R10 | **Valuation cap:** if price > 75th percentile of the quantile model or > upper log-regression band, take 20–30% of BTC to stables; reload at the median band or by R7 | Own quantile fit | 2013, 2017, 2021, 2024–25 events | Medium (the model is fitted on the same data; use only the fit available at the time) |
| R11 | **Social-euphoria alt exit:** if Google-Trends "bitcoin" (or a YouTube-views proxy) > 80th pct of its 4-year range **and** BTC.D falling → rotate all alts to BTC within 2 weeks | pytrends, YouTube Data API (forward only) | 2017-12, 2021-05, 2021-11 events | High (few events; proxy differs from his index) |
| R12 | **Macro stress overlay (hold stables longer):** if UNRATE rises ≥ 0.5pp off its 12-month low (Sahm-type) **and** the curve is re-steepening from inversion, or HY spreads > 1.5× their 1-year average, delay R7 re-entry by 8 weeks unless R7(b)+(c) both hold | FRED (UNRATE, T10Y2Y, BAMLH0A0HYM2) | Only 2020 and 2022 provide real stress events in BTC history | High (very few events in BTC's lifetime); Cowen himself mis-timed macro→BTC links in Sept 2026, so cap its weight |
| R13 | **No point forecasts as triggers:** the agent never trades on an analyst's price target or "probability the low is in", only on rule states. Cowen's videos/memos can be ingested as a *sentiment-of-expert* feature, logged for later evaluation | Transcripts (see §8) | Track the hit rate of extracted claims vs outcomes over time | n/a |

**Rules to explicitly avoid (falsified or too discretionary):** lengthening-cycle timing; fixed ETH/BTC floors; "a rate hike is immediately bearish"; analogue-year selection (2018 vs 2019 vs 2022) as a trigger; level targets ($130k top, $44k floor).

**Overfitting checklist.** There are 3–4 BTC cycles and 2–3 alt seasons, so any rule with more than about 2 free parameters per signal is suspect. Prefer rules that (1) Cowen stated *before* the outcome (timestamped videos and tweets), (2) have economic logic (liquidity → risk appetite), (3) survive leave-one-cycle-out, and (4) are robust to ±20% parameter changes (20W vs 25W, 50W vs 40W/60W). ETFs and treasuries since 2024 may change behaviour: weight the last cycle and validate on paper trading from now on.

---

## 8. Getting his transcripts in bulk (method only; nothing downloaded)

### 8.1 Channel facts (checked 2026-10-29)
- Channel: **https://www.youtube.com/@benjaminjcowen**, ID **UCRvqjQPSeaWn-uEx-w0XOIg**, 1.02M subscribers, header "3.1K videos" (vidIQ: 3,184 incl. shorts/streams; ~1.2 uploads/day). Uploads playlist ID = `UU` + ID suffix → **`UURvqjQPSeaWn-uEx-w0XOIg`**.
- Captions: recent videos carry **English auto-generated (ASR) tracks** plus auto-translations. Examples checked: 21mBnslOLd0 "Bitcoin: Post-FOMC" (2026-10-28), bWdXPK3Hlok "Bitcoin: Bears Regaining Control" (2026-10-25), -eKtrrN5P48 "Bitcoin Dominance" (2026-10-12). Video descriptions are boilerplate links, so **the content is only in the speech**.

### 8.2 Playlists (from the channel's Playlists tab)
| Playlist | Videos | ID | Priority |
|---|---|---|---|
| Bitcoin | 1,434 | PL-094UzhjjywnMvIQVGr4Z_OXPgBPs8Kd | **High** (core) |
| Ethereum | 361 | PL-094Uzhjjyynv1-mVQyB14ixJFcbEFhq | High (ETH/BTC) |
| Macroeconomics | 169 | PL-094UzhjjywfZJ6A7Z4VA_UKnAdrPQup | **High** |
| Bitcoin: The Beauty Of Mathematics | 73 | PL-094UzhjjyywsqlHcL-JyyuwRsxfI7bA | **High** (models: log regression, quantiles, fair value) |
| Stock Market | 76 | PL-094Uzhjjyz1q-EibuOUJq2jjCjDSPwX | Medium |
| On-Chain Analysis | 49 | PL-094UzhjjyzLIHvvdzzjGk5bzJoiC9e7 | Medium-high |
| Precious Metals / Gold | 46 / 25 | PL-094Uzhjjyy-k4KAvoIn5v_u6PQgfh_p / PL-094UzhjjyylQKcvksOsTzBJAYODmCwm | Low-medium |
| Collaborations | 41 | PL-094UzhjjyxtIa3QoWy410Q5UC624LPw | Medium (e.g. PlanB S2F debate) |
| Modern Portfolio Theory | 12 | PL-094UzhjjyzCsWIxR2HX4p71IeYW04qf | Medium (allocation) |
| Cardano / Tesla / Real Estate / COVID / FOREX / Derivatives / ITC Parties / Big Bang | 110/18/9/4/3/1/4/4 | — | Low |

Most videos are **not** in any playlist (≈3.1k total vs ≈2.4k playlisted), so iterate the **uploads** list and classify by title.

### 8.3 Title-based series to prioritise (examples with IDs)
- **Bitcoin Dominance** (dozens, 2022–2026): -eKtrrN5P48 (2026-10-12), 3PCBcXqTx2g, VdCMIWRHkTs; "The Final Rotation" set 5I0bw-H8icE, q6WNUuy950U, 7R0ZPddqcTI, fkXRo-28qv0; muNTKBPSgsA "Dominance Train (To 66%?)"; sMzdMn62HXk "Bitcoin Dominance and Monetary Policy".
- **Altcoins and macro:** hJeSMZQuOec "Altcoins and the end of QT" (2025-10-15), rDYzbxeMWdY "Why Alt Season Never Happened" (2026-02-20), lrttkb_-O30 "Bitcoin, Altcoins, and Macro-Economic Conditions".
- **ETH/BTC:** mbPfOvUv1wA (2022 outlook), VHD_9PGegZU "The Coming Collapse?", PUkQaTS_hoo "Ongoing Collapse", HJ3Do3PYBQ4 "Finding The Bottom", F2oPMpC5z94, 7jmAa9cj1oY, plus ~10 "ETH / BTC" updates 2024–25, JG3Zz5PMAwU / 6qVAtj-h-2g (ETH↔BTC risk strategy).
- **Risk metrics:** Y_WtgM8nSHw, 0h_NnyTf_qI, ocQTqM4lL3k, dUTlgATPEfo, g_ryyK58svM "Bitcoin Risk Metric"; TG-vdV6iapI "Sticking to Your Risk Metric"; wNiqCnx9w2s / FM8o8OVo4-Q TOTAL market-cap risk; h7QLSd6Bj-U / fDyb_p_GsMA "Total Indicator Risk"; 2DUCJDmTOks "On-Chain Risk".
- **Social risk:** WwzQ6gjktHs "An Improved Social Risk Metric" (2026-03-31), gAf6tPzkcgg, 16l2PcW3Z4g "Why Retail Never Returned", plus ~20 "Bitcoin: Social Risk" updates.
- **Valuation models:** uFn3KUE-VTI "Asymmetric Tail Curvature…" (2026-05-30), Of8Plrq1lMU "Bitcoin Fair Value Logarithmic Regression", jy8CtyjA1WY "excluding bubble phases", TTZf2SB2jJs, ye2YDUGy8zQ, cwUj8cmY60g (TOTAL log regression).
- **Cycle theory:** Sn8-f7dR1D4 / WI03C0a0XD4 "Lengthening Cycles and Diminishing Returns", D10xWiu157A "Market Cycle Theory (No Lengthening Cycles)", sWXnUc8IMLs (with PlanB), XvrN23W8T10, bRDDpxTpWh4 "Market Cycle ROI"; 2026: "The Four Year Cycle Is Not Dead" (2026-05-26), dIa8HUYDNEY "Window of Weakness", X0OzhmuWbfg "Bitcoin's Midterm Year", fV6NzO02KH4 "Midterm Year Returns", se6UlLbDTEo "Bitcoin: Q4 2026" (2026-10-08).
- **Trend filters:** ~30 "Bitcoin: Bull Market Support Band" (KZ1Jro92t48 latest), 2026 "Bear Market Resistance Band" set, ulDJeCNJo3Y "Falls to the 200W", R7OmvePBwQU "The Bitcoin Realized Price", Di8YR9nX8Q8 "Using On-Chain Metrics To Identify Market Cycle Bottoms".
- **Macro:** 4qswdknHGR4 "Bitcoin and the End of QT", PvDskt21bnI "Fed Announces QT Will End in December", 9_OaUa3BXm4 / uqOaVW3YRNA / H7415H3Z424 (yield curve, unemployment, recessions), wydFXSSJsy4 "Unemployment, Recessions, and Stock Market Bottoms", eWHlzrBwx0Q "What Will A Future Fed Pivot Mean…", wBS1zsnHZkg "Bitcoin & The Unemployment Rate", tvGHykcAwoE / LxASUgDQb5o "Bitcoin and the Yield Curve", plus the monthly CPI / jobs / FOMC series.
- **Self-assessment (for the claim ledger):** RD1IMRMH6JU "Bitcoin Breaks the May High (I Was Wrong)", iWBLplyqhl4 "Bitcoin: Where I Went Wrong" (2026-09-21/22), and the recurring "Bitcoin: Dubious Speculation" (explicitly labelled speculative; tag these separately from regime analysis).

### 8.4 Methods
1. **Enumerate IDs** (no media download):
   `yt-dlp --flat-playlist --print "%(id)s\t%(title)s\t%(upload_date)s" "https://www.youtube.com/@benjaminjcowen/videos" > ids.tsv`
   (repeat for `/streams` and `/shorts` if wanted, or use the uploads playlist `UURvqjQPSeaWn-uEx-w0XOIg`). With the official **YouTube Data API v3**, `playlistItems.list` on the uploads playlist costs 1 unit per 50 videos, so about 64 calls for the whole channel, and also gives exact publish timestamps.
2. **Transcripts via yt-dlp:**
   `yt-dlp --skip-download --write-auto-subs --sub-langs "en,en-orig" --sub-format json3 --sleep-requests 1.5 --sleep-subtitles 3 --min-sleep-interval 2 --max-sleep-interval 6 -a ids.txt -o "%(upload_date)s_%(id)s.%(ext)s"`
   `json3` keeps word timings; `vtt` is fine too. Add `--cookies-from-browser chrome` if YouTube rate-limits (HTTP 429, "Sign in to confirm you're not a bot"). Keep yt-dlp updated (`yt-dlp -U`), because YouTube changes frequently.
3. **Transcripts via youtube-transcript-api (Python):** `pip install youtube-transcript-api`. In v1.x the call is `YouTubeTranscriptApi().fetch(video_id, languages=["en"])` (instance method; older 0.6.x used `YouTubeTranscriptApi.get_transcript`). It returns snippets with `text/start/duration`. Cloud/datacenter IPs are often blocked; the library supports proxy configs (e.g. `WebshareProxyConfig`). Throttle to about 1 request every 2–5 s, and expect about 3.2k videos to take several hours.
4. **Secondary shortcut:** rosetta.to/u/intothecryptoverse holds summaries plus transcripts for ~2,385 videos up to ~2026-06-11, which is useful for a first pass or for cross-checking. Fill the gap from mid-June 2026 onwards from YouTube.
5. **Processing notes:** ASR errors are systematic ("having"→halving, "congressional"→logarithmic, "BTC.D" garbled). Build a correction dictionary. Store `video_id, publish_ts, title, playlist(s), transcript, [claims extracted: asset, direction, horizon, level, conditional/probability, invalidation]`, which gives an out-of-sample **claim ledger** to score him going forward (and the agent's own use of his signals). Respect YouTube ToS: personal research use, no redistribution.

---

## 9. Source list (dates as published)

**Market data used for verification (pulled 2026-10-29):**
- CoinMetrics community API (BTC `PriceUSD`, `CapMrktCurUSD`, `CapMVRVCur` from 2010-07-18; ETH `PriceUSD` from 2016): https://community-api.coinmetrics.io/v4/timeseries/asset-metrics
- Binance ETHBTC weekly klines: https://api.binance.com/api/v3/klines?symbol=ETHBTC&interval=1w
- FRED series DFEDTARU, DFF, DGS2, DGS10, WALCL, UNRATE, DTWEXBGS: https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES>
- CoinGecko global snapshot: https://api.coingecko.com/api/v3/global
- YouTube watch-page metadata (exact publish dates of the cited videos).
- Scripts: /private/tmp/claude-501/pxscripts/verify.py, /private/tmp/claude-501/pxscripts/verify2.py (raw data in /private/tmp/claude-501/px/)

**Primary (Cowen):**
- benjamincowen.com reports index: https://benjamincowen.com/reports — July 2026 memo (2026-07-15) https://benjamincowen.com/reports/bitcoin-cycle-memo-july-2026 ; Aug 2026 (2026-08-15) https://benjamincowen.com/reports/the-balance-of-risks-august-2026 ; Sept 2026 (2026-09-30) https://benjamincowen.com/reports/the-triple-squeeze-september-2026 ; Quantile paper (2026-05-29) https://benjamincowen.com/reports/asymmetric-tail-curvature-in-bitcoin-price-quantiles ; Bitcoin Letters (2020-01-05) https://benjamincowen.com/reports/bitcoin-letters-2020
- ITC platform: https://intothecryptoverse.com/
- YouTube channel, playlists, search results, and video metadata for 21mBnslOLd0, bWdXPK3Hlok, eN6dpreDIk4, KZ1Jro92t48, -eKtrrN5P48, se6UlLbDTEo, RD1IMRMH6JU, iWBLplyqhl4, F5RZjBsFJ_g (fetched 2026-10-29): https://www.youtube.com/@benjaminjcowen
- X posts (timestamps decoded from IDs): 2024-10-15 https://x.com/benjamincowen/status/1846250939965231387 ; 2025-06-13 https://x.com/benjamincowen/status/1933345449236443499 ; 2025-11-19 https://x.com/intocryptoverse/status/1991250695232651378 ; 2026-09-18 https://x.com/benjamincowen/status/2101053560720863561 ; 2026-09-25 https://x.com/benjamincowen/status/2103486531302281636 ; 2026-10-24 https://x.com/benjamincowen/status/2113798791736299963 ; 2026-10-26 https://x.com/benjamincowen/status/2114535552523612377

**Video summaries (auto-transcript based):**
- rosetta.to channel index https://rosetta.to/u/intothecryptoverse ; "Four Year Cycle Is Not Dead" (2026-05-26) https://rosetta.to/u/intothecryptoverse/bitcoin-the-four-year-cycle-is-not-dead ; "Window of Weakness" (2026-05-29) https://rosetta.to/u/intothecryptoverse/bitcoin-the-window-of-weakness ; "Bitcoin Dominance" (2026-02-15) https://rosetta.to/u/intothecryptoverse/bitcoin-dominance ; "Improved Social Risk Metric" (2026-03-31) https://rosetta.to/u/intothecryptoverse/bitcoin-an-improved-social-risk-metric ; "Asymmetric Tail Curvature" (2026-05-30) https://rosetta.to/u/intothecryptoverse/bitcoin-asymmetric-tail-curvature-in-bitcoin-price-quantiles ; "Beauty of Mathematics Pt 70" (2026-05-07) https://rosetta.to/u/intothecryptoverse/bitcoin-the-beauty-of-mathematics-part-70 ; "Altcoins and the end of QT" (2025-10-15) https://rosetta.to/u/intothecryptoverse/altcoins-and-the-end-of-qt ; "Why Alt Season Never Happened" (2026-02-20) https://rosetta.to/u/intothecryptoverse/why-alt-season-never-happened ; "What Is The Fair Value?" (2022) https://rosetta.to/u/intothecryptoverse/bitcoin-what-is-the-fair-value ; topic page https://rosetta.to/u/intothecryptoverse/topic/computer-science
- "Bitcoin: Where in the Cycle Are We?" (2026-08-06) https://readray.ai/notes/en/bitcoin-20260813/bitcoin-where-in-cycle

**Secondary coverage:**
- Cointelegraph Magazine (2026-03-06) https://cointelegraph.com/magazine/bitcoin-four-year-cycle-dead-debate-bear-market-2026-benjamin-cowen ; Cointelegraph (2025-12-26) https://cointelegraph.com/news/why-bitcoin-setup-looks-more-like-2019-benjamin-cowen ; Cointelegraph (2024-08-18) https://cointelegraph.com/news/bitcoin-dominance-trading-altcoin-season-benjamin-cowen-crypto-trader
- CoinMarketCap Academy (~May 2026) https://coinmarketcap.com/academy/article/%20bitcoin-4-year-cycle-october-2026
- 24/7 Wall St (2026-10-06) https://247wallst.com/investing/cryptocurrency/2026/10/06/benjamin-cowen-said-the-cycle-would-bottom-bitcoin-near-60000-in-october-did-benjamin-cowen-predict-the-bitcoin-bottom-correctly/
- CoinTurk (2026-09-25) https://en.coin-turk.com/analyst-benjamin-cowen-outlines-key-triggers-for-bitcoin-direction-in-q4-2026/
- KuCoin flash (2026-09-23) https://www.kucoin.com/news/flash/bitcoin-analyst-admits-past-bear-market-prediction-was-incorrect ; KuCoin/Real Vision (2026-09-25) https://www.kucoin.com/news/insight/BTC/6ab6cc3074fd460007c566ba
- Mitrade/BeInCrypto (2026-09-08) https://www.mitrade.com/insights/news/live-news/article-3-2067088-20260908
- Digital Today/BeInCrypto (2026-04-15/17) https://www.digitaltoday.co.kr/cn/view/48639/bitcoin-bottom-may-still-lie-ahead-cowen-sees-trough-in-fall-2026
- COINOTAG (2026-10-25) https://en.coinotag.com/benjamin-cowen-bitcoin-btc-fake-breakout-83000-weekly-close ; Benzinga (2026-10, via search snippets) https://www.benzinga.com/crypto/cryptocurrency/26/10/62696461/bitcoin-drops-to-80000-after-fed-meeting-is-the-bear-thesis-playing-out ; https://www.benzinga.com/crypto/cryptocurrency/26/10/62587401/bitcoin-drops-to-80000-are-bears-back-in-control
- Daily Hodl (2025-11-04) https://dailyhodl.com/2025/11/04/crypto-analyst-benjamin-cowen-says-bitcoin-dominance-to-rise-as-altcoins-bleed-heres-his-outlook/ ; (2025-04-18) https://dailyhodl.com/2025/04/18/bitcoin-to-continue-massively-outperforming-altcoins-until-this-happens-according-to-analyst-benjamin-cowen/
- Forklog (2022-11-28) https://forklog.com/en/news/analyst-outlines-timing-for-bitcoins-bottom
- datawallet profile and track record (upd. 2026-08-27) https://www.datawallet.com/crypto/who-is-ben-cowen
- Coin Bureau (BMSB) https://coinbureau.com/news/bitcoin-never-below-40000-ever-again-why-its-possible
- Fed decision 2026-10-28: https://www.coincu.com/fed-holds-rates-3-75-4-bitcoin-gives-back-gain/ ; https://www.cryptotimes.io/2026/10/29/bitcoin-price-today-btc-near-80000-as-crypto-markets-react-to-feds-steady-rate-decision/
- TradingView community reconstructions: https://www.tradingview.com/script/H4iCbDci-Benjamin-Cowen-s-Simplified-Risk-Metric ; https://www.tradingview.com/scripts/benjamin/ ; https://it.tradingview.com/scripts/cowen ; https://www.tradingview.com/script/8HsNtCbh-Bitcoin-Risk-Metric-II
- Channel stats: https://vidiq.com/youtube-stats/channel/UCRvqjQPSeaWn-uEx-w0XOIg
