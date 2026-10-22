"""Download prices, option chains, earnings dates, headlines, analyst data, fundamentals (Yahoo Finance via
yfinance) and FDA clearances/recalls (openFDA) for each company.

Also provides a --sample mode that generates realistic fake data so the dashboard can be tested without
network access.
"""
from __future__ import annotations

import datetime as dt
import math

import numpy as np
import pandas as pd

NY = "America/New_York"
UA = {"User-Agent": "Mozilla/5.0 (medtech-signals dashboard)"}


def _clean(df: pd.DataFrame, daily: bool = False) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
    if daily:
        # Daily bars are stamped at midnight in the exchange's own time zone (Frankfurt for SHL.DE).
        # Keep the exchange's calendar date; converting to New York would shift them to the previous day.
        days = [ts.date() for ts in df.index]
        df = df.copy()
        df.index = pd.DatetimeIndex([pd.Timestamp(d) for d in days]).tz_localize(NY)
        return df[~df.index.duplicated(keep="last")]
    if df.index.tz is None:
        df.index = df.index.tz_localize(NY)
    else:
        df.index = df.index.tz_convert(NY)
    return df


def fetch_live(cfg: dict) -> dict:
    import yfinance as yf

    start = cfg["history_start"]
    context = {}
    for c in cfg.get("context_tickers", {}):
        try:
            context[c] = _clean(yf.Ticker(c).history(start=start, interval="1d", auto_adjust=False), daily=True)
        except Exception as e:  # context is nice-to-have
            print(f"context {c} failed: {e}")
            context[c] = _clean(None)

    companies = {}
    for co in cfg["companies"]:
        sym = co["ticker"]
        print(f"---- {sym}")
        t = yf.Ticker(sym)
        daily = _clean(t.history(start=start, interval="1d", auto_adjust=False), daily=True)
        hourly = _clean(t.history(period="60d", interval="60m", auto_adjust=False))
        chain = fetch_chain(t, cfg) if co.get("options") else pd.DataFrame()
        info = _info(t)
        companies[co["key"]] = {
            "daily": daily, "hourly": hourly, "chain": chain,
            "news": fetch_news(t, keywords=co.get("news_keywords", []) + cfg.get("sector_keywords", [])),
            "analysts": fetch_analysts(t, info), "fundamentals": fundamentals(info),
            "earnings": fetch_earnings(t), "fda": fetch_fda(co.get("fda_names", [])),
        }
    return {"companies": companies, "context": context, "source": "Yahoo Finance; openFDA"}


def _info(t) -> dict:
    try:
        return t.info or {}
    except Exception as e:
        print(f"info failed: {e}")
        return {}


def fetch_chain(t, cfg: dict) -> pd.DataFrame:
    chains = []
    try:
        expiries = list(t.options)[: cfg.get("option_expirations", 6)]
    except Exception as e:
        print(f"option expiries failed: {e}")
        expiries = []
    for exp in expiries:
        try:
            oc = t.option_chain(exp)
        except Exception as e:
            print(f"chain {exp} failed: {e}")
            continue
        for kind, frame in (("call", oc.calls), ("put", oc.puts)):
            f = frame.copy()
            f["type"] = kind
            f["expiry"] = exp
            chains.append(f)
    print(f"options: {len(expiries)} expirations")
    return pd.concat(chains, ignore_index=True) if chains else pd.DataFrame()


# ---------------------------------------------------------------- earnings dates

def fetch_earnings(t) -> list[dict] | None:
    """Past and upcoming earnings dates with the time of day (before the open vs after the close). None on failure."""
    rows = []
    try:
        ed = t.get_earnings_dates(limit=24)
        if ed is not None and len(ed):
            for ts, r in ed.iterrows():
                ts = pd.Timestamp(ts)
                local = ts.tz_convert(NY) if ts.tzinfo else ts.tz_localize(NY)
                rows.append({"date": local.date().isoformat(), "time_et": local.strftime("%H:%M"),
                             "timing": "before open" if local.hour < 12 else "after close" if local.hour >= 16 else "during market",
                             "eps_est": _num_or_none(r.get("EPS Estimate")), "eps_actual": _num_or_none(r.get("Reported EPS")),
                             "surprise_pct": _num_or_none(r.get("Surprise(%)"))})
    except Exception as e:
        print(f"earnings dates failed: {e}")
    if not rows:
        try:  # at least get the next date
            cal = t.calendar or {}
            ds = cal.get("Earnings Date") if isinstance(cal, dict) else None
            for d in ds or []:
                rows.append({"date": pd.Timestamp(d).date().isoformat(), "time_et": None, "timing": "unknown",
                             "eps_est": _num_or_none(cal.get("Earnings Average")), "eps_actual": None, "surprise_pct": None})
        except Exception as e:
            print(f"earnings calendar failed: {e}")
    uniq = {r["date"]: r for r in sorted(rows, key=lambda r: r["date"])}
    print(f"earnings dates: {len(uniq)}")
    return list(uniq.values()) or None


