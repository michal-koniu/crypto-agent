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

**Cowen claim ledger** (`scripts/cowen_claims.py`, `reports/cowen_claims_scored.json`): transcripts → dated,
checkable claims extracted by the local reader model (enums, no tools; transcript text treated as untrusted) →
scored by code against price history. YouTube IP-blocked the rig after ~50 transcript downloads, so on 2026-10-29
it ran on 41 transcripts: 185 claims extracted, 164 skipped because the video's upload date was only approximate
(the channel listing says "3 years ago"), 18 still pending (horizon not reached), 3 scored. That is far too few to
say anything; the scored track record therefore remains research E's 27 calls dated from his own titles, posts and
memos. The pipeline is resumable: `fetch` continues politely when YouTube allows, `score` re-runs as horizons pass.

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
3. **Yield:** while holding USDC, up to the frozen 60 % per-protocol cap is lent on Aave v3 (Base) / Earn equivalents
   (the rest stays liquid); withdrawn first whenever BTC is bought back, and immediately on a severe protocol event.
   A deterministic **protocol-status guard** reads the reserve's on-chain flags: no deposit into a frozen, paused or
   inactive reserve, and money in a frozen reserve is withdrawn. Since 29 Oct 2026 every Aave v3 Base reserve is
   frozen, so today the agent would hold the stable leg liquid (no yield) until it is unfrozen or another venue is
   allowlisted by the owner. The backtests assumed yield on the whole stable leg; with the 60 % cap the true figure is
   ≤ 60 % of that (a small effect: the stable leg is held ~25 % of the time).
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

## 7. A finding made during testing: the time limit in stables (post-hoc - read with care)

While building the self-improvement test (2026-10-29) a scan of single-parameter changes showed that the champion is
far from optimal on one axis: `cycle_guard.max_days_in_stable` (forced re-entry after N days out of BTC). The trades
were audited (no bug): a forced re-entry ~6–8 months after the 50W exit lands near each bear-market low, which is
Cowen's **verified** cycle clock (tops→bottoms 364–406 days; research E §2.5).
`reports/robustness_max_days_in_stable.json` (all other params = champion):

| days | 120 | 150 | 180 | 210 | 240 | 270 | 300 | 365 | 450 (champion) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BTC multiple 2011–2026 | 3.65 | 3.81 | 6.12 | 8.61 | 8.82 | 5.25 | 3.14 | 2.12 | 1.55 |

A broad plateau, not a spike; 180–270 days win every halving cycle. **But** it was found after the champion was fixed,
on the same ~4 cycles: it is data snooping until forward evidence accumulates. The process response:

* **210 days** (the a-priori centre: the 50W-exit→low gaps were ~145/195/205/219 days) was submitted to the paper
  agent as a human proposal and **rejected by the gatekeeper**: it wins every cycle (bootstrap p = 0.003, DSR 0.69)
  but fails the 2017–18 must-pass window (re-enters at ~$3.9k before the final December 2018 low; −15 % vs the
  champion at the window end, limit −10 %). The gate is conservative by design; it was **not** loosened to let a
  favoured idea through.
* **240 days** passes every gate (8.82×, bootstrap p = 0.001, equal or better in all five stress windows). It was
  checked *after* the 210 rejection, so it is selected evidence; it is used in the self-improvement test to exercise
  the promotion path. **Submitted to the paper agent on 2026-10-30** (the owner asked for the agent to be taken all the
  way without approvals): `cryptoagent propose --target cycle_guard.max_days_in_stable --value 240 ...` → static ✓,
  all five must-pass windows ✓, 8.82× vs 1.55×, bootstrap p = 0.001, deflated Sharpe 0.65 (t = 801 weeks) →
  **shadow started**. The selection problem is handled by the forward process, not by the backtest: the champion holds
  BTC now, so the challenger cannot act differently in shadow; it will run the full 12 weeks and, if promoted, be
  flagged `offline_only_no_divergence_in_shadow`, and its probation keeps the old champion in shadow with automatic
  rollback armed until the two have actually differed for 12 weeks — i.e. through the next bear market's re-entry
  (SELF_IMPROVEMENT §2). The owner can withdraw it at any time: `cryptoagent withdraw --why "..."` cancels the
  challenger in shadow (or, after a promotion, rolls back through the normal rollback path); it is logged and is not
  counted as a rejection.
* A second finding while testing: **the re-entry ladder never fires** in `cycle_guard_v2`. It requires the exit signal
  to be off, but the exit signal (≥2 weekly closes below the 50W) stays on for the whole time BTC is below the 50W,
  i.e. exactly when the ladder conditions (price ≤ 200W / realised price, MVRV ≤ 1) can hold. That is why V1 and V2
  in §3 are identical. The validated results above are therefore results *without* a ladder.
  **Tested 2026-10-30** (`scripts/research_ladder.py`, `reports/ladder_study_v1.json`, four variants fixed before
  running, judged by the frozen gate code with n_trials = 22). A reachable ladder is now an opt-in parameter,
  `cycle_guard.ladder_after_exit` (default `false` = v2 behaviour, champion unchanged): the exit signal only opens the
  stablecoin position; once out, the ladder may buy back in 25 % tranches while BTC is still below the 50W, and a
  completed ladder re-entry disarms the exit until a fresh close above the 50W (otherwise it would sell again the
  next week). Results:

  | Variant | BTC multiple | per cycle 2012-16 / 2016-20 / 2020-24 / 2024-now | gate |
  |---|---:|---|---|
  | A champion | 1.55 | 1.54 / 0.74 / 1.29 / 1.05 | — |
  | B reachable ladder | 3.69 | 1.41 / 1.23 / 1.74 / 1.22 | **fails** 2017–18 must-pass (1.85 vs 2.24); bootstrap p 0.16 |
  | C 240 days | 8.82 | 2.11 / 1.41 / 2.14 / 1.39 | passes all; bootstrap p 0.001 |
  | D ladder + 240 days | 4.20 | 1.41 / 1.23 / 1.74 / 1.39 | **fails** 2017–18 must-pass |

  The ladder buys Nov–Dec 2018 at $5.6k→$3.5k: better over the whole cycle, but the stress window ends 2019-01-31 at
  $3.4k, where still holding stables scores best. The frozen gate was not loosened. The ladder **hurts** when
  combined with the 240-day re-entry (it re-enters earlier, near $350 in Oct 2014 vs ~$250 later): time-based
  re-entry near the cycle-clock bottom is the stronger and better-supported rule. Decision: ladder stays off.
* Risk if adopted: a time-based re-entry is a bet that bear markets keep their ~1-year length. If a bear market
  lasts much longer (as in 2014–15, which bottomed ~400 days after the 2013 top but chopped for another year), the
  re-entry happens too early and the 20 % stop does not help (it protects the other direction).
