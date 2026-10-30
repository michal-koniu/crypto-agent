"""Backtest pipeline on real historical data: reproducibility, no look-ahead, benchmark sanity."""
import numpy as np
import pandas as pd
import pytest

from btcagent.backtest import engine, metrics
from btcagent.data import features, history
from btcagent.improve import gatekeeper
from btcagent.risk.killswitch import emergency_plan
from btcagent.strategies.rules import StrategyState, target
from conftest import DATA_DIR, has_data, pf

needs_data = pytest.mark.skipif(not has_data(), reason="historical data not downloaded (btcagent data refresh)")


@pytest.fixture(scope="module")
def data():
    daily = history.panel(DATA_DIR)
    return daily, features.build(daily)


@needs_data
def test_panel_covers_history(data):
    daily, feat = data
    assert daily.index[0] <= pd.Timestamp("2010-08-01") and daily["btc"].iloc[-1] > 0
    assert feat["sma50w"].notna().sum() > 600


@needs_data
def test_features_have_no_lookahead(data):
    daily, feat = data
    cut = pd.Timestamp("2022-06-30")
    feat_cut = features.build(daily.loc[:cut])
    t = feat_cut.index[-2]
    cols = ["sma50w", "bmsb_low", "logreg_fair", "logreg_resid_pct", "risk", "weeks_below_50w", "days_since_ath"]
    a, b = feat_cut.loc[t, cols].astype(float), feat.loc[t, cols].astype(float)
    assert np.allclose(a.values, b.values, equal_nan=True), (a, b)


@needs_data
def test_champion_backtest_reproduces_the_selection_report(data):
    daily, feat = data
    res = engine.run(feat, daily, gatekeeper.champion_params(gatekeeper.load_strategies()), end="2026-10-28")
    s = metrics.summarize(res.nav, res.trades)
    assert abs(s["btc_multiple"] - 1.5474) < 0.02, s          # reports/variants_v1.json, V4
    assert s["n_trades"] == 14


@needs_data
def test_hodl_book_is_exactly_the_benchmark(data):
    daily, feat = data
    p = gatekeeper.champion_params(gatekeeper.load_strategies())
    p["cycle_guard"]["exit_weeks_below_50w"] = 10 ** 6
    res = engine.run(feat, daily, p)
    assert abs(metrics.btc_multiple(res.nav["nav_btc"]) - 1.0) < 1e-9 and not res.trades


def test_rules_are_deterministic_and_bounded():
    params = gatekeeper.champion_params(gatekeeper.load_strategies())
    row = {"btc": 50000, "weeks_below_50w": 3, "days_since_halving": 500, "risk": 0.5, "logreg_resid_pct": 0.5,
           "weeks_above_50w": 0, "days_since_ath": 100, "sma200w": 30000, "price_to_realized": 1.5, "mvrv": 1.5,
           "midterm_h1": 0}
    t1, t2 = target(row, StrategyState(), params), target(row, StrategyState(), params)
    assert t1.stable == t2.stable == 1.0 and t1.eth == 0.0 and t1.btc == 0.0
    assert t1.rules["exit_50w"] is True


def test_emergency_plan_shapes():
    holdings = pf(btc=0.5, usdc=1000, eth=1.0, lent_usdc=500).holdings
    plan = emergency_plan(holdings, "to_btc")
    steps = [s["step"] for s in plan]
    assert steps[:2] == ["cancel_open_orders", "revoke_approvals"] and "withdraw" in steps
    assert {(s["sell"], s["buy"]) for s in plan if s["step"] == "convert"} == {("USDC", "BTC"), ("ETH", "BTC")}
    assert [s["step"] for s in emergency_plan(holdings, "halt_only")] == ["cancel_open_orders", "revoke_approvals"]
    assert emergency_plan(holdings, "to_safe_address")[-1]["step"] == "transfer_all_to_safe"


def _bear_week(price, days_since_ath, below=True):
    return {"btc": price, "days_since_halving": 700, "weeks_below_50w": 5 if below else 0,
            "weeks_above_50w": 0 if below else 3, "days_since_ath": days_since_ath, "sma200w": 30000.0,
            "price_to_realized": 0.9, "mvrv": 0.9, "risk": 0.1, "midterm_h1": 0}


def test_ladder_unreachable_by_default_and_reachable_when_enabled():
    from btcagent.strategies.rules import advance_state
    p = gatekeeper.champion_params(gatekeeper.load_strategies())
    assert p["cycle_guard"]["ladder_after_exit"] is False              # champion = v2 behaviour
    for ladder, expect in ((False, [1.0, 1.0, 1.0, 1.0, 1.0]), (True, [1.0, 0.75, 0.5, 0.25, 0.0])):
        p["cycle_guard"]["ladder_after_exit"] = ladder
        st, seen = StrategyState(), []
        for w in range(5):                    # deep bear: every bottom condition holds, BTC stays below the 50W
            f = _bear_week(25000.0, 400 + 7 * w)
            t = target(f, st, p)
            seen.append(t.stable)
            st = advance_state(st, t, f)
        assert seen == expect, (ladder, seen)
        if ladder:
            # completed ladder re-entry disarms the exit: still below the 50W next week, but no new sell-off
            assert st.exit_armed is False
            assert target(_bear_week(25000.0, 450), st, p).stable == 0.0
            # a fresh weekly close above the 50W re-arms it
            st = advance_state(st, target(_bear_week(40000.0, 460, below=False), st, p), _bear_week(40000.0, 460, below=False))
            assert st.exit_armed is True
