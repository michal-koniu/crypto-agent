"""Client the core uses to reach the signer daemon."""
from __future__ import annotations

import json
from pathlib import Path

import httpx


class SignerRefused(RuntimeError):
    def __init__(self, violations: list[str]):
        super().__init__("; ".join(violations))
        self.violations = violations


class SignerClient:
    def __init__(self, state_dir: str):
        info = json.loads((Path(state_dir) / "signer.token").read_text())
        self.base = f"http://127.0.0.1:{info['port']}"
        self.address = info.get("address")
        self._h = {"Authorization": f"Bearer {info['token']}"}

    def health(self) -> dict:
        return httpx.get(self.base + "/health", timeout=10).json()

    def _post(self, path: str, body: dict) -> dict:
        r = httpx.post(self.base + path, json=body, headers=self._h, timeout=60)
        if r.status_code == 403:
            raise SignerRefused(r.json().get("violations", ["refused"]))
        r.raise_for_status()
        return r.json()

    def sign_tx(self, **body) -> dict:
        return self._post("/sign_tx", body)

    def cex_order(self, **body) -> dict:
        return self._post("/cex_order", body)
