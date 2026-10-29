# Self-improvement: how the course maps to the harness

Design basis: **"Self-improving agents without regressions"**, `llm-education/en/self-improving-agents` (README,
01–05, SOURCES, tools; read in full on 2026-10-29). Every rule of the course is mapped to a component below; every
deviation or extension is listed with its justification in §3.

## 1. The 15 rules → components

| # | Course rule | Where it lives | How it is enforced / tested |
|---|---|---|---|
| 1 | Never treat "nothing found" as evidence | `improve/controller.py` triggers; `llm/prompts.py` ("doing nothing is legitimate") | a quiet week opens no reflection (`test_controller_one_in_flight_backoff_and_maintenance`); `decision.action = none` is a normal, logged outcome |
| 2 | Accept the arithmetic of rare events | §2 below (our "hits" are trades: ~0.5 per month) | online A/B on trades is never used to *prove* an improvement; offline history + shadow non-inferiority + probation instead |
| 3 | The LLM proposes; code and statistics dispose | reflector emits one `Proposal`; `improve/gatekeeper.py` decides | gatekeeper is frozen code; no LLM call inside it |
| 4 | Freeze the measurement layer by construction | `frozen/` + `frozen/frozen.lock` hashes the metrics, ledger, gate rules, policy, signer, sentinel | `verify_lock()` before every cycle; tampering → kill switch (halt_only); `test_frozen_lock_detects_tampering` |
| 5 | Edit with deltas, never rewrites | `improve/playbook.py` (ADD / MODIFY / RETIRE by id; archive, never delete); params changed one or two at a time | `test_playbook_delta_edits_dedup_cap_and_retire`; static gate: ≤2 params |
| 6 | One change in flight, typed, with hypothesis, evidence, predicted effect, inverse | `Controller.in_flight`; `Proposal` schema; `change` events store the inverse | `test_controller_...`; static gate requires hypothesis/evidence/predicted_effect |
| 7 | Gate cheapest first; fix more than you break | `gatekeeper.static_gate` → `backtest_gate` (must-pass windows → full history, per cycle, bootstrap) → `shadow_decision` → `probation_check` | `frozen/gate_rules.yaml`; "max_cycles_worse: 1" is the trading form of "fix more than you break" |
| 8 | Learn only from verified outcomes | post-mortems only on **realised** BTC-terms losses from fills; lesson counters updated by code from scored forecasts | `improve/loop.py::postmortem`, `Agent.score_forecasts` |
| 9 | Shadow mode for judgment changes | parameter challengers run as a shadow `Book` on the same prices; judgment (playbook) changes are scored by paired Brier on forecasts | `ShadowBooks`, `judgment_shadow_decision` |
| 10 | Separate "the world changed" from "my change broke it" | `frozen/sentinel.yaml` runs forever in shadow next to the rules champion; probation compares new vs **old champion running in shadow** (difference-in-differences) | `sentinel_divergence` trigger; rollback test in the live self-improvement test |
| 11 | Small-sample statistics properly | `improve/stats.py`: exact binomial, McNemar, sign test, moving-block bootstrap, Page–Hinkley, Poisson CUSUM, deflated Sharpe | `test_course_statistics_match_published_tables` reproduces the course's numbers |
| 12 | A system that works should stop changing itself | controller MAINTENANCE after 3 rejections; exponential backoff 7→14→28 days; probation | controller tests |
| 13 | Match reflection to evaluation capacity | weekly at most (`schedule.review`), and only with a trigger; the backoff stretches it further | config + controller |
| 14 | Govern accumulation | playbook cap 6,000 chars, 300 per item, dedup ≥ 0.6 similarity, retrieve ≤ 3 lessons, skip items with harmful > helpful + 1, archive never delete | playbook tests |
| 15 | Treat runtime changes as challengers | model swaps are config changes recorded in every `model_call`; the replay test + golden live-LLM tests must pass after a model change (TESTING.md §5) | documented procedure; `served_model` logged |

The course's built pieces: **frozen measurement module** (`frozen/`, `backtest/metrics.py`), **evaluation assets**
(must-pass stress windows = the "must-pass subset"; the full 2011–2026 history = the "golden set"; post-2026-10-29
paper data = the "hidden slice" no reflection has seen), **itemised playbook + proposal schema**, **gatekeeper**,
**monitor** (shadow books, Page–Hinkley, drawdown and health alarms), **stopping logic** (controller), **calculator**
(`improve/stats.py`, ported from `tools/rare_event_stats.py`).

## 2. What "a hit" is here, and what that implies

