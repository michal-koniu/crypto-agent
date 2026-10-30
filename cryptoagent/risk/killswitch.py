"""Kill switch and halt (FROZEN).

* KILL: engaged manually (`cryptoagent kill`, or `touch <state>/KILL`) or automatically (drawdown limits, repeated
  execution failures, frozen-layer tampering). While engaged, the policy engine and the signer allow only the
  emergency procedure. Only the human can release it (`cryptoagent kill --release`); no code path in the agent does.
* HALT: engaged automatically for the rest of the UTC day on the daily-loss limit; new risk is blocked, exits to BTC
  are allowed. Cleared automatically at the next UTC day.

Emergency procedure (mode from frozen limits, overridable on the manual command):
  halt_only        stop trading, cancel open orders, revoke approvals; leave positions as they are
  to_btc           ... and convert every non-BTC holding into BTC (the numeraire and resting state)
  to_stable        ... and convert everything into USDC
  to_safe_address  ... to_btc, then transfer every token to the human-set safe address (on-chain only)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..ledger.store import Ledger


def kill_file(state_dir) -> Path:
    return Path(state_dir) / "KILL"


def halt_file(state_dir) -> Path:
    return Path(state_dir) / "HALT"


def is_killed(state_dir) -> bool:
    return kill_file(state_dir).exists()


def kill_info(state_dir) -> dict | None:
    f = kill_file(state_dir)
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text() or "{}")
    except json.JSONDecodeError:
        return {"reason": "manual (touch)", "mode": None}


def is_halted(state_dir) -> bool:
    f = halt_file(state_dir)
    if not f.exists():
        return False
    day = f.read_text().strip()
    if day != datetime.now(timezone.utc).date().isoformat():
        f.unlink(missing_ok=True)       # a halt lasts for the UTC day it was set
        return False
    return True


def engage(state_dir, ledger: Ledger, reason: str, mode: str, auto: bool) -> dict:
    info = {"reason": reason, "mode": mode, "auto": auto, "ts": datetime.now(timezone.utc).isoformat()}
    f = kill_file(state_dir)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(info))
    ledger.append("kill_switch", {"action": "engage", **info})
    return info


def release(state_dir, ledger: Ledger, who: str) -> None:
    """Human only. Called from the CLI after an explicit confirmation; never from the agent loop."""
    f = kill_file(state_dir)
    if f.exists():
        info = kill_info(state_dir)
        f.unlink()
        ledger.append("kill_switch", {"action": "release", "by": who, "was": info})


def halt_today(state_dir, ledger: Ledger, reason: str) -> None:
    halt_file(state_dir).write_text(datetime.now(timezone.utc).date().isoformat())
    ledger.append("halt", {"reason": reason})


def emergency_plan(holdings: list, mode: str, stable: str = "USDC") -> list[dict]:
    """Ordered list of steps; pure function so it can be tested without any venue."""
    steps: list[dict] = [{"step": "cancel_open_orders"}, {"step": "revoke_approvals"}]
    if mode == "halt_only":
        return steps
    for h in holdings:
        if h.protocol and h.qty > 0:
            steps.append({"step": "withdraw", "asset": h.asset, "qty": h.qty, "protocol": h.protocol})
    target = "BTC" if mode in ("to_btc", "to_safe_address") else stable
    for h in holdings:
        if not h.protocol and h.asset != target and h.qty > 0:
            steps.append({"step": "convert", "sell": h.asset, "buy": target, "qty": h.qty})
    if mode == "to_safe_address":
        steps.append({"step": "transfer_all_to_safe"})
    return steps
