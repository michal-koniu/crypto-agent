# Operations runbook

Everything below runs on the rig (`~/Desktop/github_repos/btc-agent`, user services). Paths: state
`~/.local/state/btcagent/`, data `~/.local/share/btcagent/data/`.

## 1. Run 24/7

```bash
cp deploy/systemd/btcagent.service ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now btcagent
loginctl enable-linger $USER                 # survive logout / reboot
journalctl --user -u btcagent -f             # live log (the ledger is the real log)
```

What runs when (config/agent.yaml `schedule`): risk tick every 60 s (no LLM); heartbeat hourly; at 00:30 UTC the
daily upkeep (shadow books, forecast scoring, post-mortems, review/reflection when triggered) then the decision
cycle. A full cycle with news (~25 reader calls) and three analyst samples takes ~10–15 minutes on the `duo`
models; between cycles the GPUs are free (llama-swap unloads after 10 min idle).

**GPU sharing.** The agent needs llama-swap group `duo` (qwen3.8 on GPU 0+1, qwen3.6 on GPU 2+3) for ~15 minutes a
day. If something else (OpenClaw's `pedro` group, ComfyUI) holds the GPUs at 00:30, llama-swap swaps models; the
other workload pauses. Move `decision_utc` if that clashes with your use of the rig.

## 2. Monitor

| What | How |
|---|---|
| Status | `btcagent status` - NAV in BTC and USD, weights, risk marks, kill/halt, controller state, ledger integrity, last decision |
| Ledger | `btcagent ledger tail -n 30`, `btcagent ledger verify` (hash chain + JSONL mirror) |
| Alerts | e-mail via msmtp (trades, halts, kills, errors, rollbacks); every alert is also a ledger `alert` event |
| Evidence a model served | `model_call` events: `served_model`, tokens, latency, fallbacks |
| Decisions | `decision` events: rules target, analyst conviction + key macro factors + justification, critic, actions |
| Self-improvement | `controller.json` (state, in-flight challenger, probation), `shadow.json` (rules-only, sentinel, HODL, challenger NAVs), `gate_decision` events |
| Rig health | Netdata (:19999) - RAM is the binding limit; the agent itself uses < 300 MB |

Weekly human review (15 min): `btcagent status`; read the last few `decision` justifications; check
`shadow.json` (is the LLM overlay helping vs `rules_champion`? is the sentinel diverging?); read any `proposal` and
`gate_decision`; labels are not needed - outcomes are computed by code.

## 3. Incidents

| Symptom | Likely cause | Do |
|---|---|---|
| `error` events / alert "error in decide" | data source down, model timeout | the cycle retries tomorrow; risk ticks continue. Check `btcagent ledger tail`. A dead model falls back automatically (see `model_call.attempts`). |
| "prices are Ns old" / "sources diverge" in `policy_check` | exchange API outage, flash crash on one venue | no new orders by design; exits still allowed when only staleness is the issue. Wait; investigate if > 1 h. |
| HALT (daily-loss limit) | NAV fell > 6 % in BTC terms today | automatic; clears at the next UTC day. Read the decision log. |
| KILL (automatic) | drawdown limit, frozen-layer tamper, policy kill | the emergency procedure runs on the next tick (default: everything to BTC). Investigate; release only when understood. |
| `frozen layer modified` | someone edited a frozen file without re-locking | `git diff frozen/ btcagent/`; if intended: `btcagent frozen lock --confirm I-AM-THE-HUMAN-OWNER`, then release the kill. |
| rollback alert | a promoted strategy underperformed the old one in probation | nothing to do; it is the loop working. Read `rollback` and `gate_decision`. |

## 4. Kill switch

```bash
btcagent kill --reason "why" [--mode halt_only|to_btc|to_stable|to_safe_address]   # manual: engages + runs the procedure
touch ~/.local/state/btcagent/KILL                                                    # also works (picked up on the next tick)
btcagent kill --release --confirm I-AM-THE-HUMAN-OWNER                                # human only
```
Procedure: cancel open orders → revoke approvals → withdraw from lending → convert (to BTC by default) →
optionally transfer to `kill_switch.safe_address` (set it in `frozen/limits.yaml` before live). While engaged, the
policy engine allows only the procedure, and the signer signs only exits, revokes and transfers to the safe address.
Automatic triggers: BTC-terms drawdown > 25 %, USD drawdown > 45 %, frozen-layer tampering.

## 5. Tax and accounting

```bash
btcagent ledger export-tax --year 2026 --out reports/tax_2026.csv
```
One row per fill with UTC time, venue/chain, tx hash or order id, assets, quantities, price, fees, gas, slippage,
USD value, NBP Table A USD/PLN of the last business day before the trade, PLN value, tax class (crypto↔crypto is
neutral; fiat legs are income/cost), strategy version, decision id and model. Interest/Earn is flagged for the
accountant (unsettled PIT treatment, research A). Keep the CSV and the ledger until the end of 2032 for 2026 trades.

## 6. Backups

The state directory is the system of record: copy `~/.local/state/btcagent/` (ledger.db + ledger.jsonl + JSON state)
daily, e.g. `rsync -a ~/.local/state/btcagent/ /mnt/backup/btcagent/`. The keystore (live stage) is encrypted; its
password lives only in Bitwarden.

## 7. Strategy changes: propose, watch, withdraw (human)
The agent changes its own strategy only through the gates (SELF_IMPROVEMENT.md). You can feed the same pipeline:

```bash
.venv/bin/btcagent propose --target cycle_guard.<param> --value <v> --hypothesis "..." --evidence <files>
.venv/bin/btcagent status                 # controller state, in-flight challenger, probation
.venv/bin/btcagent ledger tail            # gate_decision / change / probation / rollback events
.venv/bin/btcagent withdraw --why "..."   # cancel the challenger in shadow, or roll back a promotion on probation
```

A proposal runs static → must-pass windows → full history (per cycle, bootstrap, deflated Sharpe) → shadow 4–12
weeks → promotion (git commit of `evolvable/strategies.yaml`) → probation. A challenger that never acts differently
from the champion runs the full 12 weeks and is promoted on offline evidence only (flagged in the ledger); its
probation keeps the old champion in shadow with automatic rollback armed until the two have differed for 12 weeks.
`withdraw` is logged and does not count as a rejection. **In flight since 2026-10-30:**
`cycle_guard.max_days_in_stable 450 → 240` (STRATEGY.md §7).

## 8. Protocol-status guard
Every risk tick (and before every deposit) the agent reads the lending reserve's own flags on chain
(`btcagent/risk/protocol_status.py`; paper mode via `protocol_status.rpc_url`, fork/live via the executor's RPC; cached
5 minutes). Ledger events: `protocol_status` (every change of state), `protocol_exit` (withdrawal after a freeze).
Alerts: warning on frozen/inactive, critical on paused (withdrawals impossible). **As of 30 Oct 2026 every Aave v3
Base reserve is frozen on mainnet** — the stable leg stays liquid until it is unfrozen or the owner allowlists another
venue (frozen layer: `allowlists.yaml`, then `btcagent risk-check` first).
