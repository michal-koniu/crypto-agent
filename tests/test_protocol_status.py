"""Protocol-status guard (risk/protocol_status.py + Agent.protocol_guard / _place_yield), without a chain.

Fixtures are the real Aave v3 Base USDC reserve configurations read from mainnet on 2026-10-30: before (~10,000
blocks earlier) and after the 29 Oct 2026 freeze (frozen bit set, LTV 75 % -> 0)."""
from cryptoagent.agent.core import ROOT, Agent
from cryptoagent.execution.paper import PaperExecutor
from cryptoagent.risk.protocol_status import decode_aave_v3_config
from cryptoagent.types import LendIntent, Prices

BEFORE = 7237005577332262213973186568752004119305653224248996801175139707821393190220
AFTER = 7237005577332262213973186568752004119305653224248996801175283823009469038592


def test_decode_real_aave_configs_before_and_after_the_freeze():
    b, a = decode_aave_v3_config(BEFORE), decode_aave_v3_config(AFTER)
    assert b["active"] and not b["frozen"] and not b["paused"] and b["suppliable"] and b["withdrawable"]
    assert a["active"] and a["frozen"] and not a["paused"] and not a["suppliable"] and a["withdrawable"]
    assert a["supply_cap"] == b["supply_cap"] == 230_000_000
    paused = decode_aave_v3_config(AFTER | (1 << 60))
    assert paused["paused"] and not paused["withdrawable"]


class FakeStatus:
    def __init__(self, data: int | None, error: str | None = None):
        self.data, self.error, self.reads = data, error, 0

    def status(self, protocol, asset):
        self.reads += 1
        if self.error:
            return {"protocol": protocol, "asset": asset, "error": self.error, "suppliable": False, "withdrawable": None}
        return {"protocol": protocol, "asset": asset, **decode_aave_v3_config(self.data)}


def _agent(tmp_path, data=None, error=None, mode="paper"):
    ag = Agent(ROOT / "config" / "agent.yaml", overrides={"mode": mode, "state_dir": str(tmp_path), "alerts_dry_run": True,
                                                         "analyst": {"enabled": False}, "news": {"enabled": False},
                                                         "git_commit_changes": False})
    ag.executor = PaperExecutor(ag.ledger, None, tmp_path)
    ag.executor.deposit("USDC", 100.0)
    ag.protocol_status = FakeStatus(data, error)
    return ag


PRICES = Prices(usd={"BTC": 80000.0, "ETH": 2400.0, "USDC": 1.0, "USDT": 1.0}, second_source_btc_usd=80040.0, source="test")


def test_no_deposit_into_a_frozen_reserve(tmp_path):
    ag = _agent(tmp_path, AFTER)
    out = ag._place_yield("USDC", PRICES, ag.clock(), "d1", "v")
    assert out == {"lend_skipped": {"protocol": "aave_v3_base", "asset": "USDC", "why": "frozen"}}
    assert not ag.ledger.events(kind="lend")
    assert [e.payload["frozen"] for e in ag.ledger.events(kind="protocol_status")] == [True]


def test_deposit_when_the_reserve_accepts_it(tmp_path):
    ag = _agent(tmp_path, BEFORE)
    out = ag._place_yield("USDC", PRICES, ag.clock(), "d1", "v")
    assert out and "lend" in out, out
    pf = ag.executor.portfolio()                       # lent up to the frozen 60 % protocol cap, the rest stays liquid
    lent = sum(h.qty for h in pf.holdings if h.protocol == "aave_v3_base")
    assert 59.0 < lent <= 60.0 and abs(pf.qty("USDC", liquid_only=True) - (100 - lent)) < 1e-6
    assert ag._place_yield("USDC", PRICES, ag.clock(), "d2", "v") is None   # at the cap: nothing more to lend


def test_unknown_status_never_moves_money_in_and_never_forces_an_exit(tmp_path):
    ag = _agent(tmp_path, error="ConnectError: rpc down")
    assert ag._place_yield("USDC", PRICES, ag.clock(), "d1", "v")["lend_skipped"]["why"].startswith("ConnectError")
    ag.executor.lend(LendIntent(action="supply", venue="aave_v3_base", chain="base", asset="USDC", qty=100.0))
    assert ag.protocol_guard(ag.executor.portfolio(), PRICES) == []


def test_guard_withdraws_from_a_frozen_reserve_and_alerts_once(tmp_path):
    ag = _agent(tmp_path, BEFORE)
    ag.executor.lend(LendIntent(action="supply", venue="aave_v3_base", chain="base", asset="USDC", qty=100.0))
    assert ag.protocol_guard(ag.executor.portfolio(), PRICES) == []           # healthy reserve: nothing to do
    ag.protocol_status.data = AFTER                                            # governance freezes the reserve
    out = ag.protocol_guard(ag.executor.portfolio(), PRICES)
    assert out and out[0]["action"] == "withdrawn" and out[0]["why"] == "frozen"
    pf = ag.executor.portfolio()
    assert pf.qty("USDC", liquid_only=True) > 99.9 and not [h for h in pf.holdings if h.protocol]
    assert ag.ledger.events(kind="protocol_exit")
    ag._reserve_status("aave_v3_base", "USDC")                                 # same state again: no new event
    assert len(ag.ledger.events(kind="protocol_status")) == 2                  # healthy, then frozen


def test_guard_cannot_withdraw_from_a_paused_reserve(tmp_path):
    ag = _agent(tmp_path, BEFORE)
    ag.executor.lend(LendIntent(action="supply", venue="aave_v3_base", chain="base", asset="USDC", qty=100.0))
    ag.protocol_status.data = AFTER | (1 << 60)
    out = ag.protocol_guard(ag.executor.portfolio(), PRICES)
    assert out == [{"protocol": "aave_v3_base", "asset": "USDC", "action": "cannot_withdraw_paused"}]
    assert [h for h in ag.executor.portfolio().holdings if h.protocol]       # nothing moved


def test_replays_never_read_todays_chain(tmp_path):
    ag = _agent(tmp_path, AFTER, mode="replay")
    ag.protocol_status = None
    assert ag._protocols() is None
