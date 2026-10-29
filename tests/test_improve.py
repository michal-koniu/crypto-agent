"""Self-improvement guards: the agent cannot change the frozen layer, edits are deltas, one change in flight,
backoff and maintenance, probation rollback, and the frozen lock catches tampering."""
import copy
import shutil
from datetime import datetime, timedelta, timezone

import pytest
import yaml

from btcagent import frozen
from btcagent.improve import gatekeeper, stats
from btcagent.improve.controller import Controller
from btcagent.improve.playbook import Playbook
from btcagent.llm.schemas import Proposal

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
    pe = root / "btcagent" / "policy" / "engine.py"
    pe.write_text(pe.read_text() + "\n# harmless-looking edit\n")
    assert any("engine.py" in p for p in frozen.verify_lock(root))


def test_repo_frozen_layer_is_locked_and_intact():
    assert frozen.verify_lock() == [], "run `btcagent frozen lock` after reviewing changes"


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
