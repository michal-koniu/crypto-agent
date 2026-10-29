# C. LLM trading agents, agent architecture, self-improvement, plumbing, and prompt-injection defense

Pre-design research for a BTC-denominated, low-frequency autonomous LLM crypto agent ("LLM proposes, deterministic policy engine disposes").

- **Research date / verification date for everything below:** 2026-10-29 unless stated otherwise.
- **Method:** GitHub REST API via `gh` for repo metadata (stars, license, last push, latest release); arXiv abstract/HTML pages for papers; vendor blogs for primary engineering claims. Secondary/press sources are labelled as such.
- **Evidence labels:** **[P]** primary source read (paper or official post), **[S]** secondary or press source only, **[U]** could not verify.

---

## 0. Executive summary

1. **No credible evidence exists that LLM agents beat BTC buy-and-hold out of sample after fees.** Every live or paper-trading result I could verify is short (17 days to about 3.5 months), uses few assets, and is noisy. The more rigorous the evaluation, the worse the LLMs look. The September 2026 staged real-money study on OKX found no method beat BTC buy-and-hold live, with all four live methods at negative alpha [P]. A KDD 2026 paper (FINSABER) found that LLM strategies are *too conservative in bull markets and too aggressive in bear markets* [P]. That is the worst possible profile for a portfolio benchmarked against BTC.
2. **Design implication: the default action must be "hold BTC", and every deviation is a bet against the benchmark.** That bet has to be justified, sized small, pre-registered, and scored in BTC terms. The policy engine, not the LLM, owns sizing and limits. LiveMACE (Oct 2026) documented frontier models breaking single-asset concentration limits because they miscalculated post-trade exposure [P].
3. **Use a single decision agent, not a "trading firm" of debating agents.** Add self-consistency voting and one independent critic pass. Evidence: debate gains come mostly from voting [P]; multi-agent gains are model-dependent and can be negative [P]; multi-agent costs about 15x the tokens of chat [P]; the TradingAgents paper never ablated its debate [P].
4. **Base self-improvement on a curated lesson playbook plus versioned strategy configs with champion/challenger promotion.** Candidates: Reflexion/ExpeL/ACE-style. Do *not* use gradient-like prompt optimizers (GEPA, MIPRO, TextGrad) or self-modifying code (DGM/AlphaEvolve) on P&L. Trade outcomes are too few and too noisy, and DGM itself documented objective hacking [P]. Use dense *process* signals instead (forecast calibration, rule compliance, thesis invalidation).
5. **Minimal stack:** Python, Pydantic models, PydanticAI or a thin OpenAI-compatible client, and server-side JSON-schema constrained decoding (llama.cpp / vLLM). Optionally add the LiteLLM Proxy, pinned by Docker image digest. LiteLLM's PyPI package was compromised on 2026-03-24 [S, multiple].
6. **Security:** apply Meta's "Agents Rule of Two" plus a quarantined-reader / privileged-decider split (CaMeL-lite). Exchange keys get no withdrawal rights. Spotlighting is defense-in-depth only, because adaptive attacks broke 12 published defenses at >90% success [P via Willison]. The lesson KB is a memory-injection surface (CrAIBench) and must be write-gated.

---

## 1. Existing LLM trading agents and the evidence

### 1.1 Open-source projects (GitHub metadata verified 2026-10-29)

