"""Pre-registered strategy variants, evaluated per halving cycle against holding BTC.

The variant list is fixed here BEFORE results are seen (documented in docs/STRATEGY.md with the date); each
variant switches one of Cowen's verifiable rules on or off. Parameters are his stated values, never tuned.
The number of variants is the n_trials for the deflated Sharpe ratio.

Usage: python scripts/research_variants.py <data_dir> [out.json]
"""
import copy
import json
import sys
from pathlib import Path

import numpy as np
import yaml

from btcagent.backtest import engine, metrics
from btcagent.data import features, history
from btcagent.improve import stats

BASE = yaml.safe_load(open("evolvable/strategies.yaml"))["strategies"]["cycle_guard_v1"]
OFF = {"trim_fraction": 0.0, "trim_risk": 1.01, "trim_resid_pct": 1.01}
NO_LADDER = {"reentry_k": 9}
NO_STOP = {"stable_stop_btc_pct": 0.999}
NO_ALT = {"enabled": False}


def variant(cg=None, ag=None):
    p = copy.deepcopy(BASE)
    p["cycle_guard"].update(cg or {})
    p["alt_gate"].update(ag or {})
    return p


VARIANTS = {
    "V1_50w_exit_reclaim_only": variant({**OFF, **NO_LADDER, **NO_STOP}, NO_ALT),
    "V2_V1_plus_ladder": variant({**OFF, **NO_STOP}, NO_ALT),
    "V3_V1_plus_stop20": variant({**OFF, **NO_LADDER}, NO_ALT),
    "V4_V2_plus_stop20": variant({**OFF}, NO_ALT),
    "V5_V4_plus_trim": variant({}, NO_ALT),
    "V6_V1_no_maturity_filter": variant({**OFF, **NO_LADDER, **NO_STOP, "exit_min_days_since_halving": 0}, NO_ALT),
    "V7_V1_exit_3w": variant({**OFF, **NO_LADDER, **NO_STOP, "exit_weeks_below_50w": 3}, NO_ALT),
    "V8_V1_half_exit": variant({**OFF, **NO_LADDER, **NO_STOP, "exit_fraction": 0.5}, NO_ALT),
    "V9_V4_plus_alt_gate": variant({**OFF}, {}),
    "V10_alt_gate_only": variant({**OFF, **NO_LADDER, **NO_STOP, "exit_weeks_below_50w": 99}, {}),
}


def main():
    data_dir = Path(sys.argv[1]).expanduser()
    daily = history.panel(data_dir)
    feat = features.build(daily)
    out = {}
    weekly_excess = {}
    for name, p in VARIANTS.items():
        res = engine.run(feat, daily, p)
        s = metrics.summarize(res.nav, res.trades)
        pc = metrics.per_cycle(res.nav)
        wk = np.log(res.nav["nav_btc"].resample("W-SUN").last()).diff().dropna()
        weekly_excess[name] = wk
        cyc = list(pc.values())
        out[name] = {"summary": s, "per_cycle": pc,
                     "cycles_won_vs_hodl": sum(1 for x in cyc if x > 1.0), "cycles": len(cyc),
                     "sign_test_cycles": stats.sign_test([np.log(x) for x in cyc]),
                     "sign_test_years": stats.sign_test(list(metrics.yearly_log_excess(res.nav).values)),
                     "bootstrap_p_mean_le_0": stats.block_bootstrap_p(wk.values)}
    n = len(VARIANTS)
    srs = [w.mean() / w.std() for w in weekly_excess.values() if w.std() > 0]
    var_sr = float(np.var(srs)) if len(srs) > 1 else None
    for name, wk in weekly_excess.items():
        out[name]["deflated_sharpe"] = stats.deflated_sharpe(wk.values, n_trials=n, sr_trials_var=var_sr)
    table = {k: {"btc_multiple": v["summary"]["btc_multiple"], "per_cycle": v["per_cycle"],
                 "won": f"{v['cycles_won_vs_hodl']}/{v['cycles']}", "trades": v["summary"]["n_trades"],
                 "win_rate": v["summary"]["win_rate"], "max_dd_usd": v["summary"]["max_dd_usd"],
                 "max_dd_btc": v["summary"]["max_dd_btc"], "dsr": v["deflated_sharpe"]["dsr"],
                 "boot_p": v["bootstrap_p_mean_le_0"]} for k, v in out.items()}
    print(json.dumps(table, indent=1))
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
