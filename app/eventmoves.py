"""How each stock actually moved around past earnings reports, vs. what options priced in beforehand."""
from __future__ import annotations

import datetime as dt

import pandas as pd


def _close_on_or_before(closes: pd.Series, d: dt.date):
    s = closes[closes.index.date <= d]
    return float(s.iloc[-1]) if len(s) else None


def _close_after(closes: pd.Series, d: dt.date, n: int = 1):
    s = closes[closes.index.date > d]
    return float(s.iloc[n - 1]) if len(s) >= n else None


def _close_on_or_after(closes: pd.Series, d: dt.date, n: int = 1):
    s = closes[closes.index.date >= d]
    return float(s.iloc[n - 1]) if len(s) >= n else None


def reaction(closes: pd.Series, d: dt.date, timing: str):
    """Move caused by a report on day d. Before the open (or during market): prior close -> that day's close.
    After the close: that day's close -> next day's close."""
    if timing == "after close":
        before, a1, a3 = _close_on_or_before(closes, d), _close_after(closes, d, 1), _close_after(closes, d, 3)
    else:
        before, a1, a3 = _close_on_or_before(closes, d - dt.timedelta(days=1)), _close_on_or_after(closes, d, 1), _close_on_or_after(closes, d, 3)
    if before is None or a1 is None:
        return None
    return (round((a1 / before - 1) * 100, 1), round((a3 / before - 1) * 100, 1) if a3 else None)


def history(daily: pd.DataFrame, earnings: list[dict], em_hist: dict, today: dt.date, name: str) -> list[dict]:
    closes = daily["Close"]
    out = []
    for e in earnings:
        d = dt.date.fromisoformat(e["date"])
        if d > today or d < closes.index[0].date() + dt.timedelta(days=2):
            continue
        timing = e.get("timing") or "before open"
        if d == today and timing == "after close":
            continue
        r = reaction(closes, d, timing)
        if not r:
            continue
        em = em_hist.get(e["date"])
        implied = em["pct"] if em else None
        out.append({
            "date": e["date"], "type": "earnings", "timing": timing, "title": f"{name} earnings ({timing})",
            "move_1d_pct": r[0], "move_3d_pct": r[1], "implied_pct": implied,
            "eps_est": e.get("eps_est"), "eps_actual": e.get("eps_actual"), "surprise_pct": e.get("surprise_pct"),
            "vs_implied": (None if implied is None else ("bigger than priced in" if abs(r[0]) > implied else "smaller than priced in")),
        })
    return sorted(out, key=lambda x: x["date"], reverse=True)


def summarize(rows: list[dict]) -> dict:
    with_imp = [r for r in rows if r["implied_pct"] is not None]
    n = len(rows)
    beats = [r for r in rows if r.get("surprise_pct") is not None and r["surprise_pct"] > 0]
    beat_up = [r for r in beats if r["move_1d_pct"] > 0]
    misses = [r for r in rows if r.get("surprise_pct") is not None and r["surprise_pct"] < 0]
    return {
        "earnings_count": n,
        "earnings_avg_abs_move": round(sum(abs(r["move_1d_pct"]) for r in rows) / n, 1) if n else None,
        "earnings_up": sum(1 for r in rows if r["move_1d_pct"] > 0),
        "biggest_up": max((r["move_1d_pct"] for r in rows), default=None),
        "biggest_down": min((r["move_1d_pct"] for r in rows), default=None),
        "beats": len(beats), "beats_up": len(beat_up), "misses": len(misses),
        "priced_in_compared": len(with_imp),
        "smaller_than_priced": sum(1 for r in with_imp if r["vs_implied"] == "smaller than priced in"),
    }
