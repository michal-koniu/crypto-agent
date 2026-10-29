# Setup, configuration reference, staged rollout

## 1. Install from scratch (Ubuntu 24.04, Python 3.12; tested on the rig 2026-10-29)

```bash
cd ~/Desktop/github_repos && git clone git@github.com:michal-koniu/btc-agent.git && cd btc-agent
python3 -m venv .venv
.venv/bin/pip install -U pip && .venv/bin/pip install -e ".[dev]" yfinance
.venv/bin/btcagent frozen verify          # {"intact": true}
.venv/bin/btcagent data refresh           # ~8 min: CoinMetrics, Binance monthly files, Treasury, NY Fed, ...
.venv/bin/python -m pytest -q             # unit + integration; see TESTING.md for live-LLM and fork suites
```
Optional for fork testing: Docker (the rig has it) - `scripts/fork.sh start` pulls Foundry's official image.
Models: llama-swap on `localhost:8080` (RIG.md). Nothing else to install.

## 2. Files you configure

| File | Owner | What |
|---|---|---|
| `config/agent.yaml` | human | mode/executor, paths, schedule, trading threshold, yield, analyst/critic on/off, news, alerts |
| `config/models.yaml` | human | providers, per-role model + fallbacks, temperature, token limits, thinking on/off, budgets |
| `frozen/limits.yaml` | **human, frozen** | stage, capital cap, position/exposure/order limits, loss limits, stops, costs, gas, rate limits, approvals, kill mode, safe address, data freshness |
| `frozen/allowlists.yaml` | **human, frozen** | chains, venues, assets, CEX pairs, tokens (addresses), contracts + allowed selectors, approval spenders, protocols |
| `frozen/param_bounds.yaml` | **human, frozen** | the box each evolvable strategy parameter must stay in |
| `frozen/gate_rules.yaml` | **human, frozen** | thresholds of every self-improvement gate, probation, controller |
| `frozen/sentinel.yaml` | **human, frozen** | the pinned strategy copy that never changes |
| `evolvable/strategies.yaml` | agent via gatekeeper | champion strategy and params (versioned, git-committed on change) |
| `evolvable/playbook.yaml` | agent via gatekeeper | analyst guidance, lessons, procedures (itemised, counters) |

After editing anything in `frozen/` (or the frozen code listed in `btcagent/frozen.py`): review the diff, then
`btcagent frozen lock --confirm I-AM-THE-HUMAN-OWNER`. Without re-locking, the agent halts itself.

### config/agent.yaml reference
* `mode`: `paper` | `fork` | `live`. `executor`: `paper` (live prices, simulated fills) | `evm` (Base via signer).
* `schedule.risk_tick_seconds` (60), `decision_utc` ("00:30"), `review` (`daily|weekly|monthly`), `review_weekday`,
  `data_refresh_hours`, `heartbeat_minutes`.
* `trading.min_trade_nav_fraction` (0.05): smaller weight changes are ignored (anti-churn).
* `yield.*`: protocol, keep_liquid_fraction, min_usd, expected_apy, lockup_hours.
* `analyst.enabled` (false = rules only), `samples`, `critic`. `news.enabled`, `since_hours`.
* `alerts.email_to`, `email_enabled`, `telegram_enabled` (env `BTCAGENT_TELEGRAM_TOKEN`, `BTCAGENT_TELEGRAM_CHAT`).

### config/models.yaml reference
* `providers.<name>`: `kind` (openai|anthropic), `base_url`, `api_key_env`, `price_per_mtok`.
* `roles.<analyst|critic|reader|reflector|triage>`: `model` ("provider:model"), `fallbacks`, `temperature`,
  `max_tokens`, `timeout_s`, `samples`, `extra_body` (e.g. `chat_template_kwargs: {enable_thinking: false}`).
* `budgets.per_role_daily_tokens`, `per_provider_daily_usd`; an exhausted budget moves to the next fallback.
* Switching to a cloud model: set its key in the agent's environment (e.g. `ANTHROPIC_API_KEY`) and change one line,
  e.g. `analyst: {model: anthropic:claude-opus-5-5, fallbacks: [rig:qwen3.8-flash-next]}`.

## 3. Staged rollout

| Stage | What runs | Gate to the next stage (human decision) |
|---|---|---|
| 0 Backtest | `btcagent backtest --variants`; `pytest` | the champion beats HODL over full history and survives the stress windows (done: STRATEGY.md) |
| 1 Paper | `mode: paper`, `executor: paper`, `btcagent run` 24/7 with 100 USDC of paper money | ≥ 8 weeks without errors; ledger verifies; forecasts are scored; the overlay vs `rules_champion` shadow is understood |
| 2 Fork | `mode: fork`, `executor: evm`, signer + Anvil fork | every fork test passes (TESTING.md §4); a kill switch drill on the fork |
| 3 Live, tiny | `stage: live`, `capital_cap_usd: 100`, 100 USDC on Base (or OKX) | ≥ 3 months; no limit breach; behaviour matches the paper shadow |
| 4 Scale | raise `capital_cap_usd` in steps (e.g. 500 → 2,000 → 5,000); add Safe + Zodiac Roles before 5,000 | each step ≥ 1 month clean |

## 4. Wallet and keys (stage 2+)

* Create a **new** wallet for the agent - not your MetaMask account: `btcagent keystore create ~/.local/state/btcagent/keystore.json`
  (prompts nothing; password from `BTCAGENT_KEYSTORE_PASSWORD_CMD`, e.g. `bw-secret btc-agent#keystore-password`).
  Only the address is printed. Fund it from MetaMask with USDC on Base (and ~$2 of ETH on Base for gas).
  The 100 USDT: swap to USDC first (USDT is not tradable on MiCA venues; on Base, USDC is the deep market).
* CEX (optional): create an OKX Europe API key with **trade permission only, withdrawals disabled, IP whitelist =
  the rig**; put it in Bitwarden; the signer service reads `BTCAGENT_OKX_KEY/_SECRET/_PASSPHRASE` from its own
  environment. Test first with OKX EEA demo trading (`BTCAGENT_OKX_DEMO=1`).
* Set `kill_switch.safe_address` (e.g. your MetaMask address) in `frozen/limits.yaml` and re-lock.

## 5. Going live - the three human steps (never on by default)

1. `frozen/limits.yaml`: `stage: live`, a `capital_cap_usd`, a `safe_address` → review → `btcagent frozen lock --confirm ...`.
2. `config/agent.yaml`: `mode: live`, `executor: evm` (or a CEX executor), and start `btcagent-signer` with `--mode live`.
3. The agent's environment: `BTCAGENT_LIVE=I_ACCEPT_REAL_LOSSES` (systemd `Environment=`).
Missing any one of the three, the policy engine (and the signer) refuse every live action.

## 6. Upgrading

`git pull`, `pip install -e .`, `pytest -q`, review `git diff` of `frozen/` and frozen code, re-lock if intended,
`systemctl --user restart btcagent`. A model or runtime change is treated as a challenger (SELF_IMPROVEMENT.md
rule 15): run the live-LLM suite and a replay before switching.
