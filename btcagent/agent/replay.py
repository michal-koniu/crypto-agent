"""Replay: drive the real agent (live LLMs, policy engine, paper executor, ledger, improvement loop) over a window of
history with a simulated clock. Used for the end-to-end and self-improvement tests. Mechanics, not performance:
the models may remember what happened next, so replay numbers are never evidence of skill."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

import pandas as pd

from .core import ROOT, Agent
from ..execution.paper import PaperExecutor
from ..execution.simmarket import HistoricalMarket


def make_agent(state_dir: Path, start: str, overrides: dict | None = None, deposit: dict | None = None,
               workdir: Path | None = None) -> Agent:
    """A replay agent works on a private copy of evolvable/ so promotions and rollbacks never touch the repo."""
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    work = Path(workdir or state_dir / "evolvable")
    if not work.exists():
        shutil.copytree(ROOT / "evolvable", work)
    ov = {"mode": "replay", "state_dir": str(state_dir), "strategies": str(work / "strategies.yaml"),
          "playbook": str(work / "playbook.yaml"), "alerts_dry_run": True, "git_commit_changes": False,
          "news": {"enabled": False}}
    ov.update(overrides or {})
    agent = Agent(ROOT / "config" / "agent.yaml", overrides=ov)
    panel, _ = agent.panel()
    agent.market = HistoricalMarket(panel)
    agent.market.set_date(pd.Timestamp(start))
    agent.executor = PaperExecutor(agent.ledger, agent.market, agent.state, mode="replay")
    if not agent.ledger.events(kind="deposit"):
        for a, q in (deposit or {"BTC": 1.0}).items():
            agent.executor.deposit(a, q, note="replay starting capital")
    return agent


def run(agent: Agent, start: str, end: str, step_days: int = 7, decide: bool = True, upkeep: bool = True,
        on_step=None) -> list[dict]:
    out = []
    d = pd.Timestamp(start)
    while d <= pd.Timestamp(end):
        now = datetime.combine(d.date(), time(0, 30), tzinfo=timezone.utc)
        agent.clock = lambda now=now: now
        agent.ledger.clock = lambda now=now: now.isoformat(timespec="microseconds")
        agent.market.set_date(d - pd.Timedelta(days=1))           # decisions use yesterday's close
        tick = agent.safe_call(agent.risk_tick, now)
        up = agent.safe_call(agent.daily_upkeep, now, review=(d.weekday() == 0)) if upkeep else None
        dec = agent.safe_call(agent.decide, now) if decide else None
        rec = {"date": str(d.date()), "tick": tick, "upkeep": up,
               "decision": {k: (dec or {}).get(k) for k in ("action", "final_weights", "nav_btc", "nav_usd", "strategy_version")}}
        out.append(rec)
        if on_step:
            on_step(rec)
        d += pd.Timedelta(days=step_days)
    return out
