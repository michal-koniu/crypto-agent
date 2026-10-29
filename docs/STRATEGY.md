# Strategy: rationale, evidence, risks

## 1. The objective changes everything

Measured in BTC, holding BTC scores exactly 1.0. Every action is a bet *against* that benchmark:

* holding **stablecoins** is a short-BTC position: it gains BTC only if we buy back lower;
* holding an **altcoin** is a bet that it outperforms BTC;
* **yield** on BTC is ~0 % on the chains and venues we can use (research B); yield on stablecoins (≈4–6 % USDC
  lending) helps only while we already hold stablecoins for another reason.

So the agent spends most of its life 100 % in BTC, and the question is narrow: *are there rare, verifiable states
of the market in which leaving BTC (and coming back) has historically added BTC after costs?*

## 2. Where the hypotheses came from (only verifiable evidence counts)

The owner asked that the strategy learn from Benjamin Cowen and rely only on verifiable evidence. Research E
(`docs/research/E-cowen-framework.md`) labels every Cowen tool and call (a) verified against data, (b) checkable,
(c) unverifiable, and scores 27 dated calls: **12 hits, 6 partial, 9 misses**. Strong on structure (BTC beats alts;
4-year cycle timing; diminishing returns; the 50-week SMA exit), weak on price levels and macro-driven tactics
(lengthening cycles: falsified; "every midterm August −15 %": false).

Research F (verifiable track records: Hyperliquid, GMX, dYdX, Polymarket on-chain histories) found no evidence that
copying top accounts at low frequency beats a benchmark after costs (40,000 zero-skill accounts produce a best
2-year Sharpe ≈ 3 by luck). It is not used; it could be added only as a pre-registered forward experiment.

Research C: no credible evidence that LLM agents beat buy-and-hold BTC out of sample (a 32-method real-money study
on OKX: none beat BTC). So the LLM does not pick trades.

## 3. The pre-registered variant study (2026-10-29)

`scripts/research_variants.py`, results in `reports/variants_v1.json`. Ten variants were fixed *before* looking at
results, each switching one of Cowen's verifiable rules on or off with his stated parameters (no tuning).
Weekly decisions, execution at the weekly close, daily BTC-terms stop checks, 20 bps per side, stablecoin yield =
3M T-bill − 1 %. Data: CoinMetrics (2010→), Binance, Treasury, NY Fed. Start 1 BTC; result = BTC at the end.

| Variant | BTC multiple | per halving cycle (2012-16 / 2016-20 / 2020-24 / 2024-now) | trades | DSR |
|---|---:|---|---:|---:|
| V1 50W exit + reclaim re-entry | 1.19 | 1.54 / 0.58 / 1.26 / 1.05 | 14 | 0.28 |
| V2 V1 + re-entry ladder | 1.19 | identical (ladder never fired before the reclaim) | 14 | 0.28 |
| **V3/V4 V1(+ladder) + 20 % BTC-terms stop on the stable leg** | **1.55** | 1.54 / 0.74 / 1.29 / 1.05 | 14 | 0.36 |
| V5 V4 + valuation trim | 1.01 | 0.95 / 0.80 / 1.29 / 1.05 | 50 | 0.24 |
| V6 V1 without the cycle-maturity filter | 1.19 | = V1 | 14 | 0.28 |
| V7 V1 exit after 3 weeks | 1.35 | 1.44 / 0.65 / 1.29 / 1.09 | 12 | 0.32 |
| V8 V1 half exit | 1.18 | 1.27 / 0.79 / 1.15 / 1.02 | 14 | 0.31 |
| V9 V4 + alt gate (ETH) | 1.47 | 1.54 / 0.74 / 1.23 / 1.05 | 22 | 0.34 |
| V10 alt gate only | 0.95 | 1.00 / 1.00 / 0.95 / 1.00 | 8 | 0.01 |

