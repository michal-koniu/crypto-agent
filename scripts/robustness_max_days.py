import sys
import copy, json
import numpy as np
from cryptoagent.data import history, features
from cryptoagent.improve import gatekeeper, stats
from cryptoagent.backtest import engine, metrics
daily = history.panel(sys.argv[2] if len(sys.argv) > 2 else "/home/mkoniu/.local/share/cryptoagent/data"); feat = features.build(daily)
base = gatekeeper.champion_params(gatekeeper.load_strategies())
rows = []
import sys
for d in [120, 150, 180, 210, 240, 270, 300, 365, 450]:
    p = copy.deepcopy(base); p["cycle_guard"]["max_days_in_stable"] = d
    r = engine.run(feat, daily, p)
    wk = np.log(r.nav["nav_btc"].resample("W-SUN").last()).diff().dropna()
    rows.append({"days": d, "mult": round(metrics.btc_multiple(r.nav["nav_btc"]), 3), "cycles": metrics.per_cycle(r.nav),
                 "dsr_n20": stats.deflated_sharpe(wk.values, 20)["dsr"]})
for r in rows: print(json.dumps(r))
json.dump({"date": "2026-10-29", "note": "post-hoc robustness scan of cycle_guard.max_days_in_stable around the champion (found while building the self-improvement test); every other param = cycle_guard_v2", "rows": rows}, open(sys.argv[1], "w"), indent=1)
# leave-one-cycle-out flavour: would 180 have been chosen from the other cycles only?
