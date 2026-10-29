#!/usr/bin/env bash
# End-to-end test from a fresh clone, following docs/SETUP.md, on the rig with the live local models.
#   scripts/e2e_fresh_install.sh [repo-url-or-path]
# Leaves a report in /tmp/btcagent-e2e/report.txt and the run's state in /tmp/btcagent-e2e/state.
set -uo pipefail
SRC=${1:-git@github.com:michal-koniu/btc-agent.git}
BRANCH=${BRANCH:-}
W=/tmp/btcagent-e2e
gio trash "$W" 2>/dev/null || true
mkdir -p "$W" && cd "$W"
exec > >(tee "$W/report.txt") 2>&1
step() { echo; echo "=== $(date -u +%FT%TZ) $*"; }

step "1. clone"
git clone -q ${BRANCH:+-b $BRANCH} "$SRC" repo && cd repo && git log --oneline -1
step "2. install (SETUP.md §1)"
python3 -m venv .venv && .venv/bin/pip -q install -U pip && .venv/bin/pip -q install -e ".[dev]" yfinance && echo installed
step "3. frozen layer"
.venv/bin/btcagent frozen verify
step "4. data refresh"
time .venv/bin/btcagent data refresh | tail -3
step "5. unit + integration tests"
.venv/bin/python -m pytest -q -m "not live_llm and not fork" 2>&1 | tail -3
step "6. config for this run (state in $W/state)"
sed "s#state_dir: .*#state_dir: $W/state#" config/agent.yaml > config/agent.e2e.yaml
sed -i 's/email_enabled: true/email_enabled: false/' config/agent.e2e.yaml
grep -E "state_dir|email_enabled" config/agent.e2e.yaml
step "7. decision cycle 1 (live news -> reader, analyst x3, critic, policy, paper execution, ledger)"
( while sleep 20; do amd-smi metric -u 2>/dev/null | awk '/GFX_ACTIVITY/ {printf "%s ", $2} END {print ""}' >> "$W/gpu_activity.txt"; done ) & MON=$!
time .venv/bin/btcagent --config config/agent.e2e.yaml decide > "$W/decision1.json"
python3 -c "import json; d=json.load(open('$W/decision1.json')); print({k: d.get(k) for k in ('action','final_weights','nav_btc','nav_usd','strategy_version')}); print('analyst served:', (d.get('analyst') or {}).get('served')); print('actions:', json.dumps(d.get('actions'))[:600])"
step "8. risk tick, daily upkeep, reflection on request"
.venv/bin/btcagent --config config/agent.e2e.yaml tick | head -20
.venv/bin/btcagent --config config/agent.e2e.yaml upkeep | head -20
.venv/bin/btcagent --config config/agent.e2e.yaml review | head -40
kill $MON 2>/dev/null
step "9. evidence: models that served, GPU activity samples, ledger integrity, tax export"
.venv/bin/python - <<PY
from collections import Counter
from btcagent.ledger.store import Ledger
l = Ledger("$W/state/ledger.db")
print("events:", dict(Counter(e.kind for e in l.events())))
print("served models:", dict(Counter(f"{e.payload['role']}:{e.payload.get('served_model')}" for e in l.events(kind='model_call'))))
print("ledger:", l.verify())
PY
echo "GPU activity samples (GPU0..3, %):"; tail -n 12 "$W/gpu_activity.txt"
.venv/bin/btcagent --config config/agent.e2e.yaml ledger export-tax --out "$W/tax_sample.csv"
head -3 "$W/tax_sample.csv"
.venv/bin/btcagent --config config/agent.e2e.yaml status | head -30
step "done"
