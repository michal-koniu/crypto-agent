#!/usr/bin/env bash
# Start / stop an Anvil fork of Base mainnet (Foundry's official Docker image; no real funds involved).
#   scripts/fork.sh start [rpc_url]    pinned to (head - 100) so the fork is reproducible during a test run
#   scripts/fork.sh stop
set -euo pipefail
NAME=cryptoagent-anvil
IMG=ghcr.io/foundry-rs/foundry:stable
RPC=${2:-${CRYPTOAGENT_BASE_RPC:-https://mainnet.base.org}}
case "${1:-start}" in
  start)
    sg docker -c "docker rm -f $NAME" >/dev/null 2>&1 || true
    HEAD=$(curl -s -X POST "$RPC" -H 'content-type: application/json' \
      -d '{"jsonrpc":"2.0","id":1,"method":"eth_blockNumber","params":[]}' | python3 -c 'import json,sys;print(int(json.load(sys.stdin)["result"],16))')
    BLOCK=$((HEAD - 100))
    sg docker -c "docker run -d --name $NAME -p 127.0.0.1:8545:8545 $IMG \"anvil --host 0.0.0.0 --fork-url $RPC --fork-block-number $BLOCK --chain-id 8453 --block-time 1 --silent\"" >/dev/null
    for i in $(seq 1 60); do
      if curl -s -X POST http://127.0.0.1:8545 -H 'content-type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}' | grep -q 0x2105; then
        echo "anvil fork of Base at block $BLOCK on 127.0.0.1:8545"; exit 0; fi
      sleep 1
    done
    echo "anvil did not start"; sg docker -c "docker logs $NAME" | tail -20; exit 1 ;;
  stop)
    sg docker -c "docker rm -f $NAME" >/dev/null 2>&1 && echo stopped ;;
esac
