"""A virtual portfolio that follows a strategy's targets: used by the backtester, the shadow books (champion
without the LLM, challenger, sentinel, old champion during probation) and the replay simulator. One implementation
everywhere, so a backtest, a shadow and a replay of the same params give the same numbers on the same prices."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

from ..strategies.rules import StrategyState, advance_state, target


@dataclass
class Book:
    params: dict
    cost_bps: float = 20.0                  # per side: fee + slippage
    btc: float = 1.0
    usd: float = 0.0
    eth: float = 0.0
    st: StrategyState = field(default_factory=StrategyState)
    trades: list = field(default_factory=list)
    last_rules: dict = field(default_factory=dict)

    def nav(self, px: float, eb: float | None) -> float:
        return self.btc + (self.usd / px if px else 0.0) + (self.eth * eb if self.eth and eb else 0.0)

    def weights(self, px: float, eb: float | None) -> tuple[float, float]:
        n = self.nav(px, eb)
        return (self.usd / px / n if n else 0.0), ((self.eth * eb) / n if n and self.eth and eb else 0.0)

    def rebalance(self, day, px: float, eb: float | None, w_stable: float, w_eth: float, reason: str):
        n = self.nav(px, eb)
        cur_s, cur_e = self.weights(px, eb)
        cost = self.cost_bps / 1e4
        for leg, cur, want in (("STABLE", cur_s, w_stable), ("ETH", cur_e, w_eth)):
            delta = want - cur
            if abs(delta) < 0.005:
                continue
            notional = abs(delta) * n
            fee = notional * cost
            if leg == "STABLE":
                if delta > 0:
                    self.btc -= notional
                    self.usd += (notional - fee) * px
                else:
                    self.usd -= notional * px
                    self.btc += notional - fee
            else:
                if not eb or not math.isfinite(eb):
                    continue
                if delta > 0:
                    self.btc -= notional
                    self.eth += (notional - fee) / eb
                else:
                    self.eth -= notional / eb
                    self.btc += notional - fee
            self.trades.append({"date": str(day), "leg": leg, "side": "buy" if delta > 0 else "sell", "notional_btc": notional,
                                "fee_btc": fee, "btc_usd": px, "eth_btc": eb, "reason": reason})
        self.eth = max(self.eth, 0.0)
        self.usd = max(self.usd, 0.0)

    def on_day(self, day, px: float, eb: float | None, tbill_pct: float | None) -> list[str]:
        """Accrue stablecoin yield and check BTC-terms stops on a daily close. Returns triggered stop names."""
        yp = self.params.get("yield", {})
        if tbill_pct is not None and math.isfinite(tbill_pct):
            self.usd *= 1 + max(tbill_pct / 100 - yp.get("stable_apy_haircut", 0.01), 0.0) / 365
        fired = []
        cg, ag = self.params["cycle_guard"], self.params["alt_gate"]
        if self.usd > 0 and self.st.stable_entry_btc_price and px >= self.st.stable_entry_btc_price / (1 - cg["stable_stop_btc_pct"]):
            _, we = self.weights(px, eb)
            self.rebalance(day, px, eb, 0.0, we, "stable_stop")
            self.st.stable, self.st.stable_entry_btc_price, self.st.weeks_in_stable, self.st.exit_armed = 0.0, None, 0, False
            fired.append("stable_stop")
        if self.eth > 0 and self.st.eth_entry_ethbtc and eb and eb <= self.st.eth_entry_ethbtc * (1 - ag["eth_stop_btc_pct"]):
            ws, _ = self.weights(px, eb)
            self.rebalance(day, px, eb, ws, 0.0, "eth_stop")
            self.st.eth, self.st.eth_entry_ethbtc, self.st.eth_weeks_below = 0.0, None, 0
            fired.append("eth_stop")
        return fired

    def on_week(self, day, row: dict, conviction: tuple[float, float] = (1.0, 1.0)):
        """Weekly decision from a feature row. conviction scales the deviations from BTC (LLM overlay)."""
        t = target(row, self.st, self.params)
        self.last_rules = t.rules
        ws, we = t.stable * conviction[0], t.eth * conviction[1]
        cs, ce = self.weights(row["btc"], row.get("eth_btc"))
        if abs(ws - cs) > 0.005 or abs(we - ce) > 0.005:
            self.rebalance(day, row["btc"], row.get("eth_btc"), ws, we, "weekly")
        t.stable, t.eth = ws, we
        self.st = advance_state(self.st, t, row)
        return t

    def to_dict(self) -> dict:
        d = asdict(self)
        d["trades"] = self.trades[-50:]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Book":
        st = StrategyState(**d.pop("st"))
        return cls(**d, st=st)
