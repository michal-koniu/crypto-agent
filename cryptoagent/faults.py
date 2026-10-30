"""Fault injection for soak and failure tests (never active unless <state>/faults.json exists).

{"exchange_down": true}            market data calls raise (tests stale-data handling and recovery)
{"llm_down": ["rig"]}              router treats these providers as unreachable (tests fallbacks)
{"until": "2026-10-30T02:00:00+00:00"}   optional expiry
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

_PATH: Path | None = None


def configure(state_dir) -> None:
    global _PATH
    _PATH = Path(state_dir) / "faults.json"


def active() -> dict:
    p = _PATH or (Path(os.environ["CRYPTOAGENT_STATE"]) / "faults.json" if os.environ.get("CRYPTOAGENT_STATE") else None)
    if not p or not p.exists():
        return {}
    try:
        f = json.loads(p.read_text())
    except json.JSONDecodeError:
        return {}
    until = f.get("until")
    if until and datetime.now(timezone.utc) > datetime.fromisoformat(until):
        return {}
    return f


class InjectedFault(ConnectionError):
    pass
