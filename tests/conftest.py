import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from btcagent.ledger.store import Ledger  # noqa: E402
from btcagent.policy.engine import PolicyContext  # noqa: E402
from btcagent.types import CostEstimate, Holding, Portfolio, Prices  # noqa: E402

DATA_DIR = Path(os.environ.get("BTCAGENT_DATA_DIR", "~/.local/share/btcagent/data")).expanduser()


@pytest.fixture
def ledger(tmp_path):
    return Ledger(tmp_path / "ledger.db")


@pytest.fixture
def prices():
    return Prices(usd={"BTC": 80000.0, "ETH": 2400.0, "SOL": 150.0, "USDC": 1.0, "USDT": 1.0},
                  second_source_btc_usd=80040.0, source="test")


def pf(btc=1.0, usdc=0.0, eth=0.0, venue="paper", lent_usdc=0.0):
    hs = []
    if btc:
        hs.append(Holding(venue=venue, asset="BTC", qty=btc))
    if usdc:
        hs.append(Holding(venue=venue, asset="USDC", qty=usdc))
    if eth:
        hs.append(Holding(venue=venue, asset="ETH", qty=eth))
    if lent_usdc:
        hs.append(Holding(venue=venue, asset="USDC", qty=lent_usdc, protocol="aave_v3_base"))
    return Portfolio(holdings=hs)


@pytest.fixture
def ctx_factory(prices):
    def make(portfolio=None, mode="paper", **kw):
        return PolicyContext(portfolio=portfolio or pf(btc=0.05), prices=prices, mode=mode, **kw)
    return make


def cheap_cost():
    return CostEstimate(fee_bps=20, spread_bps=1, slippage_bps=2, gas_usd=0.0)


def has_rig_llm() -> bool:
    try:
        import httpx
        return httpx.get(os.environ.get("BTCAGENT_RIG_URL", "http://localhost:8080/v1").rstrip("/") + "/models", timeout=5).status_code == 200
    except Exception:
        return False


def has_data() -> bool:
    return (DATA_DIR / "cm_btc.csv").exists()


now = datetime.now(timezone.utc)
hours_ago = lambda h: now - timedelta(hours=h)  # noqa: E731