# ---------------------------------------------------------------- FDA (openFDA, free, no key)

def _fda_get(endpoint: str, search: str, sort: str, limit: int) -> list[dict]:
    import requests
    r = requests.get(f"https://api.fda.gov/device/{endpoint}.json",
                     params={"search": search, "sort": sort, "limit": limit}, timeout=25, headers=UA)
    if r.status_code == 404:  # openFDA answers 404 when nothing matches
        return []
    r.raise_for_status()
    return r.json().get("results", [])


def _fda_date(s) -> str | None:
    s = str(s or "").strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s[:10] or None


def fetch_fda(names: list[str]) -> dict | None:
    """Recent 510(k) clearances and recalls for the company's device makers. None if openFDA couldn't be reached."""
    if not names:
        return {"clearances": [], "recalls": []}
    since = (dt.date.today() - dt.timedelta(days=730)).strftime("%Y%m%d")
    today = dt.date.today().strftime("%Y%m%d")
    out, ok = {}, False
    try:
        q = "(" + " ".join(f'applicant:"{n}"' for n in names) + ")"
        res = _fda_get("510k", q, "decision_date:desc", 40)
        out["clearances"] = [{"date": _fda_date(x.get("decision_date")), "k_number": x.get("k_number"),
                              "device": (x.get("device_name") or "").strip(), "applicant": x.get("applicant"),
                              "decision": x.get("decision_description") or x.get("decision_code"),
                              "panel": x.get("advisory_committee_description")} for x in res]
        ok = True
    except Exception as e:
        print(f"fda 510k failed: {e}")
    try:
        q = "(" + " ".join(f'recalling_firm:"{n}"' for n in names) + f") AND report_date:[{since} TO {today}]"
        res = _fda_get("enforcement", q, "report_date:desc", 100)
        out["recalls"] = [{"date": _fda_date(x.get("report_date")), "started": _fda_date(x.get("recall_initiation_date")),
                           "classification": x.get("classification"), "status": x.get("status"),
                           "firm": x.get("recalling_firm"), "event_id": x.get("event_id"),
                           "recall_number": x.get("recall_number"),
                           "product": (x.get("product_description") or "").strip()[:220],
                           "reason": (x.get("reason_for_recall") or "").strip()[:300]} for x in res]
        ok = True
    except Exception as e:
        print(f"fda recalls failed: {e}")
    print(f"fda: {len(out.get('clearances', []))} clearances, {len(out.get('recalls', []))} recall records")
    return out if ok else None


# ---------------------------------------------------------------- news

def _parse_news_items(raw) -> list[dict]:
    out = []
    for n in raw or []:
        c = n.get("content") if isinstance(n, dict) and isinstance(n.get("content"), dict) else n
        if not isinstance(c, dict):
            continue
        title = c.get("title")
        link = ((c.get("clickThroughUrl") or {}).get("url") or (c.get("canonicalUrl") or {}).get("url") or c.get("link"))
        pub = (c.get("provider") or {}).get("displayName") or c.get("publisher") or ""
        when = c.get("pubDate") or c.get("displayTime")
        if not when and c.get("providerPublishTime"):
            when = dt.datetime.fromtimestamp(c["providerPublishTime"], dt.timezone.utc).isoformat()
        if title and link and str(link).startswith("http"):
            out.append({"title": title, "url": link, "publisher": pub, "time": when})
    return out


def _news_rss(symbol: str) -> list[dict]:
    """Yahoo's per-ticker RSS headline feed (a different service from the yfinance news call)."""
    import email.utils
    import xml.etree.ElementTree as ET

    import requests
    r = requests.get("https://feeds.finance.yahoo.com/rss/2.0/headline",
                     params={"s": symbol, "region": "US", "lang": "en-US"}, timeout=20, headers=UA)
    r.raise_for_status()
    out = []
    for it in ET.fromstring(r.content).iter("item"):
        title, link = (it.findtext("title") or "").strip(), (it.findtext("link") or "").strip()
        when = it.findtext("pubDate")
        try:
            when = email.utils.parsedate_to_datetime(when).isoformat() if when else None
        except Exception:
            pass
        src = it.find("source")
        if title and link.startswith("http"):
            out.append({"title": title, "url": link, "publisher": (src.text if src is not None and src.text else "Yahoo Finance"), "time": when})
    return out


