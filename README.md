# btc-agent

An autonomous agent that manages a crypto portfolio with one objective: **grow its value measured in BTC**.
The benchmark is simply holding BTC. Built to run 24/7 on a home rig with local LLMs (4× Radeon AI PRO R9700),
with cloud models available through config only.

> **The LLM proposes, code disposes.** Strategy rules are deterministic and backtested; the LLM can only scale
> down their deviations from BTC, flag protocol risk, and propose small typed changes to itself. A frozen policy
> engine, an independent signer, hard limits, allowlists and a hash-chained ledger sit outside its reach.

**Status (2026-10-30):** tested on the rig with live local models - 86 unit/integration, 19 fork, 9 live-LLM tests,
a 5-phase self-improvement run, a fresh-install end-to-end run and a multi-hour soak with injected faults
([docs/TEST_REPORT.md](docs/TEST_REPORT.md)). **Live trading is disabled** (`frozen/limits.yaml: stage: paper`) and
needs three human steps to enable ([docs/SETUP.md §5](docs/SETUP.md)).

## What it does, in one picture

```
 weekly closes, on-chain, macro ──► features (point-in-time) ──► RULES (backtested, frozen bounds) ──► target
 news / regulators (untrusted) ──► READER (tool-less, enums only) ──► digest ─┐                         │
                                                                              ▼                         ▼
                          lessons + playbook ──► ANALYST (3 samples, qwen3.8) ──► conviction ≤ 1 ──► CRITIC (qwen3.6, can only lower)
                                                                                                        │
                                       POLICY ENGINE (frozen code: limits, allowlists, costs, stops) ◄──┘
                                                │ allowed intents only
                       paper executor (live OKX books) │ Base fork / live via SIGNER (own checks, holds keys)
                                                ▼
                     LEDGER (append-only, hash-chained, tax fields)  ──►  post-mortems, forecasts, shadows
                                                                           ──► REFLECTOR (≤1 typed proposal)
                                                                           ──► GATEKEEPER (frozen): gates, shadow, probation, rollback
 risk tick every minute (no LLM): stops in BTC terms, daily-loss halt, drawdown kill switch, stale/divergent data
```

## The strategy, honestly

Pre-registered study of 10 variants built from Benjamin Cowen's *verifiable* tools, 2011–2026, in BTC terms
([docs/STRATEGY.md](docs/STRATEGY.md)): the champion — exit to USDC after two weekly closes below the 50-week SMA
in a mature cycle, re-enter on reclaim / 20 % BTC-terms stop / 450 days — ends at **1.55× the BTC of holding**,
winning 3 of 4 trading cycles with 14 trades. Altcoin rotation and valuation trims **lost** and are off.
The edge is **not statistically significant** (deflated Sharpe 0.36): there are only ~4 independent BTC cycles.
Most of the time the agent simply holds BTC. That is by design.

## Documentation

| Read | For |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | components, data flow, trust boundaries, design decisions (single agent, no framework) |
| [docs/RESEARCH.md](docs/RESEARCH.md) | the tool survey and why each tool was chosen or rejected; full reports in `docs/research/` |
| [docs/STRATEGY.md](docs/STRATEGY.md) | strategy rationale, the variant study, Cowen evidence, risks of every strategy type |
| [docs/SELF_IMPROVEMENT.md](docs/SELF_IMPROVEMENT.md) | course concept → component mapping, deviations and why |
| [docs/SETUP.md](docs/SETUP.md) | install from scratch, configuration reference, staged rollout to live |
| [docs/RIG.md](docs/RIG.md) | the rig as discovered: models, GPUs, endpoints, memory |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | 24/7 operation, monitoring, incidents, kill switch, tax export |
| [docs/TESTING.md](docs/TESTING.md) / [docs/TEST_REPORT.md](docs/TEST_REPORT.md) | how to re-run every test; the latest results |
| [docs/EXTENDING.md](docs/EXTENDING.md) | adding strategies, protocols, chains, venues and models |

## Quick start (paper)

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]" yfinance
.venv/bin/btcagent data refresh            # ~8 min the first time
.venv/bin/btcagent frozen verify
.venv/bin/python -m pytest -q              # unit + integration (live-LLM and fork tests are opt-in, see TESTING)
.venv/bin/btcagent decide                  # one full decision cycle with the rig's models, paper money
systemctl --user enable --now btcagent     # 24/7 (deploy/systemd/)
```

Private repository. Never commit secrets: the rig token, API keys, keystore passwords and keystores stay out of git
(`.gitignore`, and keys live only in the signer's environment or the Bitwarden vault).
