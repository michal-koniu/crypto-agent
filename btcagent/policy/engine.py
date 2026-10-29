"""The policy engine: deterministic, LLM-free, frozen. "The LLM proposes, the policy engine disposes."

`check(intent, ctx)` returns a PolicyDecision listing every rule that failed. It never reads `rationale` or any
other free text. Limits and allowlists come from the frozen layer only; callers cannot pass their own.

Exits are treated differently from new risk: a stop-loss or kill-switch exit back to BTC is allowed while the agent
is halted, and is exempt from anti-churn and edge-to-cost rules, because refusing an exit is the riskier choice.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .. import frozen
from ..types import (ApproveIntent, Intent, LendIntent, PolicyDecision, Portfolio, Prices, TradeIntent,
                     TransferIntent)

LIVE_ENV = "BTCAGENT_LIVE"
LIVE_VALUE = "I_ACCEPT_REAL_LOSSES"
EXIT_REASONS = {"stop_loss", "kill_switch"}


@dataclass
class PolicyContext:
    """Everything the engine needs besides the intent. Built by the core from the ledger and live data."""
    portfolio: Portfolio
    prices: Prices
    mode: str                                   # backtest | paper | fork | live
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    halted: bool = False                        # daily-loss halt or manual halt
    killed: bool = False                        # kill switch engaged
    nav_btc_day_start: float | None = None
    nav_btc_peak: float | None = None
    nav_usd_peak: float | None = None
    recent_order_times: list[datetime] = field(default_factory=list)          # all executed orders
    last_trade_time_by_asset: dict[str, datetime] = field(default_factory=dict)


def _cls(asset: str) -> str | None:
    return frozen.asset_class(asset)


def stage_allows(mode: str, limits: dict) -> tuple[bool, str]:
    """Live trading needs the frozen stage AND an explicit environment confirmation. Never on by default."""
    if mode != "live":
        return True, "ok"
    if limits.get("stage") != "live":
        return False, "live mode requested but frozen stage is not 'live'"
    if os.environ.get(LIVE_ENV) != LIVE_VALUE:
        return False, f"live mode needs {LIVE_ENV}={LIVE_VALUE} in the environment"
    return True, "ok"


def risk_state(ctx: PolicyContext, limits: dict) -> tuple[list[str], bool, bool]:
    """Daily loss and drawdown checks. Returns (violations, halt, kill)."""
    v, halt, kill = [], False, False
    nav_btc = ctx.portfolio.nav_btc(ctx.prices)
    nav_usd = ctx.portfolio.nav_usd(ctx.prices)
    lo = limits["loss"]
    if ctx.nav_btc_day_start and nav_btc < ctx.nav_btc_day_start * (1 - lo["max_daily_loss_btc_pct"]):
        v.append(f"daily loss {1 - nav_btc / ctx.nav_btc_day_start:.2%} in BTC exceeds {lo['max_daily_loss_btc_pct']:.0%}")
        halt = True
    if ctx.nav_btc_peak and nav_btc < ctx.nav_btc_peak * (1 - lo["max_drawdown_btc_pct"]):
        v.append(f"BTC drawdown {1 - nav_btc / ctx.nav_btc_peak:.2%} exceeds {lo['max_drawdown_btc_pct']:.0%}")
        kill = True
    if ctx.nav_usd_peak and nav_usd < ctx.nav_usd_peak * (1 - lo["max_drawdown_usd_pct"]):
        v.append(f"USD drawdown {1 - nav_usd / ctx.nav_usd_peak:.2%} exceeds {lo['max_drawdown_usd_pct']:.0%}")
        kill = True
    return v, halt, kill


def _data_checks(ctx: PolicyContext, limits: dict) -> list[str]:
    v = []
    d = limits["data"]
    age = (ctx.now - ctx.prices.ts).total_seconds()
    if age > d["max_price_age_seconds"]:
        v.append(f"prices are {age:.0f}s old (max {d['max_price_age_seconds']}s)")
    if ctx.prices.second_source_btc_usd:
        a, b = ctx.prices.usd["BTC"], ctx.prices.second_source_btc_usd
        div = abs(a - b) / min(a, b) * 100
        if div > d["max_source_divergence_pct"]:
            v.append(f"BTC price sources diverge {div:.2f}% (max {d['max_source_divergence_pct']}%)")
    else:
        v.append("no second BTC price source for the divergence check")
    return v


def _rate_checks(ctx: PolicyContext, limits: dict, asset: str | None, is_exit: bool) -> list[str]:
    v = []
    r = limits["rate"]
    t = ctx.recent_order_times
    for span, key in ((timedelta(hours=1), "max_orders_per_hour"), (timedelta(days=1), "max_orders_per_day"),
                      (timedelta(days=7), "max_orders_per_week")):
        n = sum(1 for x in t if ctx.now - x < span)
        if n >= r[key] and not is_exit:
            v.append(f"rate limit: {n} orders in the last {span} (max {r[key]})")
    if asset and not is_exit and asset in ctx.last_trade_time_by_asset:
        gap = ctx.now - ctx.last_trade_time_by_asset[asset]
        if gap < timedelta(hours=r["min_hours_between_trades_same_asset"]):
            v.append(f"anti-churn: last {asset} trade {gap} ago (min {r['min_hours_between_trades_same_asset']}h)")
    return v


def _post_trade_weights(intent: TradeIntent, ctx: PolicyContext) -> dict[str, float]:
    p = ctx.prices
    nav = ctx.portfolio.nav_btc(p)
    w = ctx.portfolio.weights(p)
    sell_btc = intent.sell_qty * p.btc(intent.sell_asset)
    w[intent.sell_asset] = w.get(intent.sell_asset, 0.0) - sell_btc / nav
    w[intent.buy_asset] = w.get(intent.buy_asset, 0.0) + sell_btc / nav   # before costs; conservative for limits
    return w


def check_trade(intent: TradeIntent, ctx: PolicyContext, limits: dict, allow: dict) -> PolicyDecision:
    v: list[str] = []
    checks: dict[str, str] = {}
    # An exit is a stop-loss back into BTC (always risk-reducing in BTC terms) or a step of the kill procedure.
    is_exit = (intent.reason_code == "stop_loss" and intent.buy_asset == "BTC") or \
              (intent.reason_code == "kill_switch" and ctx.killed)

    # 1. stage and switches
    ok, why = stage_allows(ctx.mode, limits)
    if not ok:
        v.append(why)
    if intent.reason_code == "kill_switch" and not ctx.killed:
        v.append("reason 'kill_switch' used while the kill switch is not engaged")
    if intent.reason_code == "stop_loss" and intent.buy_asset != "BTC":
        v.append("a stop-loss exit must go back to BTC")
    if ctx.killed and intent.reason_code != "kill_switch":
        v.append("kill switch engaged: only the emergency procedure may trade")
    if ctx.halted and not is_exit:
        v.append("agent halted: only exits back to BTC are allowed")

    # 2. allowlists
    venue = allow["venues"].get(intent.venue)
    if not venue:
        v.append(f"venue {intent.venue!r} not allowlisted")
    for a in (intent.sell_asset, intent.buy_asset):
        if _cls(a) is None:
            v.append(f"asset {a!r} not allowlisted")
    if venue and venue["kind"] == "cex":
        pairs = allow["cex_pairs"].get(intent.venue, [])
        if f"{intent.buy_asset}/{intent.sell_asset}" not in pairs and f"{intent.sell_asset}/{intent.buy_asset}" not in pairs:
            v.append(f"pair {intent.sell_asset}->{intent.buy_asset} not allowlisted on {intent.venue}")
    if venue and venue["kind"] == "dex":
        if intent.chain not in allow["chains"] or venue.get("chain") != intent.chain:
            v.append(f"chain {intent.chain!r} not allowlisted for {intent.venue}")
        toks = {t["asset"] for t in allow["tokens"].get(intent.chain or "", {}).values()}
        for a in (intent.sell_asset, intent.buy_asset):
            if a not in toks:
                v.append(f"no allowlisted token for {a} on {intent.chain}")
    checks["allowlist"] = "ok" if not any("allowlist" in x for x in v) else "fail"

    # 3. balance and size
    have = ctx.portfolio.qty(intent.sell_asset, intent.venue, liquid_only=True)
    if intent.sell_qty > have * 1.000001:
        v.append(f"sell {intent.sell_qty} {intent.sell_asset} exceeds holding {have}")
    nav_btc = ctx.portfolio.nav_btc(ctx.prices)
    order_btc = intent.sell_qty * ctx.prices.btc(intent.sell_asset)
    order_usd = intent.sell_qty * ctx.prices.usd[intent.sell_asset] if intent.sell_asset in ctx.prices.usd else 0.0
    pos = limits["position"]
    if not is_exit:
        if nav_btc and order_btc / nav_btc > pos["max_order_nav_fraction"] + 1e-9:
            v.append(f"order is {order_btc / nav_btc:.1%} of NAV (max {pos['max_order_nav_fraction']:.0%})")
        if order_usd > pos["max_order_usd"]:
            v.append(f"order ${order_usd:,.0f} exceeds max ${pos['max_order_usd']:,}")
        w = _post_trade_weights(intent, ctx)
        alts = 0.0
        for a, wt in w.items():
            c = _cls(a)
            if c and wt > pos["max_asset_weight"][c] + 1e-9:
                v.append(f"post-trade weight of {a} {wt:.1%} exceeds {c} max {pos['max_asset_weight'][c]:.0%}")
            if c == "ALT":
                alts += max(wt, 0.0)
        if alts > pos["max_alts_total_weight"] + 1e-9:
            v.append(f"post-trade altcoin total {alts:.1%} exceeds {pos['max_alts_total_weight']:.0%}")
        if ctx.mode == "live":
            nav_usd = ctx.portfolio.nav_usd(ctx.prices)
            if nav_usd > limits["capital_cap_usd"] * 1.02:
                v.append(f"NAV ${nav_usd:,.0f} above live capital cap ${limits['capital_cap_usd']:,}")
    checks["size"] = "ok" if not any(k in x for x in v for k in ("NAV", "weight", "exceeds max", "altcoin", "holding")) else "fail"

    # 4. stops: every new non-BTC risk position needs a stop in BTC terms, within the max distance
    lo = limits["loss"]
    if not is_exit and _cls(intent.buy_asset) in lo["stop_required_for"]:
        if intent.stop is None:
            v.append(f"buying {intent.buy_asset} needs a stop defined in BTC terms")
        elif intent.stop.max_loss_btc_pct > lo["max_stop_distance_pct"]:
            v.append(f"stop distance {intent.stop.max_loss_btc_pct:.0%} exceeds max {lo['max_stop_distance_pct']:.0%}")

    # 5. costs known before acting
    c = limits["costs"]
    if intent.cost is None:
        if c["require_cost_estimate"]:
            v.append("no cost estimate: the cost of an action must be known before it executes")
    else:
        if intent.cost.slippage_bps > min(c["max_slippage_bps"], intent.max_slippage_bps):
            v.append(f"expected slippage {intent.cost.slippage_bps:.0f} bps exceeds cap")
        total = intent.cost.total_bps(order_usd)
        if total > c["max_total_cost_bps"] and not is_exit:
            v.append(f"total cost {total:.0f} bps exceeds max {c['max_total_cost_bps']} bps")
        if intent.cost.gas_usd > c["max_gas_usd_per_tx"]:
            v.append(f"gas ${intent.cost.gas_usd:.2f} exceeds max ${c['max_gas_usd_per_tx']}")
        if not is_exit and intent.reason_code == "strategy" and intent.expected_edge_bps < c["min_edge_to_cost_ratio"] * total:
            v.append(f"expected edge {intent.expected_edge_bps:.0f} bps < {c['min_edge_to_cost_ratio']}x cost {total:.0f} bps")
    checks["cost"] = "ok" if intent.cost and not any("cost" in x or "slippage" in x or "gas" in x or "edge" in x for x in v) else "fail"

    # 6. rate limits, data freshness, loss state
    v += _rate_checks(ctx, limits, intent.buy_asset if intent.buy_asset != "BTC" else intent.sell_asset, is_exit)
    if ctx.mode != "backtest":
        dv = _data_checks(ctx, limits)
        v += dv if not is_exit else [x for x in dv if "old" in x]
    rv, halt, kill = risk_state(ctx, limits)
    if not is_exit:
        v += rv
    return PolicyDecision(allowed=not v, violations=v, checks=checks, halt=halt, kill=kill)


def check_approve(intent: ApproveIntent, ctx: PolicyContext, limits: dict, allow: dict) -> PolicyDecision:
    v = []
    ok, why = stage_allows(ctx.mode, limits)
    if not ok:
        v.append(why)
    if ctx.killed:
        v.append("kill switch engaged")
    toks = allow["tokens"].get(intent.chain, {})
    if intent.token not in toks:
        v.append(f"token {intent.token} not allowlisted on {intent.chain}")
    spenders = [s.lower() for s in allow["contracts"].get(intent.chain, {}).get("token_approvals", {}).get("spenders", [])]
    if intent.spender.lower() not in spenders:
        v.append(f"spender {intent.spender} not allowlisted")
    ap = limits["approvals"]
    if intent.amount <= 0:
        v.append("approval amount must be positive")
    if intent.amount > intent.for_amount * ap["max_approval_multiple"]:
        if not ap["allow_unlimited"]:
            v.append(f"approval {intent.amount} exceeds {ap['max_approval_multiple']}x the amount to spend ({intent.for_amount})")
    if intent.amount >= 2 ** 255:
        v.append("unlimited approvals are not allowed")
    return PolicyDecision(allowed=not v, violations=v)


def check_lend(intent: LendIntent, ctx: PolicyContext, limits: dict, allow: dict) -> PolicyDecision:
    v = []
    ok, why = stage_allows(ctx.mode, limits)
    if not ok:
        v.append(why)
    if ctx.killed and intent.action == "supply":
        v.append("kill switch engaged: no new deposits")
    if ctx.halted and intent.action == "supply":
        v.append("agent halted: no new deposits")
    if intent.venue not in allow["venues"]:
        v.append(f"venue {intent.venue} not allowlisted")
    if _cls(intent.asset) is None:
        v.append(f"asset {intent.asset} not allowlisted")
    if intent.action == "supply":
        prot_w = ctx.portfolio.protocol_weights(ctx.prices).get(intent.venue, 0.0)
        nav = ctx.portfolio.nav_btc(ctx.prices)
        add = intent.qty * ctx.prices.btc(intent.asset) / nav if nav else 1.0
        cap = min(limits["position"]["max_protocol_weight"], allow.get("protocols", {}).get(intent.venue, {}).get("max_weight", 1.0))
        if prot_w + add > cap + 1e-9:
            v.append(f"protocol {intent.venue} weight would be {prot_w + add:.1%} (max {cap:.0%})")
        have = ctx.portfolio.qty(intent.asset, liquid_only=True)
        if intent.qty > have * 1.000001:
            v.append(f"supply {intent.qty} {intent.asset} exceeds holding {have}")
        if intent.cost is None and limits["costs"]["require_cost_estimate"]:
            v.append("no cost estimate for the deposit")
    return PolicyDecision(allowed=not v, violations=v)


def check_transfer(intent: TransferIntent, ctx: PolicyContext, limits: dict, allow: dict) -> PolicyDecision:
    v = []
    ok, why = stage_allows(ctx.mode, limits)
    if not ok:
        v.append(why)
    safe = limits["kill_switch"].get("safe_address")
    if intent.reason_code != "kill_switch" or not ctx.killed:
        v.append("transfers are only allowed by the kill switch procedure")
    if not safe or intent.to_address.lower() != str(safe).lower():
        v.append("transfers may only go to the human-set safe address")
    return PolicyDecision(allowed=not v, violations=v)


def check(intent: Intent, ctx: PolicyContext) -> PolicyDecision:
    limits, allow = frozen.limits(), frozen.allowlists()
    if isinstance(intent, TradeIntent):
        return check_trade(intent, ctx, limits, allow)
    if isinstance(intent, ApproveIntent):
        return check_approve(intent, ctx, limits, allow)
    if isinstance(intent, LendIntent):
        return check_lend(intent, ctx, limits, allow)
    if isinstance(intent, TransferIntent):
        return check_transfer(intent, ctx, limits, allow)
    return PolicyDecision(allowed=False, violations=[f"unknown intent type {type(intent).__name__}"])
