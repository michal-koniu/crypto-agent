"""The self-improvement loop: post-mortems -> lessons, reflection -> one typed proposal -> gates -> shadow ->
promotion -> probation -> automatic rollback. Course components and where they live:

  Worker            agent/core.py decision cycle (analyst)          Harness   ledger + snapshots + metrics
  Monitor           ShadowBooks (sentinel, rules-only, HODL), Page-Hinkley in probation, drawdown alarms
  Reflector         reflect() (LLM, fresh context, <= 1 proposal, majority of k samples)
  Gatekeeper        improve/gatekeeper.py (frozen code)             Controller improve/controller.py
  Playbook          improve/playbook.py (itemised, delta edits)     Bandit    not used (deviation D1)
  Sentinel          frozen/sentinel.yaml, run in ShadowBooks        Prediction log  ledger 'proposal'/'gate_decision'
"""
from __future__ import annotations

import copy
import json
import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .. import frozen
from ..backtest import metrics
from ..backtest.book import Book
from ..ledger.store import Ledger
from ..llm import prompts, schemas
from ..llm.router import LLMError, Router
from . import gatekeeper
from .controller import Controller
from .playbook import Playbook


# ======================================================================== shadow books
class ShadowBooks:
    """Virtual portfolios marked on the same prices as the real one: rules-only champion, sentinel, HODL, and
    (when present) the challenger in shadow or the old champion during probation."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        raw = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.books: dict[str, Book] = {k: Book.from_dict(v) for k, v in raw.get("books", {}).items()}
        self.nav_hist: dict[str, list] = raw.get("nav_hist", {})
        self.meta: dict = raw.get("meta", {})

    def ensure(self, name: str, params: dict):
        if name not in self.books:
            self.books[name] = Book(params=copy.deepcopy(params))

    def drop(self, name: str):
        self.books.pop(name, None)
        self.nav_hist.pop(name, None)

    def on_day(self, day, px, eb, tbill):
        for b in self.books.values():
            b.on_day(day, px, eb, tbill)

    def on_week(self, day, row: dict):
        for name, b in self.books.items():
            b.on_week(day, row)
            self.nav_hist.setdefault(name, []).append([str(day), b.nav(row["btc"], row.get("eth_btc"))])
            self.nav_hist[name] = self.nav_hist[name][-400:]

    def nav(self, name: str) -> float | None:
        h = self.nav_hist.get(name)
        return h[-1][1] if h else None

    def weekly_log_diffs(self, a: str, b: str, since: str) -> list[float]:
        ha = {d: v for d, v in self.nav_hist.get(a, []) if d >= since}
        hb = {d: v for d, v in self.nav_hist.get(b, []) if d >= since}
        days = sorted(set(ha) & set(hb))
        out = []
        for d0, d1 in zip(days, days[1:]):
            out.append(math.log(ha[d1] / ha[d0]) - math.log(hb[d1] / hb[d0]))
        return out

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"books": {k: v.to_dict() for k, v in self.books.items()},
                                         "nav_hist": self.nav_hist, "meta": self.meta}, default=str))


# ======================================================================== post-mortems
def postmortem(trip: dict, context: dict, router: Router, ledger: Ledger, playbook: Playbook) -> dict:
    """trip: a closed round trip that lost BTC. context: code-computed facts (rule states at open, price path,
    costs, analyst conviction, ledger ids). Returns the triage record; may add one lesson to the playbook."""
    user = json.dumps({"round_trip": trip, "facts": context}, default=str)
    try:
        r = router.call("triage", prompts.TRIAGE_SYSTEM, user, schemas.Triage, context_id=trip.get("id"))
        t = r.data
        lesson = t.lesson if t.lesson and t.lesson.strip().lower() not in ("none", "null", "n/a", "-") else None
        rec = {"trip": trip, "failure_class": t.failure_class.value, "confidence": t.confidence, "model": r.model_ref,
               "served_model": r.served_model, "evidence_refs": t.evidence_refs, "lesson": lesson, "lesson_tags": t.lesson_tags}
    except LLMError as e:
        rec = {"trip": trip, "failure_class": "unclassified", "error": str(e)[:300]}
    ev = ledger.append("postmortem", rec)
    rec["postmortem_id"] = ev.id
    if rec.get("lesson") and rec["failure_class"] not in ("noise", "exogenous_shock", "unclassified") and rec.get("confidence", 0) >= 0.5:
        problems = playbook.check_add("lessons", rec["lesson"])
        if problems:
            ledger.append("lesson_rejected", {"postmortem_id": ev.id, "lesson": rec["lesson"], "why": problems})
        else:
            item = playbook.add("lessons", rec["lesson"], tags=rec["lesson_tags"] or [rec["failure_class"]],
                                provenance=[ev.id] + rec.get("evidence_refs", [])[:5])
            playbook.save()
            ledger.append("lesson_added", {"postmortem_id": ev.id, "item": item, "playbook_version": playbook.version})
            rec["lesson_id"] = item["id"]
    return rec


def losing_trips(book_trades: list[dict]) -> list[dict]:
    trips = metrics.round_trips([{**t, "date": t["date"]} for t in book_trades])
    return [{**t, "id": f"{t['leg']}:{t['open']}->{t['close']}"} for t in trips if t["gain_btc_pct"] < 0]


# ======================================================================== reflection
def reflection_digest(ledger: Ledger, shadows: ShadowBooks, cfg: dict, controller: Controller, live_nav_btc: list | None) -> dict:
    since = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
    pms = [e.payload for e in ledger.events(kind="postmortem", since=since)]
    gates = [e.payload for e in ledger.events(kind="gate_decision")][-10:]
    fc = [e.payload for e in ledger.events(kind="forecast_score")][-60:]
    brier = round(sum(f["brier"] for f in fc) / len(fc), 4) if fc else None
    return {
        "champion": cfg["champion"], "params": cfg["strategies"][cfg["champion"]],
        "param_bounds": frozen.param_bounds(),
        "shadow_navs_btc": {k: shadows.nav(k) for k in shadows.books},
        "live_nav_btc_recent": live_nav_btc[-12:] if live_nav_btc else None,
        "postmortem_classes": dict(Counter(p.get("failure_class") for p in pms)),
        "postmortems_recent": [{k: p.get(k) for k in ("failure_class", "confidence", "lesson")} | {"trip": p.get("trip")} for p in pms[-8:]],
        "forecast_brier_mean": brier, "forecasts_scored": len(fc),
        "prediction_log": [{k: g.get(k) for k in ("op", "target", "new_value", "result", "predicted_effect", "measured")} for g in gates],
        "rejected_ideas": [{k: g.get(k) for k in ("op", "target", "new_value")} for g in gates if str(g.get("result", "")).startswith("reject")],
        "controller_state": controller.s.state,
    }


def reflect(router: Router, digest: dict, ledger: Ledger) -> schemas.Proposal | None:
    """k independent samples; proceed only on a proposal the majority shares (course 03 §11)."""
    k = router.cfg["roles"]["reflector"].get("samples", 3)
    props = []
    for i in range(k):
        try:
            r = router.call("reflector", prompts.REFLECTOR_SYSTEM, json.dumps(digest, default=str), schemas.Proposal,
                            context_id=f"reflection-{i}")
            props.append(r.data)
        except LLMError:
            continue
    keys = Counter((p.op, p.target, str(p.new_value)) for p in props)
    ledger.append("reflection", {"samples": [p.model_dump() for p in props], "votes": {str(k_): v for k_, v in keys.items()}})
    if not keys:
        return None
    (op, target, val), n = keys.most_common(1)[0]
    if n <= len(props) / 2 or op == "NONE":
        return None
    return next(p for p in props if (p.op, p.target, str(p.new_value)) == (op, target, val))


# ======================================================================== the loop
class ImprovementLoop:
    def __init__(self, state_dir: str | Path, ledger: Ledger, router: Router, strategies_path: Path, playbook_path: Path,
                 commit: bool = True):
        self.state = Path(state_dir)
        self.ledger, self.router = ledger, router
        self.sp, self.pp = Path(strategies_path), Path(playbook_path)
        self.ctrl = Controller(self.state / "controller.json")
        self.shadows = ShadowBooks(self.state / "shadow.json")
        self.commit = commit

    def cfg(self) -> dict:
        return gatekeeper.load_strategies(self.sp)

    def setup_shadows(self):
        self.shadows.ensure("rules_champion", gatekeeper.champion_params(self.cfg()))
        self.shadows.ensure("sentinel", frozen.sentinel()["params"])
        hodl = copy.deepcopy(frozen.sentinel()["params"])
        hodl["cycle_guard"]["exit_weeks_below_50w"] = 10**6     # never exits
        hodl["cycle_guard"]["trim_fraction"] = 0.0
        self.shadows.ensure("hodl", hodl)

    def triggers(self, now: datetime, scheduled: bool, human: bool = False) -> set[str]:
        t = set()
        if scheduled:
            t.add("scheduled_review")
        if human:
            t.add("human_request")
        since = (now - timedelta(days=60)).isoformat()
        cls = Counter(e.payload.get("failure_class") for e in self.ledger.events(kind="postmortem", since=since))
        for c, n in cls.items():
            if c not in ("noise", "exogenous_shock", "unclassified", None) and n >= frozen.gate_rules()["controller"]["min_trigger_cluster"]:
                t.add(f"cluster:{c}")
        a, s = self.shadows.nav("rules_champion"), self.shadows.nav("sentinel")
        if a and s and a < s * 0.97:
            t.add("sentinel_divergence")
        return t

    def propose_and_gate(self, now: datetime, feat, daily, triggers: set[str], live_nav: list | None = None,
                         forced: schemas.Proposal | None = None) -> dict:
        ok, why = self.ctrl.may_reflect(now, triggers)
        if not ok and not forced:
            self.ledger.append("reflection_skipped", {"why": why, "triggers": sorted(triggers)})
            return {"result": "skipped", "why": why}
        cfg = self.cfg()
        prop = forced or reflect(self.router, reflection_digest(self.ledger, self.shadows, cfg, self.ctrl, live_nav), self.ledger)
        if prop is None:
            self.ledger.append("gate_decision", {"op": "NONE", "result": "no_proposal", "triggers": sorted(triggers)})
            self.ctrl.decided(now, accepted=False)
            self.ctrl.save()
            return {"result": "no_proposal"}
        pe = self.ledger.append("proposal", {**prop.model_dump(), "triggers": sorted(triggers)})
        v = gatekeeper.static_gate(prop, cfg, self.ledger)
        if v:
            return self._reject(now, prop, "reject:static", {"violations": v})
        if prop.op in ("PLAYBOOK_ADD", "PLAYBOOK_MODIFY", "PLAYBOOK_RETIRE"):
            return self._playbook_change(now, prop, pe.id)
        if self.ctrl.s.probation:
            return self._reject(now, prop, "reject:static", {"violations": [
                "strategy changes are blocked while the last promotion's rollback watch is armed (dormant probation)"]})
        champ = gatekeeper.champion_params(cfg)
        chall = gatekeeper.apply_proposal_to_params(champ, prop)
        n_trials = len(self.ledger.events(kind="gate_decision")) + 10      # + the 10 pre-registered variants
        bt = gatekeeper.backtest_gate(champ, chall, feat, daily, n_trials)
        if not bt["passed"]:
            return self._reject(now, prop, "reject:backtest", bt)
        self.ctrl.start({"id": pe.id, "kind": "params", "proposal": prop.model_dump(), "params": chall, "weeks": 0,
                         "backtest": {k: bt[k] for k in ("champion_multiple", "challenger_multiple", "bootstrap_p")}})
        self.shadows.drop("challenger")
        self.shadows.books["challenger"] = Book(params=chall)
        rc = self.shadows.books["rules_champion"]
        self.shadows.books["challenger"].btc, self.shadows.books["challenger"].usd = rc.btc, rc.usd   # same starting point
        self.shadows.books["challenger"].eth, self.shadows.books["challenger"].st = rc.eth, copy.deepcopy(rc.st)
        self.shadows.meta["challenger_start"] = str(now.date())
        self.ledger.append("gate_decision", {"proposal_id": pe.id, "op": prop.op, "target": prop.target, "new_value": prop.new_value,
                                             "result": "shadow_started", "backtest": bt, "predicted_effect": prop.predicted_effect})
        self.ctrl.save()
        self.shadows.save()
        return {"result": "shadow_started", "backtest": bt}

    def _reject(self, now, prop, result, detail) -> dict:
        self.ledger.append("gate_decision", {"op": prop.op, "target": prop.target, "new_value": prop.new_value,
                                             "result": result, "detail": detail, "predicted_effect": prop.predicted_effect})
        self.ctrl.decided(now, accepted=False)
        self.ctrl.save()
        return {"result": result, "detail": detail}

    def _playbook_change(self, now, prop, proposal_id) -> dict:
        pb = Playbook(self.pp)
        try:
            if prop.op == "PLAYBOOK_ADD":
                item = pb.add("judgment", str(prop.new_value), tags=["reflection"], provenance=[proposal_id] + prop.evidence[:5])
                inverse = {"op": "PLAYBOOK_RETIRE", "target": item["id"]}
            elif prop.op == "PLAYBOOK_MODIFY":
                old = pb.modify(prop.target, str(prop.new_value))
                inverse = {"op": "PLAYBOOK_MODIFY", "target": prop.target, "new_value": old}
            else:
                pb.retire(prop.target, prop.hypothesis[:200])
                inverse = {"op": "PLAYBOOK_RESTORE", "target": prop.target}
        except (ValueError, KeyError) as e:
            return self._reject(now, prop, "reject:static", {"violations": [str(e)]})
        pb.save()
        self.ledger.append("change", {"file": "evolvable/playbook.yaml", "version": pb.version, "proposal_id": proposal_id,
                                      "op": prop.op, "target": prop.target, "inverse": inverse})
        if self.commit:
            gatekeeper.git_commit(self.pp, f"playbook v{pb.version}: {prop.op} {prop.target}")
        self.ledger.append("gate_decision", {"proposal_id": proposal_id, "op": prop.op, "target": prop.target,
                                             "result": "accepted:playbook", "predicted_effect": prop.predicted_effect})
        self.ctrl.decided(now, accepted=True)
        self.ctrl.save()
        return {"result": "accepted:playbook", "inverse": inverse}

    def weekly(self, now: datetime) -> dict:
        """Called after the shadow books took their weekly step: advance shadow tests and probation."""
        out: dict = {}
        fl = self.ctrl.s.in_flight
        if fl and fl.get("kind") == "params":
            fl["weeks"] = fl.get("weeks", 0) + 1
            diverged = self.diverged("rules_champion", "challenger", self.shadows.meta.get("challenger_start", ""))
            d = gatekeeper.shadow_decision(fl["weeks"], self.shadows.nav("rules_champion") or 1, self.shadows.nav("challenger") or 1,
                                           diverged=diverged)
            out["shadow"] = d
            if d.startswith("promote"):
                cfg = self.cfg()
                old = copy.deepcopy(cfg["strategies"][cfg["champion"]])
                new_name = f"{cfg['champion'].rsplit('_v', 1)[0]}_v{int(cfg.get('version', 1)) + 1}"
                new_params = {k: v for k, v in fl["params"].items() if k != "expected_edge_bps"}
                new_params["description"] = f"promoted from {cfg['champion']}: {fl['proposal']['op']} {fl['proposal']['target']}={fl['proposal']['new_value']}"
                cfg["archive"] = cfg.get("archive") or {}
                cfg["archive"][cfg["champion"]] = {"replaced": str(now.date()), "params": old}
                cfg["strategies"] = {new_name: new_params}
                prev_name, cfg["champion"] = cfg["champion"], new_name
                ver = gatekeeper.write_strategies(cfg, self.ledger, f"promote {new_name}", self.sp, commit=self.commit)
                # the old champion keeps running in shadow for probation; the challenger becomes the rules champion
                self.shadows.books["old_champion"] = self.shadows.books.pop("rules_champion")
                self.shadows.nav_hist["old_champion"] = self.shadows.nav_hist.pop("rules_champion", [])
                self.shadows.books["rules_champion"] = self.shadows.books.pop("challenger")
                self.shadows.nav_hist["rules_champion"] = self.shadows.nav_hist.pop("challenger", [])
                self.ctrl.start_probation(old, {"old_name": prev_name, "new_name": new_name, "since": str(now.date())})
                self.ctrl.decided(now, accepted=True)
                self.ledger.append("gate_decision", {"proposal_id": fl["id"], "op": fl["proposal"]["op"], "target": fl["proposal"]["target"],
                                                     "new_value": fl["proposal"]["new_value"], "result": "promoted", "version": ver,
                                                     "evidence": "full" if d == "promote" else "offline_only_no_divergence_in_shadow"})
            elif d.startswith("reject"):
                self.shadows.drop("challenger")
                self.ledger.append("gate_decision", {"proposal_id": fl["id"], "op": fl["proposal"]["op"], "target": fl["proposal"]["target"],
                                                     "new_value": fl["proposal"]["new_value"], "result": d})
                self.ctrl.decided(now, accepted=False)
        pr = self.ctrl.s.probation
        if pr:
            diffs = self.shadows.weekly_log_diffs("rules_champion", "old_champion", pr["since"])
            pr["weekly_diffs"] = diffs
            rollback, why = gatekeeper.probation_check(diffs)
            prog = gatekeeper.probation_progress(diffs)
            out["probation"] = {**prog, "rollback": rollback, "why": why}
            if rollback:
                self.rollback(now, why)
            elif prog["done"]:
                self.shadows.drop("old_champion")
                self.ctrl.end_probation(rolled_back=False)
                self.ledger.append("probation", {"result": "passed", "weeks": prog["weeks"], "divergent_weeks": prog["divergent_weeks"]})
            elif prog["dormant"] and not pr.get("dormant"):
                pr["dormant"] = True
                self.ledger.append("probation", {"result": "dormant", "weeks": prog["weeks"], "divergent_weeks": prog["divergent_weeks"],
                                                 "note": "rollback watch stays armed; only playbook/judgment changes may proceed"})
        self.ctrl.save()
        self.shadows.save()
        return out

    def withdraw(self, now: datetime, why: str) -> dict:
        """Human only (CLI): cancel the challenger in shadow, or undo a promotion still on probation (via the normal
        rollback). Not counted as a rejection: no backoff, no step towards MAINTENANCE."""
        fl = self.ctrl.s.in_flight
        if fl:
            self.shadows.drop("challenger")
            p = fl.get("proposal", {})
            self.ledger.append("gate_decision", {"proposal_id": fl.get("id"), "op": p.get("op"), "target": p.get("target"),
                                                 "new_value": p.get("new_value"), "result": "withdrawn_by_human", "why": why})
            self.ctrl.s.in_flight = None
            self.ctrl._note(f"withdrawn by human: {why}")
            out = {"result": "withdrawn_challenger", "target": p.get("target")}
        elif self.ctrl.s.probation:
            self.rollback(now, f"withdrawn by human: {why}")
            out = {"result": "rolled_back_promotion"}
        else:
            out = {"result": "nothing_to_withdraw"}
        self.ctrl.save()
        self.shadows.save()
        return out

    def diverged(self, a: str, b: str, since: str) -> bool:
        """True if books a and b had different virtual NAVs at some common week since `since`."""
        eps = frozen.gate_rules()["shadow"]["divergence_epsilon"]
        ha = {d: v for d, v in self.shadows.nav_hist.get(a, []) if d >= since}
        return any(d in ha and ha[d] > 0 and v > 0 and abs(math.log(v / ha[d])) > eps
                   for d, v in self.shadows.nav_hist.get(b, []) if d >= since)

    def rollback(self, now: datetime, why: str):
        cfg = self.cfg()
        pr = self.ctrl.s.probation
        bad = cfg["champion"]
        cfg["archive"] = cfg.get("archive") or {}
        cfg["archive"][bad] = {"rolled_back": str(now.date()), "why": why, "params": cfg["strategies"][bad]}
        cfg["strategies"] = {pr["old_name"]: pr["old_params"]}
        cfg["champion"] = pr["old_name"]
        ver = gatekeeper.write_strategies(cfg, self.ledger, f"ROLLBACK {bad} -> {pr['old_name']}: {why}", self.sp, commit=self.commit)
        self.shadows.drop("rules_champion")
        self.shadows.books["rules_champion"] = self.shadows.books.pop("old_champion")
        self.shadows.nav_hist["rules_champion"] = self.shadows.nav_hist.pop("old_champion", [])
        self.ctrl.end_probation(rolled_back=True)
        self.ctrl.on_alarm()
        self.ledger.append("rollback", {"from": bad, "to": pr["old_name"], "why": why, "version": ver})
        self.ledger.append("gate_decision", {"op": "ROLLBACK", "target": bad, "result": "rolled_back", "why": why})
