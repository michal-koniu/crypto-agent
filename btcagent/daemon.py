"""The 24/7 loop. Stateless between iterations: everything it needs is in the state directory and the ledger, so
a crash or reboot loses nothing (systemd restarts it; see deploy/systemd/).

  every risk_tick_seconds   risk tick (stops, halts, kill switch, kill procedure)
  every heartbeat_minutes   heartbeat event (NAV, ledger head) for monitoring
  daily at decision_utc     daily upkeep (shadows, forecast scoring, post-mortems, review/reflection), then decision
"""
from __future__ import annotations

import json
import signal
import time
from datetime import datetime, timezone

from .agent.core import Agent
from .execution.market import Market
from .execution.paper import PaperExecutor

RUNNING = True


def _stop(*_):
    global RUNNING
    RUNNING = False


def build(cfg_path=None, overrides=None) -> Agent:
    from .agent.core import ROOT
    agent = Agent(cfg_path or ROOT / "config" / "agent.yaml", overrides=overrides)
    agent.market = Market()
    if agent.cfg["executor"] == "paper":
        agent.executor = PaperExecutor(agent.ledger, agent.market, agent.state, mode=agent.mode,
                                       lend_apy=agent.cfg["paper"]["lend_apy"])
        if not agent.ledger.events(kind="deposit"):
            for asset, qty in agent.cfg["paper"]["initial_deposit"].items():
                agent.executor.deposit(asset, float(qty))
    elif agent.cfg["executor"] == "evm":
        from .execution.evm import EvmExecutor
        from .signer.client import SignerClient
        agent.executor = EvmExecutor(agent.cfg["evm"]["rpc_url"], SignerClient(str(agent.state)), agent.ledger,
                                     chain=agent.cfg["evm"]["chain"], mode=agent.mode)
        problems = agent.executor.verify_allowlist()
        if problems:
            raise SystemExit("allowlist verification failed: " + "; ".join(problems))
    else:
        raise SystemExit(f"executor {agent.cfg['executor']} is not wired in this release")
    return agent


def run(cfg_path=None, overrides=None, max_iterations: int | None = None):
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    agent = build(cfg_path, overrides)
    sched = agent.cfg["schedule"]
    hh, mm = map(int, sched["decision_utc"].split(":"))
    last = agent._load("daemon.json", {"last_decision_day": None, "last_heartbeat": 0})
    agent.ledger.append("daemon", {"event": "start", "mode": agent.mode, "executor": agent.cfg["executor"]})
    it = 0
    while RUNNING and (max_iterations is None or it < max_iterations):
        it += 1
        now = datetime.now(timezone.utc)
        agent.safe_call(agent.risk_tick, now)
        if time.time() - last["last_heartbeat"] >= sched["heartbeat_minutes"] * 60:
            agent.safe_call(agent.heartbeat, now)
            last["last_heartbeat"] = time.time()
        due = (now.hour, now.minute) >= (hh, mm)
        if due and last["last_decision_day"] != str(now.date()):
            agent.safe_call(agent.daily_upkeep, now)
            agent.safe_call(agent.decide, now)
            last["last_decision_day"] = str(now.date())
        agent._save("daemon.json", last)
        for _ in range(int(sched["risk_tick_seconds"])):
            if not RUNNING:
                break
            time.sleep(1)
    agent.ledger.append("daemon", {"event": "stop", "iterations": it})
    print(json.dumps({"stopped": True, "iterations": it}))
