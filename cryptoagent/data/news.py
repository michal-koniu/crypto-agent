"""News and regulatory feeds -> typed digest, through the tool-less reader (prompt-injection firebreak).

Raw headlines and summaries are UNTRUSTED. They go to the reader model one item at a time, wrapped in
<untrusted> markers, and come back as enums (event type, asset, direction, severity, contains_instructions). The
analyst only ever sees the aggregated enums - never the raw text. An item flagged as containing instructions is
kept for the audit log, counted, and excluded from the digest.
"""
from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime, timedelta, timezone

import feedparser
import httpx

from ..ledger.store import Ledger
from ..llm import prompts, schemas
from ..llm.router import LLMError, Router

FEEDS = {   # tier: 1 = primary source (central bank, regulator), 2 = established crypto press, 3 = aggregator
    "fed": ("https://www.federalreserve.gov/feeds/press_all.xml", 1),
    "sec": ("https://www.sec.gov/news/pressreleases.rss", 1),
    "esma": ("https://www.esma.europa.eu/rss.xml", 1),
    "coindesk": ("https://www.coindesk.com/arc/outboundfeeds/rss/", 2),
    "theblock": ("https://www.theblock.co/rss.xml", 2),
    "decrypt": ("https://decrypt.co/feed", 2),
    "rekt": ("https://rekt.news/rss/feed.xml", 2),
}
MAX_ITEMS = 25
TAG_RE = re.compile(r"<[^>]+>")
# Deterministic second layer (the model is the first): instruction-like phrasing aimed at an AI/agent/system.
INJECTION_RE = re.compile(
    r"(ignore (all |any )?(previous|prior|above) instructions|\bsystem\s*(:|override|prompt)|you are now|"
    r"approve unlimited|unlimited (spending|approval)|disable (the )?(limits?|risk|signer|checks?)|"
    r"(raise|increase|lift) (the )?(drawdown|limit|max_)|max_order|allowlist|transfer (all )?funds|"
    r"as (the|an) administrator|by order of|automated (trading )?(systems|agents?)|ai agents?:|tell the (portfolio )?agent)",
    re.I)


def _clean(s: str, n: int) -> str:
    s = html.unescape(TAG_RE.sub(" ", s or ""))
    s = re.sub(r"\s+", " ", s).strip()
    return s.replace("<untrusted>", "").replace("</untrusted>", "")[:n]


def fetch(since_hours: int = 30, feeds: dict = FEEDS) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    items, seen = [], set()
    with httpx.Client(timeout=20, follow_redirects=True, headers={"User-Agent": "crypto-agent/0.1"}) as c:
        for name, (url, tier) in feeds.items():
            try:
                parsed = feedparser.parse(c.get(url).content)
            except Exception:
                continue
            for e in parsed.entries[:30]:
                t = e.get("published_parsed") or e.get("updated_parsed")
                ts = datetime(*t[:6], tzinfo=timezone.utc) if t else None
                if ts and ts < cutoff:
                    continue
                title = _clean(e.get("title", ""), 200)
                key = hashlib.sha256(title.lower().encode()).hexdigest()[:16]
                if not title or key in seen:
                    continue
                seen.add(key)
                items.append({"id": key, "source": name, "tier": tier, "ts": ts.isoformat() if ts else None,
                              "title": title, "summary": _clean(e.get("summary", ""), 600), "link": e.get("link", "")[:300]})
    items.sort(key=lambda x: (x["tier"], x["ts"] or ""), reverse=False)
    return items[:MAX_ITEMS]


def read_items(items: list[dict], router: Router, ledger: Ledger, decision_id: str | None = None) -> list[dict]:
    out = []
    for it in items:
        text = f"<untrusted>source={it['source']} (tier {it['tier']})\nTITLE: {it['title']}\nTEXT: {it['summary']}</untrusted>"
        try:
            r = router.call("reader", prompts.READER_SYSTEM, text, schemas.ReaderItem, context_id=decision_id)
            d = r.data.model_dump(mode="json")
            # source tier caps severity: an aggregator cannot produce a severity-3 event
            if it["tier"] >= 3:
                d["severity"] = min(d["severity"], 1)
            code_flag = bool(INJECTION_RE.search(it["title"] + " " + it["summary"]))
            d["flagged_by"] = ("model+code" if d["contains_instructions"] and code_flag else
                               "model" if d["contains_instructions"] else "code" if code_flag else None)
            d["contains_instructions"] = d["contains_instructions"] or code_flag
            rec = {"item_id": it["id"], "source": it["source"], "tier": it["tier"], "model": r.model_ref, **d}
        except LLMError as e:
            rec = {"item_id": it["id"], "source": it["source"], "error": str(e)[:200]}
        ledger.append("news_item", {**rec, "title": it["title"], "decision_id": decision_id})
        out.append(rec)
    return out


def digest(read: list[dict]) -> dict:
    """Aggregate typed items into counts the analyst can use. No raw text survives."""
    ok = [r for r in read if "event_type" in r and r.get("relevant") and not r.get("contains_instructions")]
    flagged = sum(1 for r in read if r.get("contains_instructions"))
    agg: dict = {}
    for r in ok:
        k = r["event_type"]
        a = agg.setdefault(k, {"n": 0, "bearish": 0, "bullish": 0, "max_severity": 0, "protocols": set()})
        a["n"] += 1
        a[r["direction"]] = a.get(r["direction"], 0) + 1
        a["max_severity"] = max(a["max_severity"], r["severity"])
        if r.get("protocol") not in (None, "none"):
            a["protocols"].add(r["protocol"])
    for a in agg.values():
        a["protocols"] = sorted(a["protocols"])
    severe_protocol = sorted({r["protocol"] for r in ok if r["event_type"] in ("protocol_exploit", "stablecoin_depeg", "exchange_risk")
                              and r["severity"] >= 3 and r["tier"] <= 2 and r.get("protocol") not in (None, "none")})
    return {"items_read": len(read), "relevant": len(ok), "flagged_injection_attempts": flagged,
            "by_event_type": agg, "severe_protocol_events": severe_protocol}
