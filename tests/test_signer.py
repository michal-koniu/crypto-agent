"""The signer re-checks raw transactions independently of the policy engine."""
import json
import os
import threading
import time

import httpx
import pytest
from eth_abi import encode
from eth_utils import keccak

from cryptoagent import frozen
from cryptoagent.signer import keystore
from cryptoagent.signer.policy import (SEL_APPROVE, SEL_EXACT_INPUT_SINGLE, SEL_SUPPLY, SEL_TRANSFER, SEL_WITHDRAW,
                                    SignRequest, check_cex_order, check_tx)

ALLOW, LIMITS = frozen.allowlists(), frozen.limits()
ME = "0x1111111111111111111111111111111111111111"
EVIL = "0x000000000000000000000000000000000000dEaD"
USDC = ALLOW["tokens"]["base"]["USDC"]["address"]
CBBTC = ALLOW["tokens"]["base"]["cbBTC"]["address"]
ROUTER = ALLOW["contracts"]["base"]["uniswap_v3_swap_router02"]["address"]
POOL = ALLOW["contracts"]["base"]["aave_v3_pool"]["address"]


def sel(sig):
    return "0x" + keccak(text=sig)[:4].hex()


def test_selectors_match_signatures():
    assert SEL_EXACT_INPUT_SINGLE == sel("exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))")
    assert SEL_SUPPLY == sel("supply(address,uint256,address,uint16)")
    assert SEL_WITHDRAW == sel("withdraw(address,uint256,address)")
    assert SEL_APPROVE == sel("approve(address,uint256)")
    assert SEL_TRANSFER == sel("transfer(address,uint256)")
    quoter = ALLOW["contracts"]["base"]["uniswap_v3_quoter_v2"]["selectors"]["quoteExactInputSingle"]
    assert quoter == sel("quoteExactInputSingle((address,address,uint256,uint24,uint160))")


def swap(recipient=ME, min_out=1, tin=USDC, tout=CBBTC, amount=10**8):
    return SEL_EXACT_INPUT_SINGLE + encode(["(address,address,uint24,address,uint256,uint256,uint160)"],
                                           [(tin, tout, 500, recipient, amount, min_out, 0)]).hex()


def req(to, data, **kw):
    return SignRequest(chain="base", chain_id=8453, to=to, data=data, **kw)


def test_good_swap_signs():
    assert check_tx(req(ROUTER, swap()), ME, ALLOW, LIMITS, killed=False) == []


def test_swap_to_foreign_recipient_refused():
    assert any("recipient" in v for v in check_tx(req(ROUTER, swap(recipient=EVIL)), ME, ALLOW, LIMITS, False))


def test_swap_without_slippage_protection_refused():
    assert any("amountOutMinimum" in v for v in check_tx(req(ROUTER, swap(min_out=0)), ME, ALLOW, LIMITS, False))


def test_unknown_contract_and_selector_refused():
    assert any("not allowlisted" in v for v in check_tx(req(EVIL, swap()), ME, ALLOW, LIMITS, False))
    assert any("selector" in v for v in check_tx(req(ROUTER, "0xdeadbeef" + "00" * 64), ME, ALLOW, LIMITS, False))


def test_native_value_refused():
    assert any("native value" in v for v in check_tx(req(ROUTER, swap(), value=1), ME, ALLOW, LIMITS, False))


def test_wrong_chain_refused():
    r = SignRequest(chain="base", chain_id=1, to=ROUTER, data=swap())
    assert check_tx(r, ME, ALLOW, LIMITS, False)


def test_approvals():
    good = SEL_APPROVE + encode(["address", "uint256"], [ROUTER, 100]).hex()
    assert check_tx(req(USDC, good, declared_spend=100), ME, ALLOW, LIMITS, False) == []
    unlimited = SEL_APPROVE + encode(["address", "uint256"], [ROUTER, 2 ** 256 - 1]).hex()
    assert any("unlimited" in v for v in check_tx(req(USDC, unlimited, declared_spend=100), ME, ALLOW, LIMITS, False))
    too_big = SEL_APPROVE + encode(["address", "uint256"], [ROUTER, 1000]).hex()
    assert check_tx(req(USDC, too_big, declared_spend=100), ME, ALLOW, LIMITS, False)
    evil = SEL_APPROVE + encode(["address", "uint256"], [EVIL, 100]).hex()
    assert any("spender" in v for v in check_tx(req(USDC, evil, declared_spend=100), ME, ALLOW, LIMITS, False))
    revoke = SEL_APPROVE + encode(["address", "uint256"], [ROUTER, 0]).hex()
    assert check_tx(req(USDC, revoke), ME, ALLOW, LIMITS, killed=True) == []
    # while killed: an exact approval to the router (for the exit swap) is fine, to the lending pool it is not
    assert check_tx(req(USDC, good, declared_spend=100), ME, ALLOW, LIMITS, killed=True) == []
    to_pool = SEL_APPROVE + encode(["address", "uint256"], [POOL, 100]).hex()
    assert check_tx(req(USDC, to_pool, declared_spend=100), ME, ALLOW, LIMITS, killed=True)


def test_transfers_only_when_killed_and_to_safe():
    t = SEL_TRANSFER + encode(["address", "uint256"], [EVIL, 5]).hex()
    v = check_tx(req(USDC, t), ME, ALLOW, LIMITS, killed=False)
    assert any("only signed during the kill" in x for x in v)
    v = check_tx(req(USDC, t), ME, ALLOW, LIMITS, killed=True)
    assert any("safe address" in x for x in v)        # safe_address is null in the frozen limits


