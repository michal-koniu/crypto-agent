"""The gatekeeper (FROZEN, pure code): decides whether a typed proposal may change the agent.

Course mapping (03 §6 gate cascade): static -> must-pass -> paired evaluation on frozen data -> online shadow ->
probation with automatic rollback. The LLM never judges its own proposal; only these functions and frozen/gate_rules
thresholds do. The only files it writes are evolvable/strategies.yaml and evolvable/playbook.yaml, and every write
is a new version with its inverse recorded in the ledger.
"""
from __future__ import annotations

import copy
import math
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import yaml

from .. import frozen
from ..backtest import engine, metrics
from ..ledger.store import Ledger
from ..llm.schemas import Proposal
from . import stats

ROOT = frozen.ROOT
STRATEGIES = ROOT / "evolvable" / "strategies.yaml"
PARAM_GROUPS = ("cycle_guard", "alt_gate", "yield")


# ------------------------------------------------------------------ helpers
def load_strategies(path: Path = STRATEGIES) -> dict:
    return yaml.safe_load(Path(path).read_text())


def champion_params(cfg: dict) -> dict:
    p = copy.deepcopy(cfg["strategies"][cfg["champion"]])
    p["expected_edge_bps"] = cfg.get("expected_edge_bps", 300)
    return p


def as_bool(x) -> bool:
    """Strict boolean parsing: model output may carry "false" as a string, and bool("false") is True."""
    if isinstance(x, bool):
        return x
    if isinstance(x, (int, float)) and x in (0, 1):
        return bool(x)
    if isinstance(x, str) and x.strip().lower() in ("true", "false", "1", "0", "yes", "no", "on", "off"):
        return x.strip().lower() in ("true", "1", "yes", "on")
    raise ValueError(f"not a boolean: {x!r}")


def apply_proposal_to_params(params: dict, prop: Proposal) -> dict:
    p = copy.deepcopy(params)
    if prop.op == "PARAM_CHANGE":
        group, key = prop.target.split(".", 1)
        p[group][key] = type(p[group][key])(prop.new_value) if not isinstance(p[group][key], bool) else as_bool(prop.new_value)
    elif prop.op == "DISABLE_ALT_GATE":
        p["alt_gate"]["enabled"] = False
    elif prop.op == "ENABLE_ALT_GATE":
        p["alt_gate"]["enabled"] = True
    return p


def rejected_recently(ledger: Ledger, prop: Proposal, days: int) -> bool:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    for e in ledger.events(kind="gate_decision", since=since):
        p = e.payload
        if p.get("result", "").startswith("reject") and p.get("op") == prop.op and p.get("target") == prop.target \
                and str(p.get("new_value")) == str(prop.new_value):
            return True
    return False


# ------------------------------------------------------------------ gate 1: static
def static_gate(prop: Proposal, cfg: dict, ledger: Ledger | None = None) -> list[str]:
    rules = frozen.gate_rules()["static"]
    bounds = frozen.param_bounds()
    v: list[str] = []
    if prop.op == "NONE":
        return ["no proposal"]
    if prop.op in rules["human_only_ops"]:
        return ["frozen-layer change requests go to the human digest; nothing is changed"]
    if prop.op not in rules["allowed_ops"]:
        return [f"op {prop.op} not allowed"]
    for f in rules["require"]:
        if not getattr(prop, f):
            v.append(f"missing {f}")
    if prop.op == "PARAM_CHANGE":
        if "." not in prop.target:
            return v + ["target must be group.param"]
        group, key = prop.target.split(".", 1)
        if group not in PARAM_GROUPS:
            v.append(f"{group} is not an evolvable parameter group (frozen or unknown)")
        elif key not in bounds.get(group, {}):
            v.append(f"{prop.target} has no bounds in frozen/param_bounds.yaml (not evolvable)")
        else:
            lo, hi = bounds[group][key]
            is_bool = isinstance(lo, bool)
            try:
                val = float(prop.new_value) if not is_bool else as_bool(prop.new_value)
            except (TypeError, ValueError):
                return v + [f"value {prop.new_value!r} is not a {'boolean' if is_bool else 'number'}"]
            if not is_bool and not (lo <= val <= hi):
                v.append(f"{prop.target}={val} outside bounds [{lo}, {hi}]")
            cur = cfg["strategies"][cfg["champion"]][group].get(key)
            if cur is None:
                v.append(f"{prop.target} is not a parameter of the champion")
            elif (as_bool(cur) == val) if is_bool else math.isclose(float(cur), float(val)):
                v.append("no change from the current value")
    if prop.op.startswith("PLAYBOOK") and not prop.target and prop.op != "PLAYBOOK_ADD":
        v.append("playbook MODIFY/RETIRE need an item id")
    lowered = (prop.target + " " + str(prop.new_value)).lower()
    for word in ("limits", "allowlist", "signer", "policy", "frozen", "gate_rules", "param_bounds", "sentinel", "constitution"):
        if word in lowered:
            v.append(f"proposal touches the frozen layer ({word})")
    if ledger and rejected_recently(ledger, prop, rules["rejected_idea_cooldown_days"]):
        v.append("same idea was rejected within the cooldown")
    return v


