"""On-chain tests on an Anvil fork of Base mainnet: real contracts, real pool state, test money only.
Start the fork first: scripts/fork.sh start   (marked `fork`; skipped when no fork is running)."""
import threading
import time
from datetime import datetime, timezone

import httpx
import pytest
from web3 import Web3

from cryptoagent import frozen
from cryptoagent.execution.evm import ERC20_ABI, EvmExecutor
from cryptoagent.ledger.store import Ledger
from cryptoagent.policy.engine import PolicyContext, check
from cryptoagent.signer import keystore
from cryptoagent.signer.client import SignerClient, SignerRefused
from cryptoagent.types import LendIntent, Prices, StopRule, TradeIntent

RPC = "http://127.0.0.1:8545"


def fork_up() -> bool:
    try:
        return httpx.post(RPC, json={"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []}, timeout=3).json()["result"] == "0x2105"
    except Exception:
        return False


pytestmark = [pytest.mark.fork, pytest.mark.skipif(not fork_up(), reason="no Anvil fork on 127.0.0.1:8545")]


def rpc(method, params):
    r = httpx.post(RPC, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=60).json()
    if "error" in r:
        raise RuntimeError(r["error"])
    return r["result"]


ACL_ABI = [
    {"name": "ADDRESSES_PROVIDER", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"name": "", "type": "address"}]},
    {"name": "getACLAdmin", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"name": "", "type": "address"}]},
    {"name": "getACLManager", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"name": "", "type": "address"}]},
    {"name": "getPoolConfigurator", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"name": "", "type": "address"}]},
    {"name": "addPoolAdmin", "type": "function", "stateMutability": "nonpayable", "inputs": [{"name": "admin", "type": "address"}], "outputs": []},
    {"name": "setReserveFreeze", "type": "function", "stateMutability": "nonpayable", "inputs": [{"name": "asset", "type": "address"}, {"name": "freeze", "type": "bool"}], "outputs": []},
]


def set_reserve_frozen(ex, asset: str, frozen_flag: bool):
    """FORK-ONLY test setup: (un)freeze an Aave reserve by impersonating Aave's ACL admin on the local Anvil fork.
    Since 29 Oct 2026 every Aave v3 Base reserve is frozen on mainnet; the deposit/withdraw/kill mechanics can only be
    exercised on a fork after unfreezing. Never touches mainnet; the signer is not involved."""
    w3 = ex.w3
    pool = w3.eth.contract(ex.pool.address, abi=ACL_ABI)
    prov = w3.eth.contract(pool.functions.ADDRESSES_PROVIDER().call(), abi=ACL_ABI)
    admin, acl, conf = prov.functions.getACLAdmin().call(), prov.functions.getACLManager().call(), prov.functions.getPoolConfigurator().call()
    rpc("anvil_impersonateAccount", [admin])
    rpc("anvil_setBalance", [admin, hex(10**18)])
    for to, data in ((acl, w3.eth.contract(acl, abi=ACL_ABI).encode_abi("addPoolAdmin", args=[admin])),
                     (conf, w3.eth.contract(conf, abi=ACL_ABI).encode_abi("setReserveFreeze", args=[ex.tokens[asset]["address"], frozen_flag]))):
        h = rpc("eth_sendTransaction", [{"from": admin, "to": to, "data": data}])
        assert w3.eth.wait_for_transaction_receipt(h, timeout=60)["status"] == 1, (to, frozen_flag)
    rpc("anvil_stopImpersonatingAccount", [admin])


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    import os
    d = tmp_path_factory.mktemp("fork")
    os.environ["CRYPTOAGENT_KEYSTORE_PASSWORD"] = "fork-test-only"
    ks = d / "k.json"
    addr = keystore.create(ks)
    from cryptoagent.signer.server import serve
    threading.Thread(target=serve, args=(str(d), str(ks), "fork", 18795), daemon=True).start()
    for _ in range(50):
        if (d / "signer.token").exists():
            break
        time.sleep(0.1)
    signer = SignerClient(str(d))
    led = Ledger(d / "ledger.db")
    ex = EvmExecutor(RPC, signer, led, mode="fork")
    w3 = ex.w3
    # fund: 1 ETH for gas, 2,000 USDC taken from Aave's aUSDC contract (which holds the underlying)
    rpc("anvil_setBalance", [addr, hex(10**18)])
    usdc = ex.tokens["USDC"]["address"]
    a_token = ex.atoken("USDC").address
    rpc("anvil_impersonateAccount", [a_token])
    rpc("anvil_setBalance", [a_token, hex(10**18)])
    data = ex.erc20("USDC").encode_abi("transfer", args=[Web3.to_checksum_address(addr), 2000 * 10**6])
    h = rpc("eth_sendTransaction", [{"from": a_token, "to": usdc, "data": data}])
    w3.eth.wait_for_transaction_receipt(h, timeout=60)
    rpc("anvil_stopImpersonatingAccount", [a_token])
    from cryptoagent.execution.market import Market
    from cryptoagent.risk.protocol_status import from_allowlists
    prices = Market().prices()
    live = from_allowlists(RPC, frozen.allowlists(), w3=w3, ttl_seconds=0).status("aave_v3_base", "USDC")
    if live["frozen"]:
        set_reserve_frozen(ex, "USDC", False)        # mainnet state since 29 Oct 2026; see set_reserve_frozen
    return {"dir": d, "addr": addr, "ex": ex, "ledger": led, "prices": prices, "signer": signer, "usdc_frozen_at_fork_block": live["frozen"]}


