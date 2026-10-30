"""Alerts: e-mail through the rig's msmtp (already configured for Netdata) and optional Telegram.

Every alert is also a ledger event, so nothing depends on delivery. Repeated alerts of the same kind are rate
limited. Alert text is built by code from typed fields; LLM text is never forwarded verbatim.
"""
from __future__ import annotations

import os
import subprocess
import time

import httpx

from .ledger.store import Ledger

LEVELS = ("info", "trade", "warning", "critical")


class Alerts:
    def __init__(self, cfg: dict, ledger: Ledger, dry_run: bool = False):
        self.cfg, self.ledger, self.dry_run = cfg, ledger, dry_run
        self._last: dict[str, float] = {}

    def send(self, kind: str, level: str, subject: str, body: str) -> bool:
        now = time.time()
        gap = self.cfg.get("min_interval_minutes", 30) * 60
        if level != "critical" and now - self._last.get(kind, 0) < gap:
            return False
        self._last[kind] = now
        delivered = []
        if not self.dry_run and self.cfg.get("email_enabled") and self.cfg.get("email_to"):
            delivered.append(("email", self._email(f"[crypto agent {level}] {subject}", body)))
        if not self.dry_run and self.cfg.get("telegram_enabled"):
            delivered.append(("telegram", self._telegram(f"[{level}] {subject}\n{body}")))
        self.ledger.append("alert", {"kind": kind, "level": level, "subject": subject, "body": body[:2000],
                                     "delivered": delivered, "dry_run": self.dry_run})
        return True

    def _email(self, subject: str, body: str) -> bool:
        msg = f"To: {self.cfg['email_to']}\nSubject: {subject}\nContent-Type: text/plain; charset=utf-8\n\n{body}\n"
        try:
            r = subprocess.run(["msmtp", "-t"], input=msg, text=True, capture_output=True, timeout=60)
            return r.returncode == 0
        except Exception:
            return False

    def _telegram(self, text: str) -> bool:
        tok, chat = os.environ.get("CRYPTOAGENT_TELEGRAM_TOKEN"), os.environ.get("CRYPTOAGENT_TELEGRAM_CHAT")
        if not tok or not chat:
            return False
        try:
            r = httpx.post(f"https://api.telegram.org/bot{tok}/sendMessage", json={"chat_id": chat, "text": text[:3500]}, timeout=20)
            return r.status_code == 200
        except Exception:
            return False
