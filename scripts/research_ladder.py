"""Pre-registered study (2026-10-30): does a reachable re-entry ladder help the champion?

Fixed before running: four variants, every other parameter = cycle_guard_v2.
  A  champion (ladder unreachable, 450 days)
  B  ladder_after_exit = true
  C  max_days_in_stable = 240               (the post-hoc finding of STRATEGY §7, for reference)
  D  ladder_after_exit = true + 240 days
Each challenger is judged by the frozen gate code itself (gatekeeper.backtest_gate: must-pass windows, full history
per cycle, moving-block bootstrap, deflated Sharpe) with n_trials = 10 pre-registered variants + 9 max_days values
+ these 3 challengers. Adoption is NOT decided here: a winner still needs `btcagent propose` -> shadow -> probation.
Usage: python scripts/research_ladder.py <out.json> [data_dir]"""
import copy
import json
import sys

from btcagent.backtest import engine, metrics
from btcagent.data import features, history
from btcagent.improve import gatekeeper

daily = history.panel(sys.argv[2] if len(sys.argv) > 2 else "/home/mkoniu/.local/share/btcagent/data")
feat = features.build(daily)
champ = gatekeeper.champion_params(gatekeeper.load_strategies())
N_TRIALS = 10 + 9 + 3


def variant(ladder: bool, days: int | None) -> dict:
    p = copy.deepcopy(champ)
    p["cycle_guard"]["ladder_after_exit"] = ladder
    if days:
        p["cycle_guard"]["max_days_in_stable"] = days
    return p


VARIANTS = {"A_champion": variant(False, None), "B_ladder": variant(True, None),
            "C_240d": variant(False, 240), "D_ladder_240d": variant(True, 240)}
out = {"date": "2026-10-30", "n_trials": N_TRIALS, "data_to": str(daily.index[-1].date()), "variants": {}}
for name, p in VARIANTS.items():
    r = engine.run(feat, daily, p)
    trades = [{"date": str(t.get("date"))[:10], "leg": t.get("leg"), "side": t.get("side"), "btc_usd": round(float(t.get("btc_usd") or 0), 2), "notional_btc": round(float(t.get("notional_btc") or 0), 4),
               "reason": t.get("reason")} for t in r.trades]
    row = {"btc_multiple": round(metrics.btc_multiple(r.nav["nav_btc"]), 3), "per_cycle": metrics.per_cycle(r.nav),
           "summary": metrics.summarize(r.nav, r.trades), "trades": trades}
    if name != "A_champion":
        g = gatekeeper.backtest_gate(champ, p, feat, daily, N_TRIALS)
        row["gate"] = {k: v for k, v in g.items() if k not in ("nav",)}
    out["variants"][name] = row
    print(name, row["btc_multiple"], row["per_cycle"], row.get("gate", {}).get("passed"), row.get("gate", {}).get("reasons"))
json.dump(out, open(sys.argv[1], "w"), indent=1, default=str)
