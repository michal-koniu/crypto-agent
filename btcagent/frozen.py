"""The frozen, human-owned layer: limits, allowlists, gate rules, parameter bounds, constitution.

`frozen/frozen.lock` holds the SHA-256 of every frozen file *and* of the source files of the modules that enforce
them (policy engine, signer, ledger, metrics, gatekeeper). The core verifies the lock at start-up and before every
cycle; a mismatch halts the agent. Only the human re-locks (`btcagent frozen lock`), normally after reviewing a diff.

This is the course's "freeze the measurement layer by construction" (03 §2): the LLM has no tool that writes files,
the gatekeeper only writes to `evolvable/`, and even a code path that wrote here would be caught by the lock.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
FROZEN_DIR = ROOT / "frozen"
LOCK_FILE = FROZEN_DIR / "frozen.lock"

# Files whose content the agent must never be able to change.
FROZEN_FILES = [
    "frozen/constitution.md",
    "frozen/limits.yaml",
    "frozen/allowlists.yaml",
    "frozen/gate_rules.yaml",
    "frozen/param_bounds.yaml",
    "frozen/sentinel.yaml",
    "btcagent/frozen.py",
    "btcagent/types.py",
    "btcagent/policy/engine.py",
    "btcagent/signer/policy.py",
    "btcagent/signer/server.py",
    "btcagent/signer/keystore.py",
    "btcagent/ledger/store.py",
    "btcagent/ledger/tax.py",
    "btcagent/backtest/metrics.py",
    "btcagent/improve/gatekeeper.py",
    "btcagent/improve/stats.py",
    "btcagent/risk/killswitch.py",
]

# The only files the gatekeeper may write (after gates pass). Everything else is out of the agent's reach.
EVOLVABLE_FILES = ["evolvable/strategies.yaml", "evolvable/playbook.yaml"]


class FrozenLayerError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compute_hashes(root: Path = ROOT) -> dict[str, str]:
    return {f: _sha(root / f) for f in FROZEN_FILES if (root / f).exists()}


def write_lock(root: Path = ROOT) -> dict[str, str]:
    hashes = compute_hashes(root)
    (root / "frozen" / "frozen.lock").write_text(json.dumps(hashes, indent=1, sort_keys=True) + "\n")
    return hashes


def verify_lock(root: Path = ROOT) -> list[str]:
    """Return a list of problems (empty when the frozen layer is intact)."""
    lock = root / "frozen" / "frozen.lock"
    if not lock.exists():
        return ["frozen.lock missing"]
    want = json.loads(lock.read_text())
    have = compute_hashes(root)
    problems = [f"{f}: changed" for f, h in want.items() if have.get(f) != h]
    problems += [f"{f}: not in lock" for f in have if f not in want]
    return problems


def assert_intact(root: Path = ROOT) -> None:
    problems = verify_lock(root)
    if problems:
        raise FrozenLayerError("frozen layer modified: " + "; ".join(problems))


@lru_cache(maxsize=None)
def _load(name: str, root: str) -> dict:
    return yaml.safe_load((Path(root) / "frozen" / name).read_text())


def limits(root: Path = ROOT) -> dict:
    return _load("limits.yaml", str(root))


def allowlists(root: Path = ROOT) -> dict:
    return _load("allowlists.yaml", str(root))


def gate_rules(root: Path = ROOT) -> dict:
    return _load("gate_rules.yaml", str(root))


def param_bounds(root: Path = ROOT) -> dict:
    return _load("param_bounds.yaml", str(root))


def sentinel(root: Path = ROOT) -> dict:
    return _load("sentinel.yaml", str(root))


def asset_class(asset: str, root: Path = ROOT) -> str | None:
    a = allowlists(root)["assets"].get(asset.upper())
    return a["class"] if a else None


def is_frozen_path(path: str) -> bool:
    p = path.replace("\\", "/").lstrip("./")
    return any(p == f or p.startswith("frozen/") for f in FROZEN_FILES) or not any(p == e for e in EVOLVABLE_FILES)
