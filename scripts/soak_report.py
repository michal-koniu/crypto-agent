"""Summarise a soak run: uptime, decisions, errors and recovery, model usage, resources, ledger integrity.
Usage: python scripts/soak_report.py <state_dir> [out.json]"""
import csv
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from cryptoagent.ledger.store import Ledger

state = Path(sys.argv[1]).expanduser()
led = Ledger(state / "ledger.db")
ev = led.events()
kinds = Counter(e.kind for e in ev)
t0, t1 = datetime.fromisoformat(ev[0].ts), datetime.fromisoformat(ev[-1].ts)
starts = [e.ts for e in ev if e.kind == "daemon" and e.payload.get("event") == "start"]
stops = [e.ts for e in ev if e.kind == "daemon" and e.payload.get("event") == "stop"]
errors = [{"ts": e.ts, "where": e.payload.get("where"), "error": e.payload.get("error", "")[:160]} for e in ev if e.kind == "error"]
decisions = [e.payload for e in ev if e.kind == "decision"]
calls = [e.payload for e in ev if e.kind == "model_call"]
fallbacks = [c for c in calls if c.get("ok") and len(c.get("attempts", [])) > 1]
failed_calls = [c for c in calls if not c.get("ok")]
mon = []
mf = state / "soak_monitor.csv"
if mf.exists():
    mon = list(csv.DictReader(open(mf)))


def col(name, fn=max):
    vals = [float(r[name]) for r in mon if r.get(name) not in (None, "")]
    return fn(vals) if vals else None


rep = {
    "window": {"from": ev[0].ts, "to": ev[-1].ts, "hours": round((t1 - t0).total_seconds() / 3600, 2)},
    "events": dict(kinds),
    "daemon_starts": starts, "daemon_clean_stops": stops,
    "decisions": len(decisions),
    "decision_actions": dict(Counter(d.get("action") for d in decisions)),
    "decisions_with_analyst": sum(1 for d in decisions if d.get("analyst")),
    "served_models": dict(Counter(f"{c['role']}:{c.get('served_model')}" for c in calls if c.get("ok"))),
    "model_calls": len(calls), "model_calls_failed": len(failed_calls), "model_calls_with_fallback": len(fallbacks),
    "errors": len(errors), "errors_sample": errors[:12],
    "heartbeats": kinds.get("heartbeat", 0),
    "faults_seen": sorted({e["error"][:60] for e in errors if "injected" in e["error"]}),
    "resources": {"agent_rss_mb_max": col("agent_rss_mb"), "ram_avail_gb_min": col("ram_avail_gb", min),
                  "vram_gpu0_mb_max": col("vram_gpu0_mb"), "vram_gpu2_mb_max": col("vram_gpu2_mb"),
                  "samples": len(mon), "restarts_systemd": mon[-1]["restarts"] if mon else None},
    "ledger_verify": led.verify(),
    "last_status": {k: decisions[-1].get(k) for k in ("as_of", "action", "nav_btc", "nav_usd", "strategy_version")} if decisions else None,
}
print(json.dumps(rep, indent=1, default=str))
if len(sys.argv) > 2:
    Path(sys.argv[2]).write_text(json.dumps(rep, indent=1, default=str))
