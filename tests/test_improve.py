"""Self-improvement guards: the agent cannot change the frozen layer, edits are deltas, one change in flight,
backoff and maintenance, probation rollback, and the frozen lock catches tampering."""
import copy
import shutil
from datetime import datetime, timedelta, timezone

import pytest
import yaml

from cryptoagent import frozen
from cryptoagent.improve import gatekeeper, stats
from cryptoagent.improve.controller import Controller
from cryptoagent.improve.playbook import Playbook
from cryptoagent.llm.schemas import Proposal

NOW = datetime(2026, 10, 29, tzinfo=timezone.utc)


def cfg():
    return gatekeeper.load_strategies()


def P(**kw):
    base = dict(hypothesis="h", evidence=["e1"], predicted_effect={"metric": "btc_multiple", "direction": "up", "size": "+3%"})
    base.update(kw)
    return Proposal(**base)


@pytest.mark.parametrize("target,value", [
    ("limits.max_drawdown_btc_pct", 0.9),
    ("policy.max_order_usd", 1e9),
    ("allowlists.tokens", "PEPE"),
    ("signer.allow_unlimited", True),
    ("gate_rules.min_full_multiple_gain", 0),
    ("sentinel.exit_weeks_below_50w", 1),
    ("cycle_guard.stable_stop_btc_pct", 0.9),      # evolvable, but outside the frozen bound (looser than policy)
    ("cycle_guard.not_a_param", 1),
    ("alt_gate.eth_weight", 0.5),                   # above the ALT cap
])
def test_agent_cannot_touch_frozen_or_exceed_bounds(target, value):
    v = gatekeeper.static_gate(P(op="PARAM_CHANGE", target=target, new_value=value), cfg())
    assert v, f"{target} should be rejected"


def test_frozen_change_request_changes_nothing():
    v = gatekeeper.static_gate(P(op="FROZEN_CHANGE_REQUEST", target="limits.max_order_usd", new_value=1e6), cfg())
    assert v and "human" in v[0]


def test_valid_param_proposal_passes_static():
    assert gatekeeper.static_gate(P(op="PARAM_CHANGE", target="cycle_guard.reclaim_weeks", new_value=3), cfg()) == []


def test_missing_hypothesis_rejected():
    assert gatekeeper.static_gate(Proposal(op="PARAM_CHANGE", target="cycle_guard.reclaim_weeks", new_value=3), cfg())