def _rank(items: list[dict], keywords: list[str]) -> list[dict]:
    """Headlines that mention the company or medtech topics first; general market stories after."""
    kw = [k.lower() for k in keywords]
    rel = [x for x in items if any(k in x["title"].lower() for k in kw)]
    return rel + [x for x in items if x not in rel]


def fetch_news(ticker, keywords: list[str], limit: int = 8) -> list[dict] | None:
    """Latest headlines. Tries several Yahoo sources; returns None only if all of them fail (keep the cache)."""
    got_any_response = False
    for name in ("news", "all", "press releases"):
        try:
            ticker._news = []  # yfinance caches the first answer; clear it between tabs
            items = _parse_news_items(ticker.get_news(count=limit + 6, tab=name))
            got_any_response = True
            print(f"news ({name}): {len(items)} headlines")
            if items:
                return _rank(items, keywords)[:limit]
        except Exception as e:
            print(f"news ({name}) failed: {e}")
    try:
        items = _news_rss(ticker.ticker)
        got_any_response = True
        print(f"news (rss): {len(items)} headlines")
        if items:
            return _rank(items, keywords)[:limit]
    except Exception as e:
        print(f"news (rss) failed: {e}")
    return [] if got_any_response else None


# ---------------------------------------------------------------- analysts & fundamentals

def _num_or_none(x):
    try:
        f = float(x)
        return None if f != f or math.isinf(f) else f
    except (TypeError, ValueError):
        return None


def fetch_analysts(ticker, info: dict) -> dict | None:
    """Price targets, rating mix and recent rating changes (Yahoo). None if nothing came back."""
    out = {}
    try:
        pt = ticker.get_analyst_price_targets() or {}
        out["targets"] = {k: _num_or_none(pt.get(k)) for k in ("low", "mean", "median", "high", "current")}
    except Exception as e:
        print(f"analyst targets failed: {e}")
    out["count"] = info.get("numberOfAnalystOpinions")
    out["rating_key"] = info.get("recommendationKey")
    out["rating_mean"] = _num_or_none(info.get("recommendationMean"))
    t = out.setdefault("targets", {})
    for k, ik in (("low", "targetLowPrice"), ("mean", "targetMeanPrice"), ("median", "targetMedianPrice"), ("high", "targetHighPrice")):
        if t.get(k) is None:
            t[k] = _num_or_none(info.get(ik))
    try:
        rec = ticker.get_recommendations_summary()
        if rec is not None and len(rec):
            row = rec.iloc[0]
            out["mix"] = {k: int(row.get(k, 0) or 0) for k in ("strongBuy", "buy", "hold", "sell", "strongSell")}
    except Exception as e:
        print(f"analyst mix failed: {e}")
    try:
        ud = ticker.get_upgrades_downgrades()
        if ud is not None and len(ud):
            ud = ud.reset_index()
            ud = ud.sort_values(ud.columns[0], ascending=False).head(10)
            out["changes"] = [{
                "date": str(r.get("GradeDate", r.iloc[0]))[:10], "firm": r.get("Firm", ""),
                "to": r.get("ToGrade", ""), "from": r.get("FromGrade", ""), "action": r.get("Action", ""),
                "target": _num_or_none(r.get("currentPriceTarget")), "prior_target": _num_or_none(r.get("priorPriceTarget")),
            } for _, r in ud.iterrows()]
    except Exception as e:
        print(f"analyst changes failed: {e}")
    has = any(v is not None for v in (out.get("targets") or {}).values()) or out.get("mix") or out.get("changes")
    print(f"analysts: {'ok' if has else 'nothing returned'}")
    return out if has else None


