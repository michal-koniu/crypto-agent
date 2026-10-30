# Research findings: what exists, what was reused, what was rejected

Six research reports were produced on 2026-10-29 before any code was written; each checked maintenance status live
(GitHub API, PyPI, official docs, real API calls). Full reports with sources and verification dates:
`docs/research/A..F-*.md`. This page is the decision summary.

| Report | Topic |
|---|---|
| A | trading/backtesting frameworks, exchanges for a Polish resident (MiCA), Polish crypto tax |
| B | agent DeFi toolkits, signing/key infrastructure, DEX execution, BTC on L2, yield, token risk checks, fork testing |
| C | autonomous LLM trading agents and their evidence, single vs multi-agent, self-improvement methods, LLM plumbing, prompt-injection defences |
| D | macro, market-structure, on-chain and news data sources (free tiers, limits, licences) |
| E | Benjamin Cowen's framework: tools, theses, dated track record scored against data, candidate rules |
| F | verifiable on-chain track records (Hyperliquid, GMX, dYdX, Polymarket) and the statistics of copy-trading |

## Decisions by category

| Need | Chosen | Rejected (why) |
|---|---|---|
| Exchange connectivity | **ccxt** 4.5.x (MIT, near-daily releases, unified stop params) | exchange SDKs one by one (more code, same capability) |
| Backtest / paper engine | **custom, BTC numeraire** (`backtest/book.py`), shared by backtest, shadow and replay | freqtrade (single stake currency; cannot express BTC↔stable rotation in BTC accounting); backtrader (no commits since 2023); Hummingbot (market making); OctoBot (opinionated, 3.0 beta); Jesse (live is paid); vectorbt (fine for research, but a second engine means numbers that disagree); **NautilusTrader** kept as the upgrade path once 2.0 is final (rc8 today) |
| Exchange | **OKX Europe** (MiCA, PL passport, 0.10/0.20 %, native stop/OCO/trailing, EEA demo) + **Kraken** (second price source, 31 BTC pairs) | Binance (withdraw-only in PL since 2026-07-01, API trading revoked), Bitget (no MiCA licence), Zonda (bankrupt), Coinbase (EU fees unverified) |
| Stablecoin | **USDC** | USDT (not tradable on MiCA venues) |
| Agent / DeFi toolkit | **none**; thin web3.py / eth-account | GOAT (archived), Brian (shut down 2025), Virtuals GAME (stale), Coinbase AgentKit (maintenance mode), ElizaOS and Wayfinder (keys in the agent process) |
| LLM plumbing | **own ~250-line router** (OpenAI-compatible + Anthropic), Pydantic schemas, JSON-schema decoding on vLLM / llama.cpp / radiance | LiteLLM (PyPI 1.82.7/1.82.8 malicious, 2026-03-24; usable as a pinned-digest proxy only); LangGraph/PydanticAI/Agents SDK (not needed for a typed, few-call pipeline) |
| Signer | **separate daemon + encrypted keystore** (eth-account) with its own allowlist checks | EIP-7702 (the EOA key can still do anything); MPC/CDP/Privy (cloud dependency; possible second layer at $5k) |
| On-chain limits (upgrade) | **Safe + Zodiac Roles v2** with karpatkey DeFi Kit presets | ERC-4337 session-key stacks (more moving parts; Kernel v4 audit unverified) |
| Chain / BTC | **Base / cbBTC** (48.6k BTC on Base) | Arbitrum (66 cbBTC; WBTC custody concerns) |
| Swaps | **Uniswap v3 SwapRouter02 + QuoterV2** (works on a fork, quotes are pool state) | CoW Swap (best MEV protection, but off-chain solvers do not exist on a fork - a candidate for live); 0x/1inch (API keys); Odos (shut down 2026-07-30) |
| Lending | **Aave v3 Base** (instant withdrawal unless 100 % utilised) | Morpho vaults (higher APY 5.5–6.8 %, curator risk; candidate via EXTENDING), Pendle (lockups) |
| Stops | **own risk tick, BTC terms** | Gelato automations (reported end-of-life), CEX native stops (USD-denominated) |
| Token/contract checks | **GoPlus** (no key) + on-chain code check (`cryptoagent risk-check`) | honeypot.is (Base only - fine as a manual second opinion); Etherscan Base API (paid) |
| Fork testing | **Anvil** (Foundry Docker image) pinned to head−100 on mainnet.base.org | Hardhat (slower; no need) |
| BTC history, on-chain | **CoinMetrics Community** (2010→; MVRV, supply, hash rate, exchange flows) | Glassnode (no free plan); BGeometrics free tier (4 years, 15 req/day) |
| Prices for backtests | **data.binance.vision** (2017→), OKX REST for the latest days | CoinDesk/CryptoCompare (free tier ended May 2026) |
| Macro | **US Treasury** yield curve, **NY Fed** EFFR, Yahoo for DXY/S&P (secondary), DefiLlama stablecoins, alternative.me Fear & Greed | FRED (needs a key; unreachable without one from the rig - optional), ISM (not free) |
| News | RSS: Fed, SEC, ESMA, CoinDesk, The Block, Decrypt, rekt.news | CryptoPanic (free tier gone), social media (unverifiable, injection-prone) |
| Strategy inputs | Cowen's **verified** tools only (research E §2.11): 50W SMA, BMSB, log regression, realised price/MVRV, cycle clock, FF−2Y | his proprietary risk metric (approximated, not trusted), analogue-year narratives, price targets, lengthening cycles (falsified) |
| Learning from others | **not** copy-trading (research F) | Hyperliquid/GMX leaderboards: survivorship and luck dominate; no out-of-sample evidence at low frequency |
| Multi-agent | **single decision agent + vote + critic** | research/risk/execution/reviewer agent teams (~15× tokens, no evidence of better trading; LiveMACE: model-dependent) |
| Self-improvement method | **the course's safe loop** (gates, shadow, sentinel, probation, maintenance) | GEPA/TextGrad/DGM on P&L (too few outcomes; DGM documented metric gaming); Letta/Mem0 (a file with counters scored as well in Letta's own test) |

## "At least as good as the best public alternative"

The closest public systems (TradingAgents, ai-hedge-fund, FinRobot, ElizaOS trading plugins, Alpha Arena entrants)
let the LLM choose trades and have **no published out-of-sample evidence of beating BTC buy-and-hold** (research C;
the 2026 real-money OKX study: 32 methods, all negative alpha vs BTC). None combines a frozen policy engine, an
independent signer, BTC-denominated accounting, pre-registered strategy selection and a gated, reversible
self-improvement loop. On the dimensions that the evidence says matter - not losing to the benchmark, controlling
risk, auditability - this harness is at least as strong; on raw "intelligence" it uses the best local model and can
switch to any frontier model by config.