def ctx(env, killed=False):
    return PolicyContext(portfolio=env["ex"].portfolio(), prices=env["prices"], mode="fork", killed=killed,
                         now=datetime.now(timezone.utc))


def test_allowlisted_contracts_verified_on_chain(env):
    assert env["ex"].verify_allowlist() == []


def test_swap_usdc_to_cbbtc_with_exact_approval_and_revoke(env):
    ex, p = env["ex"], env["prices"]
    p.ts = datetime.now(timezone.utc)
    intent = TradeIntent(venue="uniswap_v3_base", chain="base", sell_asset="USDC", buy_asset="BTC", sell_qty=100.0,
                         expected_edge_bps=900, strategy_id="t", strategy_version="t", max_slippage_bps=60)
    cost, quote = ex.estimate(intent, p)
    assert cost.gas_usd < 1.0 and quote["amount_out"] > 0
    intent.cost = cost
    d = check(intent, ctx(env))
    assert d.allowed, d.violations
    fill = ex.execute(intent, p, quote, cost)
    assert fill["buy_qty"] > 0 and fill["tx_hash"].startswith("0x")
    allowance = ex.erc20("USDC").functions.allowance(ex.me, ex.router.address).call()
    assert allowance == 0                                      # approval hygiene: nothing left behind
    assert abs(fill["buy_qty"] - quote["amount_out"]) / quote["amount_out"] < 0.01
    env["ledger"].append("fork_evidence", {"swap_tx": fill["tx_hash"], "gas_usd": fill["gas_usd"]})


def test_aave_supply_and_withdraw(env):
    ex = env["ex"]
    li = LendIntent(action="supply", venue="aave_v3_base", chain="base", asset="USDC", qty=50.0)
    ex.lend(li)
    lent = [h for h in ex.portfolio().holdings if h.protocol == "aave_v3_base"]
    assert lent and lent[0].qty >= 49.99
    ex.lend(LendIntent(action="withdraw", venue="aave_v3_base", chain="base", asset="USDC", qty=lent[0].qty * 0.999))
    assert ex.erc20("USDC").functions.allowance(ex.me, ex.pool.address).call() == 0


def test_protocol_guard_on_fork(env, tmp_path):
    """The real Aave contracts: a frozen reserve gets no deposit, and money already in it is withdrawn by the guard."""
    from cryptoagent.agent.core import Agent, ROOT
    ex = env["ex"]
    agent = Agent(ROOT / "config" / "agent.yaml", overrides={"mode": "fork", "state_dir": str(tmp_path), "alerts_dry_run": True,
                                                             "analyst": {"enabled": False}, "news": {"enabled": False},
                                                             "protocol_status": {"ttl_seconds": 0}})
    agent.executor, agent.ledger = ex, env["ledger"]
    agent.alerts.ledger = env["ledger"]
    ex.lend(LendIntent(action="supply", venue="aave_v3_base", chain="base", asset="USDC", qty=60.0))
    assert agent.protocol_guard(ex.portfolio(), env["prices"]) == []          # healthy (unfrozen on the fork)
    set_reserve_frozen(ex, "USDC", True)                                       # the mainnet event, replayed on the fork
    try:
        out = agent.protocol_guard(ex.portfolio(), env["prices"])
        assert out and out[0]["action"] == "withdrawn" and out[0]["why"] == "frozen", out
        assert ex.atoken("USDC").functions.balanceOf(ex.me).call() < 10**4       # < 0.01 USDC left in Aave
        skipped = agent._place_yield("USDC", env["prices"], datetime.now(timezone.utc), "fork-yield", "t")
        assert skipped and skipped["lend_skipped"]["why"] == "frozen", skipped
        env["ledger"].append("fork_evidence", {"protocol_guard": out, "usdc_frozen_at_fork_block": env["usdc_frozen_at_fork_block"]})
    finally:
        set_reserve_frozen(ex, "USDC", False)                                  # the kill drills below deposit first


def _sign(env, to, data, declared_spend=None):
    """Ask the signer directly (no gas estimation: a hostile tx may not even be executable)."""
    ex = env["ex"]
    return env["signer"].sign_tx(chain="base", chain_id=8453, to=to, data=data, value=0,
                                 nonce=ex.w3.eth.get_transaction_count(ex.me), gas=400000, max_fee_per_gas=10**8,
                                 max_priority_fee_per_gas=10**6, declared_spend=declared_spend)


