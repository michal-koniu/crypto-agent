#!/usr/bin/env bash
# Scheduled fault injection for the soak test. Every action is logged with a UTC timestamp.
ST=${1:-$HOME/.local/state/cryptoagent-soak}
LOG=$ST/soak_faults.log
t() { date -u +%FT%TZ; }
iso_in() { date -u -d "+$1 minutes" +%FT%T+00:00; }
pid() { systemctl --user show -p MainPID --value cryptoagent-soak; }
echo "$(t) schedule start" >> $LOG
sleep 5400
echo "{\"exchange_down\": true, \"until\": \"$(iso_in 20)\"}" > $ST/faults.json; echo "$(t) FAULT exchange_down for 20 min" >> $LOG
sleep 1500
echo "{\"llm_down\": [\"rig\"], \"until\": \"$(iso_in 70)\"}" > $ST/faults.json; echo "$(t) FAULT llm_down rig for 70 min" >> $LOG
sleep 5400
P=$(pid); kill -9 $P; echo "$(t) FAULT kill -9 pid $P" >> $LOG
sleep 120; echo "$(t) after crash: active=$(systemctl --user is-active cryptoagent-soak) pid=$(pid) restarts=$(systemctl --user show -p NRestarts --value cryptoagent-soak)" >> $LOG
sleep 5400
systemctl --user stop cryptoagent-soak; echo "$(t) FAULT graceful stop (simulated reboot)" >> $LOG
sleep 60
systemctl --user start cryptoagent-soak; echo "$(t) restarted: active=$(systemctl --user is-active cryptoagent-soak)" >> $LOG
echo "$(t) schedule done" >> $LOG