def fundamentals(info: dict) -> dict | None:
    keys = {"market_cap": "marketCap", "pe": "trailingPE", "forward_pe": "forwardPE", "ps": "priceToSalesTrailing12Months",
            "ev_ebitda": "enterpriseToEbitda", "div_yield": "dividendYield", "beta": "beta", "revenue": "totalRevenue",
            "revenue_growth": "revenueGrowth", "profit_margin": "profitMargins", "op_margin": "operatingMargins",
            "debt_to_equity": "debtToEquity", "free_cash_flow": "freeCashflow",
            "high_52w": "fiftyTwoWeekHigh", "low_52w": "fiftyTwoWeekLow", "short_pct_float": "shortPercentOfFloat"}
    out = {k: _num_or_none(info.get(v)) for k, v in keys.items()}
    out["financial_currency"] = info.get("financialCurrency")
    # Yahoo has reported dividendYield both as a fraction (0.012) and as a percent (1.2); normalize to percent.
    if out["div_yield"] is not None and out["div_yield"] < 0.2:
        out["div_yield"] *= 100
    return out if any(v is not None for k, v in out.items() if k != "financial_currency") else None


# ---------------------------------------------------------------- sample data

def _sample_path(n: int, start: float, vol: float, seed: int, drift: float = 0.0003) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return start * np.exp(np.cumsum(rng.normal(drift, vol, n)))


