"""Analyst summary and FDA activity (510(k) clearances and recalls) for each company."""
from __future__ import annotations

import datetime as dt


# ---------------------------------------------------------------- FDA activity

def fda(raw: dict | None, today: dt.date) -> dict | None:
    if raw is None:
        return None
    clear = sorted([c for c in raw.get("clearances", []) if c.get("date")], key=lambda c: c["date"], reverse=True)
    recs = [r for r in raw.get("recalls", []) if r.get("date")]
    # openFDA lists one record per product; group them into recall events
    events: dict[str, dict] = {}
    for r in sorted(recs, key=lambda r: r["date"]):
        key = r.get("event_id") or r.get("recall_number")
        e = events.get(key)
        if e is None:
            events[key] = e = {**r, "products": 0}
        e["products"] += 1
        e["date"] = min(e["date"], r["date"])
        if r.get("classification") == "Class I":
            e["classification"] = "Class I"
    ev = sorted(events.values(), key=lambda e: e["date"], reverse=True)
    y1 = (today - dt.timedelta(days=365)).isoformat()
    q1 = (today - dt.timedelta(days=90)).isoformat()
    return {
        "clearances": clear[:12],
        "recalls": ev[:15],
        "summary": {
            "clearances_12m": sum(1 for c in clear if c["date"] >= y1),
            "clearances_90d": sum(1 for c in clear if c["date"] >= q1),
            "recalls_12m": sum(1 for e in ev if e["date"] >= y1),
            "class1_12m": sum(1 for e in ev if e["date"] >= y1 and e.get("classification") == "Class I"),
            "recalls_90d": sum(1 for e in ev if e["date"] >= q1),
            "last_class1": next((e["date"] for e in ev if e.get("classification") == "Class I"), None),
        },
    }


# ---------------------------------------------------------------- analysts

def analysts(a: dict | None, price: float) -> dict | None:
    if not a:
        return None
    t = a.get("targets") or {}
    mean = t.get("mean") or t.get("median")
    out = dict(a)
    out["price"] = round(price, 2)
    out["upside_mean_pct"] = round((mean / price - 1) * 100, 1) if mean else None
    for k in ("low", "high"):
        out[f"upside_{k}_pct"] = round((t[k] / price - 1) * 100, 1) if t.get(k) else None
    words = {"strong_buy": "Strong buy", "buy": "Buy", "hold": "Hold", "underperform": "Underperform", "sell": "Sell",
             "strong_sell": "Strong sell", "none": None}
    out["rating_text"] = words.get((a.get("rating_key") or "").lower(), (a.get("rating_key") or "").replace("_", " ").title() or None)
    return out
