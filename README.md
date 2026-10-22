# MedTech Signals

A dashboard that watches three medical equipment makers and their options, and tells you when conditions favor **buying or selling options**, with the reasons:

| Company | Ticker | Options analysis |
|---|---|---|
| GE HealthCare | GEHC (Nasdaq) | Yes |
| Philips | PHG (NYSE ADR) | Yes |
| Siemens Healthineers | SHL.DE (Xetra, euros) | No US-listed options, so the stock only |

**Open the dashboard:** https://dyunck.github.io/mdec/
**Tutorial:** https://dyunck.github.io/mdec/guide.html · **Weekly recap:** https://dyunck.github.io/mdec/weekly.html

> This tool never places trades and never sends messages. It only analyzes and shows results on the dashboard. It is not financial advice. Signals can be wrong, and options can lose 100% of what you pay.

## What it does

Built on the same engine as the SPCX Signals app, for each company:

- Direction score (−100 to +100) from daily and hourly indicators, with every reason listed
- Options cheap or expensive (implied vs. actual volatility, IV rank), expected move, contract suggestions, "what if" payoff calculator, option chain heat map, put/call ratio
- Plain-English "today in one paragraph" and a weekly recap per company
- Backtest and per-signal grading on each stock's history since January 2023, plus a live log of strong signals and how they turned out

Medtech-specific additions:

- **Company switcher and "at a glance" cards** for all three side by side
- **Earnings tracker**: every report since 2023 with EPS estimate vs. actual and the stock's reaction (dates pulled from Yahoo automatically; these companies report before the US open)
- **FDA activity**: 510(k) clearances and recalls (Class I = most serious) from the FDA's openFDA database
- **Peer comparison chart** vs. the medical-device ETF (IHI) and S&P 500, and a **valuation table** (P/E, EV/EBITDA, margins, dividend yield)
- Industry events such as RSNA (radiology's big trade show) in the calendar

## Schedule

GitHub Actions runs it hourly during US market hours (Mon–Fri), twice during European trading for Siemens Healthineers, and once after the US close. Data: Yahoo Finance (≈15 min delay) and openFDA.

## Customize (edit on GitHub with the pencil icon)

| File | What to change |
|---|---|
| `config.yaml` | Companies, FDA name matching, strong-signal level (`signal_min_score`), contract filters |
| `data/events.yaml` | Extra events (earnings backups, RSNA, Fed meetings); `companies: [gehc]` limits one to a company |

Refresh now: **Actions → Update MedTech signals → Run workflow**.

## How the pieces fit

```
app/fetch.py        prices, option chains, earnings dates, news, analysts, fundamentals, openFDA
app/indicators.py   RSI, MACD, moving averages, Bollinger bands, volatility, support/resistance
app/options.py      Greeks, expected move, put/call ratio, contract picks
app/signals.py      direction score, options cheap/expensive, plain-English stance
app/backtest.py     backtest and per-signal grading
app/eventmoves.py   earnings reactions vs. what options priced in
app/trackers.py     FDA activity summary, analyst targets
app/summary.py      the daily paragraph;  app/weekly.py  weekly recaps
app/run.py          runs everything; writes docs/data/overview.json, <company>.json, <company>_weekly.json
docs/               the dashboard (GitHub Pages)
```

Run locally: `pip install -r requirements.txt`, then `python -m app.run` (or `--sample` for fake data without internet).
