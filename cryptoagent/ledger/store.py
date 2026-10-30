"""Append-only, hash-chained event ledger (SQLite + JSONL mirror).

Every row stores the SHA-256 of the previous row, so editing or deleting any past row breaks the chain and
`verify()` finds it. SQLite triggers reject UPDATE and DELETE outright. The JSONL mirror is a second, plain-text
copy that `verify()` also compares, so a tamperer would have to rewrite both consistently.

Event kinds (open set): decision, proposal, policy_check, order, fill, transfer, approval, deposit, withdraw,
stop_trigger, kill_switch, model_call, review, postmortem, change, rollback, alert, error, heartbeat, valuation.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

GENESIS = "0" * 64

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    seq        INTEGER PRIMARY KEY,
    id         TEXT NOT NULL UNIQUE,
    ts         TEXT NOT NULL,
    kind       TEXT NOT NULL,
    payload    TEXT NOT NULL,
    prev_hash  TEXT NOT NULL,
    hash       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_kind_ts ON events(kind, ts);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def row_hash(prev_hash: str, seq: int, eid: str, ts: str, kind: str, payload_json: str) -> str:
    h = hashlib.sha256()
    for part in (prev_hash, str(seq), eid, ts, kind, payload_json):
        h.update(part.encode())
        h.update(b"\x1f")
    return h.hexdigest()


@dataclass
class Event:
    seq: int
    id: str
    ts: str
    kind: str
    payload: dict
    prev_hash: str
    hash: str


class Ledger:
    """Thread-safe append-only ledger. One file per deployment (and one per test)."""

    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.jsonl = self.path.with_suffix(".jsonl")
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.executescript(SCHEMA)
        self.clock = None          # optional callable returning an ISO timestamp (replay uses the simulated clock)

    # ------------------------------------------------------------------ write
    def append(self, kind: str, payload: dict, ts: str | None = None) -> Event:
        payload_json = canonical(payload)
        with self._lock:
            cur = self._db.execute("SELECT seq, hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
            seq, prev = (cur[0] + 1, cur[1]) if cur else (1, GENESIS)
            eid = str(uuid.uuid4())
            ts = ts or (self.clock() if self.clock else utcnow())
            h = row_hash(prev, seq, eid, ts, kind, payload_json)
            self._db.execute("BEGIN IMMEDIATE")
            try:
                self._db.execute(
                    "INSERT INTO events(seq,id,ts,kind,payload,prev_hash,hash) VALUES (?,?,?,?,?,?,?)",
                    (seq, eid, ts, kind, payload_json, prev, h))
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise
            line = canonical({"seq": seq, "id": eid, "ts": ts, "kind": kind, "payload": payload,
                              "prev_hash": prev, "hash": h})
            with open(self.jsonl, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                os.fsync(f.fileno())
        return Event(seq, eid, ts, kind, payload, prev, h)

    # ------------------------------------------------------------------ read
    def events(self, kind: str | None = None, since: str | None = None, limit: int | None = None) -> list[Event]:
        q, args = "SELECT seq,id,ts,kind,payload,prev_hash,hash FROM events WHERE 1=1", []
        if kind:
            q += " AND kind=?"
            args.append(kind)
        if since:
            q += " AND ts>=?"
            args.append(since)
        q += " ORDER BY seq DESC LIMIT ?" if limit else " ORDER BY seq"
        if limit:
            args.append(int(limit))
        with self._lock:
            rows = self._db.execute(q, args).fetchall()
        if limit:
            rows.reverse()
        return [Event(r[0], r[1], r[2], r[3], json.loads(r[4]), r[5], r[6]) for r in rows]

    def last(self, kind: str) -> Event | None:
        ev = self.events(kind=kind, limit=1)
        return ev[-1] if ev else None

    def head(self) -> tuple[int, str]:
        with self._lock:
            cur = self._db.execute("SELECT seq, hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        return (cur[0], cur[1]) if cur else (0, GENESIS)

    def count(self, kind: str, since: str) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM events WHERE kind=? AND ts>=?", (kind, since)).fetchone()[0]

    # ------------------------------------------------------------------ integrity
    def verify(self) -> tuple[bool, str]:
        """Recompute the whole chain and compare it with the JSONL mirror."""
        prev = GENESIS
        n = 0
        with self._lock:
            rows = self._db.execute("SELECT seq,id,ts,kind,payload,prev_hash,hash FROM events ORDER BY seq").fetchall()
        for r in rows:
            seq, eid, ts, kind, payload_json, prev_hash, h = r
            if seq != n + 1:
                return False, f"gap before seq {seq}"
            if prev_hash != prev:
                return False, f"broken link at seq {seq}"
            if row_hash(prev_hash, seq, eid, ts, kind, payload_json) != h:
                return False, f"hash mismatch at seq {seq}"
            prev, n = h, seq
        if self.jsonl.exists():
            lines = [json.loads(x) for x in self.jsonl.read_text(encoding="utf-8").splitlines() if x.strip()]
            if len(lines) != n:
                return False, f"jsonl mirror has {len(lines)} rows, db has {n}"
            for line, r in zip(lines, rows):
                if line["hash"] != r[6] or canonical(line["payload"]) != r[4]:
                    return False, f"jsonl mirror differs at seq {line['seq']}"
        return True, f"ok: {n} events, head {prev[:16]}"

    def iter_payloads(self, kind: str) -> Iterator[dict]:
        for e in self.events(kind=kind):
            yield {"_ts": e.ts, "_id": e.id, **e.payload}

    def close(self):
        self._db.close()
