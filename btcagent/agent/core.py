"""The agent: decision cycle, risk tick, kill procedure, daily/weekly upkeep.

Decision cycle (daily; the rule step itself is weekly):
  1 integrity    frozen layer intact? killed/halted?
  2 data         refresh the panel when stale; point-in-time weekly features
  3 rules        champion strategy target (weekly step on the first cycle after Sunday's close)
  4 news         untrusted feeds -> tool-less reader -> typed digest (no raw text reaches the analyst)
  5 analyst      k samples -> median conviction; critic (different model) can only lower it
  6 plan         final weights = rule deviations x conviction; orders only when the change is material
  7 policy       every intent through the frozen policy engine (and, on-chain, the signer's own checks)
  8 execute      paper / fork / live executor; fills logged with every tax field
  9 log          one `decision` event with inputs, outputs, models, versions - also when nothing is done
Risk tick (every minute, no LLM): stops in BTC terms, daily-loss halt, drawdown kill, stale/divergent data.
"""
from __future__ import annotations

import copy
import json
import statistics
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yaml

from .. import faults, frozen
from ..alerts import Alerts
from ..data import features, history, news
from ..improve import gatekeeper
from ..improve.loop import ImprovementLoop, losing_trips, postmortem
from ..improve.playbook import Playbook
from ..ledger.store import Ledger
from ..llm import prompts, schemas
from ..llm.router import LLMError, Router
from ..policy.engine import PolicyContext, check, risk_state
from ..risk import killswitch
from ..strategies.rules import StrategyState, advance_state, target
from ..types import LendIntent, Portfolio, Prices, StopRule, TradeIntent

ROOT = frozen.ROOT


def expand(p: str) -> Path:
    return Path(p).expanduser() if Path(p).expanduser().is_absolute() else ROOT / p


