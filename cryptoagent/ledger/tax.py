"""Tax and accounting export for a Polish tax resident (PIT-38 support data).

What the export does (sources in docs/RESEARCH.md, research A):
* every fill becomes one row with UTC time, venue, chain, tx hash or order id, assets, quantities, price, fees,
  gas, slippage, strategy version, decision id and the model that proposed it;
* each row is valued in USD and in PLN at the **NBP Table A mid rate of the last business day before** the
  transaction (art. 11a ust. 1 ustawy o PIT), fetched from api.nbp.pl and cached;
* each row is classified:
    - crypto -> crypto (including stablecoins such as USDT/USDC): tax-neutral exchange ("wymiana") - logged,
      no income and no deductible cost; fees on these swaps are recorded but are NOT deductible costs;
    - fiat -> crypto: acquisition cost (koszt uzyskania przychodu), deductible, pooled (no lot matching);
    - crypto -> fiat (or paying for goods/services with crypto): income (przychód) at 19 %;
  The agent never sells into fiat itself; fiat rows appear only for the human's own deposits/withdrawals, which
  can be added as manual events (`cryptoagent ledger add-fiat ...`).
* interest/Earn/lending rewards are exported separately: their PIT treatment is unsettled (research A), so they
  are flagged for the accountant rather than classified.

This module is frozen (part of the measurement layer): the agent cannot change how its results are accounted.
"""
from __future__ import annotations

import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx

from .store import Ledger

FIAT = {"PLN", "EUR", "USD"}
TAX_FIELDS = [
    "ts_utc", "event_id", "decision_id", "mode", "venue", "chain", "tx_hash_or_order_id", "side",
    "sell_asset", "sell_qty", "buy_asset", "buy_qty", "price", "price_quote", "fee_asset", "fee_qty",
    "fee_usd", "gas_native", "gas_usd", "slippage_bps", "value_usd", "nbp_table_date", "usd_pln",
    "value_pln", "fee_pln", "tax_class", "deductible_cost_pln", "income_pln", "strategy_id",
    "strategy_version", "playbook_version", "model", "reason_code",
]


class NBP:
    """NBP Table A mid rates with a local cache. Rate for D = mid rate published on the last business day < D."""

    def __init__(self, cache_file: str | Path, offline: bool = False):
        self.cache_file = Path(cache_file)
        self.offline = offline
        self.cache: dict[str, dict[str, float]] = json.loads(self.cache_file.read_text()) if self.cache_file.exists() else {}

    def _fetch_range(self, code: str, start: date, end: date) -> None:
        url = f"https://api.nbp.pl/api/exchangerates/rates/a/{code.lower()}/{start}/{end}/?format=json"
        r = httpx.get(url, timeout=30)
        if r.status_code == 404:
            return
        r.raise_for_status()
        for row in r.json()["rates"]:
            self.cache.setdefault(code, {})[row["effectiveDate"]] = row["mid"]
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.cache_file.write_text(json.dumps(self.cache))

    def rate_before(self, code: str, d: date) -> tuple[str, float]:
        code = code.upper()
        for attempt in range(2):
            table = self.cache.get(code, {})
            for back in range(1, 15):
                day = (d - timedelta(days=back)).isoformat()
                if day in table:
                    return day, table[day]
            if self.offline or attempt:
                break
            self._fetch_range(code, d - timedelta(days=20), d - timedelta(days=1))
        raise LookupError(f"no NBP {code} rate before {d}")


def classify(sell_asset: str, buy_asset: str) -> str:
    s, b = sell_asset.upper() in FIAT, buy_asset.upper() in FIAT
    if not s and not b:
        return "crypto_to_crypto_neutral"
    if s and not b:
        return "fiat_to_crypto_cost"
    if not s and b:
        return "crypto_to_fiat_income"
    return "fiat_to_fiat"


def export(ledger: Ledger, out_csv: str | Path, nbp: NBP, year: int | None = None) -> int:
    """Write one CSV row per fill. Returns the number of rows."""
    decisions = {e.payload.get("decision_id"): e.payload for e in ledger.events(kind="decision")}
    rows = []
    for e in ledger.events(kind="fill"):
        p = e.payload
        ts = datetime.fromisoformat(e.ts)
        if year and ts.year != year:
            continue
        table_date, usd_pln = nbp.rate_before("USD", ts.date())
        value_usd = float(p.get("value_usd", 0.0))
        fee_usd = float(p.get("fee_usd", 0.0)) + float(p.get("gas_usd", 0.0))
        cls = classify(p["sell_asset"], p["buy_asset"])
        value_pln = value_usd * usd_pln
        fee_pln = fee_usd * usd_pln
        d = decisions.get(p.get("decision_id"), {})
        rows.append({
            "ts_utc": e.ts, "event_id": e.id, "decision_id": p.get("decision_id"), "mode": p.get("mode"),
            "venue": p.get("venue"), "chain": p.get("chain"), "tx_hash_or_order_id": p.get("tx_hash") or p.get("order_id"),
            "side": p.get("side"), "sell_asset": p["sell_asset"], "sell_qty": p["sell_qty"], "buy_asset": p["buy_asset"],
            "buy_qty": p["buy_qty"], "price": p.get("price"), "price_quote": p.get("price_quote"),
            "fee_asset": p.get("fee_asset"), "fee_qty": p.get("fee_qty"), "fee_usd": round(fee_usd, 6),
            "gas_native": p.get("gas_native"), "gas_usd": p.get("gas_usd"), "slippage_bps": p.get("slippage_bps"),
            "value_usd": round(value_usd, 6), "nbp_table_date": table_date, "usd_pln": usd_pln,
            "value_pln": round(value_pln, 2), "fee_pln": round(fee_pln, 2), "tax_class": cls,
            "deductible_cost_pln": round(value_pln + fee_pln, 2) if cls == "fiat_to_crypto_cost" else 0.0,
            "income_pln": round(value_pln - fee_pln, 2) if cls == "crypto_to_fiat_income" else 0.0,
            "strategy_id": p.get("strategy_id"), "strategy_version": p.get("strategy_version"),
            "playbook_version": d.get("playbook_version"), "model": d.get("model"), "reason_code": p.get("reason_code"),
        })
    out = Path(out_csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TAX_FIELDS)
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def summary(csv_path: str | Path) -> dict:
    """PIT-38 style totals for the accountant (pooled costs, no lot matching)."""
    tot = {"rows": 0, "neutral_swaps": 0, "income_pln": 0.0, "deductible_cost_pln": 0.0, "non_deductible_fees_pln": 0.0}
    with open(csv_path) as f:
        for r in csv.DictReader(f):
            tot["rows"] += 1
            tot["income_pln"] += float(r["income_pln"])
            tot["deductible_cost_pln"] += float(r["deductible_cost_pln"])
            if r["tax_class"] == "crypto_to_crypto_neutral":
                tot["neutral_swaps"] += 1
                tot["non_deductible_fees_pln"] += float(r["fee_pln"])
    tot["taxable_base_pln"] = round(tot["income_pln"] - tot["deductible_cost_pln"], 2)
    return {k: round(v, 2) if isinstance(v, float) else v for k, v in tot.items()}
