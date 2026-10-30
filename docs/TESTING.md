# Testing guide

All commands run on the rig from the repository root. Nothing here touches real funds: paper fills, an Anvil fork
of Base, and historical replays only. `frozen/limits.yaml` keeps `stage: paper` throughout.

## 1. Unit and integration (fast, no models, no fork) - ~3 s
```bash
.venv/bin/python -m pytest -q -m "not live_llm and not fork"
```
| File | Covers |
|---|---|
| `tests/test_policy.py` | every policy limit, attacked: oversized orders (USD), more than held, lent funds not spendable, ALT weight cap, non-allowlisted asset/venue/pair, missing/too-wide stops, unknown costs, slippage/gas/edge caps, hourly/daily rate limits, anti-churn, daily-loss halt, drawdown kill, halted = exits only, mislabelled stop/kill reason codes, killed, stale and divergent prices, live stage gate, unlimited/oversized/foreign-spender approvals, protocol cap, transfers, rationale ignored |
| `tests/test_signer.py` | selectors = keccak of the signatures; swap recipient/min-out/allowlist; unknown contract/selector; native value; wrong chain; approvals (unlimited, oversized, foreign spender, revoke while killed, router approval while killed, pool approval while killed); transfers; Aave on-behalf/destination; CEX order rules; keystore never contains the key (0600); the real HTTP signer daemon signs a good tx, refuses a hostile one, refuses unauthenticated calls, journals both without secrets |
| `tests/test_ledger_tax.py` | hash chain, UPDATE/DELETE refused, tampering detected even with triggers dropped, JSONL mirror tampering, tax classes, export has every field and uses the NBP rate of the business day before |
| `tests/test_improve.py` | the agent cannot target limits/policy/allowlists/signer/gate rules/sentinel or exceed bounds; frozen-change requests change nothing; the lock detects tampering of limits and of policy code; the repository lock is intact; playbook deltas, dedup, cap, archive/restore; harmful lessons not retrieved; controller (no trigger → no reflection, one in flight, backoff, maintenance, reopen); probation rollback logic; shadow decisions; course statistics reproduce the course's tables; deflated Sharpe penalises many trials |
| `tests/test_router.py` | provider switching by config only for Anthropic, OpenAI, DeepSeek, Qwen, Kimi, GLM and the rig (**mocked endpoints**: no cloud keys available); fallback on a dead endpoint and on invalid output; all-fail raises and is logged; missing key → fallback; budget exhaustion → fallback |
| `tests/test_strategy_backtest.py` | real historical data: panel coverage; **no look-ahead** (features at t identical with or without later data); the champion reproduces the selection report (1.547×, 14 trades); HODL book = benchmark; rules deterministic; kill procedure plans |

## 2. Live local models - ~15–25 min
```bash
.venv/bin/python -m pytest -q -m live_llm tests/test_live_llm.py
.venv/bin/python scripts/smoke_llm.py rig:qwen3.6-35b-a3b rig:qwen3.8-flash-next rig:gemma-4-26b-a4b
```
Every local model in any role chain answers with schema-valid output; four injection attempts (web content, token
metadata, tool output, fake regulator) are flagged and excluded from the digest; the analyst cannot create exposure
the rules did not; the policy verdict is unchanged by model output; a poisoned reflection cannot reach the frozen
layer; **fallback when a local endpoint is actually stopped** (llama-swap unload) moves to the next model.

## 3. Self-improvement end to end (live triage + reflector, replayed history) - ~20–60 min
```bash
.venv/bin/python -u scripts/selfimprove_test.py reports/selfimprove_<date>.json
```
Five phases (losses → post-mortems → lessons; live reflection → gates; canonical fix → gates → shadow →
promotion → new version in use; automatic rollback of an underperforming promotion; frozen layer unreachable).
Exit code 0 only if every phase passed. The JSON report is the evidence.

## 4. Fork (Anvil fork of Base mainnet) - ~2 min
```bash
scripts/fork.sh start            # Foundry Docker image, pinned to head-100 of mainnet.base.org
.venv/bin/python -m pytest -q tests/test_fork.py
scripts/fork.sh stop
```
Allowlisted contracts verified on-chain; USDC→cbBTC on Uniswap v3 with an exact approval that is revoked after;
Aave v3 supply/withdraw; the signer refuses hostile transactions; **manual kill switch on the fork**: withdraw from
Aave, convert all stables to cbBTC, then new deposits and strategy trades are refused.

## 5. Fresh install, end to end - ~25 min
```bash
BRANCH=feat/initial-harness scripts/e2e_fresh_install.sh git@github.com:michal-koniu/crypto-agent.git
```
Clone → install → frozen verify → data refresh → tests → a live decision cycle (news reader, 3 analyst samples,
critic, policy, paper execution) → risk tick → upkeep → requested reflection → evidence (served model names, GPU
activity samples, ledger verify) → tax export.

## 6. Soak (hours)
```bash
cp deploy/systemd/cryptoagent-soak.service ~/.config/systemd/user/ && systemctl --user daemon-reload
systemctl --user start cryptoagent-soak                 # paper, decides every 60 min, separate state dir
scripts/soak_monitor.sh ~/.local/state/cryptoagent-soak &   # CSV every 5 min: RSS, RAM, VRAM, GPU activity, ledger
# fault injection (the agent reads <state>/faults.json):
echo '{"exchange_down": true, "until": "<iso time>"}' > ~/.local/state/cryptoagent-soak/faults.json
echo '{"llm_down": ["rig"], "until": "<iso time>"}'    > ~/.local/state/cryptoagent-soak/faults.json
kill -9 $(systemctl --user show -p MainPID --value cryptoagent-soak)        # crash -> systemd restarts it
systemctl --user stop cryptoagent-soak && systemctl --user start cryptoagent-soak  # graceful restart ("reboot")
.venv/bin/python scripts/soak_report.py ~/.local/state/cryptoagent-soak       # summary + integrity
```

## 7. Strategy research (reproducible)
```bash
.venv/bin/python scripts/research_variants.py ~/.local/share/cryptoagent/data reports/variants_v1.json
```

## When something fails
Fix the cause, re-run the failing suite, then the whole fast suite. Never skip or delete a failing test; if a
test was wrong, fix the test and say so in the test report (TEST_REPORT.md lists every such case).