class Agent:
    def __init__(self, cfg_path: str | Path = ROOT / "config" / "agent.yaml", overrides: dict | None = None,
                 market=None, executor=None, clock=None):
        self.cfg = yaml.safe_load(Path(cfg_path).read_text())
        for k, v in (overrides or {}).items():
            self.cfg[k] = v if not isinstance(v, dict) else {**self.cfg.get(k, {}), **v}
        self.mode = self.cfg["mode"]
        self.state = expand(self.cfg["state_dir"])
        self.state.mkdir(parents=True, exist_ok=True)
        faults.configure(self.state)
        self.data_dir = expand(self.cfg["data_dir"])
        self.ledger = Ledger(self.state / "ledger.db")
        self.router = Router(expand(self.cfg["models"]), ledger=self.ledger)
        self.alerts = Alerts(self.cfg["alerts"], self.ledger, dry_run=self.cfg.get("alerts_dry_run", False))
        self.strategies_path = expand(self.cfg["strategies"])
        self.playbook_path = expand(self.cfg["playbook"])
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.market = market
        self.executor = executor
        self.loop = ImprovementLoop(self.state, self.ledger, self.router, self.strategies_path, self.playbook_path,
                                    commit=self.cfg.get("git_commit_changes", True))
        self._panel = None
        self._feat = None

    # ------------------------------------------------------------------ state files
    def _sf(self, name: str) -> Path:
        return self.state / name

    def _load(self, name: str, default):
        f = self._sf(name)
        return json.loads(f.read_text()) if f.exists() else default

    def _save(self, name: str, obj):
        self._sf(name).write_text(json.dumps(obj, indent=1, default=str))

    # ------------------------------------------------------------------ data
    def panel(self, refresh: bool = False):
        stamp = self._sf("data_refreshed")
        stale = not stamp.exists() or (datetime.now(timezone.utc).timestamp() - stamp.stat().st_mtime) > self.cfg["schedule"]["data_refresh_hours"] * 3600
        if (refresh or stale) and self.mode != "replay":
            history.download_all(self.data_dir, log=lambda m: None)
            stamp.write_text(datetime.now(timezone.utc).isoformat())
            self._panel = None
        if self._panel is None:
            self._panel = history.panel(self.data_dir)
            self._feat = features.build(self._panel)
        return self._panel, self._feat

    def features_asof(self, now: datetime) -> pd.DataFrame:
        _, f = self.panel()
        # only completed weekly bars: a week labelled Sunday D is complete after D 23:59 UTC
        return f.loc[: pd.Timestamp(now.date()) - pd.Timedelta(days=1)]

    # ------------------------------------------------------------------ portfolio and policy context
    def prices(self) -> Prices:
        return self.market.prices()

    def risk(self) -> dict:
        return self._load("risk.json", {"day": None, "nav_btc_day_start": None, "nav_btc_peak": None, "nav_usd_peak": None})

    def context(self, pf: Portfolio, prices: Prices, now: datetime) -> PolicyContext:
        r = self.risk()
        fills = self.ledger.events(kind="fill", since=(now - timedelta(days=8)).isoformat())
        times = [datetime.fromisoformat(e.ts) for e in fills]
        last_by_asset: dict[str, datetime] = {}
        for e in fills:
            for a in (e.payload["sell_asset"], e.payload["buy_asset"]):
                if a not in ("BTC",):
                    last_by_asset[a] = datetime.fromisoformat(e.ts)
        mode = "backtest" if self.mode == "replay" else self.mode
        return PolicyContext(portfolio=pf, prices=prices, mode=mode, now=now,
                             halted=killswitch.is_halted(self.state) if self.mode != "replay" else self._load("replay_halt.json", {}).get("day") == str(now.date()),
                             killed=killswitch.is_killed(self.state), nav_btc_day_start=r.get("nav_btc_day_start"),
                             nav_btc_peak=r.get("nav_btc_peak"), nav_usd_peak=r.get("nav_usd_peak"),
                             recent_order_times=times, last_trade_time_by_asset=last_by_asset)

    def update_risk_marks(self, pf: Portfolio, prices: Prices, now: datetime) -> dict:
        r = self.risk()
        nb, nu = pf.nav_btc(prices), pf.nav_usd(prices)
        day = str(now.date())
        if r.get("day") != day:
            r["day"], r["nav_btc_day_start"] = day, nb
        r["nav_btc_peak"] = max(r.get("nav_btc_peak") or 0.0, nb)
        r["nav_usd_peak"] = max(r.get("nav_usd_peak") or 0.0, nu)
        r["nav_btc"], r["nav_usd"], r["ts"] = nb, nu, now.isoformat()
        self._save("risk.json", r)
        return r

    # ------------------------------------------------------------------ execution helpers
    def _trade(self, sell: str, buy: str, qty: float, prices: Prices, now: datetime, decision_id: str, reason: str,
               stop: StopRule | None, params: dict, version: str) -> dict:
        pf = self.executor.portfolio()
        intent = TradeIntent(venue=self.executor.venue, chain=getattr(self.executor, "chain", None), sell_asset=sell,
                             buy_asset=buy, sell_qty=qty, stop=stop, reason_code=reason, strategy_id=self._champion_name(),
                             strategy_version=version, decision_id=decision_id,
                             expected_edge_bps=params.get("expected_edge_bps", 300.0), max_slippage_bps=50)
        try:
            cost, quote = self.executor.estimate(intent, prices)
        except Exception as e:
            self.ledger.append("error", {"where": "estimate", "error": f"{type(e).__name__}: {e}"[:300], "decision_id": decision_id})
            return {"status": "estimate_failed", "error": str(e)[:200]}
        intent.cost = cost
        d = check(intent, self.context(pf, prices, now))
        self.ledger.append("policy_check", {"decision_id": decision_id, "intent": intent.model_dump(mode="json"),
                                            "allowed": d.allowed, "violations": d.violations, "checks": d.checks})
        if d.kill and not killswitch.is_killed(self.state):
            self.kill("policy: " + "; ".join(d.violations), auto=True)
        if not d.allowed:
            return {"status": "rejected", "violations": d.violations}
        fill = self.executor.execute(intent, prices, quote, cost)
        pos = self._load("positions.json", {})
        if buy != "BTC":
            pos[buy] = {"entry_btc_usd": prices.usd["BTC"], "entry_ts": now.isoformat(), "stop": stop.model_dump() if stop else None,
                        "decision_id": decision_id}
        elif sell in pos and self.executor.portfolio().qty(sell) < 1e-9:
            pos.pop(sell, None)
        self._save("positions.json", pos)
        self.alerts.send("trade", "trade", f"{reason}: {sell}->{buy} {qty:.6g}",
                         f"filled {fill.get('buy_qty'):.8g} {buy} at {fill.get('price')}; cost est {cost.total_bps(fill['value_usd']):.1f} bps; "
                         f"mode {self.mode}; decision {decision_id}")
        return {"status": "filled", "fill": fill}

    def _withdraw_all(self, asset: str, prices: Prices, decision_id: str, protocol_filter: set | None = None) -> list:
        out = []
        for h in list(self.executor.portfolio().holdings):
            if h.protocol and h.asset == asset and h.qty > 0 and (not protocol_filter or h.protocol in protocol_filter):
                li = LendIntent(action="withdraw", venue=h.protocol, chain=h.chain, asset=asset, qty=h.qty, decision_id=decision_id)
                d = check(li, self.context(self.executor.portfolio(), prices, self.clock()))
                if d.allowed:
                    out.append(self.executor.lend(li))
        return out

    def _champion_name(self) -> str:
        return gatekeeper.load_strategies(self.strategies_path)["champion"]

    # ------------------------------------------------------------------ decision cycle
    def decide(self, now: datetime | None = None) -> dict:
        now = now or self.clock()
        did = str(uuid.uuid4())
        problems = frozen.verify_lock()
        if problems:
            self.kill("frozen layer modified: " + "; ".join(problems)[:300], auto=True, mode="halt_only")
            return {"decision_id": did, "action": "killed", "why": problems}
        if killswitch.is_killed(self.state):
            self.ledger.append("decision", {"decision_id": did, "action": "none", "why": "kill switch engaged"})
            return {"decision_id": did, "action": "none", "why": "killed"}

        cfg = gatekeeper.load_strategies(self.strategies_path)
        params = gatekeeper.champion_params(cfg)
        version = f"{cfg['champion']}@v{cfg.get('version')}"
        feat = self.features_asof(now)
        row = feat.iloc[-1].to_dict()
        week = str(feat.index[-1].date())

        # rule step: once per completed weekly bar; daily cycles in between reuse it
        sst = self._load("strategy_state.json", {"week": None, "state": None, "target": None, "rules": None, "params_version": None})
        st = StrategyState(**sst["state"]) if sst["state"] else StrategyState()
        new_week = sst["week"] != week or sst.get("params_version") != version
        if new_week:
            t = target(row, st, params)
            st2 = advance_state(st, t, row)
            sst = {"week": week, "state": st2.__dict__, "target": {"stable": t.stable, "eth": t.eth,
                   "stop_stable": t.stop_stable_btc_pct, "stop_eth": t.stop_eth_btc_pct}, "rules": t.rules,
                   "params_version": version}
            self._save("strategy_state.json", sst)
            self._weekly_upkeep(now, row, week)
        tgt, rules = sst["target"], sst["rules"]

        prices = self.prices()
        pf = self.executor.portfolio()
        self.update_risk_marks(pf, prices, now)
        w = pf.weights(prices)
        nav_btc, nav_usd = pf.nav_btc(prices), pf.nav_usd(prices)

        # news -> typed digest
        dg = {"items_read": 0, "note": "news disabled"}
        if self.cfg["news"]["enabled"] and self.mode != "replay":
            try:
                items = news.fetch(self.cfg["news"]["since_hours"])
                dg = news.digest(news.read_items(items, self.router, self.ledger, did))
            except Exception as e:
                dg = {"items_read": 0, "error": f"{type(e).__name__}"}

        # analyst + critic -> conviction
        conv_s, conv_a, analyst_rec, critic_rec, protocol_exit = 1.0, 1.0, None, None, []
        snap = features.snapshot(feat)
        deviation = tgt["stable"] > 0 or tgt["eth"] > 0 or w.get("USDC", 0) > 0.01 or w.get("ETH", 0) > 0.01
        pb = Playbook(self.playbook_path)
        if self.cfg["analyst"]["enabled"]:
            tags = {"rules", "macro"} | ({"exit"} if tgt["stable"] > 0 else {"reentry"} if w.get("USDC", 0) > 0.01 else set())
            lessons = pb.retrieve_lessons(tags)
            payload = {"as_of": now.isoformat(), "goal": "grow NAV measured in BTC; benchmark = hold BTC",
                       "portfolio": {"nav_btc": round(nav_btc, 8), "nav_usd": round(nav_usd, 2), "weights": {k: round(v, 4) for k, v in w.items()}},
                       "rules_target": tgt, "rule_states": rules, "strategy": version,
                       "backtest_record": {"btc_multiple_2011_2026": 1.55, "cycles_won": "3/4", "round_trips": 7, "win_rate": 0.57,
                                           "deflated_sharpe": 0.36, "note": "positive but not statistically significant"},
                       "features": snap, "news_digest": dg,
                       "playbook_judgment": [{"id": i["id"], "text": i["text"]} for i in pb.items("judgment")],
                       "lessons": [{"id": i["id"], "text": i["text"], "helpful": i["helpful"], "harmful": i["harmful"]} for i in lessons]}
            samples = []
            for i in range(self.cfg["analyst"].get("samples", 3)):
                try:
                    r = self.router.call("analyst", prompts.ANALYST_SYSTEM, json.dumps(payload, default=str), schemas.AnalystDecision, context_id=did)
                    samples.append((r, r.data))
                except LLMError as e:
                    self.ledger.append("error", {"where": "analyst", "error": str(e)[:300], "decision_id": did})
            if samples:
                ds = [s[1] for s in samples]
                conv_s = statistics.median(d.conviction_stable for d in ds)
                conv_a = statistics.median(d.conviction_alt for d in ds)
                votes = {}
                for d in ds:
                    for p in d.protocol_risk_exit:
                        votes[p.value] = votes.get(p.value, 0) + 1
                protocol_exit = [p for p, n in votes.items() if n > len(ds) / 2]
                best = min(ds, key=lambda d: abs(d.conviction_stable - conv_s))
                analyst_rec = {"models": [s[0].model_ref for s in samples], "served": [s[0].served_model for s in samples],
                               "regime_votes": [d.regime for d in ds], "conviction_stable": conv_s, "conviction_alt": conv_a,
                               "p_btc_up_7d": statistics.median(d.p_btc_up_7d for d in ds),
                               "p_btc_up_30d": statistics.median(d.p_btc_up_30d for d in ds),
                               "key_factors": [f.model_dump() for f in best.key_factors],
                               "lessons_applied": sorted({x for d in ds for x in d.lessons_applied}),
                               "justification": best.justification, "protocol_risk_exit": protocol_exit}
                if self.cfg["analyst"].get("critic") and deviation:
                    try:
                        c = self.router.call("critic", prompts.CRITIC_SYSTEM,
                                             json.dumps({"evidence": payload, "proposal": analyst_rec}, default=str), schemas.CriticVerdict, context_id=did)
                        critic_rec = {"model": c.model_ref, "served": c.served_model, **c.data.model_dump()}
                        conv_s, conv_a = min(conv_s, c.data.max_conviction_stable), min(conv_a, c.data.max_conviction_alt)
                    except LLMError as e:
                        critic_rec = {"error": str(e)[:200]}
        final_s, final_e = tgt["stable"] * conv_s, tgt["eth"] * conv_a

        # plan and execute
        actions = []
        cur_s = w.get("USDC", 0.0)
        thr = self.cfg["trading"]["min_trade_nav_fraction"]
        stable = self.cfg["trading"]["stable"]
        if protocol_exit:
            actions.append({"protocol_exit": protocol_exit, "result": self._withdraw_all(stable, prices, did, set(protocol_exit))})
        if abs(final_s - cur_s) >= thr or (final_s == 0 and cur_s > 0.01):
            if final_s > cur_s:          # BTC -> stable
                qty = (final_s - cur_s) * nav_btc
                stop = StopRule(max_loss_btc_pct=tgt["stop_stable"] or params["cycle_guard"]["stable_stop_btc_pct"])
                actions.append(self._trade("BTC", stable, min(qty, pf.qty("BTC", liquid_only=True)), prices, now, did, "strategy", stop, params, version))
            else:                        # stable -> BTC
                self._withdraw_all(stable, prices, did)
                pf2 = self.executor.portfolio()
                qty = pf2.qty(stable, liquid_only=True) if final_s == 0 else (cur_s - final_s) * nav_btc * prices.usd["BTC"]
                if qty > 0:
                    actions.append(self._trade(stable, "BTC", min(qty, pf2.qty(stable, liquid_only=True)), prices, now, did, "strategy", None, params, version))
        # idle stables earn yield (only when the rules want to hold stables and the analyst flagged no protocol risk)
        y = self.cfg["yield"]
        if y["enabled"] and not protocol_exit and final_s > 0:
            pf3 = self.executor.portfolio()
            liquid = pf3.qty(stable, liquid_only=True) * (1 - y["keep_liquid_fraction"])
            if liquid * prices.usd[stable] >= y["min_usd"]:
                from ..types import CostEstimate
                li = LendIntent(action="supply", venue=y["protocol"], chain="base", asset=stable, qty=liquid, expected_apy=y["expected_apy"],
                                cost=CostEstimate(gas_usd=0.05, lockup_hours=y["lockup_hours"], source="config"), strategy_id=self._champion_name(),
                                strategy_version=version, decision_id=did)
                d = check(li, self.context(pf3, prices, now))
                self.ledger.append("policy_check", {"decision_id": did, "intent": li.model_dump(mode="json"), "allowed": d.allowed, "violations": d.violations})
                if d.allowed:
                    actions.append({"lend": self.executor.lend(li)})
        pf_after = self.executor.portfolio()
        rec = {"decision_id": did, "mode": self.mode, "as_of": now.isoformat(), "week": week, "new_week": new_week,
               "strategy_version": version, "playbook_version": pb.version, "prompt_version": prompts.PROMPT_VERSION,
               "model": analyst_rec["models"][0] if analyst_rec else None, "rules_target": tgt, "rule_states": rules,
               "features": snap, "news_digest": dg, "analyst": analyst_rec, "critic": critic_rec,
               "final_weights": {"stable": final_s, "eth": final_e}, "weights_before": w,
               "weights_after": pf_after.weights(prices), "nav_btc": pf_after.nav_btc(prices), "nav_usd": pf_after.nav_usd(prices),
               "btc_usd": prices.usd["BTC"], "actions": actions,
               "action": ("trade" if any(a.get("status") == "filled" for a in actions)
                          else "lend" if any("lend" in a for a in actions)
                          else "attempted_failed" if actions else "none")}
        self.ledger.append("decision", rec)
        if analyst_rec:
            self.ledger.append("forecast", {"decision_id": did, "ts": now.isoformat(), "btc_usd": prices.usd["BTC"],
                                            "p_up_7d": analyst_rec["p_btc_up_7d"], "p_up_30d": analyst_rec["p_btc_up_30d"],
                                            "lessons_applied": analyst_rec["lessons_applied"]})
        return rec

    # ------------------------------------------------------------------ weekly upkeep: shadows, improvement loop
    def _weekly_upkeep(self, now: datetime, row: dict, week: str):
        self.loop.setup_shadows()
        self.loop.shadows.on_week(week, row)
        out = self.loop.weekly(now)
        self.loop.shadows.save()
        self.ledger.append("weekly", {"week": week, "shadow_navs": {k: self.loop.shadows.nav(k) for k in self.loop.shadows.books},
                                      "loop": out, "controller": self.loop.ctrl.s.state})
        if out.get("probation", {}).get("rollback"):
            self.alerts.send("rollback", "warning", "strategy rolled back", json.dumps(out["probation"]))

    def daily_upkeep(self, now: datetime | None = None, review: bool | None = None) -> dict:
        now = now or self.clock()
        panel, _ = self.panel()
        day = panel.loc[:pd.Timestamp(now.date()) - pd.Timedelta(days=1)].iloc[-1]
        self.loop.setup_shadows()
        up = self._load("upkeep.json", {"day": None})
        if up["day"] != str(day.name.date()):          # once per market day, however often upkeep runs
            self.loop.shadows.on_day(str(day.name.date()), float(day["btc"]), float(day["eth_btc"]) if pd.notna(day.get("eth_btc")) else None,
                                     float(day["ust3m"]) if pd.notna(day.get("ust3m")) else None)
            self.loop.shadows.save()
            if hasattr(self.executor, "accrue_interest"):
                self.executor.accrue_interest(1.0)
            self._save("upkeep.json", {"day": str(day.name.date())})
        scored = self.score_forecasts(now)
        pms = self.run_postmortems()
        sched = self.cfg["schedule"]
        if review is None:
            review = (sched["review"] == "daily" or (sched["review"] == "weekly" and now.weekday() == sched["review_weekday"])
                      or (sched["review"] == "monthly" and now.day == sched["monthly_report_day"]))
        trig = self.loop.triggers(now, scheduled=review)
        res = None
        if trig:
            _, feat = self.panel()
            panel, _ = self.panel()
            res = self.loop.propose_and_gate(now, feat.loc[:pd.Timestamp(now.date())], panel.loc[:pd.Timestamp(now.date())], trig,
                                             live_nav=[e.payload.get("nav_btc") for e in self.ledger.events(kind="decision")][-30:])
        out = {"forecasts_scored": scored, "postmortems": len(pms), "triggers": sorted(trig), "reflection": res}
        self.ledger.append("daily", out)
        return out

    def score_forecasts(self, now: datetime) -> int:
        panel, _ = self.panel()
        done = {e.payload["forecast_id"] for e in self.ledger.events(kind="forecast_score")}
        n = 0
        pb = Playbook(self.playbook_path)
        for e in self.ledger.events(kind="forecast"):
            for h, key in ((7, "p_up_7d"), (30, "p_up_30d")):
                fid = f"{e.id}:{h}"
                t0 = datetime.fromisoformat(e.payload["ts"])
                if fid in done or now < t0 + timedelta(days=h):
                    continue
                px = panel["btc"].loc[:pd.Timestamp((t0 + timedelta(days=h)).date())]
                if px.empty:
                    continue
                up = float(px.iloc[-1]) > e.payload["btc_usd"]
                brier = (e.payload[key] - (1.0 if up else 0.0)) ** 2
                self.ledger.append("forecast_score", {"forecast_id": fid, "horizon_days": h, "p": e.payload[key], "outcome_up": up, "brier": brier})
                if h == 30:
                    for lid in e.payload.get("lessons_applied", []):
                        pb.count(lid, helpful=brier < 0.25)       # better than a coin flip -> the lesson helped
                n += 1
        if n:
            pb.save()
        return n

    def run_postmortems(self) -> list:
        """Post-mortem every closed round trip of the real (paper/fork/live) book that lost BTC, once."""
        fills = self.ledger.events(kind="fill")
        trades = []
        for e in fills:
            p = e.payload
            if p.get("reason_code") == "kill_switch":
                continue
            leg = "STABLE" if "USDC" in (p["sell_asset"], p["buy_asset"]) else "ETH"
            side = "buy" if p["sell_asset"] == "BTC" else "sell"
            trades.append({"date": e.ts[:10], "leg": leg, "side": side, "btc_usd": p.get("price_btc_usd"),
                           "eth_btc": None, "fee_btc": p.get("fee_usd", 0) / (p.get("price_btc_usd") or 1), "fill_id": e.id,
                           "decision_id": p.get("decision_id")})
        done = {e.payload.get("trip", {}).get("id") for e in self.ledger.events(kind="postmortem")}
        out = []
        pb = Playbook(self.playbook_path)
        for trip in losing_trips(trades):
            if trip["id"] in done:
                continue
            decisions = [e for e in self.ledger.events(kind="decision") if trip["open"] <= e.ts[:10] <= trip["close"]]
            ctx = {"decision_ids": [e.id for e in decisions][:10],
                   "rule_states_at_open": decisions[0].payload.get("rule_states") if decisions else None,
                   "analyst_at_open": (decisions[0].payload.get("analyst") or {}).get("key_factors") if decisions else None,
                   "btc_path_usd": [e.payload.get("btc_usd") for e in decisions][:60]}
            out.append(postmortem(trip, ctx, self.router, self.ledger, pb))
        return out

    # ------------------------------------------------------------------ risk tick and kill switch
    def risk_tick(self, now: datetime | None = None) -> dict:
        now = now or self.clock()
        prices = self.prices()
        pf = self.executor.portfolio()
        r = self.update_risk_marks(pf, prices, now)
        ctx = self.context(pf, prices, now)
        limits = frozen.limits()
        out: dict = {"nav_btc": r["nav_btc"], "nav_usd": r["nav_usd"]}
        v, halt, kill = risk_state(ctx, limits)
        if kill and not ctx.killed:
            self.kill("automatic: " + "; ".join(v), auto=True)
            out["kill"] = v
        elif halt and not ctx.halted:
            if self.mode == "replay":
                self._save("replay_halt.json", {"day": str(now.date())})
            else:
                killswitch.halt_today(self.state, self.ledger, "; ".join(v))
            self.alerts.send("halt", "warning", "daily loss limit: halted for the day", "; ".join(v))
            out["halt"] = v
        # stops (BTC terms), evaluated in code on every tick
        pos = self._load("positions.json", {})
        for asset, p in list(pos.items()):
            stop = (p.get("stop") or {}).get("max_loss_btc_pct")
            if not stop or pf.qty(asset) <= 1e-9:
                continue
            if asset in ("USDC", "USDT"):
                trigger = prices.usd["BTC"] >= p["entry_btc_usd"] / (1 - stop)
            else:
                trigger = prices.btc(asset) <= p.get("entry_price_btc", prices.btc(asset)) * (1 - stop)
            if trigger:
                did = f"stop-{uuid.uuid4()}"
                self._withdraw_all(asset, prices, did)
                qty = self.executor.portfolio().qty(asset, liquid_only=True)
                cfg = gatekeeper.load_strategies(self.strategies_path)
                res = self._trade(asset, "BTC", qty, prices, now, did, "stop_loss", None, gatekeeper.champion_params(cfg), cfg["champion"])
                self.ledger.append("stop_trigger", {"asset": asset, "entry_btc_usd": p["entry_btc_usd"], "btc_usd": prices.usd["BTC"],
                                                   "stop": stop, "result": res.get("status")})
                # the rule state must know the stop fired: block re-exit until a fresh 50W reclaim
                sst = self._load("strategy_state.json", {})
                if sst.get("state"):
                    sst["state"].update(stable=0.0, stable_entry_btc_price=None, weeks_in_stable=0, exit_armed=False)
                    sst["target"]["stable"] = 0.0
                    self._save("strategy_state.json", sst)
                out.setdefault("stops", []).append(asset)
        if killswitch.is_killed(self.state) and not self._load("kill_done.json", {}).get("done"):
            out["kill_procedure"] = self.kill_procedure(prices, now)
        return out

    def kill(self, reason: str, auto: bool, mode: str | None = None) -> dict:
        mode = mode or frozen.limits()["kill_switch"]["default_mode"]
        info = killswitch.engage(self.state, self.ledger, reason, mode, auto)
        self._save("kill_done.json", {"done": False})
        self.alerts.send("kill", "critical", f"KILL SWITCH ({'auto' if auto else 'manual'}): {mode}", reason)
        return info

    def kill_procedure(self, prices: Prices, now: datetime) -> dict:
        info = killswitch.kill_info(self.state) or {}
        mode = info.get("mode") or frozen.limits()["kill_switch"]["default_mode"]
        pf = self.executor.portfolio()
        plan = killswitch.emergency_plan(pf.holdings, mode, self.cfg["trading"]["stable"])
        done = []
        cfg = gatekeeper.load_strategies(self.strategies_path)
        params = gatekeeper.champion_params(cfg)
        for step in plan:
            try:
                if step["step"] == "withdraw":
                    done.append({**step, "result": self._withdraw_all(step["asset"], prices, "kill")})
                elif step["step"] == "convert":
                    qty = self.executor.portfolio().qty(step["sell"], liquid_only=True)
                    if qty > 0:
                        done.append({**step, "result": self._trade(step["sell"], step["buy"], qty, prices, now, "kill", "kill_switch", None, params, cfg["champion"])})
                elif step["step"] == "transfer_all_to_safe" and hasattr(self.executor, "transfer"):
                    safe = frozen.limits()["kill_switch"]["safe_address"]
                    for h in self.executor.portfolio().holdings:
                        if not h.protocol and h.qty > 0:
                            done.append({**step, "result": self.executor.transfer(h.asset, h.qty, safe)})
                else:
                    done.append({**step, "result": "n/a for this executor" if step["step"] != "cancel_open_orders" else "no open orders (market orders only)"})
            except Exception as e:
                done.append({**step, "error": f"{type(e).__name__}: {e}"[:300]})
        # after a conversion, leftovers in a protocol (withdrawn above) are converted on the next tick
        after = self.executor.portfolio()
        self._save("kill_done.json", {"done": True, "ts": now.isoformat()})
        self.ledger.append("kill_switch", {"action": "procedure", "mode": mode, "steps": done,
                                           "holdings_after": [h.model_dump() for h in after.holdings]})
        self.alerts.send("kill_done", "critical", f"kill procedure finished ({mode})", json.dumps([s.get("step") for s in done]))
        return {"mode": mode, "steps": done}

    def heartbeat(self, now: datetime | None = None) -> dict:
        now = now or self.clock()
        prices = self.prices()
        pf = self.executor.portfolio()
        rec = {"nav_btc": pf.nav_btc(prices), "nav_usd": pf.nav_usd(prices), "btc_usd": prices.usd["BTC"],
               "killed": killswitch.is_killed(self.state), "halted": killswitch.is_halted(self.state),
               "ledger_head": self.ledger.head()[1][:16]}
        self.ledger.append("heartbeat", rec)
        return rec

    def safe_call(self, fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except Exception as e:
            self.ledger.append("error", {"where": getattr(fn, "__name__", "?"), "error": f"{type(e).__name__}: {e}"[:400],
                                         "trace": traceback.format_exc()[-1500:]})
            self.alerts.send("error:" + getattr(fn, "__name__", "?"), "warning", f"error in {getattr(fn, '__name__', '?')}", f"{type(e).__name__}: {e}"[:500])
            return {"error": f"{type(e).__name__}: {e}"[:300]}