def test_frozen_lock_detects_tampering(tmp_path):
    root = tmp_path / "repo"
    shutil.copytree(frozen.ROOT, root, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", "state", "reports"))
    frozen.write_lock(root)
    assert frozen.verify_lock(root) == []
    lim = root / "frozen" / "limits.yaml"
    lim.write_text(lim.read_text().replace("max_order_usd: 3500", "max_order_usd: 3500000"))
    assert any("limits.yaml" in p for p in frozen.verify_lock(root))
    pe = root / "cryptoagent" / "policy" / "engine.py"
    pe.write_text(pe.read_text() + "\n# harmless-looking edit\n")
    assert any("engine.py" in p for p in frozen.verify_lock(root))


def test_repo_frozen_layer_is_locked_and_intact():
    assert frozen.verify_lock() == [], "run `cryptoagent frozen lock` after reviewing changes"


def test_playbook_delta_edits_dedup_cap_and_retire(tmp_path):
    p = tmp_path / "pb.yaml"
    shutil.copy(frozen.ROOT / "evolvable" / "playbook.yaml", p)
    pb = Playbook(p)
    v0, n0 = pb.version, len(pb.items())
    item = pb.add("lessons", "After a stop-out, wait for a fresh weekly close above the 50W SMA before exiting again.", ["stop"], ["pm1"])
    assert item["id"] == "L-001" and pb.version == v0 + 1
    with pytest.raises(ValueError):
        pb.add("lessons", "After a stop out, wait for a fresh weekly close above the 50W SMA before exiting again!", ["stop"], ["pm2"])
    with pytest.raises(ValueError):
        pb.add("lessons", "x" * 400, ["a"], ["pm3"])
    old = pb.modify("L-001", "After a stop-out, require a fresh weekly close above the 50W SMA before a new exit.")
    assert "wait for" in old
    pb.retire("L-001", "test")
    assert pb.get("L-001") is None and pb.data["archive"][-1]["id"] == "L-001"      # archived, never deleted
    assert len(pb.items()) == n0
    pb.restore("L-001", "lessons")
    assert pb.get("L-001")


def test_lesson_retrieval_skips_harmful(tmp_path):
    pb = Playbook(tmp_path / "x.yaml")
    a = pb.add("lessons", "lesson about exits and macro", ["exit"], ["p"])
    b = pb.add("lessons", "a different lesson on reentry timing", ["exit"], ["p"])
    for _ in range(4):
        pb.count(b["id"], helpful=False)
    got = [i["id"] for i in pb.retrieve_lessons({"exit"})]
    assert a["id"] in got and b["id"] not in got


def test_controller_one_in_flight_backoff_and_maintenance(tmp_path):
    c = Controller(tmp_path / "c.json")
    ok, _ = c.may_reflect(NOW, set())
    assert not ok                                          # nothing happened -> no reflection
    ok, _ = c.may_reflect(NOW, {"scheduled_review"})
    assert ok
    c.start({"id": "p1"})
    assert not c.may_reflect(NOW, {"scheduled_review"})[0]
    for i in range(3):
        c.s.in_flight = None
        c.decided(NOW, accepted=False)
    assert c.s.state == "MAINTENANCE" and c.s.backoff_days == 28
    assert not c.may_reflect(NOW + timedelta(days=60), {"scheduled_review"})[0]
    assert c.may_reflect(NOW + timedelta(days=60), {"alarm"})[0] and c.s.state == "ADAPT"


def test_probation_rollback_logic():
    assert gatekeeper.probation_check([0.0] * 12) == (False, "ok")
    rb, why = gatekeeper.probation_check([-0.01] * 6)
    assert rb
    rb, why = gatekeeper.probation_check([0.004, -0.002] * 6)
    assert not rb


def test_shadow_decisions():
    assert gatekeeper.shadow_decision(2, 1.0, 1.1) == "continue"
    assert gatekeeper.shadow_decision(4, 1.0, 1.0) == "promote"
    assert gatekeeper.shadow_decision(12, 1.0, 0.985).startswith("reject")


def test_shadow_without_divergence_is_not_evidence():
    # course rule 1: a challenger that never acted differently proved nothing -> no promotion at min_weeks
    assert gatekeeper.shadow_decision(4, 1.0, 1.0, diverged=False) == "continue"
    assert gatekeeper.shadow_decision(11, 1.0, 1.0, diverged=False) == "continue"
    assert gatekeeper.shadow_decision(12, 1.0, 1.0, diverged=False) == "promote:offline_evidence_only"


def test_probation_waits_for_real_divergence():
    p = gatekeeper.probation_progress([0.0] * 12)
    assert not p["done"] and p["dormant"] and p["divergent_weeks"] == 0
    p = gatekeeper.probation_progress([0.0] * 30 + [0.001] * 11)
    assert not p["done"] and p["dormant"]
    p = gatekeeper.probation_progress([0.0] * 30 + [0.001] * 12)
    assert p["done"] and p["divergent_weeks"] == 12


def test_dormant_probation_reopens_judgment_only(tmp_path):
    c = Controller(tmp_path / "c.json")
    c.start_probation({"x": 1}, {"old_name": "a", "new_name": "b", "since": "2026-01-04"})
    assert not c.may_reflect(NOW, {"scheduled_review"})[0]
    c.s.probation["dormant"] = True
    assert c.may_reflect(NOW, {"scheduled_review"})[0]


def test_loop_identical_challenger_promoted_late_and_rollback_stays_armed(tmp_path, ledger):
    """End to end through ImprovementLoop.weekly: a challenger identical to the champion is promoted only at
    max_weeks, flagged offline-only; its probation goes dormant instead of passing; parameter proposals are refused
    meanwhile; when the two finally diverge and the new one underperforms, the rollback still fires."""
    import math
    from cryptoagent.backtest.book import Book
    from cryptoagent.improve.loop import ImprovementLoop
    sp, pp = tmp_path / "strategies.yaml", tmp_path / "playbook.yaml"
    shutil.copy(frozen.ROOT / "evolvable" / "strategies.yaml", sp)
    shutil.copy(frozen.ROOT / "evolvable" / "playbook.yaml", pp)
    loop = ImprovementLoop(tmp_path / "st", ledger, router=None, strategies_path=sp, playbook_path=pp, commit=False)
    champ = gatekeeper.champion_params(loop.cfg())
    chall = copy.deepcopy(champ)
    chall["cycle_guard"]["max_days_in_stable"] = 240
    loop.shadows.books["rules_champion"] = Book(params=champ)
    loop.shadows.books["challenger"] = Book(params=chall)
    loop.shadows.meta["challenger_start"] = "2027-01-03"
    loop.ctrl.start({"id": "p1", "kind": "params", "params": chall, "weeks": 0,
                     "proposal": {"op": "PARAM_CHANGE", "target": "cycle_guard.max_days_in_stable", "new_value": 240}})
    day = datetime(2027, 1, 3, tzinfo=timezone.utc)

    def week(a, b):
        nonlocal day
        day += timedelta(days=7)
        for name, v in ((("rules_champion", a), ("challenger", b)) if "challenger" in loop.shadows.books
                        else (("rules_champion", a), ("old_champion", b))):
            loop.shadows.nav_hist.setdefault(name, []).append([str(day.date()), v])
        return loop.weekly(day)

    outs = [week(1.0, 1.0) for _ in range(12)]
    assert [o["shadow"] for o in outs[:11]] == ["continue"] * 11
    assert outs[11]["shadow"] == "promote:offline_evidence_only"
    promo = [e.payload for e in ledger.events(kind="gate_decision") if e.payload.get("result") == "promoted"]
    assert promo and promo[-1]["evidence"] == "offline_only_no_divergence_in_shadow"
    assert loop.ctrl.s.probation and "old_champion" in loop.shadows.books
    # 13 identical weeks of probation: dormant, not passed; the old champion stays in shadow
    for _ in range(13):
        out = week(1.0, 1.0)            # (new = rules_champion, old = old_champion)
    assert out["probation"]["dormant"] and not out["probation"]["done"]
    assert loop.ctrl.s.probation.get("dormant") and "old_champion" in loop.shadows.books
    assert loop.ctrl.may_reflect(day, {"scheduled_review"})[0]          # judgment changes may proceed
    prop = P(op="PARAM_CHANGE", target="cycle_guard.exit_weeks_below_50w", new_value=3)
    r = loop.propose_and_gate(day, None, None, {"scheduled_review"}, forced=prop)
    assert r["result"] == "reject:static" and "rollback watch" in r["detail"]["violations"][0]
    # the rare state arrives and the new champion falls behind the old one: rollback fires
    nav_new, nav_old = 1.0, 1.0
    for _ in range(8):
        nav_new *= math.exp(-0.01)
        out = week(nav_new, nav_old)
        if not loop.ctrl.s.probation:
            break
    assert out["probation"]["rollback"]
    assert ledger.events(kind="rollback")


def test_course_statistics_match_published_tables():
    assert round(stats.mcnemar_p(3, 11), 3) == 0.029
    assert round(stats.mcnemar_p(20, 23), 2) == 0.38
    assert stats.shadow_min_wins(10) == 9 and stats.shadow_min_wins(20) == 15
    s = 0.0
    for _ in range(5):
        s = stats.cusum_step(s, 0, 0.3, 0.15)
    assert round(s, 3) == 0.75


def test_deflated_sharpe_penalises_many_trials():
    import numpy as np
    r = np.random.default_rng(1).normal(0.002, 0.02, 520)
    one, many = stats.deflated_sharpe(r, 1), stats.deflated_sharpe(r, 1000)
    assert many["dsr"] < one["dsr"]


def test_boolean_params_parse_strictly():
    assert gatekeeper.as_bool("false") is False and gatekeeper.as_bool("True") is True and gatekeeper.as_bool(1) is True
    with pytest.raises(ValueError):
        gatekeeper.as_bool("maybe")
    champ = gatekeeper.champion_params(cfg())
    got = gatekeeper.apply_proposal_to_params(champ, P(op="PARAM_CHANGE", target="cycle_guard.ladder_after_exit", new_value="false"))
    assert got["cycle_guard"]["ladder_after_exit"] is False            # bool("false") would have been True
    assert "no change from the current value" in gatekeeper.static_gate(
        P(op="PARAM_CHANGE", target="cycle_guard.ladder_after_exit", new_value="false"), cfg())
    assert gatekeeper.static_gate(P(op="PARAM_CHANGE", target="cycle_guard.ladder_after_exit", new_value=True), cfg()) == []
    assert "not a boolean" in gatekeeper.static_gate(
        P(op="PARAM_CHANGE", target="cycle_guard.ladder_after_exit", new_value="sometimes"), cfg())[0]


def test_human_withdraw_cancels_shadow_without_counting_a_rejection(tmp_path, ledger):
    from cryptoagent.backtest.book import Book
    from cryptoagent.improve.loop import ImprovementLoop
    sp, pp = tmp_path / "strategies.yaml", tmp_path / "playbook.yaml"
    shutil.copy(frozen.ROOT / "evolvable" / "strategies.yaml", sp)
    shutil.copy(frozen.ROOT / "evolvable" / "playbook.yaml", pp)
    loop = ImprovementLoop(tmp_path / "st", ledger, router=None, strategies_path=sp, playbook_path=pp, commit=False)
    champ = gatekeeper.champion_params(loop.cfg())
    loop.shadows.books["challenger"] = Book(params=champ)
    loop.ctrl.start({"id": "p9", "kind": "params", "params": champ, "weeks": 3,
                     "proposal": {"op": "PARAM_CHANGE", "target": "cycle_guard.max_days_in_stable", "new_value": 240}})
    before = loop.ctrl.s.rejections_in_row
    assert loop.withdraw(NOW, "owner changed his mind")["result"] == "withdrawn_challenger"
    assert loop.ctrl.s.in_flight is None and "challenger" not in loop.shadows.books
    assert loop.ctrl.s.rejections_in_row == before
    assert [e.payload["result"] for e in ledger.events(kind="gate_decision")] == ["withdrawn_by_human"]
    assert loop.withdraw(NOW, "again")["result"] == "nothing_to_withdraw"
