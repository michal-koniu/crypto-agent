"""Typed records shared by the policy engine, executors, signer and agent.

Everything an LLM produces is parsed into these models before code looks at it; free text from a model never
reaches the policy engine except in the `rationale` field, which the engine does not read.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class AssetClass(str, Enum):
    BTC = "BTC"
    STABLE = "STABLE"
    ALT = "ALT"


class Prices(BaseModel):
    """Prices of each asset in USD, with the time they were observed and their source."""
    usd: dict[str, float]
    ts: datetime = Field(default_factory=now_utc)
    source: str = "unknown"
    second_source_btc_usd: float | None = None   # independent BTC price for the divergence check

    def btc(self, asset: str) -> float:
        """Price of one unit of `asset` in BTC."""
        if asset == "BTC":
            return 1.0
        return self.usd[asset] / self.usd["BTC"]


class Holding(BaseModel):
    venue: str
    asset: str
    qty: float
    protocol: str | None = None    # e.g. aave_v3_base when supplied to a lending market
    chain: str | None = None


class StopRule(BaseModel):
    """A stop defined in BTC terms: exit when the position's value in BTC falls this far from entry.

    For a stablecoin position, value in BTC falls when BTC rises, so the stop is the re-entry trigger.
    """
    max_loss_btc_pct: float = Field(gt=0, lt=1)
    entry_price_btc: float | None = None   # filled by the executor at fill time


class Position(BaseModel):
    asset: str
    venue: str
    qty: float
    entry_price_btc: float
    entry_ts: datetime
    stop: StopRule | None = None
    strategy_id: str | None = None
    decision_id: str | None = None


class Portfolio(BaseModel):
    holdings: list[Holding] = []
    positions: dict[str, Position] = {}   # open risk positions keyed by asset (non-BTC)

    def qty(self, asset: str, venue: str | None = None, liquid_only: bool = False) -> float:
        """Total quantity; liquid_only excludes amounts deposited in a protocol (they must be withdrawn first)."""
        return sum(h.qty for h in self.holdings if h.asset == asset and (venue is None or h.venue == venue)
                   and not (liquid_only and h.protocol))

    def nav_btc(self, prices: Prices) -> float:
        return sum(h.qty * prices.btc(h.asset) for h in self.holdings)

    def nav_usd(self, prices: Prices) -> float:
        return sum(h.qty * prices.usd[h.asset] for h in self.holdings)

    def weights(self, prices: Prices) -> dict[str, float]:
        nav = self.nav_btc(prices)
        out: dict[str, float] = {}
        for h in self.holdings:
            out[h.asset] = out.get(h.asset, 0.0) + (h.qty * prices.btc(h.asset) / nav if nav else 0.0)
        return out

    def protocol_weights(self, prices: Prices) -> dict[str, float]:
        nav = self.nav_btc(prices)
        out: dict[str, float] = {}
        for h in self.holdings:
            if h.protocol:
                out[h.protocol] = out.get(h.protocol, 0.0) + h.qty * prices.btc(h.asset) / nav
        return out


class CostEstimate(BaseModel):
    """Known cost of an action *before* it happens. All bps are relative to the order's notional."""
    fee_bps: float = 0.0
    spread_bps: float = 0.0
    slippage_bps: float = 0.0          # expected price impact vs the reference price
    gas_usd: float = 0.0
    other_usd: float = 0.0             # withdrawal fees, bridge fees, protocol fees
    lockup_hours: float = 0.0          # time until funds can be moved again
    source: str = "estimate"

    def total_bps(self, notional_usd: float) -> float:
        fixed = (self.gas_usd + self.other_usd) / notional_usd * 1e4 if notional_usd else 0.0
        return self.fee_bps + self.spread_bps + self.slippage_bps + fixed


class TradeIntent(BaseModel):
    kind: Literal["trade"] = "trade"
    venue: str
    chain: str | None = None
    sell_asset: str
    buy_asset: str
    sell_qty: float = Field(gt=0)
    order_type: Literal["market", "limit"] = "market"
    limit_price: float | None = None
    max_slippage_bps: float = 30.0
    stop: StopRule | None = None
    expected_edge_bps: float = 0.0     # strategy's expected edge, used for the edge-to-cost check
    reason_code: str = "strategy"      # strategy | stop_loss | take_profit | kill_switch | rebalance
    strategy_id: str = "unknown"
    strategy_version: str = "unknown"
    decision_id: str | None = None
    cost: CostEstimate | None = None
    rationale: str = ""                # human-readable reasoning; NOT read by the policy engine

    @field_validator("sell_asset", "buy_asset")
    @classmethod
    def _upper(cls, v: str) -> str:
        if not v.isalnum() or len(v) > 12:
            raise ValueError("asset symbols are short alphanumeric codes")
        return v.upper()


class ApproveIntent(BaseModel):
    kind: Literal["approve"] = "approve"
    chain: str
    token: str          # allowlisted token symbol on that chain
    spender: str        # address
    amount: float       # token units; "unlimited" is not representable on purpose
    for_amount: float   # the amount the following action will spend
    decision_id: str | None = None


class LendIntent(BaseModel):
    kind: Literal["lend"] = "lend"
    action: Literal["supply", "withdraw"]
    venue: str          # e.g. aave_v3_base or okx (Earn)
    chain: str | None = None
    asset: str
    qty: float = Field(gt=0)
    expected_apy: float = 0.0
    cost: CostEstimate | None = None
    strategy_id: str = "unknown"
    strategy_version: str = "unknown"
    decision_id: str | None = None
    rationale: str = ""


class TransferIntent(BaseModel):
    kind: Literal["transfer"] = "transfer"
    chain: str
    asset: str
    qty: float
    to_address: str
    reason_code: Literal["kill_switch"] = "kill_switch"   # the agent can never transfer for any other reason
    decision_id: str | None = None


Intent = TradeIntent | ApproveIntent | LendIntent | TransferIntent


class PolicyDecision(BaseModel):
    allowed: bool
    violations: list[str] = []
    checks: dict[str, str] = {}      # check name -> "ok" or a short note
    halt: bool = False               # this decision should put the agent into a halt
    kill: bool = False               # this decision should trigger the kill switch
    ts: datetime = Field(default_factory=now_utc)
