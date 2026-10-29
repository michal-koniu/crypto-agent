"""Strategy rules: deterministic functions from point-in-time features to target weights.

A strategy never places orders. It returns a Target (weights over BTC / STABLE / ETH, stops, expected edge and a
machine-readable list of the rule states that produced it). The agent's LLM may *reduce* risk relative to the
target (an overlay in [0, 1] on the non-BTC legs, or a veto); it can never add risk beyond it. The policy engine
then checks the resulting orders.

All parameters live in evolvable/strategies.yaml (the only strategy file the self-improvement loop may change) and
are bounded by frozen/param_bounds.yaml.

Rules (sources and evidence in docs/STRATEGY.md):
  cycle_guard  BTC <-> stablecoin. Exit after N weekly closes below the 50W SMA once the cycle is mature;
               partial trim at extreme valuation; staged re-entry when >= k of the bottom conditions hold;
               forced re-entry on a sustained 50W reclaim, a BTC-terms stop, or a maximum time out.
  alt_gate     ETH/BTC overlay, only when every liquidity-and-trend condition holds; tight BTC-terms stop.
  yield        idle stablecoins earn the configured lending yield; BTC earns its (near-zero) yield.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class Target:
    stable: float = 0.0          # share of NAV in stablecoins
    eth: float = 0.0             # share of NAV in ETH (the only alt the gate may open for)
    stop_stable_btc_pct: float | None = None
    stop_eth_btc_pct: float | None = None
    expected_edge_bps: float = 0.0
    rules: dict = field(default_factory=dict)   # rule name -> state, logged with every decision

    @property
    def btc(self) -> float:
        return max(0.0, 1.0 - self.stable - self.eth)


@dataclass
class StrategyState:
    stable: float = 0.0
    eth: float = 0.0
    stable_entry_btc_price: float | None = None    # BTC/USD when we went to stables (stop reference)
    eth_entry_ethbtc: float | None = None
    eth_weeks_below: int = 0
    weeks_in_stable: int = 0
    exit_armed: bool = True       # after a forced re-entry, a new exit needs a fresh weekly close above the 50W


def _ok(x) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def cycle_guard(f: dict, st: StrategyState, p: dict) -> tuple[float, dict]:
    """Return the target stablecoin share and the rule states."""
    rules: dict = {}
    price = f["btc"]
    s = st.stable
    mature = _ok(f.get("days_since_halving")) and f["days_since_halving"] >= p["exit_min_days_since_halving"]
    exit_sig = _ok(f.get("weeks_below_50w")) and f["weeks_below_50w"] >= p["exit_weeks_below_50w"] and mature and st.exit_armed
    rules["exit_50w"] = bool(exit_sig)
    trim = (_ok(f.get("risk")) and f["risk"] >= p["trim_risk"]) or \
           (_ok(f.get("logreg_resid_pct")) and f["logreg_resid_pct"] >= p["trim_resid_pct"])
    rules["valuation_trim"] = bool(trim)
    if exit_sig:
        s = max(s, p["exit_fraction"])
    elif trim:
        s = max(s, p["trim_fraction"])

    if st.stable > 0:
        conds = {
            "late_in_bear": _ok(f.get("days_since_ath")) and f["days_since_ath"] >= p["reentry_min_days_since_ath"],
            "cheap_vs_trend": (_ok(f.get("sma200w")) and price <= f["sma200w"] * p["reentry_sma200w_mult"]) or
                              (_ok(f.get("price_to_realized")) and f["price_to_realized"] <= p["reentry_max_price_to_realized"]),
            "onchain_reset": _ok(f.get("mvrv")) and f["mvrv"] <= p["reentry_max_mvrv"],
            "low_risk": _ok(f.get("risk")) and f["risk"] <= p["reentry_max_risk"],
        }
        n = sum(bool(v) for v in conds.values())
        rules["reentry_conditions"] = {k: bool(v) for k, v in conds.items()}
        blocked = f.get("midterm_h1") == 1 and not (conds["cheap_vs_trend"] and conds["onchain_reset"])
        rules["midterm_h1_block"] = bool(blocked) and n >= p["reentry_k"]
        if n >= p["reentry_k"] and not blocked and not exit_sig:
            s = max(0.0, s - p["reentry_tranche"])
        reclaim = _ok(f.get("weeks_above_50w")) and f["weeks_above_50w"] >= p["reclaim_weeks"]
        timed_out = st.weeks_in_stable * 7 >= p["max_days_in_stable"]
        stop_hit = st.stable_entry_btc_price and price >= st.stable_entry_btc_price / (1 - p["stable_stop_btc_pct"])
        rules.update(reclaim_50w=bool(reclaim), max_time_out=bool(timed_out), stable_stop=bool(stop_hit))
        if reclaim or timed_out or stop_hit:
            s = p["trim_fraction"] if trim and not stop_hit else 0.0
    return min(max(s, 0.0), 1.0), rules


def alt_gate(f: dict, st: StrategyState, p: dict) -> tuple[float, dict]:
    """ETH weight. Opens only when *every* condition holds; closes on the first sign of trouble."""
    rules: dict = {}
    if not p.get("enabled", True):
        return 0.0, {"alt_gate": "disabled"}
    loose = (_ok(f.get("ff_minus_2y")) and f["ff_minus_2y"] <= 0 and _ok(f.get("ust2y_chg13w")) and f["ust2y_chg13w"] <= 0)
    no_hikes = _ok(f.get("ff_chg26w")) and f["ff_chg26w"] <= 0
    conds = {
        "btc_ath_recent": f.get("ath_recent_13w") == 1,
        "policy_loose": bool(loose and no_hikes),
        "dominance_falling": _ok(f.get("dom_vs_sma20w")) and f["dom_vs_sma20w"] < 0,
        "ethbtc_uptrend": _ok(f.get("ethbtc_vs_sma20w")) and f["ethbtc_vs_sma20w"] > 0,
        "dollar_weak": (not _ok(f.get("dxy_vs_sma50w"))) or f["dxy_vs_sma50w"] < 0,
    }
    rules["alt_gate_conditions"] = {k: bool(v) for k, v in conds.items()}
    gate = all(conds.values())
    w = st.eth
    if st.eth > 0:
        weak = _ok(f.get("ethbtc_vs_sma20w")) and f["ethbtc_vs_sma20w"] < 0
        st_below = st.eth_weeks_below + 1 if weak else 0
        stop = st.eth_entry_ethbtc and _ok(f.get("eth_btc")) and f["eth_btc"] <= st.eth_entry_ethbtc * (1 - p["eth_stop_btc_pct"])
        dom_reclaim = _ok(f.get("dom_vs_sma20w")) and f["dom_vs_sma20w"] > 0
        rules.update(eth_trend_lost=st_below >= p["exit_weeks_below_sma20w"], eth_stop=bool(stop), dom_reclaim=bool(dom_reclaim))
        if st_below >= p["exit_weeks_below_sma20w"] or stop or dom_reclaim or not conds["policy_loose"]:
            w = 0.0
    elif gate:
        w = p["eth_weight"]
    rules["alt_gate_open"] = gate
    return w, rules


def target(f: dict, st: StrategyState, params: dict) -> Target:
    s, r1 = cycle_guard(f, st, params["cycle_guard"])
    e, r2 = alt_gate(f, st, params["alt_gate"]) if s < 0.5 else (0.0, {"alt_gate": "blocked: risk-off"})
    e = min(e, 1.0 - s)
    t = Target(stable=s, eth=e, rules={**r1, **r2})
    t.stop_stable_btc_pct = params["cycle_guard"]["stable_stop_btc_pct"] if s > 0 else None
    t.stop_eth_btc_pct = params["alt_gate"]["eth_stop_btc_pct"] if e > 0 else None
    # Expected edge of a change, from the strategy's validated backtest record (bps of the traded notional);
    # set by the backtest report, used by the policy engine's edge-to-cost check.
    t.expected_edge_bps = params.get("expected_edge_bps", 300.0)
    return t


def advance_state(st: StrategyState, t: Target, f: dict) -> StrategyState:
    """Update the bookkeeping after the target has been executed at this week's close."""
    new = StrategyState(**st.__dict__)
    if t.stable > 0 and st.stable == 0:
        new.stable_entry_btc_price = f["btc"]
        new.weeks_in_stable = 0
    if t.stable > 0:
        new.weeks_in_stable = st.weeks_in_stable + 1 if st.stable > 0 else 0
    else:
        new.stable_entry_btc_price, new.weeks_in_stable = None, 0
    if t.eth > 0 and st.eth == 0:
        new.eth_entry_ethbtc = f.get("eth_btc")
        new.eth_weeks_below = 0
    if t.eth > 0:
        weak = _ok(f.get("ethbtc_vs_sma20w")) and f["ethbtc_vs_sma20w"] < 0
        new.eth_weeks_below = st.eth_weeks_below + 1 if weak else 0
    else:
        new.eth_entry_ethbtc, new.eth_weeks_below = None, 0
    if st.stable > 0 and t.stable < st.stable and (t.rules.get("stable_stop") or t.rules.get("max_time_out")):
        new.exit_armed = False
    if _ok(f.get("weeks_above_50w")) and f["weeks_above_50w"] >= 1:
        new.exit_armed = True
    new.stable, new.eth = t.stable, t.eth
    return new
