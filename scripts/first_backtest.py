"""Quick research run: refresh data, build features, backtest the champion vs HODL. Prints JSON."""
import json, sys, yaml
from pathlib import Path
from cryptoagent.data import history, features
from cryptoagent.backtest import engine, metrics
data_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "~/.local/share/cryptoagent/data").expanduser()
if "--refresh" in sys.argv:
    history.download_all(data_dir)
daily = history.panel(data_dir)
feat = features.build(daily)
cfg = yaml.safe_load(open("evolvable/strategies.yaml"))
params = cfg["strategies"][cfg["champion"]]
res = engine.run(feat, daily, params, keep_decisions=True)
out = {"summary": metrics.summarize(res.nav, res.trades), "per_cycle": metrics.per_cycle(res.nav),
       "trades": [{**t, "date": str(t["date"].date())} for t in res.trades]}
print(json.dumps(out, indent=1, default=str))
print("last features:", json.dumps(features.snapshot(feat), default=str))
