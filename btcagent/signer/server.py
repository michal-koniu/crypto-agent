"""The signer daemon: holds keys, signs only what its own policy allows, never talks to an LLM.

Runs as its own process (`btcagent signer`), listening on 127.0.0.1 with a bearer token written to a 0600 file in
the state directory. The core asks it to sign; it answers with a raw signed transaction or a refusal with reasons.

Keys: the EVM key comes from an encrypted keystore (see keystore.py). CEX API keys come from the environment of
this process only (BTCAGENT_OKX_KEY / _SECRET / _PASSPHRASE etc., normally injected from Bitwarden by the
systemd unit) and must be created on the exchange with trading permission only - no withdrawals. The signer exposes
no withdrawal endpoint for any venue.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .. import frozen
from ..ledger.store import Ledger
from . import keystore
from .policy import SEL_APPROVE, SEL_WITHDRAW, SignRequest, check_cex_order, check_tx

# Exits while the kill switch is engaged, and calls that only reduce risk (Aave withdraw to our own wallet, approve-to-
# zero), are never blocked by the normal order-rate cap: an emergency must not fail because the last hour was busy.
# They count against their own, bounded ceiling instead (found in the final review: the kill drill on the fork was
# refused with "signer rate limit reached" after a protocol-guard withdrawal).
EMERGENCY_SIGNATURES_PER_HOUR = 60


class Signer:
    def __init__(self, state_dir: str | os.PathLike, keystore_path: str | None, mode: str):
        frozen.assert_intact()
        self.state = Path(state_dir)
        self.state.mkdir(parents=True, exist_ok=True)
        self.mode = mode
        self.allow = frozen.allowlists()
        self.limits = frozen.limits()
        self.journal = Ledger(self.state / "signer.db")
        self.account = keystore.load(keystore_path) if keystore_path else None
        self.address = self.account.address if self.account else None
        self._times: list[float] = []
        self._emergency_times: list[float] = []
        self._lock = threading.Lock()
        self._cex = {}

    @property
    def killed(self) -> bool:
        return (self.state / "KILL").exists()

    def _rate_ok(self, emergency: bool = False) -> bool:
        cap = EMERGENCY_SIGNATURES_PER_HOUR if emergency else self.limits["rate"]["max_orders_per_hour"] * 4   # swaps + approvals + revokes
        now = time.time()
        with self._lock:
            times = self._emergency_times if emergency else self._times
            times[:] = [t for t in times if now - t < 3600]
            if len(times) >= cap:
                return False
            times.append(now)
            return True

    @staticmethod
    def _derisking(req: SignRequest) -> bool:
        """Calls that can only reduce risk; check_tx has already verified recipient/allowlists."""
        sel = req.data[:10].lower()
        if sel == SEL_WITHDRAW:
            return True
        return sel == SEL_APPROVE and len(req.data) >= 138 and int(req.data[-64:], 16) == 0

    def sign_tx(self, body: dict) -> tuple[int, dict]:
        if not self.account:
            return 400, {"error": "no EVM key loaded"}
        req = SignRequest(chain=body["chain"], chain_id=int(body["chain_id"]), to=body["to"], data=body["data"],
                          value=int(body.get("value", 0)), declared_spend=body.get("declared_spend"))
        v = check_tx(req, self.address, self.allow, self.limits, self.killed)
        if self.mode == "live" and self.limits.get("stage") != "live":
            v.append("signer: frozen stage is not live")
        emergency = self.killed or self._derisking(req)
        if not v and not self._rate_ok(emergency):
            v.append("signer rate limit reached" + (" (emergency ceiling)" if emergency else ""))
        rec = {"chain": req.chain, "to": req.to, "selector": req.data[:10], "nonce": body.get("nonce"),
               "allowed": not v, "violations": v, "killed": self.killed, "rate_bucket": "emergency" if emergency else "normal"}
        if v:
            self.journal.append("sign_refused", rec)
            return 403, {"violations": v}
        tx = {"chainId": req.chain_id, "to": req.to, "data": req.data, "value": 0, "nonce": int(body["nonce"]),
              "gas": int(body["gas"]), "maxFeePerGas": int(body["max_fee_per_gas"]),
              "maxPriorityFeePerGas": int(body["max_priority_fee_per_gas"]), "type": 2}
        signed = self.account.sign_transaction(tx)
        raw = signed.raw_transaction.hex() if hasattr(signed, "raw_transaction") else signed.rawTransaction.hex()
        txh = signed.hash.hex()
        self.journal.append("sign_ok", {**rec, "tx_hash": txh})
        return 200, {"raw_tx": raw if raw.startswith("0x") else "0x" + raw, "tx_hash": txh if txh.startswith("0x") else "0x" + txh}

    def _exchange(self, venue: str):
        if venue in self._cex:
            return self._cex[venue]
        import ccxt
        cfg = self.allow["venues"][venue]
        up = venue.upper()
        params = {"apiKey": os.environ.get(f"BTCAGENT_{up}_KEY"), "secret": os.environ.get(f"BTCAGENT_{up}_SECRET"),
                  "password": os.environ.get(f"BTCAGENT_{up}_PASSPHRASE"), "enableRateLimit": True}
        if not params["apiKey"]:
            raise RuntimeError(f"no API key for {venue} in the signer's environment")
        ex = getattr(ccxt, cfg["ccxt_id"])(params)
        if os.environ.get(f"BTCAGENT_{up}_DEMO") == "1":
            ex.set_sandbox_mode(True)            # OKX demo trading (EEA) / exchange testnets
        self._cex[venue] = ex
        return ex

    def cex_order(self, body: dict) -> tuple[int, dict]:
        v = check_cex_order(body["venue"], body["symbol"], body["side"], float(body["amount"]),
                            float(body.get("notional_usd", 0)), self.allow, self.limits, self.killed)
        if self.mode not in ("live", "fork") and os.environ.get(f"BTCAGENT_{body['venue'].upper()}_DEMO") != "1":
            v.append(f"signer: real CEX orders need mode live (or the venue's demo flag); mode is {self.mode}")
        if self.mode == "live" and self.limits.get("stage") != "live":
            v.append("signer: frozen stage is not live")
        if not v and not self._rate_ok(emergency=self.killed):
            v.append("signer rate limit reached")
        rec = {k: body.get(k) for k in ("venue", "symbol", "side", "type", "amount", "price", "notional_usd")}
        if v:
            self.journal.append("cex_refused", {**rec, "violations": v})
            return 403, {"violations": v}
        ex = self._exchange(body["venue"])
        o = ex.create_order(body["symbol"], body.get("type", "market"), body["side"], float(body["amount"]),
                            body.get("price"), body.get("params") or {})
        self.journal.append("cex_ok", {**rec, "order_id": o.get("id")})
        return 200, {"order": o}


def serve(state_dir: str, keystore_path: str | None, mode: str, port: int = 8790) -> None:
    signer = Signer(state_dir, keystore_path, mode)
    token = secrets.token_urlsafe(32)
    tok_file = Path(state_dir) / "signer.token"
    tok_file.write_text(json.dumps({"port": port, "token": token, "address": signer.address}))
    os.chmod(tok_file, 0o600)

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet; the journal is the log
            pass

        def _send(self, code: int, obj: dict):
            b = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def _auth(self) -> bool:
            return secrets.compare_digest(self.headers.get("Authorization", ""), f"Bearer {token}")

        def do_GET(self):
            if self.path == "/health":
                return self._send(200, {"ok": True, "address": signer.address, "killed": signer.killed, "mode": mode})
            self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self._auth():
                return self._send(401, {"error": "unauthorised"})
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                if self.path == "/sign_tx":
                    return self._send(*signer.sign_tx(body))
                if self.path == "/cex_order":
                    return self._send(*signer.cex_order(body))
                self._send(404, {"error": "not found"})
            except Exception as e:  # never echo secrets; type and message only
                signer.journal.append("signer_error", {"path": self.path, "error": f"{type(e).__name__}: {e}"[:300]})
                self._send(500, {"error": type(e).__name__})

    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