# ------------------------------------------------------------------ gates 2-3: must-pass windows and full backtest
def backtest_gate(champ: dict, chall: dict, feat, daily, n_trials: int) -> dict:
    gr = frozen.gate_rules()
    out: dict = {"must_pass": {}, "passed": False, "reasons": []}
    for w in gr["must_pass"]["windows"]:
        try:
            a = metrics.btc_multiple(engine.run(feat, daily, champ, start=w["start"], end=w["end"]).nav["nav_btc"])
            b = metrics.btc_multiple(engine.run(feat, daily, chall, start=w["start"], end=w["end"]).nav["nav_btc"])
        except (IndexError, KeyError):
            continue
        ok = b >= a * (1 - gr["must_pass"]["max_rel_loss"])
        out["must_pass"][w["name"]] = {"champion": round(a, 4), "challenger": round(b, 4), "ok": ok}
        if not ok:
            out["reasons"].append(f"must-pass window {w['name']}: {b:.3f} vs champion {a:.3f}")
    rc = engine.run(feat, daily, champ)
    rx = engine.run(feat, daily, chall)
    ma, mb = metrics.btc_multiple(rc.nav["nav_btc"]), metrics.btc_multiple(rx.nav["nav_btc"])
    ca, cb = metrics.per_cycle(rc.nav), metrics.per_cycle(rx.nav)
    bt = gr["backtest"]
    worse = [c for c in ca if cb.get(c, 0) < ca[c] * (1 - bt["cycle_worse_tolerance"])]
    wa = np.log(rc.nav["nav_btc"].resample("W-SUN").last()).diff().dropna()
    wb = np.log(rx.nav["nav_btc"].resample("W-SUN").last()).diff().dropna()
    diff = (wb - wa).dropna().values
    boot_p = stats.block_bootstrap_p(diff)
    out.update(champion_multiple=round(ma, 4), challenger_multiple=round(mb, 4), champion_cycles=ca, challenger_cycles=cb,
               cycles_worse=worse, bootstrap_p=round(boot_p, 4), sign_test_cycles=stats.sign_test([math.log(cb[c] / ca[c]) for c in ca if c in cb]),
               deflated_sharpe=stats.deflated_sharpe(wb.values, n_trials=n_trials),
               challenger_summary=metrics.summarize(rx.nav, rx.trades))
    if mb / ma - 1 < bt["min_full_multiple_gain"]:
        out["reasons"].append(f"full-history gain {mb / ma - 1:+.2%} below required {bt['min_full_multiple_gain']:.0%}")
    if len(worse) > bt["max_cycles_worse"]:
        out["reasons"].append(f"worse than the champion in {len(worse)} cycles: {worse}")
    if boot_p > bt["max_bootstrap_p"]:
        out["reasons"].append(f"bootstrap p {boot_p:.2f} > {bt['max_bootstrap_p']}")
    out["passed"] = not out["reasons"]
    return out


