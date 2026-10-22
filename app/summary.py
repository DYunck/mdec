"""Plain-English 'today in one paragraph', built from the numbers (no AI, no guessing)."""
from __future__ import annotations

import datetime as dt


def paragraph(r: dict, mode: str, today: dt.date, recent_event: dict | None) -> str:
    sym = r.get("currency_symbol", "$")
    _money = lambda x: f"{sym}{x:,.2f}"
    p, chg = r["price"], r["change_pct"]
    ds, hs = r["daily_snapshot"], r.get("hourly_snapshot") or {}
    d, v = r["direction"], r["volatility"]
    parts = []

    verb = "closed at" if r.get("market_closed") else "is at"
    name = r["short_name"]
    way = "up" if chg > 0 else "down" if chg < 0 else "flat"
    s = f"{name} {verb} {_money(p)}, {way} {abs(chg):.1f}% today" if way != "flat" else f"{name} {verb} {_money(p)}, unchanged today"
    vr = ds.get("volume_vs_avg")
    if vr and vr >= 1.5:
        s += f" on {vr:.1f}× normal volume"
    elif vr and vr <= 0.6 and r.get("market_closed"):
        s += " on light volume"
    if recent_event:
        when = "today" if recent_event["days"] == 0 else "yesterday" if recent_event["days"] == -1 else f"{-recent_event['days']} days ago"
        s += f", after its earnings report {when}"
    parts.append(s + ".")

    c, s20, s50 = ds.get("Close"), ds.get("sma20"), ds.get("sma50")
    if c and s20 and s50:
        if c > s20 and s20 > s50:
            t = "The daily trend is up: price is above its 20-day average, which is above the 50-day."
        elif c < s20 and s20 < s50:
            t = "The daily trend is down: price is below its 20-day average, which is below the 50-day."
        elif c > s20:
            t = "Price is back above its 20-day average, but the longer trend hasn't turned up yet."
        else:
            t = "Price has slipped below its 20-day average, though the longer trend is still up."
        parts.append(t)

    score = d["score"]
    s = f"The overall score is {d['label'].lower()} ({score:+d})"
    against = [x for x in d["reasons"] if x["points"] * score < 0 and abs(x["points"]) >= 4]
    if abs(score) >= 20 and against:
        tf, _, rest = against[0]["text"].partition(": ")
        rest = rest.replace(" — ", ", ")
        s += f", with one caution on the {tf.lower()} chart: {rest[0].lower() + rest[1:] if not rest[:3].isupper() else rest}"
    elif abs(score) < 20:
        s += ", so signals are mixed"
    parts.append(s + ".")

    rel = r.get("relative")
    if rel and rel.get("vs_sector_20d") is not None and abs(rel["vs_sector_20d"]) >= 3:
        parts.append(f"Over the last month it has {'beaten' if rel['vs_sector_20d'] > 0 else 'lagged'} the medical-device ETF (IHI) by {abs(rel['vs_sector_20d']):.0f} points.")

    iv, rv = v.get("atm_iv"), v.get("realized_vol")
    verdict = v.get("verdict")
    if not r.get("has_options"):
        parts.append("There are no US-listed options on this stock, so the options sections are left out.")
    elif iv and rv:
        word = {"expensive": "expensive", "cheap": "cheap", "fair": "fairly priced"}[verdict]
        parts.append(f"Options look {word}, assuming {iv:.0f}% yearly volatility versus {rv:.0f}% the stock has actually shown.")
    em = r.get("expected_move")
    if em:
        exp = dt.date.fromisoformat(em["expiry"])
        days = (exp - today).days
        when = "by Friday" if 0 < days <= 6 and exp.weekday() == 4 else f"by {exp:%b} {exp.day}"
        parts.append(f"The options market expects a move of about ±{em['pct']:.0f}% {when}.")

    nb = r.get("next_big_event")
    if nb and nb["days"] is not None and nb["days"] <= 14:
        when = "today" if nb["days"] == 0 else "tomorrow" if nb["days"] == 1 else f"in {nb['days']} days"
        title = nb["title"].split(" — ")[0]
        tail = f" Earnings have moved it about ±{r['event_moves']['summary']['earnings_avg_abs_move']:.0f}% on average." \
            if nb["type"] == "earnings" and (r.get("event_moves") or {}).get("summary", {}).get("earnings_avg_abs_move") else ""
        if nb["type"] == "earnings" and r.get("has_options"):
            tail += " Option prices often drop sharply right after the report."
        parts.append(f"Next up: {title} {when}.{tail}")
    return " ".join(parts)