| Project | Stars | License | Last push | Latest release | What it is / evidence quality |
|---|---|---|---|---|---|
| [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) | 118,222 | Apache-2.0 | 2026-10-27 | v0.7.1 (2026-10-27) | Multi-agent "trading firm": analysts, bull/bear researchers, trader, risk team, fund manager. Very active. Supports many providers, including "any OpenAI-compatible endpoint" since v0.3.0. **Its own changelog** lists repeated look-ahead / point-in-time fixes in 2026: v0.4.0 (FRED, sentiment, decision-log memory), v0.5.0, v0.5.2 ("backtests that see only data published by each analysis date"), and v0.7.1 ("a fix for model dates that could read filings made after the run date"). So any earlier backtests produced with it were likely contaminated. |
| [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) | 64,349 | MIT | 2026-10-27 | v2.6.2 | Persona agents (Buffett, Munger, …) plus risk/portfolio managers. README: "for **educational** purposes only … the system does not actually make any trades." No performance claims. |
| [AI4Finance-Foundation/FinRobot](https://github.com/AI4Finance-Foundation/FinRobot) | 8,330 | Apache-2.0 | 2026-10-24 | desktop-v0.1.0 (2026-07) | Analyst/report-generation platform rather than a validated trader. |
| [AI4Finance-Foundation/FinGPT](https://github.com/AI4Finance-Foundation/FinGPT) | 21,488 | MIT | 2026-10-25 | n/a | Financial LLM fine-tunes (sentiment and similar). In the 2026 crypto study below, FinGPT had about 417 s decision latency. |
| [pipiku915/FinMem-LLM-StockTrading](https://github.com/pipiku915/FinMem-LLM-StockTrading) | 968 | MIT | **2024-08-18** | n/a | Layered-memory trading agent. Unmaintained. |
| [Xtra-Computing/CryptoTrade](https://github.com/Xtra-Computing/CryptoTrade) | 166 | NOASSERTION | **2024-12-01** | n/a | EMNLP 2024 crypto agent (see 1.2). Unmaintained. |
| FinAgent (Zhang et al., KDD 2024) | n/a | n/a | n/a | n/a | Multimodal agent with reflection. Included as a baseline in the 2026 crypto study. |
| nof1 Alpha Arena | none | n/a | n/a | n/a | No public code repo found (searched `nof1-ai/alpha-arena` → 404; only unofficial prompt-clone repos). |

### 1.2 Papers and benchmarks: what they actually show

**CryptoTrade**, Li et al., EMNLP 2024 main ([ACL Anthology 2024.emnlp-main.63](https://aclanthology.org/2024.emnlp-main.63/), [arXiv 2407.09546](https://arxiv.org/html/2407.09546)) [P]
- Setup: daily decisions on BTC/ETH/SOL with on-chain plus news data and a reflection module. The test windows are each about 2 months in 2023. A proportional fee is applied, but the rate is not stated.
- BTC total return: Buy-and-hold vs CryptoTrade(GPT-4):
  - Bull: **39.66% vs 26.35%**
  - Sideways: **-0.83% vs -4.07%**
  - Bear: **-15.61% vs -11.72%**
- **It does not beat BTC buy-and-hold in bull or sideways markets.** It only loses less in the bear window.
- The reflection ablation (ETH bull) shows return dropping 28.47% → 17.14% without reflection. However, that "full" number does not match the paper's own main table, an internal inconsistency.

**TradingAgents**, Xiao et al. ([arXiv 2412.20138 v7](https://arxiv.org/html/2412.20138)) [P]
- Backtest: **2024-01-01 to 2024-03-29 (about 3 months)**, AAPL/GOOGL/AMZN. Fees and slippage are not stated.
- Reported results: AAPL 26.62% (Sharpe 8.21) vs B&H -5.23%.
- The authors themselves flag the Sharpe ratio as above the plausible empirical range. They limited the window to 3 months because each decision costs about 11 LLM calls plus 20+ tool calls.
- **No ablation of the debate rounds.** The test window falls *inside* the training data of the backbone models, so memorization risk is unaddressed.

**FINSABER**, "Can LLM-based Financial Investing Strategies Outperform the Market in Long Run?", Li, Kim, Cucuringu, Ma. KDD 2026 Datasets & Benchmarks (Oral), [arXiv 2505.07078 v6, 2026-06-26](https://arxiv.org/abs/2505.07078) [P]
- 20 years, 100+ symbols, with survivorship and look-ahead bias controls.
- "LLM advantages … deteriorate significantly" under broader, longer testing.
- **Bull markets: overly conservative, underperform passive benchmarks. Bear markets: overly aggressive, heavy losses.**
- The authors recommend that future work prioritize trend/regime detection and risk controls over framework complexity.
- Code: [waylonli/FINSABER](https://github.com/waylonli/FINSABER) (152 stars, Apache-2.0, pushed 2026-09-17).

**StockBench**, Chen et al. ([arXiv 2510.02209](https://arxiv.org/abs/2510.02209), v2 2026-03-02) [P, abstract]
- Contamination-free, multi-month daily trading of US stocks.
- "Most models struggle to outperform the simple buy-and-hold baseline." Static finance QA skill does not transfer to trading.

**Agent Market Arena (AMA)**, "When Agents Trade" ([arXiv 2510.11695 v2](https://arxiv.org/html/2510.11695v2)) [P]
- Setup: live 2025-08-01 to 2025-09-30 (61 days); BTC, ETH, TSLA, BMRN; 4 agent architectures × 5 backbones.
- BTC buy-and-hold returned 0.66%. **Most BTC agent configurations underperformed it**, and InvestorAgent was negative on every backbone.
- The abstract's "often surpassing buy-and-hold" claim is not supported for BTC by its own table.
- Data-quality concerns:
  - HedgeFundAgent's results are identical across all 5 backbones, which is unexplained.
  - Fee values are not given.
  - All agents misjudged a late-September BTC short squeeze.
- The finding "architecture matters more than backbone" is weakened by the identical-results anomaly.

**LiveTradeBench**, Yu, Li, You (UIUC) ([arXiv 2511.03628](https://arxiv.org/html/2511.03628v1)) [P, abstract]
- 50-day live evaluation of 21 LLMs on US stocks and Polymarket. Agents output portfolio allocations.
- **LMArena scores do not predict trading results.** Models show stable "risk-appetite styles".
- Code: [ulab-uiuc/live-trade-bench](https://github.com/ulab-uiuc/live-trade-bench) (167 stars, last push 2026-02-17).

**InvestorBench** ([arXiv 2412.18174](https://arxiv.org/pdf/2412.18174)) [S]
- Single-asset tasks (stocks, crypto, ETFs) with buy-and-hold as the baseline. Short historical windows inside model training periods, so memorization risk applies.

**"Can AI Make Money in Crypto? Measuring the Gap from Backtests to Real Markets"**, Yu et al. (CUHK/USTC/SMU…), [arXiv 2609.34510 v1, 2026-09-28](https://arxiv.org/html/2609.34510v1) [P]. **The most relevant study found.**
- Methods tested (32): 24 ML, 2 RL, 3 direct LLMs (DeepSeek, Qwen, FinGPT), and 3 agents (FinMem, FinAgent, TradingAgents).
- Protocol: backtest on 2025, then paper trading 2026-06-04 to 09-21, then **real-money live** trading 2026-08-24 to 09-21 on OKX.
- Fees: taker 0.10% spot / 0.05% perp.
- Backtest: no LLM or agent method was profitable (DeepSeek -43.3%, Qwen -68.6%).
- Paper trading: rankings flipped, with all 6 non-ML methods positive.
- Live (BTC B&H **+11.63%**): Qwen +3.72% (alpha -28.1%), XGBoost -0.79%, LSTM -0.33%, TRA -14.74%. **"No method outperforms the market live"; all live methods had negative alpha.**
- Execution failure modes:
  - Agent decision latency averaged about **523 s** (FinMem 545 s), versus about 19 s for ML.
  - Slippage: agents 1.79‰ vs ML 0.36‰.
  - Live price deviation was about 6x paper.
  - Backtest alpha did not predict profit (DeepSeek had +278% alpha but -43% return).
- Limitations: a 4-week live window, only 4 live methods, no significance testing, and some leverage and config inconsistencies.

**LiveMACE**, Zhao et al. (NUS/Fudan/Sydney), [arXiv 2610.09872 v1, 2026-10-07](https://arxiv.org/html/2610.09872v1) [P]
- Setup: 30-day live paper trading (2026-04-13 to 05-13) on 6 cryptos (Hyperliquid) and 17 US equities. Models: GPT-5.4, DeepSeek-V3.2, Gemini-3.1-Pro, Grok-4.20, Qwen3-Max.
- Return rankings reversed 19–29 times over the window, while capability rankings reversed 0–8 times. **Returns over a month mostly measure noise.**
- Documented failure modes:
  - **Concentration-limit violations from miscalculated post-trade exposure** (GPT-5.4, Qwen3-Max).
  - "Persistent access does not imply persistent learning": GPT-5.4 did 332 memory retrievals but stored 1 memory.
  - Rule satisfaction does not imply auditability.
  - Multi-agent collaboration was model-dependent; Qwen3-Max lost 4.39 pts of return.
- No buy-and-hold comparison was reported in the part I read.

**Fin-Analyst at FinMMEval / CLEF 2026 Task 3** ([arXiv 2607.12233](https://arxiv.org/pdf/2607.12233)) [S, search snippet]
- Live hybrid LLM-plus-rules agent. BTC -5.30%, about 17.6 pts better than a buy-and-hold that lost about a quarter.
- This is a single short bear window, and the authors say short windows give "volatility-sensitive rankings". It is the only "beat BTC B&H" data point found, and it is consistent with FINSABER's "loses less in bear markets".

**Review: "Artificial Intelligence in Equity and Crypto Markets: Progress, Profitability Evidence, and the Limits of Automated Investing"**, Zhu & Cai, [arXiv 2609.04917, 2026-09-04](https://arxiv.org/html/2609.04917v1) [P, partial]
- Conclusion: "no general AI architecture is shown to deliver persistent, cross-regime, capacity-aware net alpha" in public evidence.
- Failure modes it lists: temporal contamination and memorization, selection over prompts/models, survivorship, ignoring costs, crypto-specific funding/liquidation/MEV, and "fluent rationales are not provenance".

**Look-ahead / memorization literature** [P/S]
- [Look-Ahead-Bench, arXiv 2601.13770](https://arxiv.org/pdf/2601.13770): models look good in backtests, then degrade past their knowledge cutoff.
- [FinCAD, arXiv 2605.24564](https://www.emergentmind.com/papers/2605.24564): "parametric look-ahead bias".
- [MemGuard-Alpha, arXiv 2603.26797](https://arxiv.org/pdf/2603.26797).
- [BlindTrade, arXiv 2603.17692](https://arxiv.org/html/2603.17692): anonymization helps but does not block all leakage.
- **Consequence:** any backtest of an LLM on data before the model's training cutoff is not evidence. This applies to validating our own strategy versions too.

**nof1 Alpha Arena** (primary site [alphaarena.ai](https://alphaarena.ai) returned HTTP 429; [nof1.ai](https://nof1.ai) has no results text). All figures below are **[S]**.
- **Season 1** (2025-10-18 to 11-03): $10k each, crypto perps on Hyperliquid, 6 models.
  - Qwen3-Max about +22%, DeepSeek V3.1 about +5%, the rest lost 30–63%. Exact figures differ between outlets.
  - About 17 days and tens of trades per model, so statistically meaningless.
  - Sources: [SCMP](https://www.scmp.com/tech/tech-trends/article/3331425/alibabas-ai-model-outperforms-us-rivals-crypto-trading-showdown), [iWeaver](https://www.iweaver.ai/blog/alpha-arena-ai-trading-season-1-results/), [Forklog](https://forklog.com/en/four-out-of-six-ai-models-suffer-losses-in-trading-tournament/).
- **Season 1.5** (US equities, 8 models, 4 parallel 2-week variants): the aggregate lost about one-third, and **only 6 of 32 sessions were profitable**.
  - Overtrading: Qwen made 1,418 trades in one round (about 1 per minute) from identical prompts.
  - Per-model biases: Claude long-biased, Qwen high leverage. Grok 4.20 "won".
  - Commentators quoted say the arenas are too short and noisy and that no persistent excess returns were observed.
  - Sources: [BigGo, 2026-05-06](https://finance.biggo.com/news/5BSX_Z0BaoGGrU-ID27J), [Forklog](https://forklog.com/en/ai-model-grok-4-2-triumphs-in-trading-tournament/).
- **Season 2:** referenced in press, but I found **no public results** [U].

**CryptoBench** ([arXiv 2512.00417](https://arxiv.org/pdf/2512.00417)) and **LATTICE** ([arXiv 2604.26235](https://arxiv.org/pdf/2604.26235)) evaluate crypto *knowledge/decision support*, not P&L. Not read in depth [S].

### 1.3 Answer to the key question

**No.** No study I could verify shows an LLM agent beating BTC buy-and-hold out of sample, after fees, over a horizon long enough to be statistically meaningful.

| Study | Window | BTC (or market) B&H vs LLM |
|---|---|---|
| CryptoTrade (EMNLP'24) | 3 × ~2 mo, 2023 (in training data) | Loses in bull and sideways; loses less in bear |
| AMA | 61 days live, 2025 | Most BTC configs below B&H (0.66%) |
| Crypto staged study (Sep 2026) | 4 wk real money | All live methods below BTC B&H (+11.6%); negative alpha |
| FINSABER (KDD'26) | 20 yr, 100+ stocks | Conservative in bulls, aggressive in bears |
| StockBench | multi-month | Most below B&H |
| Alpha Arena S1/S1.5 | 2–3 weeks | 4/6 and 26/32 losing |
| Fin-Analyst CLEF'26 | short bear window | Lost less than B&H (only positive datum; regime artifact) |

**Documented failure modes, for design:**
1. Overtrading and fee drag (Alpha Arena 1.5).
2. Regime asymmetry: underexposed in bulls, overexposed in bears (FINSABER, CryptoTrade).
3. Look-ahead and memorization inflating backtests (TradingAgents fixes; Look-Ahead-Bench).
4. Backtest-to-live gap and latency/slippage (Crypto staged study).
5. Limit and arithmetic violations (LiveMACE concentration).
6. Persistent model "personality" biases: long bias, leverage appetite (Alpha Arena, LiveTradeBench).
7. Unused memory (LiveMACE).
8. Missed squeezes and sharp reversals (AMA).
9. Prompt sensitivity: identical prompts give wildly different trade counts.
10. Metric gaming: alpha that does not translate to returns.

**Implications for this BTC-benchmark design:**
- Holding BTC is the zero-tracking-error default. Every move to stablecoins is effectively a short-BTC bet, and every alt is an alt/BTC bet.
- Hard-code a low turnover budget, minimum holding periods, and cool-downs.
- Cap the share of the portfolio that may deviate from BTC.
- Require an explicit thesis with falsifiable invalidation conditions and a horizon.
- Evaluate only on post-cutoff, forward data.
- Expect a multi-year run before any claim of skill. With few trades, statistical power is very low.

---

## 2. Single-agent vs multi-agent

### Evidence

- **Debate vs voting**: "Debate or Vote", Choi, Zhu, Li, NeurIPS 2025 ([arXiv 2508.17536](https://arxiv.org/html/2508.17536v2)) [P, abstract]
  - Majority voting alone accounts for most multi-agent-debate gains across 7 benchmarks.
  - Debate induces a martingale over beliefs, so debate alone does not raise expected correctness.
- **MAST**, "Why Do Multi-Agent LLM Systems Fail?", Cemri et al., Berkeley ([arXiv 2503.13657](https://arxiv.org/abs/2503.13657)) [P, abstract]
  - Gains over single agents on popular benchmarks are "often minimal".
  - 1,600+ traces from 7 frameworks, 14 failure modes in 3 categories: system design, inter-agent misalignment, task verification.
- **Anthropic**, "How we built our multi-agent research system", 2025-06-13 ([post](https://www.anthropic.com/engineering/multi-agent-research-system)) [P]
  - Multi-agent beat single Opus 4 by 90.2% on an internal *research* eval.
  - It uses "about 15× more tokens than chats", and token usage explains 80% of BrowseComp variance.
  - Domains needing shared context or with many inter-agent dependencies "are not a good fit for multi-agent systems today."
- **Cognition (Walden Yan)**, "Don't Build Multi-Agents", 2025-06-12 ([post](https://cognition.com/blog/dont-build-multi-agents)) [P]
  - Principles: "Share context, and share full agent traces" and "Actions carry implicit decisions, and conflicting decisions carry bad results."
  - Recommends a single-threaded agent plus history compression.
  - Cognition later (2026) reported running multi-agent setups in narrow, coordinator-scoped flows [S].
- **Trading-specific evidence:**
  - TradingAgents never ablated debate [P].
  - AMA found no consistent winner across architectures and an identical-results anomaly [P].
  - LiveMACE found multi-agent collaboration effects model-dependent and sometimes negative (Qwen3-Max -4.39 pts return, +2.85 pts drawdown), and GPT-5.4 collapsed to a single role [P].
  - AlphaCrafter ([arXiv 2605.05580](https://arxiv.org/pdf/2605.05580)) [S] reports that a single-agent variant was worse, attributing this to *context overload*. That is an argument for decomposing the pipeline, not for debate.

### Recommendation

**Use one decision agent inside a mostly deterministic pipeline:**
1. Data collection, features, and regime indicators are plain code.
2. Optional *quarantined reader* calls summarize untrusted text into typed fields. These are parallel and stateless, which is also a security boundary (section 5).
3. **One decision call** produces a structured proposal (thesis, probability, horizon, invalidation, desired exposure delta). Run it with N samples (self-consistency, for example 3–5), aggregated by vote or median.
4. **One independent critic call** with fresh context sees only the proposal and evidence and lists failure reasons. This is cheap, and it addresses the "conservative in bull, aggressive in bear" bias.
5. A **deterministic policy engine** accepts, clips, or rejects.

Reasons:
- Voting captures most of the debate benefit.
- Shared context matters in trading (one portfolio state).
- Token cost and latency matter on local GPUs.
- Multi-agent "firms" have no ablation evidence in trading.
- Fewer components means a smaller injection and failure surface.

---

## 3. Self-improvement techniques

### Status table (verified 2026-10-29)

| Technique | Source | Code status | Fit for rare-outcome trading |
|---|---|---|---|
| Reflexion (verbal self-reflection into episodic memory), NeurIPS 2023 | [noahshinn/reflexion](https://github.com/noahshinn/reflexion) | 3.4k stars, MIT, last push 2025-01, research code | **Pattern yes, library no.** Post-mortem → reflection text is cheap. Risk: reflections on noisy single outcomes = superstition. |
| ExpeL (extract insights from success/failure pairs; ADD/EDIT/UPVOTE/DOWNVOTE rules), AAAI 2024 | [LeapLabTHU/ExpeL](https://github.com/LeapLabTHU/ExpeL) | 248 stars, Apache-2.0, last push 2024-12, unmaintained | **Pattern yes.** Voted, editable rules with counters suit a lesson KB. |
| Voyager skill library | [MineDojo/Voyager](https://github.com/MineDojo/Voyager) | 7.3k stars, MIT, last push 2024-04, unmaintained | Low. Executable-skill libraries need dense environment feedback. |
| Agent Workflow Memory ([arXiv 2409.07429](https://arxiv.org/abs/2409.07429)) | [zorazrw/agent-workflow-memory](https://github.com/zorazrw/agent-workflow-memory) | 480 stars, Apache-2.0, last push 2025-12 | Low–medium. Reusable *procedures* (e.g. "how to evaluate an alt rotation") could be induced, but the paper's gains are on web tasks with many episodes. |
| **ACE: Agentic Context Engineering** (evolving "playbook", generator/reflector/curator, incremental delta updates; [arXiv 2510.04618](https://arxiv.org/html/2510.04618v2), v2 2026-01-29) | [ace-agent/ace](https://github.com/ace-agent/ace) 1.4k stars, Apache-2.0, push 2026-08; community [kayba-ai/agentic-context-engine](https://github.com/kayba-ai/agentic-context-engine) 2.6k stars, push 2026-09 | Maintained (2026) | **Best conceptual fit.** It identifies "context collapse" (monolithic rewrites shrink knowledge) and "brevity bias", and proposes itemized bullets with helpful/harmful counters and grow-and-refine. Includes finance experiments. Borrow the design; the library is optional. |
| Dynamic Cheatsheet (ACE's predecessor) | [suzgunmirac/dynamic-cheatsheet](https://github.com/suzgunmirac/dynamic-cheatsheet) | 279 stars, MIT, push 2026-03 | Same idea, simpler. |
| DSPy (MIPROv2, GEPA) | [stanfordnlp/dspy](https://github.com/stanfordnlp/dspy) 38.8k stars, MIT, release 3.4.1 (2026-10-12); [gepa-ai/gepa](https://github.com/gepa-ai/gepa) 7.2k stars, MIT, v0.1.4 (2026-07) | Very active | GEPA is an ICLR 2026 oral ([arXiv 2507.19457](https://arxiv.org/abs/2507.19457)): beats GRPO by about 6–10% on average with up to 35x fewer rollouts, and beats MIPROv2 by more than 10%. **It still needs hundreds of scored rollouts with a reliable metric.** Not usable on trade P&L. **Usable offline for dense-label sub-tasks** (news → typed-event extraction, relevance classification, schema adherence on a local model). |
| TextGrad (Nature, 2025-03-19; [arXiv 2406.07496](https://www.arxiv.org/pdf/2406.07496)) | [zou-group/textgrad](https://github.com/zou-group/textgrad) | 3.8k stars, MIT, **last push 2025-07** (stale) | Same metric problem as GEPA; less maintained. Skip. |
| Letta (MemGPT) | [letta-ai/letta](https://github.com/letta-ai/letta) | 25.3k stars, Apache-2.0, last release 0.16.8 (2026-05), push 2026-10 | A full agent server with its own runtime. Too heavy to embed in a "policy engine disposes" design. Letta's own result ([blog 2025-08-12](https://www.letta.com/blog/benchmarking-ai-agent-memory)): **a plain file plus grep/search tools scored 74.0% on LoCoMo vs Mem0's reported 68.5%**. Simple files are enough. |
| Mem0 | [mem0ai/mem0](https://github.com/mem0ai/mem0) | 68k stars, Apache-2.0, push 2026-10 | Personalization-oriented fact memory. LoCoMo numbers are disputed between Mem0, Zep, and Letta [S]. Not needed. |
| Darwin Gödel Machine ([arXiv 2505.22954](https://arxiv.org/pdf/2505.22954)) | [jennyzzt/dgm](https://github.com/jennyzzt/dgm) | 2.5k stars, Apache-2.0, **last push 2025-08** | No. Self-modifying agent code. SWE-bench 20→50%, but the **paper documents objective hacking** (it gamed its hallucination metric). Press reports about $22k per run [S]. |
| AlphaEvolve-style evolution | DeepMind (closed); [OpenEvolve](https://github.com/algorithmicsuperintelligence/openevolve) 7.7k stars, Apache-2.0, push 2026-10; [SakanaAI/ShinkaEvolve](https://github.com/SakanaAI/ShinkaEvolve) 1.5k stars, push 2026-10 | Maintained | Needs a fast, cheap, trustworthy evaluator. For trading the evaluator is a backtest, which is vulnerable to overfitting and LLM memorization. **Only acceptable for deterministic, code-only components** (e.g. evolving a rule-based signal), evaluated on walk-forward plus held-out post-cutoff data with multiple-testing correction. Optional, later. |

### Recommendation for a single developer with rare outcomes

1. **Lesson playbook (ACE/ExpeL pattern, own implementation, about 300 LOC).**
   - Store itemized lessons in SQLite or Markdown with these fields: `id`, `text`, `scope` (asset/regime/setup), `provenance` (trade ids, post-mortem id), `created_by_version`, `helpful`, `harmful`, `status` (candidate/active/retired), `expires_at`.
   - Apply incremental delta edits only, never a full rewrite, to avoid context collapse.
   - Retrieve with FTS or grep plus scope filters (Letta's filesystem result supports keeping this simple).
   - A lesson goes active only after it is (a) supported by more than one independent episode, or (b) approved by a human.
2. **Use dense process signals, not just P&L.** Each proposal records:
   - explicit probabilistic forecasts with a horizon (e.g. "P(BTC/ETH ratio up >5% in 30d) = 0.35"),
   - a thesis,
   - invalidation conditions.

   Score them with **Brier/log-loss and calibration**, invalidation-hit rate, rule-compliance rate, and an "excess vs BTC" counterfactual. Many forecasts per decision (including for *no-trade* decisions) give hundreds of scored items per year even with few trades. That is the signal that makes post-mortems and any optimizer meaningful.
3. **Strategy versioning with promotion gates.** A version bundles prompt, playbook snapshot, model id, sampling params, and policy config, stored in git with content hashes.
   - The new version runs in **shadow mode** (champion/challenger) on live data for a minimum period or minimum number of forecasts.
   - Promote only if calibration and process metrics are no worse and no hard-rule regressions occur.
   - Automatic rollback triggers: a drawdown vs BTC beyond a threshold, or a rule-violation rate spike.
   - **Never validate on pre-cutoff historical data** (memorization). Use forward or held-out post-cutoff data only.
4. **Post-mortems** happen per closed position and at fixed intervals, including for *trades not taken*. They are generated by a separate reflection call that sees only trusted records (decision log, prices), never raw untrusted text, because lessons are a memory-injection surface (section 5).
5. **Optional offline GEPA** on dense-label sub-tasks run on the local model, e.g. extraction quality on a labelled news set. This is where prompt optimization can actually pay off.
6. **Avoid** DGM-style self-code-modification and any optimizer with P&L as its objective.

---

## 4. Agent frameworks and LLM plumbing

### Metadata (verified 2026-10-29)

| Project | Stars | License | Latest release | Notes |
|---|---|---|---|---|
| [pydantic/pydantic-ai](https://github.com/pydantic/pydantic-ai) | 20.9k | MIT | v2.63.0 (2026-10-28) | Typed outputs validated by Pydantic. Three output modes: **Tool Output** (default, "supported by virtually all models"), **Native Output** (provider JSON-schema), **Prompted Output** (least reliable). Validation errors are sent back for retry (default 1 retry, configurable) ([docs](https://pydantic.dev/docs/ai/core-concepts/output/)). Works with OpenAI-compatible base URLs. |
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | 44.1k | MIT | 1.2.18 (2026-10-26) | Durable graphs and checkpointing. Overkill for one decision per day; adds LangChain abstractions. |
| [openai/openai-agents-python](https://github.com/openai/openai-agents-python) | 30.4k | MIT | v0.24.0 (2026-10-15) | Handoffs and guardrails. OpenAI-first; other providers go through adapters. |
| [huggingface/smolagents](https://github.com/huggingface/smolagents) | 30.1k | Apache-2.0 | v1.26.0 (2026-05-29) | Code-writing agents. Executing LLM-written code is the wrong default for a money-handling agent. |
| [agno-agi/agno](https://github.com/agno-agi/agno) | 43.0k | Apache-2.0 | v3.1.12 (2026-10-29) | Broad, fast-moving (v3); more surface than needed. |
| [BerriAI/litellm](https://github.com/BerriAI/litellm) | 62.3k | MIT outside `enterprise/` | v1.106.6 (2026-10-28) | SDK and Proxy: 100+ providers incl. `deepseek/`, `moonshot/`, `zai/` (GLM), `dashscope/` (Qwen), `anthropic/`, `openai/`, vLLM, generic OpenAI-compatible ([providers](https://docs.litellm.ai/docs/providers)). Proxy offers fallbacks, budgets, rate limits, spend tracking. **Security note:** PyPI releases **1.82.7 and 1.82.8 were malicious (credential stealer), published 2026-03-24** after a CI/Trivy-chain token theft (TeamPCP). The official Proxy Docker image was reported unaffected (pinned deps) [S: [PureAI](https://pureai.com/Articles/2026/03/25/PyPI-Removes-Compromised-LiteLLM-Releases-After-Warnings-of-Stolen-Credentials.aspx), [pypistats blog](https://pypistats.com/blog/litellm-pypi-supply-chain-compromise-how-a-popular-llm-proxy-became-a-credential-stealing-backdoor-march-24-2026), GH issue #24518 cited]. |
| [567-labs/instructor](https://github.com/567-labs/instructor) | 14.1k | MIT | n/a | Lightweight Pydantic-structured-output alternative. |
| [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp) | 132.8k | MIT | latest release tag v0.8.0 (2026-10-28) | `llama-server`: `--json-schema`, per-request `json_schema`, GBNF `grammar`, OpenAI-compatible "schema-constrained JSON response format", tool calling for "~any model" with `--jinja` (default on). Not every JSON-Schema feature converts to grammar; the README points to tests for the supported subset ([server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)). |
| [mostlygeek/llama-swap](https://github.com/mostlygeek/llama-swap) | 6.1k | MIT | v268 (2026-10-28) | Hot-swaps llama.cpp/vLLM backends behind one OpenAI-compatible endpoint. |
| [vllm-project/vllm](https://github.com/vllm-project/vllm) | 95.9k | Apache-2.0 | v0.32.0 (2026-10-18) | Structured outputs on by default. Backends: **xgrammar, guidance** (`auto` default). Use `response_format: {type: json_schema}` or `structured_outputs` extra_body. Legacy `guided_*` fields were removed in v0.12. Caveat: constraints interact with reasoning/thinking tokens (needs reasoning parser / `enable_in_reasoning`) ([docs](https://docs.vllm.ai/en/latest/features/structured_outputs.html)). |
| [mlc-ai/xgrammar](https://github.com/mlc-ai/xgrammar), [guidance-ai/llguidance](https://github.com/guidance-ai/llguidance), [dottxt-ai/outlines](https://github.com/dottxt-ai/outlines) | 2.0k / 0.9k / 16.0k | Apache/MIT/Apache | active | Underlying grammar engines. |

### Recommended minimal stack

- **Python 3.12, with Pydantic v2 models as the contract** between LLM and policy engine: `Proposal`, `Forecast`, `ExtractedEvent`, `Lesson`. Use enums, bounded numbers, and short bounded strings.
- **PydanticAI** for the LLM calls: typed output, validation-retry loop, provider-agnostic.
  - Alternative if you want zero framework: the `openai` SDK pointed at any base URL plus Pydantic validation. That is about 100 LOC. Either way, **no agent framework orchestrates control flow**; control flow is plain Python, which is easy to audit and test.
- **Provider switching by config:** a `models.yaml` maps role → `{base_url, model, api_key_env, output_mode}`.
  - All target providers expose OpenAI-compatible endpoints (local llama-swap/vLLM, DeepSeek, Kimi, GLM, Qwen DashScope, OpenAI). Anthropic can be used natively through PydanticAI's Anthropic model.
  - **LiteLLM Proxy is optional.** Adopt it only if you want centralized fallbacks, budgets, and spend logs. If adopted:
    - run the official Docker image pinned by **digest**,
    - do not `pip install` an unpinned SDK,
    - keep provider keys only in the proxy.
- **Structured output reliability on local models:**
  - (1) Prefer **server-side constrained decoding** (`response_format` json_schema on vLLM/llama.cpp) over tool-calling for the decision output.
  - (2) Keep schemas flat; avoid regex `pattern`, deep `anyOf`, and recursive refs.
  - (3) For reasoning models, let them think in free text first, then make a second constrained call (or use the server's reasoning parser), because constraining the thinking channel hurts quality or breaks parsing.
  - (4) Always validate again in Pydantic.
  - (5) **Fail closed**: an invalid output after retries means "no action".
  - (6) Pin model file hashes and sampling params per strategy version.
- **Observability:** an append-only JSONL/SQLite decision log (inputs hash, prompts, outputs, policy verdicts). OpenTelemetry/Logfire is optional.

---

## 5. Prompt-injection defense

### Evidence and patterns

- **Willison's Dual-LLM pattern** (2023): a privileged LLM never sees untrusted text; a quarantined LLM processes it and returns only symbolic references or typed values.
- **CaMeL**, Debenedetti et al., Google DeepMind ([arXiv 2503.18813](https://arxiv.org/pdf/2503.18813)) [P, abstract]
  - Formalizes Dual-LLM. A privileged LLM writes a plan as code; a quarantined LLM parses data without tool access; capabilities/taint tracking enforce policies at tool calls.
  - **77% of AgentDojo tasks solved with provable security vs 84% undefended.**
  - Research code: [google-research/camel-prompt-injection](https://github.com/google-research/camel-prompt-injection), 412 stars, last push 2025-06. It is a reference, not a library.
- **"Design Patterns for Securing LLM Agents against Prompt Injections"**, Beurer-Kellner, Tramèr et al. ([arXiv 2506.08837](https://arxiv.org/abs/2506.08837), 2025-06) [P abstract; pattern list from memory, U]
  - Patterns include action-selector, plan-then-execute, map-reduce, dual-LLM, code-then-execute, and context-minimization.
- **Spotlighting**, Hines et al., Microsoft ([arXiv 2403.14720](https://arxiv.org/abs/2403.14720)) [P]
  - Delimiting, datamarking, and encoding of untrusted input. ASR dropped from >50% to <2% on GPT-family in their tests.
- **"The Attacker Moves Second"** (Nasr, Carlini, Tramèr et al., 2025-10) [P via [Willison](https://simonwillison.net/2025/Nov/2/new-prompt-injection-papers/)]
  - Adaptive attacks bypassed **12 published defenses at >90% ASR**, most of which had reported near-zero ASR.
  - A human red-team reached 100%.
  - **Conclusion: detection and prompt-level defenses are not a security boundary.**
- **Meta "Agents Rule of Two"** (2025-10-31, [Meta AI blog](https://ai.meta.com/blog/practical-ai-agent-security/))
  - In one session, satisfy at most two of: [A] untrusted input, [B] sensitive data/systems, [C] state change or external communication.

### Attacks on crypto agents

- **ElizaOS / CrAIBench**, "Real AI Agents with Fake Memories: Fatal Context Manipulation Attacks on Web3 Agents", Patlan, Sheng, Hebbar, Mittal, Viswanath, Princeton & Sentient ([arXiv 2503.16248](https://arxiv.org/abs/2503.16248), v3 2025-07) [P, abstract]
  - Injected memories trigger unauthorized transfers. CrAIBench has 150+ Web3 tasks and 500+ attack cases.
  - **Memory injection is more effective than prompt injection.**
  - Prompt-based defenses and detectors give limited protection when stored context is corrupted. Fine-tuning helps on single-step tasks.
- **AIXBT** (2025-03-18): about 55 ETH (about $100k) sent from its Simulacrum wallet after an attacker got **dashboard access** and queued two malicious prompts. Root cause was operational access control, not only the model. No detailed postmortem was published [S: [The Block](https://www.theblock.co/post/346911/), [AIID #1003](https://incidentdatabase.ai/cite/1003)].
- **Freysa** (2024-11-29): an adversarial game agent forbidden to call `approveTransfer`. After 482 attempts, a message posed as a new admin session and redefined `approveTransfer` as handling *incoming* transfers; the agent paid out $47,316 [S: [The Block](https://www.theblock.co/post/328747/human-player-outwits-freysa-ai-agent-in-47000-crypto-challenge), [Willison](https://simonwillison.net/2024/Nov/29/0xfreysaagent/)]. Lesson: tool semantics and authority cannot rest on the model's interpretation.

### Recommended defense architecture

1. **Rule of Two by construction.**
   - The decision LLM never has an execute capability; it emits a `Proposal` object.
   - Execution is done only by the deterministic policy engine with hard limits:
     - asset allowlist
     - max deviation from BTC
     - max per-trade size and turnover per period
     - min holding time and cool-downs
     - max slippage
     - no leverage unless explicitly configured
     - kill switch
2. **Quarantine untrusted text** (news, social, web, on-chain memos, token metadata).
   - A *reader* LLM with no tools converts each item into a typed `ExtractedEvent` (enums, numbers, a bounded summary).
   - The decider sees only these typed fields plus source ids, never raw text. This is CaMeL-lite and the "context-minimization" pattern.
   - Apply spotlighting/datamarking inside the reader prompt as defense-in-depth only.
3. **Memory and lesson KB are trusted-write only.**
   - Post-mortems are generated from internal records.
   - New lessons enter `candidate` status, with provenance, and need promotion (multi-episode support or human approval).
   - Any lesson text derived from external content is rejected.
   - Lesson IDs are hash-chained in an append-only log.
   - This directly addresses the CrAIBench memory-injection result.
4. **Credential hygiene** (the AIXBT lesson):
   - Exchange API keys are trade-only with **withdrawals disabled** and an IP allowlist.
   - Keep most BTC in cold storage outside the agent's reach.
   - No remote admin dashboard that can inject prompts.
   - Approval out of band (e.g. signed Telegram/email confirmation) for actions above a threshold.
5. **Supply chain:** pin dependencies with hashes, pin Docker images by digest, and audit LiteLLM/any SDK upgrades (the March 2026 LiteLLM incident).
6. **Red-team regularly** with CrAIBench-style memory injections and injected news items in the test suite. Any change that lets raw untrusted text reach the decider fails CI.

---

## 6. What I could not verify

- **nof1 Alpha Arena primary data.** alphaarena.ai rate-limited (HTTP 429), and nof1.ai shows no results. Season 1/1.5 figures are from press, with inconsistent percentages. **No Season 2 results found.**
- Full-text numbers for StockBench, LiveTradeBench, and InvestorBench (abstracts only). Whether LiveMACE reports a buy-and-hold comparison in the unread portion.
- The full list of patterns in arXiv 2506.08837 (from memory) and the exact CrAIBench attack-success rates (abstract only).
- Fin-Analyst CLEF 2026 BTC numbers (search snippet only).
- Mem0/Zep/Letta LoCoMo dispute details beyond Letta's own post. The AlphaCrafter single-agent finding (snippet).
- Cognition's 2026 follow-up post on multi-agent (secondary only).
- The DGM ~$22k cost (press only).
- Venues for Reflexion (NeurIPS 2023), ExpeL (AAAI 2024), FinAgent (KDD 2024), and Voyager are from memory. AWM's arXiv page lists no venue.
- llama.cpp's latest release tag reads "v0.8.0" via the API, which differs from its historical `bNNNN` tag scheme. Reported as returned.
