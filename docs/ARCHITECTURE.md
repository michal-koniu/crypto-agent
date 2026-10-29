# Architecture and design decisions

## 1. Principles

1. **The LLM proposes, code disposes.** No model output reaches money without passing deterministic code: the
   strategy rules produce the target, the analyst can only *reduce* deviations from BTC, the policy engine checks
   every intent against frozen limits, and the signer re-checks every raw transaction against its own allowlist.
2. **Measured in BTC.** NAV, drawdowns, stops, edges and every benchmark are in BTC. Holding BTC is the resting
   state; holding stablecoins is a (deliberate, temporary) bet against BTC with a stop.
3. **Only verifiable evidence** shapes the strategy: our backtests on raw data, on-chain data, dated public calls
   scored against price history ([STRATEGY.md](STRATEGY.md)).
4. **Freeze the measurement layer by construction** (course rule 4): limits, allowlists, policy, signer, ledger,
   metrics, gate rules and the sentinel are hashed in `frozen/frozen.lock`; the agent has no tool that writes
   files; the gatekeeper writes only `evolvable/`; a mismatch halts the agent.
5. **Everything is logged** in an append-only, hash-chained ledger, including "do nothing".

## 2. Components

| Layer | Module | What it does | Trust |
|---|---|---|---|
| Data ingestion | `data/history.py`, `data/features.py`, `execution/market.py` | CoinMetrics, Binance, OKX, Treasury, NY Fed, DefiLlama, Fear & Greed, Yahoo → daily panel → point-in-time weekly features; live prices and order books from OKX with Kraken as the independent second source | public data, cross-checked |
| News | `data/news.py` | RSS from the Fed, SEC, ESMA, crypto press, rekt.news → **reader** model one item at a time → enums → digest | **untrusted** input; firebreak |
| Strategy layer | `strategies/rules.py`, `evolvable/strategies.yaml` | deterministic rules → target weights (BTC/USDC/ETH) and BTC-terms stops | code; params bounded by `frozen/param_bounds.yaml` |
| Analyst + critic | `agent/core.py`, `llm/prompts.py`, `llm/schemas.py` | 3 analyst samples → median conviction ∈ [0,1] per deviation, protocol-risk flags, calibrated forecasts; critic (different model) can only lower | LLM, structured output, validated |
| Policy / risk engine | `policy/engine.py` (frozen) | position, exposure, order size, stops, costs-before-acting, edge-to-cost, slippage, gas, rate limits, anti-churn, stale/divergent data, daily loss halt, drawdown kill, live-stage gate | **frozen code** |
| Execution | `execution/paper.py`, `execution/evm.py`, signer `/cex_order` | paper fills on live OKX books; Base (Uniswap v3 + Aave v3) with exact approvals then revoke; CEX via the signer | code |
| Signer | `signer/server.py`, `signer/policy.py`, `signer/keystore.py` (frozen) | separate process; encrypted keystore; signs only allowlisted contracts/selectors, recipient = own wallet, no native value, bounded approvals, transfers only to the safe address during a kill; rate-limited; own journal | **frozen code, holds keys** |
| Risk tick | `agent/core.py::risk_tick`, `risk/killswitch.py` (frozen) | every minute, no LLM: stops, halt, kill, kill procedure | code |
| Logging | `ledger/store.py`, `ledger/tax.py` (frozen) | SQLite + JSONL mirror, SHA-256 chain, triggers refuse UPDATE/DELETE; Polish tax export with NBP D-1 rates | **frozen code** |
| Self-improvement | `improve/` | post-mortems → lessons; reflector → one typed proposal; gatekeeper (frozen) → static, must-pass, backtest, shadow, probation, rollback; controller (lifecycle, backoff, maintenance) | gatekeeper frozen; reflector LLM |
| Knowledge base | `evolvable/playbook.yaml`, `improve/playbook.py` | itemised judgment / lessons / procedure with helpful/harmful counters, caps, dedup, archive-not-delete | evolvable through gates |
| Alerts | `alerts.py` | e-mail via the rig's msmtp, optional Telegram; every alert is also a ledger event | code |
| Daemon / CLI | `daemon.py`, `cli.py`, `deploy/systemd/` | 24/7 loop, crash-safe (state in files and the ledger) | code |

## 3. Trust boundaries

