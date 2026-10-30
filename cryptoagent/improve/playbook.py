"""The itemised playbook and lesson store (course 03 §4: items with IDs and counters, delta edits only).

evolvable/playbook.yaml has three sections:
  judgment   standing guidance for the analyst (e.g. how to weigh a macro event)
  lessons    post-mortem lessons; retrieved 1-3 at a time by tag; counters updated from outcomes
  procedure  operational notes (e.g. how to treat stale data)
Each item: id, text, tags, added_in, provenance (ledger ids), helpful, harmful, last_used. Items are never deleted:
RETIRE moves them to `archive` (Hermes Curator style). A size cap and write-time deduplication stop bloat.
Only code edits this file, and only by applying a delta that passed its gate.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

MAX_TOTAL_CHARS = 6000
MAX_ITEM_CHARS = 300
SECTIONS = ("judgment", "lessons", "procedure")
PREFIX = {"judgment": "J", "lessons": "L", "procedure": "P"}


def _words(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def similarity(a: str, b: str) -> float:
    wa, wb = _words(a), _words(b)
    return len(wa & wb) / len(wa | wb) if wa and wb else 0.0


class Playbook:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.data = yaml.safe_load(self.path.read_text()) if self.path.exists() else {"version": 0, "sections": {}, "archive": []}
        for s in SECTIONS:
            self.data["sections"].setdefault(s, [])
        self.data.setdefault("archive", [])

    @property
    def version(self) -> int:
        return int(self.data.get("version", 0))

    def items(self, section: str | None = None) -> list[dict]:
        secs = [section] if section else SECTIONS
        return [i for s in secs for i in self.data["sections"][s]]

    def get(self, item_id: str) -> dict | None:
        return next((i for i in self.items() if i["id"] == item_id), None)

    def total_chars(self) -> int:
        return sum(len(i["text"]) for i in self.items())

    def save(self):
        self.path.write_text(yaml.safe_dump(self.data, sort_keys=False, allow_unicode=True, width=120))

    # ------------------------------------------------------------------ validation (static gate helpers)
    def check_add(self, section: str, text: str) -> list[str]:
        v = []
        if section not in SECTIONS:
            v.append(f"unknown section {section}")
        if not text or len(text) > MAX_ITEM_CHARS:
            v.append(f"item text must be 1-{MAX_ITEM_CHARS} chars")
        if self.total_chars() + len(text) > MAX_TOTAL_CHARS:
            v.append(f"playbook would exceed the {MAX_TOTAL_CHARS}-char cap; retire something first")
        for i in self.items() + self.data["archive"]:
            if similarity(text, i["text"]) >= 0.6:
                v.append(f"near-duplicate of {i['id']}")
                break
        return v

    # ------------------------------------------------------------------ deltas
    def _next_id(self, section: str) -> str:
        n = [int(i["id"].split("-")[1]) for i in self.items(section) + [a for a in self.data["archive"] if a["id"].startswith(PREFIX[section])]]
        return f"{PREFIX[section]}-{(max(n) + 1) if n else 1:03d}"

    def add(self, section: str, text: str, tags: list[str], provenance: list[str]) -> dict:
        v = self.check_add(section, text)
        if v:
            raise ValueError("; ".join(v))
        item = {"id": self._next_id(section), "text": text, "tags": tags, "added_in": self.version + 1,
                "provenance": provenance, "helpful": 0, "harmful": 0, "last_used": None,
                "added": datetime.now(timezone.utc).date().isoformat()}
        self.data["sections"][section].append(item)
        self.data["version"] = self.version + 1
        return item

    def modify(self, item_id: str, text: str) -> str:
        it = self.get(item_id)
        if not it:
            raise KeyError(item_id)
        if len(text) > MAX_ITEM_CHARS:
            raise ValueError("item too long")
        old = it["text"]
        it["text"] = text
        it["modified_in"] = self.version + 1
        self.data["version"] = self.version + 1
        return old

    def retire(self, item_id: str, reason: str) -> dict:
        for s in SECTIONS:
            for i, it in enumerate(self.data["sections"][s]):
                if it["id"] == item_id:
                    it = self.data["sections"][s].pop(i)
                    it["retired"] = {"reason": reason, "in": self.version + 1}
                    self.data["archive"].append(it)
                    self.data["version"] = self.version + 1
                    return it
        raise KeyError(item_id)

    def restore(self, item_id: str, section: str) -> None:
        for i, it in enumerate(self.data["archive"]):
            if it["id"] == item_id:
                it = self.data["archive"].pop(i)
                it.pop("retired", None)
                self.data["sections"][section].append(it)
                self.data["version"] = self.version + 1
                return
        raise KeyError(item_id)

    # ------------------------------------------------------------------ retrieval and counters
    def retrieve_lessons(self, tags: set[str], k: int = 3) -> list[dict]:
        """Top-k lessons by tag overlap, then by (helpful - harmful); items that hurt more than helped are skipped."""
        scored = []
        for it in self.items("lessons"):
            if it["harmful"] > it["helpful"] + 1:
                continue
            overlap = len(tags & set(it.get("tags", [])))
            if overlap:
                scored.append((overlap, it["helpful"] - it["harmful"], it))
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [s[2] for s in scored[:k]]

    def count(self, item_id: str, helpful: bool):
        """Called by the harness when an outcome is known - never by an LLM."""
        it = self.get(item_id)
        if it:
            it["helpful" if helpful else "harmful"] += 1
            it["last_used"] = datetime.now(timezone.utc).date().isoformat()