The scout in the course has 0.1–0.3 hits per 15-minute round. This agent decides weekly and trades ~7 round trips
in 15 years. That is the rare-event problem in its most extreme form: **no online test can show that a strategy
change helped** within any reasonable time (02 §2). Consequences, all implemented:

* The *primary* evaluation door for strategy changes is **offline**: the full history in BTC terms, per halving
  cycle, with must-pass stress windows - the course's "evaluate whatever you can offline, on frozen data" (02 §3).
* The online door is **non-inferiority**, not superiority: a shadow challenger must not fall behind the champion by
  more than 1 % over 4–12 weeks; reaching 12 weeks without a decision keeps the champion (status-quo bias, 03 §6).
* The dense signal (02 §3, "denser leading indicators") is the analyst's **probabilistic forecasts** (7-day and
  30-day P(BTC up)), scored with Brier scores daily. They feed lesson counters and the judgment shadow test.
* The expected number of validated strategy changes is **a few per year**; the controller reaches MAINTENANCE fast.

## 3. Deviations and extensions (each justified)

| # | Deviation / extension | Course says | Why here |
|---|---|---|---|
| D1 | **No bandit** for allocation | 03 §5: Gamma-Poisson Thompson sampling over (source × query) arms | Our "arms" would be strategies, but outcomes arrive once per cycle (years); a bandit would allocate on noise. Allocation is fixed by the champion and changed only through the gates. |
| D2 | Outcome = BTC-terms return, not hit counts | Poisson hits, SPRT on hit attribution | Returns are continuous and autocorrelated; we use per-cycle paired comparison, a sign test across cycles, and a moving-block bootstrap of weekly differences. |
| D3 | **Deflated Sharpe ratio** (Bailey & López de Prado) added | winner's curse: discount, test one at a time | Every proposal ever backtested counts as a trial (`n_trials` from the ledger + the 10 pre-registered variants); reported with each gate decision. |
| D4 | Golden set = **history**, hidden slice = **the future** | ≥200 labelled items, 15–20 % hidden | There is one market history; the honest hidden slice is data after the strategy was fixed (2026-10-29 onward), which the forward paper record provides. Must-pass = 5 stress windows. |
| D5 | Probation compares to the **old champion in shadow** | CUSUM on the hit rate with the sentinel as control | Direct paired comparison on the same prices is more sensitive than a rate CUSUM; Page–Hinkley on weekly log differences plus a 3 % cumulative limit trigger rollback. The sentinel still separates world change from self-inflicted change. |
| D6 | LLM cannot write strategy **code** | course allows skill/code changes with gates | Self-written skills scored below none (SkillsBench); code would bypass param bounds. New strategy types are human work (EXTENDING.md); the agent tunes bounded params and the playbook. |
| D7 | Reflection: **3 samples + majority** on the local 80B-class model by default; a cloud "advisor" is a config switch | 03 §11 order of preference: stronger model weekly → local 70–80B with sampling → classification only | The rig's best model (Qwen3.8-Flash-Next) is near the course's threshold; majority-of-3 and code gates are the guard. Switching the reflector to a frontier model is one line in `config/models.yaml`. |
| D8 | Post-mortem triage uses a **fixed failure taxonomy** with "noise" as a first-class class | 03 §11 item 3 | Most single trading losses are variance; making "noise" legitimate (like "zero hits" in the course) prevents learning from luck. |

## 4. The loop, end to end

```
 fill closes a round trip that lost BTC
   └─► post-mortem: code facts (rule states at open, price path, costs, conviction) ─► triage model ─► class
         └─► (not noise, confidence ≥ 0.5) lesson ─► playbook ADD (cap, dedup, provenance) ─► retrieved ≤ 3 later
 weekly upkeep: shadow books step; ≥3 same-class post-mortems / sentinel divergence / scheduled review = trigger
   └─► controller: one in flight? probation? backoff? maintenance? ─► reflector (3 samples, majority) ─► Proposal
         └─► static gate ─► must-pass windows ─► full-history per-cycle + bootstrap (+ DSR reported)
               └─► shadow (4–12 weeks, non-inferiority) ─► promote: new version + git commit + old champion kept in shadow
                     └─► probation 12 weeks: Page–Hinkley / −3 % ─► automatic ROLLBACK (version + ledger + alert)
```

Every arrow is a ledger event (`postmortem`, `lesson_added`, `reflection`, `proposal`, `gate_decision`, `change`,
`probation`, `rollback`), so the whole history of how the agent changed itself can be audited and replayed.