```
 untrusted text ──► reader (no tools, enum output) ──► digest (counts only) ──► analyst
 analyst/critic output (JSON, validated) ──► conviction ∈ [0,1] ──► × rule deviation      (can only reduce)
 reflector output (one typed proposal) ──► gatekeeper (code) ──► evolvable/ only          (bounded, gated, reversible)
 intents ──► policy engine (frozen) ──► executor ──► signer (frozen, own checks, keys) ──► chain / exchange
```

* **Prompt injection** can at worst mislabel a news item (enums) or lower conviction (toward BTC, the
  benchmark). It cannot add exposure, change a limit, or reach the signer. Tested with live models
  ([TEST_REPORT.md](TEST_REPORT.md) §adversarial).
* **Keys** exist only in the signer process (EVM keystore decrypted in memory; CEX keys in its environment, created
  without withdrawal permission). The signer exposes no withdrawal endpoint.
* **Self-modification** is limited to `evolvable/strategies.yaml` (within `param_bounds`) and
  `evolvable/playbook.yaml`; the gatekeeper's static gate rejects anything naming the frozen layer, and the lock
  catches any write to it.

## 4. Design decisions

| Decision | Choice | Why |
|---|---|---|
| Single vs multi-agent | **single decision agent + voting + a critic of a different model** | research C: voting explains most "debate" gains; multi-agent costs ~15× tokens; no evidence it improves trading. The critic is a check, not a co-trader. |
| Agent framework | **none** (thin router, Pydantic schemas) | research B/C: GOAT archived, Brian shut down, AgentKit in maintenance, ElizaOS keeps keys in-process; LiteLLM had malicious PyPI releases (March 2026). A thin, studyable core is safer. |
| Backtest / execution engine | **custom, BTC numeraire**, ccxt for exchanges | research A: only LEAN supports a BTC account currency natively and it is heavy; freqtrade cannot express BTC↔stable rotation in BTC accounting. One `Book` class serves backtest, shadow and replay so numbers agree. |
| Exchange | **OKX Europe** (primary), Kraken (second price source / BTC pairs) | MiCA-licensed for Poland, lowest fees, native stops, the only EEA demo environment. Binance excluded (no API trading in PL since July 2026). USDT is not tradable on MiCA venues → USDC. |
| Chain | **Base**, BTC = cbBTC | research B: deepest BTC liquidity among L2s (48.6k cbBTC on Base vs 66 on Arbitrum); cents of gas. cbBTC is custodial (Coinbase) - a documented risk. |
| Wallet / signer | encrypted keystore in a separate signer daemon; Safe + Zodiac Roles as the upgrade path at the 5k stage | at $100 an on-chain Safe deployment adds cost and complexity; the off-chain signer policy is tested on a fork. For $5k, on-chain limits (Roles) add a second, chain-enforced layer (EXTENDING.md). |
| Stops | in the agent's own risk tick, in BTC terms | on-chain stop orders (Gelato) reported end-of-life; CEX native stops are USD-denominated; a BTC-terms stop on a stablecoin leg must be custom anyway. |
| Strategy | rules from Cowen's verifiable tools, pre-registered variants, champion by data | STRATEGY.md |
| LLM role | conviction overlay + forecasts + post-mortem triage + reflection | research C: no credible evidence LLMs beat buy-and-hold BTC; FINSABER: LLMs too cautious in bulls and too aggressive in bears. The overlay is measured against the rules-only shadow book. |
| Self-improvement | course design (gates, shadow, sentinel, probation, maintenance) | SELF_IMPROVEMENT.md |

## 5. Data flow of one decision (what the ledger shows)

`decision` event fields: `decision_id, mode, as_of, week, strategy_version, playbook_version, prompt_version, model,
rules_target, rule_states, features, news_digest, analyst{models, served, regime_votes, conviction, forecasts,
key_factors, lessons_applied, justification}, critic, final_weights, weights_before/after, nav_btc, nav_usd, btc_usd,
actions[]`. Linked events: `model_call` (every model request: role, requested and served model, tokens, latency,
attempts/fallbacks), `news_item`, `policy_check` (intent, allowed, violations), `fill` (all tax fields), `lend`,
`forecast`, later `forecast_score`, `postmortem`, `lesson_added`, `proposal`, `gate_decision`, `change`, `rollback`.
Macro influence is visible in `analyst.key_factors` (factor, direction more/less BTC, weight) and in the features.