def _sample_company(co: dict, cfg: dict, end: pd.Timestamp, seed: int) -> dict:
    days = pd.bdate_range(cfg["history_start"], end).tz_localize(NY)
    n = len(days)
    base = {"GEHC": 72, "PHG": 24, "SHL.DE": 50}.get(co["ticker"], 50)
    close = _sample_path(n, base, 0.016, seed)
    rng = np.random.default_rng(seed + 1)
    openp = close * (1 + rng.normal(0, 0.006, n))
    high = np.maximum(openp, close) * (1 + abs(rng.normal(0, 0.008, n)))
    low = np.minimum(openp, close) * (1 - abs(rng.normal(0, 0.008, n)))
    vol = rng.integers(2e6, 6e6, n)
    daily = pd.DataFrame({"Open": openp, "High": high, "Low": low, "Close": close, "Volume": vol}, index=days)

    hrs = []
    for d in days[-40:]:
        for h in range(7):
            hrs.append(d + pd.Timedelta(hours=9, minutes=30) + pd.Timedelta(hours=h))
    hidx = pd.DatetimeIndex(hrs)
    hclose = _sample_path(len(hidx), close[-40], 0.005, seed + 2, 0)
    hclose *= close[-1] / hclose[-1]
    hopen = np.roll(hclose, 1); hopen[0] = hclose[0]
    hourly = pd.DataFrame({"Open": hopen, "High": np.maximum(hopen, hclose) * 1.002, "Low": np.minimum(hopen, hclose) * 0.998,
                           "Close": hclose, "Volume": rng.integers(2e5, 9e5, len(hidx))}, index=hidx)

    spot = close[-1]
    today = end.date()
    rows = []
    if co.get("options"):
        exps, d = [], today
        while len(exps) < 2:
            d += dt.timedelta(days=1)
            if d.weekday() == 4:
                exps.append(d)
        exps += [x for x in _third_fridays(today, 6) if x > exps[1]][:4]
        from .options import bs_price
        step = 1 if spot < 40 else 2.5
        for e in exps:
            T = max((e - today).days, 1) / 365
            for k in np.arange(round(spot * 0.7 / step) * step, spot * 1.3, step):
                for kind in ("call", "put"):
                    iv = 0.27 + 0.18 * abs(math.log(k / spot)) + (0.06 if (e - today).days < 12 else 0)
                    p = bs_price(spot, k, T, iv, kind)
                    spr = max(0.05, p * 0.05)
                    oi = int(max(0, 3000 * math.exp(-abs(k - spot) / (spot * 0.08)) * rng.uniform(0.5, 1.5)))
                    rows.append({"contractSymbol": f"{co['ticker']}{e:%y%m%d}{kind[0].upper()}{int(k * 1000):08d}",
                                 "strike": float(k), "lastPrice": p, "bid": max(0, p - spr / 2), "ask": p + spr / 2,
                                 "volume": int(oi * rng.uniform(0.02, 0.4)), "openInterest": oi,
                                 "impliedVolatility": iv, "type": kind, "expiry": e.isoformat()})
    now = pd.Timestamp.now(tz="UTC")
    news = [{"title": f"Sample headline {i + 1} about {co['short']} (test data)", "url": "https://example.com/",
             "publisher": ["Reuters", "Bloomberg", "MedTech Dive"][i % 3], "time": (now - pd.Timedelta(hours=7 * i + 2)).isoformat()}
            for i in range(6)]
    # quarterly earnings, before the open, roughly every 91 days back from an upcoming date
    nxt = today + dt.timedelta(days=6 + seed % 10)
    earnings = []
    for q in range(-14, 2):
        d = nxt + dt.timedelta(days=91 * q)
        while d.weekday() > 4:
            d += dt.timedelta(days=1)
        past = d <= today
        est = round(1.0 + 0.02 * q, 2)
        earnings.append({"date": d.isoformat(), "time_et": "06:30", "timing": "before open", "eps_est": est,
                         "eps_actual": round(est * rng.uniform(0.93, 1.1), 2) if past else None,
                         "surprise_pct": None})
    for e in earnings:
        if e["eps_actual"]:
            e["surprise_pct"] = round((e["eps_actual"] / e["eps_est"] - 1) * 100, 1)
    fda = {"clearances": [{"date": (today - dt.timedelta(days=9 * i + 3)).isoformat(), "k_number": f"K26{1234 + i}",
                           "device": ["CT scanner software update (sample)", "Ultrasound system (sample)", "MRI coil (sample)",
                                      "Patient monitor (sample)"][i % 4], "applicant": co["fda_names"][0],
                           "decision": "Substantially Equivalent", "panel": "Radiology"} for i in range(6)],
           "recalls": [{"date": (today - dt.timedelta(days=40 * i + 11)).isoformat(), "started": None,
                        "classification": ["Class II", "Class I", "Class II", "Class III"][i % 4], "status": "Ongoing",
                        "firm": co["fda_names"][0], "event_id": str(90000 + i), "recall_number": f"Z-{1000 + i}-2026",
                        "product": "Sample device (test data)", "reason": "Sample reason (test data)."} for i in range(4)]}
    analysts = {"targets": {"low": round(spot * 0.8, 2), "mean": round(spot * 1.1, 2), "median": round(spot * 1.08, 2),
                            "high": round(spot * 1.35, 2), "current": round(spot, 2)},
                "count": 20, "rating_key": "buy", "rating_mean": 2.2,
                "mix": {"strongBuy": 4, "buy": 8, "hold": 7, "sell": 1, "strongSell": 0},
                "changes": [{"date": (today - dt.timedelta(days=3)).isoformat(), "firm": "Sample Securities", "to": "Buy", "from": "Hold",
                             "action": "up", "target": round(spot * 1.2), "prior_target": round(spot * 1.05)}]}
    fund = {"market_cap": spot * {"GEHC": 457e6, "PHG": 930e6, "SHL.DE": 1.13e9}.get(co["ticker"], 1e9),
            "pe": 18.5 + seed, "forward_pe": 15.0 + seed, "ps": 1.9, "ev_ebitda": 12.0, "div_yield": 0.2 + seed * 0.6,
            "beta": 1.0, "revenue": 20e9, "revenue_growth": 0.03, "profit_margin": 0.09, "op_margin": 0.14,
            "debt_to_equity": 90.0, "free_cash_flow": 1.5e9, "high_52w": float(daily["High"].tail(252).max()),
            "low_52w": float(daily["Low"].tail(252).min()), "short_pct_float": 0.015, "financial_currency": co["currency"]}
    return {"daily": daily, "hourly": hourly, "chain": pd.DataFrame(rows), "news": news, "analysts": analysts,
            "fundamentals": fund, "earnings": earnings, "fda": fda}


def fetch_sample(cfg: dict) -> dict:
    end = pd.Timestamp.now(tz=NY).normalize().tz_localize(None)
    companies = {co["key"]: _sample_company(co, cfg, end, i + 1) for i, co in enumerate(cfg["companies"])}
    context = {}
    for i, c in enumerate(cfg.get("context_tickers", {})):
        base = {"IHI": 60, "SPY": 600, "^VIX": 17, "EURUSD=X": 1.12}.get(c, 100)
        cd = pd.bdate_range(cfg["history_start"], end).tz_localize(NY)
        cc = _sample_path(len(cd), base, 0.01, 20 + i)
        context[c] = pd.DataFrame({"Open": cc, "High": cc, "Low": cc, "Close": cc, "Volume": 0}, index=cd)
    return {"companies": companies, "context": context, "source": "SAMPLE DATA (not real)"}


def _third_fridays(start: dt.date, count: int) -> list[dt.date]:
    out = []
    y, m = start.year, start.month
    while len(out) < count:
        first = dt.date(y, m, 1)
        fri = first + dt.timedelta(days=(4 - first.weekday()) % 7 + 14)
        if fri >= start:
            out.append(fri)
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out