def test_aave_onbehalf_and_destination():
    good = SEL_SUPPLY + encode(["address", "uint256", "address", "uint16"], [USDC, 10, ME, 0]).hex()
    assert check_tx(req(POOL, good), ME, ALLOW, LIMITS, False) == []
    bad = SEL_SUPPLY + encode(["address", "uint256", "address", "uint16"], [USDC, 10, EVIL, 0]).hex()
    assert check_tx(req(POOL, bad), ME, ALLOW, LIMITS, False)
    wbad = SEL_WITHDRAW + encode(["address", "uint256", "address"], [USDC, 10, EVIL]).hex()
    assert check_tx(req(POOL, wbad), ME, ALLOW, LIMITS, False)
    assert any("no new deposits" in v for v in check_tx(req(POOL, good), ME, ALLOW, LIMITS, killed=True))


def test_cex_order_rules():
    assert check_cex_order("okx", "BTC/USDC", "buy", 0.001, 80, ALLOW, LIMITS, False) == []
    assert check_cex_order("okx", "PEPE/USDC", "buy", 1, 80, ALLOW, LIMITS, False)
    assert check_cex_order("okx", "BTC/USDC", "buy", 1, 80000, ALLOW, LIMITS, False)
    assert check_cex_order("okx", "ETH/USDC", "buy", 1, 100, ALLOW, LIMITS, killed=True)


def test_keystore_never_exposes_key(tmp_path, monkeypatch):
    monkeypatch.setenv("CRYPTOAGENT_KEYSTORE_PASSWORD", "test-only-password")
    pk = "0x" + "11" * 32
    addr = keystore.create(tmp_path / "k.json", private_key=pk)
    text = (tmp_path / "k.json").read_text()
    assert pk[2:] not in text and addr.lower()[2:] in text.lower()
    assert oct(os.stat(tmp_path / "k.json").st_mode)[-3:] == "600"
    assert keystore.load(tmp_path / "k.json").address == addr


def test_signer_daemon_end_to_end(tmp_path, monkeypatch):
    """Run the real HTTP signer; it signs an allowlisted swap and refuses a hostile one."""
    from cryptoagent.signer.client import SignerClient, SignerRefused
    from cryptoagent.signer.server import serve
    monkeypatch.setenv("CRYPTOAGENT_KEYSTORE_PASSWORD", "test-only-password")
    ks = tmp_path / "k.json"
    addr = keystore.create(ks)
    port = 18791
    threading.Thread(target=serve, args=(str(tmp_path), str(ks), "fork", port), daemon=True).start()
    for _ in range(50):
        if (tmp_path / "signer.token").exists():
            break
        time.sleep(0.1)
    c = SignerClient(str(tmp_path))
    assert c.health()["address"] == addr
    ok = c.sign_tx(chain="base", chain_id=8453, to=ROUTER, data=swap(recipient=addr), nonce=0, gas=300000,
                   max_fee_per_gas=10**8, max_priority_fee_per_gas=10**6)
    assert ok["raw_tx"].startswith("0x") and ok["tx_hash"].startswith("0x")
    with pytest.raises(SignerRefused):
        c.sign_tx(chain="base", chain_id=8453, to=ROUTER, data=swap(recipient=EVIL), nonce=1, gas=300000,
                  max_fee_per_gas=10**8, max_priority_fee_per_gas=10**6)
    r = httpx.post(c.base + "/sign_tx", json={}, timeout=5)
    assert r.status_code == 401                                   # no token, no service
    journal = (tmp_path / "signer.jsonl").read_text()
    assert "sign_ok" in journal and "sign_refused" in journal and "test-only-password" not in journal


def test_rate_limit_never_blocks_exits_or_derisking(tmp_path, monkeypatch):
    """Normal orders hit the hourly cap; withdrawals to self, approve-to-zero and (while killed) exits still sign,
    against their own bounded ceiling."""
    from cryptoagent.signer.server import EMERGENCY_SIGNATURES_PER_HOUR, Signer
    monkeypatch.setenv("CRYPTOAGENT_KEYSTORE_PASSWORD", "test-only-password")
    ks = tmp_path / "k.json"
    addr = keystore.create(ks)
    sg = Signer(tmp_path / "st", str(ks), "fork")
    n = [0]

    def sign(to, data):
        n[0] += 1
        return sg.sign_tx({"chain": "base", "chain_id": 8453, "to": to, "data": data, "nonce": n[0], "gas": 300000,
                           "max_fee_per_gas": 10**8, "max_priority_fee_per_gas": 10**6})

    cap = LIMITS["rate"]["max_orders_per_hour"] * 4
    for _ in range(cap):
        assert sign(ROUTER, swap(recipient=addr))[0] == 200
    code, body = sign(ROUTER, swap(recipient=addr))
    assert code == 403 and "signer rate limit reached" in body["violations"]
    withdraw = SEL_WITHDRAW + encode(["address", "uint256", "address"], [USDC, 10**6, addr]).hex()
    assert sign(POOL, withdraw)[0] == 200                                     # de-risking: not blocked
    revoke = SEL_APPROVE + encode(["address", "uint256"], [ROUTER, 0]).hex()
    assert sign(USDC, revoke)[0] == 200                                       # approve-to-zero: not blocked
    (tmp_path / "st" / "KILL").write_text("{}")
    assert sign(ROUTER, swap(recipient=addr, tin=USDC, tout=CBBTC))[0] == 200  # kill exit: not blocked
    code, body = sign(POOL, SEL_SUPPLY + encode(["address", "uint256", "address", "uint16"], [USDC, 1, addr, 0]).hex())
    assert code == 403                                                        # killed: deposits still refused
    for _ in range(EMERGENCY_SIGNATURES_PER_HOUR - 3):
        assert sign(POOL, withdraw)[0] == 200
    code, body = sign(POOL, withdraw)
    assert code == 403 and "emergency ceiling" in body["violations"][0]       # but the emergency bucket is bounded