def test_signer_refuses_hostile_transactions_on_fork(env):
    ex = env["ex"]
    evil = "0x000000000000000000000000000000000000dEaD"
    data = ex.router.encode_abi("exactInputSingle", args=[(ex.tokens["USDC"]["address"], ex.tokens["BTC"]["address"], 500,
                                                          Web3.to_checksum_address(evil), 10**6, 1, 0)])
    with pytest.raises(SignerRefused):
        _sign(env, ex.router.address, data)
    data = ex.erc20("USDC").encode_abi("approve", args=[ex.router.address, 2**256 - 1])
    with pytest.raises(SignerRefused):
        _sign(env, ex.tokens["USDC"]["address"], data, declared_spend=10**6)
    data = ex.erc20("USDC").encode_abi("transfer", args=[Web3.to_checksum_address(evil), 10**6])
    with pytest.raises(SignerRefused):
        _sign(env, ex.tokens["USDC"]["address"], data)


def test_kill_switch_procedure_on_fork(env, tmp_path):
    """Manual kill (mode to_btc): withdraw from Aave, convert every stablecoin into cbBTC, then only exits are signed."""
    from cryptoagent.agent.core import Agent, ROOT
    from cryptoagent.risk import killswitch
    ex = env["ex"]
    ex.lend(LendIntent(action="supply", venue="aave_v3_base", chain="base", asset="USDC", qty=100.0))
    agent = Agent(ROOT / "config" / "agent.yaml", overrides={"mode": "fork", "state_dir": str(env["dir"]), "alerts_dry_run": True,
                                                             "analyst": {"enabled": False}, "news": {"enabled": False}})
    agent.executor = ex
    agent.ledger = env["ledger"]
    ex.ledger = env["ledger"]
    agent.alerts.ledger = env["ledger"]

    class M:
        def prices(self):
            p = env["prices"]
            p.ts = datetime.now(timezone.utc)
            return p
    agent.market = M()
    agent.kill("test: manual kill on fork", auto=False, mode="to_btc")
    assert killswitch.is_killed(env["dir"])
    out = agent.risk_tick()
    assert "kill_procedure" in out, out
    pf = ex.portfolio()
    usdc = pf.qty("USDC")
    why = [(e.kind, e.payload.get("violations") or e.payload.get("error")) for e in env["ledger"].events()
           if e.kind in ("policy_check", "error") and (e.payload.get("violations") or e.payload.get("error"))]
    assert usdc < 1.0, (why[-5:], [str(s)[:400] for s in out["kill_procedure"]["steps"]])  # stables converted (dust may remain)
    assert pf.qty("BTC") > 0
    # while killed, a strategy trade is refused by the policy engine; a deposit is refused by the signer
    t = TradeIntent(venue="uniswap_v3_base", chain="base", sell_asset="BTC", buy_asset="USDC", sell_qty=pf.qty("BTC") / 2,
                    stop=StopRule(max_loss_btc_pct=0.2), strategy_id="t", strategy_version="t")
    assert any("kill switch" in v for v in check(t, ctx(env, killed=True)).violations)
    data = ex.pool.encode_abi("supply", args=[ex.tokens["USDC"]["address"], 1, ex.me, 0])
    with pytest.raises(SignerRefused):
        _sign(env, ex.pool.address, data)
    kevents = [e.payload for e in env["ledger"].events(kind="kill_switch")]
    assert any(k.get("action") == "procedure" for k in kevents)
    killswitch.release(env["dir"], env["ledger"], who="test")


def test_automatic_kill_on_realised_drawdown_on_fork(env):
    """A realised BTC drawdown beyond the frozen limit engages the kill switch with no human action."""
    import json as _json
    from cryptoagent.agent.core import Agent, ROOT
    from cryptoagent.risk import killswitch
    ex = env["ex"]
    agent = Agent(ROOT / "config" / "agent.yaml", overrides={"mode": "fork", "state_dir": str(env["dir"]), "alerts_dry_run": True,
                                                             "analyst": {"enabled": False}, "news": {"enabled": False}})
    agent.executor, agent.ledger = ex, env["ledger"]
    agent.alerts.ledger = env["ledger"]

    class M:
        def prices(self):
            p = env["prices"]
            p.ts = datetime.now(timezone.utc)
            return p
    agent.market = M()
    assert not killswitch.is_killed(env["dir"])
    pf = ex.portfolio()
    assert pf.weights(env["prices"]).get("BTC", 0) >= 0.95            # at rest after the previous kill drill
    nav = pf.nav_btc(env["prices"])
    risk = {"day": None, "nav_btc_rest_peak": nav / 0.6, "nav_btc_peak": nav / 0.6, "nav_usd_peak": None}   # as if 40 % BTC lost
    (env["dir"] / "risk.json").write_text(_json.dumps(risk))
    out = agent.risk_tick()
    assert "kill" in out and killswitch.is_killed(env["dir"]), out
    info = killswitch.kill_info(env["dir"])
    assert info["auto"] is True and "realised BTC drawdown" in info["reason"]
    assert "kill_procedure" in out                                     # the procedure ran in the same tick
    killswitch.release(env["dir"], env["ledger"], who="test")
