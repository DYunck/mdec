"""Main job: fetch data for every company, analyze, write dashboard data. Sends nothing to anyone.

    python -m app.run              # live data
    python -m app.run --sample     # fake data for testing
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path

import pandas as pd
import yaml

from . import backtest, eventmoves, fetch, indicators as ind, options as opt, signals, summary, trackers, weekly

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "data"
NY = "America/New_York"
SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "CHF": "CHF "}
# Regular trading hours in New York time (Xetra 9:00–17:30 Frankfurt is about 3:00–11:30 New York)
HOURS = {"SHL.DE": (3 * 60, 11 * 60 + 30)}
US_HOURS = (9 * 60 + 30, 16 * 60)


# ------------------------------------------------------------------ helpers

def _num(x, nd=2):
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else round(f, nd)


def _load_json(p: Path, default):
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def _save(p: Path, obj, compact=False):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, separators=(",", ":")) if compact else json.dumps(obj, indent=1))


def load_yaml_events(today: dt.date) -> list[dict]:
    raw = yaml.safe_load((ROOT / "data" / "events.yaml").read_text()) or {}
    return [dict(e, date=str(e["date"])) for e in raw.get("events", []) if e.get("date")]


def events_for(co: dict, yaml_events: list[dict], earnings: list[dict], today: dt.date) -> list[dict]:
    """Calendar for one company: its earnings (Yahoo + events.yaml), shared events, and monthly options expirations."""
    key = co["key"]
    mine = [e for e in yaml_events if not e.get("companies") or key in e["companies"]]
    ev = []
    yahoo_dates = [dt.date.fromisoformat(e["date"]) for e in earnings]
    for e in earnings:
        ev.append({"date": e["date"], "type": "earnings", "title": f"{co['short']} earnings ({e.get('timing', 'time TBD')})",
                   "timing": e.get("timing"), "verified": True, "source": "Yahoo"})
    for e in mine:
        if e.get("type") == "earnings":
            d = dt.date.fromisoformat(e["date"])
            if any(abs((d - y).days) <= 5 for y in yahoo_dates):
                # Yahoo has a date for the same report; keep the events.yaml title/timing if Yahoo's timing is unknown
                for x in ev:
                    if x["type"] == "earnings" and abs((dt.date.fromisoformat(x["date"]) - d).days) <= 5 and x.get("timing") in (None, "unknown"):
                        x.update(date=e["date"], title=e["title"], timing=e.get("timing", "before open"), verified=e.get("verified", True))
                continue
            ev.append({"date": e["date"], "type": "earnings", "title": e["title"], "timing": e.get("timing", "before open"),
                       "verified": e.get("verified", True), "source": "events.yaml"})
        else:
            ev.append({k: e[k] for k in ("date", "type", "title") if k in e} | {"verified": e.get("verified", True)})
    if co.get("options"):
        for f in fetch._third_fridays(today, 3):
            ev.append({"date": f.isoformat(), "type": "opex", "title": "Monthly options expiration", "verified": True})
    return sorted(ev, key=lambda e: e["date"])


def bars(df: pd.DataFrame, intraday: bool, cols=("sma20", "sma50", "bb_up", "bb_low")) -> list[dict]:
    out = []
    for ts, r in df.iterrows():
        t = int(pd.Timestamp(ts.tz_localize(None)).timestamp()) if intraday else ts.strftime("%Y-%m-%d")
        row = {"t": t, "o": _num(r.Open), "h": _num(r.High), "l": _num(r.Low), "c": _num(r.Close), "v": int(r.Volume)}
        for c in cols + ("rsi", "macd_hist"):
            row[c] = _num(r.get(c))
        out.append(row)
    return out


def snapshot(df: pd.DataFrame) -> dict:
    r = df.iloc[-1]
    return {k: _num(r.get(k)) for k in ("Close", "sma20", "sma50", "rsi", "macd", "macd_signal", "macd_hist",
                                         "bb_up", "bb_low", "atr", "rvol20")} | {
        "volume_vs_avg": _num(r["Volume"] / r["vol_avg20"]) if r.get("vol_avg20") else None}


def pct_change(s: pd.Series, n: int):
    s = s.dropna()
    return _num((s.iloc[-1] / s.iloc[max(0, len(s) - 1 - n)] - 1) * 100) if len(s) > 1 else None


def cached(new, path: Path, sample: bool):
    """Use fresh data when the fetch worked; otherwise fall back to the last good copy on disk."""
    if new is None:
        return _load_json(path, None)
    if new and not sample:
        _save(path, new)
    return new


# ------------------------------------------------------------------ one company

def analyze(co: dict, c: dict, ctx_data: dict, yaml_events: list[dict], cfg: dict, now: pd.Timestamp, mode: str, sample: bool):
    today = now.date()
    key, sym = co["key"], co["ticker"]
    hist_dir = OUT / key
    cur = SYMBOLS.get(co.get("currency", "USD"), co.get("currency", "") + " ")
    daily, hourly = c["daily"], c["hourly"]
    # Yahoo sometimes leaves today's daily bar out; build it from today's hourly bars.
    if not hourly.empty and not daily.empty and hourly.index[-1].date() > daily.index[-1].date():
        day = hourly.index[-1].date()
        hb = hourly[hourly.index.date == day]
        today_bar = pd.DataFrame({"Open": [hb["Open"].iloc[0]], "High": [hb["High"].max()], "Low": [hb["Low"].min()],
                                  "Close": [hb["Close"].iloc[-1]], "Volume": [hb["Volume"].sum()]},
                                 index=pd.DatetimeIndex([pd.Timestamp(day, tz=NY)]))
        daily = pd.concat([daily, today_bar])
    if daily.empty:
        print(f"{sym}: no daily data returned — skipped")
        return None

    daily = ind.add_all(daily, 252)
    hourly = ind.add_all(hourly, 252 * (8.5 if co.get("currency") == "EUR" else 6.5)) if not hourly.empty else hourly
    spot = float(hourly["Close"].iloc[-1]) if not hourly.empty and hourly.index[-1] > daily.index[-1] else float(daily["Close"].iloc[-1])
    prev_close = float(daily["Close"].iloc[-2]) if len(daily) > 1 else spot

    open_m, close_m = HOURS.get(sym, US_HOURS)
    mins = now.hour * 60 + now.minute
    market_open = now.weekday() < 5 and open_m <= mins < close_m and daily.index[-1].date() == today

    news = cached(c.get("news"), hist_dir / "news.json", sample) or []
    analyst_raw = cached(c.get("analysts"), hist_dir / "analysts.json", sample)
    fund = cached(c.get("fundamentals"), hist_dir / "fundamentals.json", sample)
    fda_raw = cached(c.get("fda"), hist_dir / "fda.json", sample)
    # Earnings dates: merge fresh Yahoo dates into the saved list so older reports aren't lost
    earn_saved = _load_json(hist_dir / "earnings.json", [])
    earn_new = c.get("earnings")
    if earn_new:
        merged = {e["date"]: e for e in earn_saved}
        for e in earn_new:
            # drop a saved upcoming date that Yahoo has since moved
            merged = {d: x for d, x in merged.items() if not (x.get("eps_actual") is None and d >= today.isoformat()
                                                              and abs((dt.date.fromisoformat(d) - dt.date.fromisoformat(e["date"])).days) <= 10 and d != e["date"])}
            merged[e["date"]] = {**merged.get(e["date"], {}), **{k: v for k, v in e.items() if v is not None}}
        earnings = sorted(merged.values(), key=lambda e: e["date"])
        if not sample:
            _save(hist_dir / "earnings.json", earnings)
    else:
        earnings = earn_saved

    events = events_for(co, yaml_events, earnings, today)
    upcoming = [e for e in events if e["date"] >= today.isoformat()]
    big = [e for e in upcoming if e["type"] == "earnings" and not (e["date"] == today.isoformat() and e.get("timing") != "after close" and not market_open and mins >= open_m)]
    next_big = big[0] if big else None
    days_to_big = (dt.date.fromisoformat(next_big["date"]) - today).days if next_big else None

    # ---- options
    has_opt = bool(co.get("options")) and c["chain"] is not None and not c["chain"].empty
    chain = opt.prepare_chain(c["chain"], spot, today) if has_opt else pd.DataFrame()
    iv, iv_exp = opt.atm_iv(chain, spot) if has_opt else (None, None)
    iv_hist = _load_json(hist_dir / "iv_history.json", [])
    settled = mins >= 10 * 60  # opening quotes are often stale or wide; wait until 10:00 New York time
    if iv and not sample and mode == "intraday" and market_open and settled:  # only record IV from live market prices
        iv_hist = [h for h in iv_hist if h["date"] != today.isoformat()] + [{"date": today.isoformat(), "iv": round(iv, 4)}]
        iv_hist = iv_hist[-400:]
    hist_vals = [h["iv"] for h in iv_hist[-252:]]
    iv_rank = None
    if iv and len(hist_vals) >= 20 and max(hist_vals) > min(hist_vals):
        iv_rank = (iv - min(hist_vals)) / (max(hist_vals) - min(hist_vals)) * 100
    rv = _num(daily["rvol20"].iloc[-1], 4)

    em_date = dt.date.fromisoformat(next_big["date"]) if next_big and days_to_big is not None and days_to_big <= 45 else None
    if em_date and next_big.get("timing") == "after close":
        em_date = em_date + dt.timedelta(days=1)  # the reaction happens the next trading day
    exp_move = opt.expected_move(chain, spot, em_date) if has_opt else None
    flow = opt.flow(chain) if has_opt else {}

    em_hist = _load_json(hist_dir / "expected_moves.json", {})
    if exp_move and next_big and em_date and mode == "intraday" and market_open and settled and not sample:
        before_event = today < dt.date.fromisoformat(next_big["date"]) or next_big.get("timing") == "after close"
        if before_event:
            em_hist[next_big["date"]] = {"pct": exp_move["pct"], "dollars": exp_move["dollars"],
                                         "expiry": exp_move["expiry"], "recorded": now.isoformat(timespec="minutes")}

    # ---- signals
    direction = signals.direction(daily, hourly)
    vol = signals.volatility_verdict(iv, rv, iv_rank, days_to_big) if has_opt else {"verdict": "n/a", "iv_rv_ratio": None, "notes": []}
    stance = signals.stance(direction["score"], vol["verdict"] if has_opt else "fair")
    if not has_opt:
        lab = direction["label"]
        stance = {"action": {"Bullish": "Trend and momentum point up", "Bearish": "Trend and momentum point down",
                             "Leaning bullish": "Leaning bullish — wait for confirmation",
                             "Leaning bearish": "Leaning bearish — watch for weakness"}.get(lab, "No clear signal — wait"),
                  "detail": "There are no US-listed options on this stock, so this reads the stock's trend only. "
                            + ("Signals line up strongly in one direction." if abs(direction["score"]) >= 40 else
                               "Some signals point one way but not enough agree yet." if abs(direction["score"]) >= 20 else
                               "Signals are mixed; waiting is a valid choice.")}
    calls = opt.suggest(chain, "call", cfg, events, today, sym) if has_opt else []
    puts = opt.suggest(chain, "put", cfg, events, today, sym) if has_opt else []

    # ---- strong-signal log + outcomes (recorded for the dashboard; nothing is sent)
    state = _load_json(hist_dir / "state.json", {})
    log = _load_json(hist_dir / "signals.json", [])
    closes = daily["Close"]
    for e in log:
        if e.get("price") and e.get("direction"):
            after = closes[closes.index.date > dt.date.fromisoformat(e["time"][:10])]
            for n in (1, 5, 10):
                k = f"after_{n}d"
                if e.get(k) is None and len(after) >= n:
                    ch = (float(after.iloc[n - 1]) / e["price"] - 1) * 100
                    e[k] = round(ch, 2)
                    e[f"right_{n}d"] = (ch > 0) == (e["direction"] == "up")
    score, label = direction["score"], direction["label"]
    strong = abs(score) >= cfg["signal_min_score"]
    new_signal = False
    if market_open and strong and state.get("last_signal_label") != label and not sample:
        log.append({"time": now.isoformat(timespec="minutes"), "label": label, "score": score,
                    "price": round(spot, 2), "direction": "up" if score > 0 else "down", "headline": stance["action"]})
        state["last_signal_label"] = label
        new_signal = True
    if not strong and abs(score) < cfg["signal_min_score"] * 0.5:
        state["last_signal_label"] = None  # re-arm once things calm down
    log = log[-300:]
    graded = [e for e in log if e.get("right_5d") is not None]
    track = {"signals": len(log), "graded_5d": len(graded),
             "right_5d_pct": round(sum(e["right_5d"] for e in graded) / len(graded) * 100) if graded else None}

    # ---- market context and relative strength
    ctx = {}
    for csym, cname in cfg.get("context_tickers", {}).items():
        d = ctx_data.get(csym)
        if d is not None and len(d) > 1:
            ctx[csym] = {"name": cname, "last": _num(d["Close"].iloc[-1], 4 if csym.endswith("=X") else 2),
                         "change_pct": _num((d["Close"].iloc[-1] / d["Close"].iloc[-2] - 1) * 100),
                         "change_20d_pct": pct_change(d["Close"], 20)}
            if csym in ("IHI", "SPY", "EURUSD=X") and len(d) > 30:
                j = pd.concat([daily["Close"].pct_change(), d["Close"].pct_change()], axis=1, join="inner").dropna().tail(60)
                if len(j) > 20:
                    ctx[csym]["corr_60d"] = _num(j.corr().iloc[0, 1])
    my20, my60 = pct_change(closes, 20), pct_change(closes, 60)
    rel = {"chg_20d": my20, "chg_60d": my60}
    for csym, k in (("IHI", "sector"), ("SPY", "market")):
        d = ctx_data.get(csym)
        if d is not None and len(d) > 61 and my20 is not None:
            rel[f"vs_{k}_20d"] = _num(my20 - pct_change(d["Close"], 20))
            rel[f"vs_{k}_60d"] = _num(my60 - pct_change(d["Close"], 60))

    result = {
        "generated": now.isoformat(timespec="minutes"), "mode": mode, "market_open": market_open,
        "market_closed": not market_open, "source": "", "key": key, "ticker": sym, "name": co["name"],
        "short_name": co["short"], "exchange": co.get("exchange", ""), "currency": co.get("currency", "USD"),
        "currency_symbol": cur, "has_options": has_opt, "options_listed": bool(co.get("options")),
        "price": round(spot, 2), "prev_close": round(prev_close, 2), "change_pct": round((spot / prev_close - 1) * 100, 2),
        "high_52w": _num(daily["High"].tail(252).max()), "low_52w": _num(daily["Low"].tail(252).min()),
        "chg_ytd_pct": _num((spot / float(closes[closes.index.year < today.year].iloc[-1]) - 1) * 100) if (closes.index.year < today.year).any() else None,
        "direction": direction,
        "volatility": vol | {"atm_iv": _num(iv * 100 if iv else None, 1), "atm_iv_expiry": iv_exp,
                             "realized_vol": _num(rv * 100 if rv else None, 1), "iv_rank": _num(iv_rank, 0),
                             "iv_history_days": len(hist_vals)},
        "stance": stance, "expected_move": exp_move, "flow": flow, "suggestions": {"calls": calls, "puts": puts},
        "levels": ind.support_resistance(daily),
        "daily_snapshot": snapshot(daily), "hourly_snapshot": snapshot(hourly) if not hourly.empty else None,
        "events": [e | {"days": (dt.date.fromisoformat(e["date"]) - today).days} for e in events
                   if -7 <= (dt.date.fromisoformat(e["date"]) - today).days <= 120],
        "next_big_event": next_big | {"days": days_to_big} if next_big else None,
        "context": ctx, "relative": rel,
        "backtest": backtest.all_tests(daily, hourly, cfg["signal_min_score"], sym),
        "track_record": track, "signal_min_score": cfg["signal_min_score"],
        "daily": bars(daily.tail(504), False), "hourly": bars(hourly.tail(8 * 30), True) if not hourly.empty else [],
        "iv_history": iv_hist[-252:],
        "signal_grades": backtest.grade_all(daily, hourly, sym),
        "news": news[:8],
        "vol_history": [{"t": ts.strftime("%Y-%m-%d"), "rv": _num(v * 100, 1)} for ts, v in daily["rvol20"].tail(504).items() if pd.notna(v)],
        "chain": opt.compact_chain(chain, spot) if has_opt else [], "rate": opt.RATE, "today": today.isoformat(),
        "fundamentals": fund, "fda": trackers.fda(fda_raw, today), "analysts": trackers.analysts(analyst_raw, spot),
    }
    moves = eventmoves.history(daily, earnings, em_hist, today, co["short"])
    result["event_moves"] = {"rows": moves[:16], "summary": eventmoves.summarize(moves)}
    recent = [e | {"days": (dt.date.fromisoformat(e["date"]) - today).days} for e in events
              if e["type"] == "earnings" and -2 <= (dt.date.fromisoformat(e["date"]) - today).days <= 0
              and not (e["date"] == today.isoformat() and (e.get("timing") == "after close" or mins < open_m))]
    result["today_paragraph"] = summary.paragraph(result, mode, today, recent[-1] if recent else None)
    weeks = weekly.build(daily, events, log, iv_hist, today, name=co["short"], sym=cur)

    if not sample:
        _save(hist_dir / "signals.json", log)
        _save(hist_dir / "state.json", state)
        _save(hist_dir / "iv_history.json", iv_hist, compact=True)
        _save(hist_dir / "expected_moves.json", em_hist)
    print(f"{sym}: {cur}{spot:.2f}  {label} ({score:+d})  options {vol['verdict']}  new strong signal: {new_signal}")
    return result, weeks, daily


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--mode", choices=["auto", "intraday", "summary"], default="auto")
    a = ap.parse_args()

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    now = pd.Timestamp.now(tz=NY)
    today = now.date()
    OUT.mkdir(parents=True, exist_ok=True)
    mode = a.mode
    if mode == "auto":
        mins = now.hour * 60 + now.minute
        mode = "summary" if mins >= 16 * 60 + 10 or mins < 3 * 60 else "intraday"

    data = fetch.fetch_sample(cfg) if a.sample else fetch.fetch_live(cfg)
    yaml_events = load_yaml_events(today)
    overview, closes = [], {}
    for co in cfg["companies"]:
        c = data["companies"].get(co["key"])
        if not c:
            continue
        try:
            out = analyze(co, c, data["context"], yaml_events, cfg, now, mode, a.sample)
        except Exception as e:  # one company failing shouldn't stop the others
            import traceback
            traceback.print_exc()
            print(f"{co['ticker']} failed: {e}")
            continue
        if not out:
            continue
        r, weeks, daily = out
        r["source"] = data["source"]
        _save(OUT / f"{co['key']}.json", r, compact=True)
        _save(OUT / f"{co['key']}_weekly.json", {"generated": r["generated"], "source": data["source"], "key": co["key"],
                                                 "name": co["short"], "currency_symbol": r["currency_symbol"], "weeks": weeks}, compact=True)
        closes[co["key"]] = daily["Close"]
        nb = r["next_big_event"]
        f = r.get("fundamentals") or {}
        overview.append({
            "key": co["key"], "ticker": co["ticker"], "name": co["name"], "short": co["short"],
            "currency_symbol": r["currency_symbol"], "currency": r["currency"], "has_options": r["has_options"],
            "price": r["price"], "change_pct": r["change_pct"], "market_open": r["market_open"],
            "score": r["direction"]["score"], "label": r["direction"]["label"], "stance": r["stance"]["action"],
            "options_verdict": r["volatility"]["verdict"], "iv": r["volatility"]["atm_iv"], "iv_rank": r["volatility"]["iv_rank"],
            "next_earnings": {"date": nb["date"], "days": nb["days"], "timing": nb.get("timing")} if nb else None,
            "avg_earnings_move": r["event_moves"]["summary"].get("earnings_avg_abs_move"),
            "chg_20d": r["relative"].get("chg_20d"), "chg_ytd": r.get("chg_ytd_pct"),
            "vs_sector_20d": r["relative"].get("vs_sector_20d"),
            "high_52w": r["high_52w"], "low_52w": r["low_52w"],
            "analyst_upside": (r.get("analysts") or {}).get("upside_mean_pct"),
            "analyst_rating": (r.get("analysts") or {}).get("rating_text"),
            "fda": (r.get("fda") or {}).get("summary"),
            "valuation": {k: f.get(k) for k in ("market_cap", "pe", "forward_pe", "ps", "ev_ebitda", "div_yield", "beta",
                                                 "revenue_growth", "op_margin", "financial_currency")},
            "sparkline": [_num(x) for x in daily["Close"].tail(30)],
        })

    # Peer comparison: every company plus the sector and market ETFs, on common trading days
    cols = dict(closes)
    for csym, k in (("IHI", "ihi"), ("SPY", "spy")):
        d = data["context"].get(csym)
        if d is not None and not d.empty:
            cols[k] = d["Close"]
    compare = []
    if cols:
        df = pd.DataFrame({k: v.groupby(v.index.date).last() for k, v in cols.items()}).sort_index().ffill(limit=3)
        df = df.dropna(how="all").tail(504)
        compare = [{"t": d.isoformat(), **{k: _num(r[k]) for k in df.columns}} for d, r in df.iterrows()]
    eurusd = data["context"].get("EURUSD=X")
    _save(OUT / "overview.json", {
        "generated": now.isoformat(timespec="minutes"), "source": data["source"], "mode": mode,
        "companies": overview, "compare": compare,
        "eurusd": _num(eurusd["Close"].iloc[-1], 4) if eurusd is not None and not eurusd.empty else None,
    }, compact=True)
    print(f"done: {len(overview)} companies")


if __name__ == "__main__":
    main()
