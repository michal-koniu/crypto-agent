"""Encrypted keystore handling. The private key exists in plaintext only inside the signer process's memory.

Password sources, in order:
  1. BTCAGENT_KEYSTORE_PASSWORD_CMD: a command whose stdout is the password (e.g. `bw-secret btc-agent#keystore`
     with the rig's Bitwarden vault) - preferred;
  2. BTCAGENT_KEYSTORE_PASSWORD: the password itself (tests and forks only).
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path

from eth_account import Account


def _password() -> str:
    cmd = os.environ.get("BTCAGENT_KEYSTORE_PASSWORD_CMD")
    if cmd:
        out = subprocess.run(shlex.split(cmd), capture_output=True, text=True, timeout=60, check=True).stdout
        return out.strip()
    pw = os.environ.get("BTCAGENT_KEYSTORE_PASSWORD")
    if pw:
        return pw
    raise RuntimeError("no keystore password source configured")


def create(path: str | os.PathLike, private_key: str | None = None, password: str | None = None) -> str:
    """Create an encrypted keystore (new random key unless one is given). Returns the address only."""
    acct = Account.from_key(private_key) if private_key else Account.create()
    enc = Account.encrypt(acct.key, password or _password())
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(enc))
    os.chmod(p, 0o600)
    return acct.address


def load(path: str | os.PathLike):
    """Return an eth_account LocalAccount. Never log or return the key itself."""
    enc = json.loads(Path(path).read_text())
    return Account.from_key(Account.decrypt(enc, _password()))


def address_of(path: str | os.PathLike) -> str:
    enc = json.loads(Path(path).read_text())
    return "0x" + enc["address"] if not enc["address"].startswith("0x") else enc["address"]