# ------------------------------------------------------------------ gate 4: shadow
def shadow_decision(weeks: int, champ_nav: float, chall_nav: float, diverged: bool = True) -> str:
    """diverged: the challenger's virtual NAV has differed from the champion's at some week of the shadow. A challenger
    that never acted differently is not evidence of anything: it runs to max_weeks, then is promoted on the offline
    evidence alone ("promote:offline_evidence_only"), with its probation waiting for real divergence."""
    s = frozen.gate_rules()["shadow"]
    if weeks < s["min_weeks"]:
        return "continue"
    if not diverged:
        return "promote:offline_evidence_only" if weeks >= s["max_weeks"] else "continue"
    if chall_nav >= champ_nav * (1 - s["non_inferiority"]):
        return "promote"
    if weeks >= s["max_weeks"]:
        return "reject:shadow_inconclusive_keep_champion"
    return "reject:shadow_inferior" if chall_nav < champ_nav * (1 - 2 * s["non_inferiority"]) else "continue"


def judgment_shadow_decision(brier_champ: list[float], brier_chall: list[float]) -> str:
    s = frozen.gate_rules()["shadow"]
    n = min(len(brier_champ), len(brier_chall))
    if n < s["judgment_min_scored_forecasts"]:
        return "continue"
    a, b = np.mean(brier_champ[:n]), np.mean(brier_chall[:n])
    wins = sum(1 for x, y in zip(brier_champ[:n], brier_chall[:n]) if y < x)
    return "promote" if b <= a and wins >= n / 2 else "reject:judgment_not_better"


# ------------------------------------------------------------------ gate 5: probation
def probation_check(weekly_log_diffs: list[float]) -> tuple[bool, str]:
    """weekly_log_diffs: log(NAV_new_week / NAV_new_prev) - log(NAV_old_week / NAV_old_prev) since promotion."""
    pr = frozen.gate_rules()["probation"]
    ph = stats.PageHinkley(pr["page_hinkley"]["delta"], pr["page_hinkley"]["lambda"])
    for x in weekly_log_diffs:
        if ph.update(x):
            return True, "page_hinkley_alarm"
    cum = sum(weekly_log_diffs)
    if cum < math.log(1 - pr["max_underperformance"]):
        return True, f"cumulative underperformance {math.exp(cum) - 1:.2%}"
    return False, "ok"


def probation_progress(weekly_log_diffs: list[float]) -> dict:
    """done: probation can end; dormant: enough calendar weeks have passed but the new and old champions have not yet
    differed for long enough - the rollback watch stays armed, only playbook/judgment changes may proceed."""
    rules = frozen.gate_rules()
    pr, eps = rules["probation"], rules["shadow"]["divergence_epsilon"]
    div = sum(1 for x in weekly_log_diffs if abs(x) > eps)
    done = (div if pr.get("require_divergent_weeks") else len(weekly_log_diffs)) >= pr["weeks"]
    return {"weeks": len(weekly_log_diffs), "divergent_weeks": div, "done": done,
            "dormant": not done and len(weekly_log_diffs) >= pr["weeks"]}


# ------------------------------------------------------------------ versioned writes (the only writes it makes)
def write_strategies(cfg: dict, ledger: Ledger, reason: str, path: Path = STRATEGIES, commit: bool = True) -> int:
    old = Path(path).read_text()
    cfg = copy.deepcopy(cfg)
    cfg["version"] = int(cfg.get("version", 0)) + 1
    new = yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True, width=120)
    Path(path).write_text(new)
    ledger.append("change", {"file": "evolvable/strategies.yaml", "version": cfg["version"], "reason": reason,
                             "inverse": old, "new": new})
    if commit:
        git_commit(path, f"strategies v{cfg['version']}: {reason}")
    return cfg["version"]


def git_commit(path: Path, message: str) -> None:
    """Local commit only; pushing is a human decision."""
    try:
        subprocess.run(["git", "-C", str(ROOT), "add", str(path)], check=True, capture_output=True, timeout=30)
        subprocess.run(["git", "-C", str(ROOT), "commit", "-m", f"[agent] {message}"], capture_output=True, timeout=30)
    except Exception:
        pass
