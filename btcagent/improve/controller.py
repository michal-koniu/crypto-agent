"""Lifecycle controller (course 04): BOOTSTRAP -> GATED -> MAINTENANCE <-> ADAPT, one change in flight, probation,
exponential backoff after rejections, and evidence-gated triggers. "Nothing happened" never triggers a reflection.

State is a small JSON file in the state directory; every transition is also a ledger event.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .. import frozen

REOPEN = {"alarm", "health_alarm", "human_request", "monthly_review", "drawdown_alarm", "sentinel_divergence"}


@dataclass
class ControllerState:
    state: str = "BOOTSTRAP"                       # BOOTSTRAP | GATED | MAINTENANCE | ADAPT
    in_flight: dict | None = None                  # the one challenger under test: {id, kind, started, ...}
    probation: dict | None = None                  # {promoted_at, old_params, weekly_diffs: []}
    backoff_days: float = 7.0
    next_reflection: str = "1970-01-01T00:00:00+00:00"
    rejections_in_row: int = 0
    history: list = field(default_factory=list)


class Controller:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.s = ControllerState(**json.loads(self.path.read_text())) if self.path.exists() else ControllerState()
        self.rules = frozen.gate_rules()["controller"]
        if self.s.state == "BOOTSTRAP" and not self.path.exists():
            self.s.backoff_days = self.rules["base_reflection_interval_days"]

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(self.s), indent=1, default=str))

    def _note(self, what: str):
        self.s.history = (self.s.history + [{"ts": datetime.now(timezone.utc).isoformat(), "event": what}])[-100:]

    def may_reflect(self, now: datetime, triggers: set[str]) -> tuple[bool, str]:
        if self.s.in_flight:
            return False, "a challenger is already in flight (one change at a time)"
        if self.s.probation:
            return False, "the last promotion is on probation"
        if not triggers:
            return False, "no evidence-gated trigger"
        if self.s.state == "MAINTENANCE":
            if triggers & REOPEN:
                self.s.state = "ADAPT"
                self._note(f"ADAPT on {sorted(triggers & REOPEN)}")
                return True, "maintenance reopened by " + ",".join(sorted(triggers & REOPEN))
            return False, "maintenance mode: playbook and params frozen until an alarm, a human request or the monthly review"
        if now < datetime.fromisoformat(self.s.next_reflection) and not (triggers & {"human_request"}):
            return False, f"backoff until {self.s.next_reflection}"
        return True, "triggers: " + ",".join(sorted(triggers))

    def start(self, challenger: dict):
        self.s.in_flight = {**challenger, "started": datetime.now(timezone.utc).isoformat()}
        self._note(f"in flight {challenger.get('id')}")

    def decided(self, now: datetime, accepted: bool):
        self.s.in_flight = None
        cap = self.rules["backoff_cap_days"]
        if accepted:
            self.s.rejections_in_row = 0
            self.s.backoff_days = self.rules["base_reflection_interval_days"]
        else:
            self.s.rejections_in_row += 1
            self.s.backoff_days = min(self.s.backoff_days * 2, cap)
        self.s.next_reflection = (now + timedelta(days=self.s.backoff_days)).isoformat()
        if self.s.state == "ADAPT" or (self.s.state in ("GATED", "BOOTSTRAP") and
                                       self.s.rejections_in_row >= self.rules["maintenance_after_rejections"]):
            self.s.state = "MAINTENANCE"
            self._note("MAINTENANCE")
        self._note("accepted" if accepted else "rejected")

    def start_probation(self, old_params: dict, info: dict):
        self.s.probation = {"promoted_at": datetime.now(timezone.utc).isoformat(), "old_params": old_params,
                            "weekly_diffs": [], **info}

    def end_probation(self, rolled_back: bool):
        self.s.probation = None
        self._note("rollback" if rolled_back else "probation passed")

    def on_alarm(self):
        self.s.backoff_days = self.rules["base_reflection_interval_days"]
        self.s.next_reflection = datetime.now(timezone.utc).isoformat()

    def set_state(self, state: str, why: str):
        """BOOTSTRAP -> GATED is a human decision (course 04 §8); exposed on the CLI."""
        self.s.state = state
        self._note(f"{state} ({why})")
