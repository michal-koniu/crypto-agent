#!/usr/bin/env bash
# Every 5 minutes: agent process RSS, system RAM, per-GPU VRAM and activity, ledger size and integrity.
STATE=${1:-$HOME/.local/state/cryptoagent-soak}
OUT=${2:-$STATE/soak_monitor.csv}
cd "$(dirname "$0")/.."
[ -f "$OUT" ] || echo "ts,agent_pid,agent_rss_mb,ram_used_gb,ram_avail_gb,vram_gpu0_mb,vram_gpu1_mb,vram_gpu2_mb,vram_gpu3_mb,gfx0,gfx1,gfx2,gfx3,ledger_events,ledger_ok,restarts" > "$OUT"
while true; do
  PID=$(systemctl --user show -p MainPID --value cryptoagent-soak 2>/dev/null)
  RSS=$(ps -o rss= -p "$PID" 2>/dev/null | awk '{printf "%.0f", $1/1024}')
  read USED AVAIL < <(free -g | awk '/Mem:/ {print $3, $7}')
  V=$(amd-smi metric -m 2>/dev/null | awk '/USED_VRAM:/ && !/VISIBLE/ {print $2}' | head -4 | paste -sd, -)
  G=$(amd-smi metric -u 2>/dev/null | awk '/GFX_ACTIVITY:/ {print $2}' | head -4 | paste -sd, -)
  LED=$(.venv/bin/python -c "from cryptoagent.ledger.store import Ledger; l=Ledger('$STATE/ledger.db'); ok,m=l.verify(); print(l.head()[0], ok)" 2>/dev/null | tr ' ' ',')
  R=$(systemctl --user show -p NRestarts --value cryptoagent-soak 2>/dev/null)
  echo "$(date -u +%FT%TZ),$PID,$RSS,$USED,$AVAIL,$V,$G,$LED,$R" >> "$OUT"
  sleep 300
done