**Champion: V4 = `cycle_guard_v2`.** Trades: exits 2014-08 ($508), 2018-06 ($7.7k), 2022-01 ($41.9k), 2022-04,
2025-11 ($86.9k); re-entries 2015-11 ($330), 2019-05 ($6.9k), 2023-03 ($28.0k), 2026-09 ($84.4k); losses in the 2020
whipsaws (January; the COVID crash where the stop fired). Since 2014 the worst USD drawdown is −78 % vs −84 % for
holding.

**Honest reading.** 1.55× over 15 years with 3 of 4 trading cycles won is encouraging, but with ~4 independent
cycles and 10 variants tried the deflated Sharpe ratio is 0.36 (not significant). The study cannot prove an edge;
it can rule rules *out* (trim, alt gate). The champion keeps the agent close to the benchmark most of the time and
leaves BTC only in rare, well-defined bear states, with a stop. A post-hoc idea (limit exits to the window after the
post-halving year, which would have avoided the 2020 whipsaws) was noticed **after** seeing results; it is recorded
as a hypothesis for the self-improvement loop, not adopted - adopting it now would be data snooping.

## 4. How a decision is made

1. **Rules** (weekly, Sunday close): exit to USDC after 2 consecutive weekly closes below the 50W SMA when ≥365 days
   past the halving; re-enter in 25 % tranches when ≥2 of {≥300 days since ATH, price ≤ 200W SMA or realised price,
   MVRV ≤ 1, risk ≤ 0.2} (not in midterm H1 unless deep value); force full re-entry on 2 weekly closes back above the
   50W, on the 20 % BTC-terms stop (BTC rising 25 % above the exit price), or after 450 days. A stop-out disarms the
   exit until a fresh close above the 50W (no whipsaw loop).
2. **Analyst** (daily, three samples, median): conviction in [0,1] on the rules' stable share (and ETH share, off),
   protocol-risk exits, forecasts; key macro factors named. **Critic** (other model) can only lower conviction.
3. **Yield:** while holding USDC, it is lent on Aave v3 (Base) / Earn equivalents; withdrawn first whenever BTC is
   bought back, and immediately on a severe protocol event.
4. **Policy** checks every intent; **costs are known before acting** (order-book walk or on-chain quote + gas) and the
   expected edge (≈ 900 bps per round trip in the backtest) must exceed 2× the cost.

## 5. Risks of each strategy type (and what the agent does about them)

| Strategy type | Main risks | Status here |
|---|---|---|
| BTC ↔ stablecoin regime switching | whipsaws (2020), missing a V-shaped recovery, few independent cycles, ETF/treasury-era regime change | **used**, with a BTC-terms stop, re-arm rule, time limit, analyst can only reduce |
| Stablecoin lending (Aave/Morpho, CEX Earn) | smart-contract exploit, depeg (USDC is an EMT issued by Circle), utilisation lock (Aave Base USDC ~91 % utilised = delayed withdrawals), CEX insolvency | **used** only while in stables; protocol cap 60 % NAV; protocol-risk exits; lockup counted as cost |
| BTC yield (lending cbBTC/WBTC, BTC LST/LRT) | wrapper custody (cbBTC = Coinbase, freezable), ~0 % yield, rehypothecation | **not used** (yield ≈ 0) |
| Altcoin rotation vs BTC | alts bleed vs BTC most of the time (V10 lost in every cycle), survivorship bias, liquidity | **disabled** (gate off; can only be enabled through the gates, ≤15 % ETH, 12 % stop) |
| LP / AMM liquidity | impermanent loss is a short-volatility position vs BTC; MEV; gas | **not used** |
| Basis / funding carry (perps) | exchange risk, liquidation on spikes, funding regime flips | **not used** (needs perps; not in the allowlist) |
| Airdrop farming | Sybil filters, gas cost vs $100 capital, scam tokens/approval drains | **not used** (negative expected value at this size; prohibited approvals) |
| Copy-trading verifiable accounts | luck vs skill, survivorship, capacity | **not used** (research F) |

## 6. What would change the strategy

Only the gates: a typed proposal that beats the champion over the full history, per cycle, in every stress window,
then survives 4–12 weeks of shadow and 12 weeks of probation. Or the human, by editing the frozen files.
