"""Command line: `btcagent <command>` (or `python -m btcagent.cli <command>`). See docs/OPERATIONS.md."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import frozen

HUMAN_CONFIRM = "I-AM-THE-HUMAN-OWNER"


def _agent(args):
    from .daemon import build
    ov = {"mode": args.mode} if getattr(args, "mode", None) else None
    return build(args.config, ov)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="btcagent")
    ap.add_argument("--config", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="run the 24/7 daemon")
    sub.add_parser("decide", help="run one decision cycle now")
    sub.add_parser("tick", help="run one risk tick now")
    sub.add_parser("upkeep", help="run the daily upkeep now (shadows, forecasts, post-mortems, review)")
    sub.add_parser("status", help="portfolio, risk state, controller, last decision")
    k = sub.add_parser("kill", help="engage (or release) the kill switch")
    k.add_argument("--mode", choices=["halt_only", "to_btc", "to_stable", "to_safe_address"])
    k.add_argument("--reason", default="manual")
    k.add_argument("--release", action="store_true")
    k.add_argument("--confirm", default="")
    d = sub.add_parser("data", help="data refresh")
    d.add_argument("action", choices=["refresh"])
    b = sub.add_parser("backtest", help="backtest the champion (or the pre-registered variants)")
    b.add_argument("--variants", action="store_true")
    f = sub.add_parser("frozen", help="frozen layer: verify or lock (human only)")
    f.add_argument("action", choices=["verify", "lock"])
    f.add_argument("--confirm", default="")
    lg = sub.add_parser("ledger", help="ledger: verify the hash chain or export tax records")
    lg.add_argument("action", choices=["verify", "export-tax", "tail"])
    lg.add_argument("--year", type=int)
    lg.add_argument("--out", default="reports/tax_export.csv")
    lg.add_argument("-n", type=int, default=20)
    s = sub.add_parser("signer", help="run the signer daemon")
    s.add_argument("--keystore")
    s.add_argument("--port", type=int, default=8790)
    s.add_argument("--mode", default="fork")
    ks = sub.add_parser("keystore", help="create an encrypted keystore (prints only the address)")
    ks.add_argument("path")
    rv = sub.add_parser("review", help="ask for a reflection now (human request trigger)")
    pp = sub.add_parser("propose", help="submit a human proposal; it goes through the same gates, shadow and probation")
    pp.add_argument("--target", required=True, help="e.g. cycle_guard.max_days_in_stable")
    pp.add_argument("--value", required=True)
    pp.add_argument("--hypothesis", required=True)
    pp.add_argument("--evidence", nargs="*", default=["human research"])
    rc = sub.add_parser("risk-check", help="token/contract risk report before allowlisting (GoPlus, on-chain code)")
    rc.add_argument("address")
    rc.add_argument("--chain-id", default="8453")
    st = sub.add_parser("state", help="controller state change (human only): BOOTSTRAP -> GATED etc.")
    st.add_argument("to", choices=["BOOTSTRAP", "GATED", "MAINTENANCE"])
    st.add_argument("--why", default="human decision")
    wd = sub.add_parser("withdraw", help="cancel the challenger in shadow, or roll back a promotion on probation (human only)")
    wd.add_argument("--why", required=True)
    args = ap.parse_args(argv)

    if args.cmd == "frozen":
        if args.action == "verify":
            p = frozen.verify_lock()
            print(json.dumps({"intact": not p, "problems": p}, indent=1))
            return 0 if not p else 2
        if args.confirm != HUMAN_CONFIRM:
            print(f"Re-locking the frozen layer is a human decision. Review `git diff frozen/ btcagent/` first, then run:\n"
                  f"  btcagent frozen lock --confirm {HUMAN_CONFIRM}")
            return 3
        print(json.dumps(frozen.write_lock(), indent=1))
        return 0
    if args.cmd == "keystore":
        from .signer import keystore
        print(keystore.create(args.path))
        return 0
    if args.cmd == "signer":
        from .agent.core import ROOT, expand
        import yaml
        cfg = yaml.safe_load((ROOT / "config" / "agent.yaml").read_text())
        from .signer.server import serve
        serve(str(expand(cfg["state_dir"])), args.keystore, args.mode, args.port)
        return 0
    if args.cmd == "risk-check":
        from .risk.riskcheck import report
        print(json.dumps(report(args.address, args.chain_id), indent=1, default=str))
        return 0
    if args.cmd == "backtest":
        import subprocess
        script = "scripts/research_variants.py" if args.variants else "scripts/first_backtest.py"
        from .agent.core import ROOT, expand
        import yaml
        cfg = yaml.safe_load((ROOT / "config" / "agent.yaml").read_text())
        return subprocess.call([sys.executable, str(ROOT / script), str(expand(cfg["data_dir"]))], cwd=ROOT)
    if args.cmd == "data":
        from .data import history
        from .agent.core import ROOT, expand
        import yaml
        cfg = yaml.safe_load((ROOT / "config" / "agent.yaml").read_text())
        print(json.dumps(history.download_all(expand(cfg["data_dir"])), indent=1))
        return 0
    if args.cmd == "run":
        from .daemon import run
        run(args.config)
        return 0

    agent = _agent(args)
    if args.cmd == "decide":
        print(json.dumps(agent.decide(), indent=1, default=str)[:20000])
    elif args.cmd == "tick":
        print(json.dumps(agent.risk_tick(), indent=1, default=str))
    elif args.cmd == "upkeep":
        print(json.dumps(agent.daily_upkeep(), indent=1, default=str))
    elif args.cmd == "status":
        prices = agent.prices()
        pf = agent.executor.portfolio()
        from .risk import killswitch
        last = agent.ledger.last("decision")
        print(json.dumps({"mode": agent.mode, "nav_btc": pf.nav_btc(prices), "nav_usd": pf.nav_usd(prices),
                          "weights": pf.weights(prices), "holdings": [h.model_dump() for h in pf.holdings],
                          "risk": agent.risk(), "killed": killswitch.kill_info(agent.state), "halted": killswitch.is_halted(agent.state),
                          "controller": agent.loop.ctrl.s.state, "in_flight": bool(agent.loop.ctrl.s.in_flight),
                          "probation": bool(agent.loop.ctrl.s.probation), "frozen_intact": not frozen.verify_lock(),
                          "ledger": agent.ledger.verify(),
                          "last_decision": {k: last.payload.get(k) for k in ("as_of", "action", "final_weights", "strategy_version")} if last else None},
                         indent=1, default=str))
    elif args.cmd == "kill":
        from .risk import killswitch
        if args.release:
            if args.confirm != HUMAN_CONFIRM:
                print(f"Releasing the kill switch is a human decision: btcagent kill --release --confirm {HUMAN_CONFIRM}")
                return 3
            killswitch.release(agent.state, agent.ledger, who="human via CLI")
            agent._save("kill_done.json", {"done": False})
            print("released")
        else:
            print(json.dumps(agent.kill(args.reason, auto=False, mode=args.mode), indent=1))
            print(json.dumps(agent.risk_tick(), indent=1, default=str))
    elif args.cmd == "ledger":
        if args.action == "verify":
            print(agent.ledger.verify())
        elif args.action == "tail":
            for e in agent.ledger.events(limit=args.n):
                print(e.seq, e.ts, e.kind, json.dumps(e.payload, default=str)[:300])
        else:
            from .ledger import tax
            n = tax.export(agent.ledger, args.out, tax.NBP(agent.state / "nbp_cache.json"), args.year)
            print(json.dumps({"rows": n, "out": args.out, "summary": tax.summary(args.out)}, indent=1))
    elif args.cmd == "review":
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        panel, feat = agent.panel()
        print(json.dumps(agent.loop.propose_and_gate(now, feat, panel, {"human_request"}), indent=1, default=str)[:20000])
    elif args.cmd == "propose":
        from datetime import datetime, timezone
        from .llm.schemas import Proposal
        val = float(args.value) if args.value.replace(".", "", 1).isdigit() else args.value
        prop = Proposal(op="PARAM_CHANGE", target=args.target, new_value=int(val) if isinstance(val, float) and val.is_integer() else val,
                        hypothesis=args.hypothesis, evidence=args.evidence, predicted_effect={"metric": "btc_multiple", "direction": "up"})
        panel, feat = agent.panel()
        print(json.dumps(agent.loop.propose_and_gate(datetime.now(timezone.utc), feat, panel, {"human_request"}, forced=prop),
                         indent=1, default=str)[:20000])
    elif args.cmd == "withdraw":
        print(json.dumps(agent.loop.withdraw(datetime.now(timezone.utc), args.why), indent=1))
    elif args.cmd == "state":
        agent.loop.ctrl.set_state(args.to, args.why)
        agent.loop.ctrl.save()
        print(agent.loop.ctrl.s.state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
