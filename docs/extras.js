// Explain-this popovers, option chain heat map, headlines, peer comparison and volatility charts.
(function () {
  const $ = (id) => document.getElementById(id);
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const fmt = (x, d = 2) => Number(x).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
  const pct = (x, d = 1) => (x == null ? "—" : (x > 0 ? "+" : "") + fmt(x, d) + "%");
  const cls = (x) => (x > 0 ? "pos" : x < 0 ? "neg" : "muted");
  let D;

  // ------------------------------------------------------------ explain-this
  const EX = {
    peers: ["At a glance", "All three companies side by side: price, today's change, the direction score and the next earnings date. Tap one to switch the whole page to that company."],
    fda: ["FDA activity", "New 510(k) clearances (permission to sell a new or updated device in the US) and product recalls posted by the FDA. Class I recalls are the most serious (risk of serious harm) and have hit these stocks before, e.g. Philips' 2021 breathing-device recall."],
    valuation: ["Valuation", "P/E = price ÷ yearly earnings per share; forward P/E uses next year's expected earnings. Lower can mean cheaper, or that investors expect less growth. EV/EBITDA compares the whole company's value with its operating profit and is less affected by debt."],
    analysts: ["Analyst price targets", "Where Wall Street analysts think the stock will trade in about 12 months. The bar runs from the lowest to the highest target; the marker shows today's price. Targets are opinions and are often wrong."],
    rating: ["Consensus rating", "The average analyst recommendation on a 1–5 scale: 1 = strong buy, 3 = hold, 5 = sell."],
    today: ["Today in one paragraph", "A plain-English summary written automatically from the numbers on this page each hour. Nothing in it is a prediction or advice."],
    score: ["Direction score", "Adds up points from about a dozen chart signals, from −100 (bearish) to +100 (bullish). ±40 or more counts as a strong signal. It describes current conditions; it doesn't predict the future."],
    why: ["Why", "Every signal that went into the score, sorted by size. Green numbers push toward bullish, red toward bearish. Check \"Which signals have actually worked\" to see how much to trust each one."],
    tf: ["Daily vs. hourly", "The same indicators measured on daily bars (the bigger picture) and hourly bars (the last few days). When the two disagree, signals are less reliable."],
    iv: ["Implied volatility (IV)", "How much movement option prices assume, as a yearly percentage. Higher IV means more expensive options. 30% IV implies a typical move of about ±1.9% per day."],
    realvol: ["Actual volatility", "How much the stock really moved over the last 20 trading days, on the same yearly scale as implied volatility, so the two can be compared."],
    ivratio: ["Implied ÷ actual", "Option prices divided by real movement. Above 1.3× means options are pricey compared with how the stock actually moves; below 0.9× means they're relatively cheap."],
    ivrank: ["IV rank", "Where today's implied volatility sits in its own past range: 0 is the cheapest options have been, 100 the most expensive. It needs 20 trading days of collected history."],
    ivhist: ["Option prices over time", "Implied volatility (what options assume) against actual volatility (what the stock did). Implied usually rises into earnings and drops right after; that drop is the volatility crush."],
    expmove: ["Expected move", "How far the options market thinks the stock could move by a date, worked out from option prices. The stock usually ends up inside this range about two-thirds of the time."],
    contracts: ["Contracts worth a look", "A few options that are easy to trade (tight bid/ask, real open interest) with a delta near 0.45. Starting points to research, not recommendations."],
    mid: ["Mid price", "Halfway between the bid (what buyers pay) and the ask (what sellers want). Prices are per share; one contract covers 100 shares."],
    cost: ["Cost / max loss", "What one contract costs (mid price × 100). If you buy an option, this is the most you can lose."],
    breakeven: ["Breakeven", "Where the stock has to be at expiration for the option to be worth what you paid: strike plus the price for a call, strike minus the price for a put."],
    delta: ["Delta", "How much the option's price moves when the stock moves $1. A 0.45 delta gains about $0.45 per share ($45 per contract) for each $1 rise. It's also a rough chance of finishing in the money."],
    decay: ["Decay per day (theta)", "Roughly how much one contract loses each day just from time passing, if nothing else changes. It speeds up in the last three weeks."],
    spread: ["Bid/ask spread", "The gap between buying and selling prices, as a % of the mid price. Under 5% is good. A 15% spread means you start 15% behind."],
    oi: ["Open interest", "How many of these contracts currently exist. Higher open interest usually means easier, cheaper trading."],
    volume: ["Volume", "How many contracts traded today."],
    calc: ["Payoff calculator", "Estimates an option's value at different stock prices and dates using the Black-Scholes model. Use the sliders to see time decay and volatility crush. Real prices will differ."],
    heatmap: ["Option chain heat map", "Every strike and expiration in one grid. Cells with stronger color have more contracts traded today (volume) or outstanding (open interest), showing where traders are placing their bets."],
    events: ["Upcoming events", "Dates that can move the stock or its option prices: earnings, Fed meetings, monthly options expirations and industry events like RSNA, the big radiology trade show where GE HealthCare, Philips and Siemens Healthineers show new scanners."],
    levels: ["Support and resistance", "Prices where the stock has repeatedly turned around over the past year. Support is where buyers stepped in; resistance is where sellers did. The 52-week high and low are watched by many traders."],
    compare: ["Peer comparison", "Percentage change of all three companies, the US medical-device ETF (IHI) and the S&P 500 (SPY) from the start of the chosen period. If they all move together, the move is about the sector or market, not one company. Siemens Healthineers is measured in euros."],
    eventmoves: ["Earnings tracker", "What the stock actually did after each earnings report, with Wall Street's earnings-per-share estimate vs. the actual number. A beat doesn't always mean the stock rises: guidance (the outlook for the rest of the year) often matters more."],
    putcall: ["Put/call ratio", "Puts traded divided by calls traded. Below 0.7 means traders mostly bet on a rise; above 1.0 means mostly bets on a drop or buying protection."],
    backtest: ["Backtest", "How the scoring rules would have done on this stock's past prices. \"Right direction\" near 50% is a coin flip."],
    grades: ["Signal grades", "Each signal tested on its own against this stock's history. Helpful = right at least 58% of the time with a positive average move. Misleading = wrong more often than right."],
    history: ["Strong-signal history", "Every time the score crossed the strong-signal line during trading hours, with how the stock moved 1, 5 and 10 trading days later."],
    rsi: ["RSI (Relative Strength Index)", "A 0–100 momentum gauge. Above 70 = overbought (a pullback is more likely); below 30 = oversold (a bounce is more likely)."],
    macd: ["MACD", "A momentum indicator from two moving averages. Positive means upward momentum; crossing from negative to positive is a classic buy signal, and the reverse a sell signal."],
    bollinger: ["Bollinger bands", "A band around the 20-bar average, two standard deviations wide. Closing outside the band means the price is stretched and often snaps back."],
    atr: ["Average true range", "The typical size of one bar's high-to-low swing. A rough measure of how much the stock moves in a day (or hour)."],
    sma20: ["20-bar average", "The average closing price over the last 20 bars (days or hours). Price above it is a sign of a short-term uptrend."],
    sma50: ["50-bar average", "The average closing price over the last 50 bars. When the 20-bar average is above the 50-bar, the longer trend is up."],
    volnormal: ["Volume vs. normal", "Today's trading volume compared with the 20-bar average. 2× means twice the usual activity, so something is happening."],
    pe: ["P/E ratio", "Share price divided by the last 12 months' earnings per share. A P/E of 20 means investors pay $20 for each $1 of yearly profit."],
    fpe: ["Forward P/E", "Share price divided by analysts' expected earnings for the next 12 months."],
    divy: ["Dividend yield", "Yearly dividends as a percentage of the share price."],
    beta: ["Beta", "How much the stock tends to move with the overall market. 1.0 = same as the market; below 1 = calmer."],
  };
  // label text on the page -> glossary key
  const LABELS = [
    ["Implied volatility (at the money)", "iv"], ["Actual volatility (20 days)", "realvol"], ["Implied ÷ actual", "ivratio"],
    ["IV rank", "ivrank"], ["Daily score / hourly score", "tf"], ["Expected move", "expmove"], ["Put/call ratio", "putcall"],
    ["Price (mid)", "mid"], ["Cost / max loss", "cost"], ["Breakeven", "breakeven"], ["Delta", "delta"], ["Decay/day", "decay"],
    ["IV", "iv"], ["Spread", "spread"], ["Open int.", "oi"], ["Priced in", "expmove"],
    ["RSI (14)", "rsi"], ["MACD histogram", "macd"], ["Bollinger upper", "bollinger"], ["Bollinger lower", "bollinger"],
    ["Avg true range", "atr"], ["20-bar average", "sma20"], ["50-bar average", "sma50"], ["Volume vs. normal", "volnormal"],
    ["Actual volatility (annual)", "realvol"], ["P/E (last 12 months)", "pe"], ["Forward P/E", "fpe"], ["Dividend yield", "divy"], ["Beta", "beta"],
    ["EV / EBITDA", "valuation"],
  ];
  const btn = (k) => `<button class="ex" data-ex="${k}" aria-label="Explain">i</button>`;
  function decorate(root) {
    (root || document).querySelectorAll("dt, th, #tf td:first-child").forEach((el) => {
      if (el.querySelector(".ex")) return;
      const t = el.textContent.trim();
      const hit = LABELS.find(([label]) => t === label || (label.length > 8 && t.startsWith(label)));
      if (hit) el.insertAdjacentHTML("beforeend", " " + btn(hit[1]));
    });
  }
  const pop = () => $("ex-pop");
  function openPop(b) {
    const e = EX[b.dataset.ex]; if (!e) return;
    const p = pop();
    p.innerHTML = `<strong>${esc(e[0])}</strong><p>${esc(e[1])}</p><button class="ex-close" aria-label="Close">×</button>`;
    p.hidden = false;
    const r = b.getBoundingClientRect(), vw = document.documentElement.clientWidth;
    const w = Math.min(320, vw - 24);
    p.style.width = w + "px";
    p.style.left = Math.max(12, Math.min(r.left + r.width / 2 - w / 2, vw - w - 12)) + "px";
    const below = r.bottom + 8, ph = p.offsetHeight;
    p.style.top = (below + ph > window.innerHeight - 8 && r.top - ph - 8 > 8 ? r.top - ph - 8 : below) + "px";
    p.dataset.for = b.dataset.ex;
  }
  document.addEventListener("click", (ev) => {
    const b = ev.target.closest("button.ex");
    if (b) { ev.preventDefault(); ev.stopPropagation(); if (!pop().hidden && pop().dataset.for === b.dataset.ex) { pop().hidden = true; } else openPop(b); return; }
    if (!ev.target.closest("#ex-pop") || ev.target.closest(".ex-close")) pop().hidden = true;
  }, true);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") pop().hidden = true; });
  window.addEventListener("scroll", () => { if (!pop().hidden) pop().hidden = true; }, { passive: true });

  // ------------------------------------------------------------ heat map
  let hmType = "c", hmMetric = "v";
  const short = (n) => (n >= 10000 ? Math.round(n / 1000) + "k" : n >= 1000 ? (n / 1000).toFixed(1) + "k" : String(n));
  function renderHeatmap() {
    const chain = (D.chain || []).filter((o) => o.t === hmType);
    const el = $("heatmap");
    if (!chain.length) { el.innerHTML = '<tbody><tr><td class="empty">No option data in this update.</td></tr></tbody>'; return; }
    const spot = D.price;
    const exps = [...new Set(chain.map((o) => o.e))].sort();
    const strikes = [...new Set(chain.filter((o) => o.k >= spot * 0.75 && o.k <= spot * 1.25).map((o) => o.k))].sort((a, b) => b - a);
    const map = new Map(chain.map((o) => [o.e + "|" + o.k, o]));
    const val = (o) => (o ? (hmMetric === "v" ? o.v || 0 : o.oi || 0) : 0);
    let max = 0;
    for (const e of exps) for (const k of strikes) max = Math.max(max, val(map.get(e + "|" + k)));
    const atm = strikes.reduce((a, b) => (Math.abs(b - spot) < Math.abs(a - spot) ? b : a), strikes[0]);
    const color = hmType === "c" ? "63,160,120" : "214,84,84";
    const head = `<thead><tr><th>Strike</th>${exps.map((e) => {
      const [y, m, d] = e.split("-").map(Number); const dt = new Date(y, m - 1, d);
      return `<th class="n">${dt.toLocaleDateString(undefined, { month: "short", day: "numeric" })}</th>`;
    }).join("")}</tr></thead>`;
    const body = strikes.map((k) => {
      const cells = exps.map((e) => {
        const o = map.get(e + "|" + k), v = val(o);
        if (!o) return '<td class="hm-empty"></td>';
        const a = max ? Math.sqrt(v / max) : 0;
        const dark = a > 0.55;
        return `<td class="hm-cell${dark ? " hm-dark" : ""}" style="background:rgba(${color},${(0.06 + a * 0.88).toFixed(3)})" data-e="${e}" data-k="${k}" title="${esc(`$${k} ${hmType === "c" ? "call" : "put"} ${e}: volume ${o.v}, open interest ${o.oi}, mid $${o.m}`)}">${v ? short(v) : "·"}</td>`;
      }).join("");
      const kTxt = "$" + fmt(k, k % 1 ? 1 : 0);
      return `<tr class="${k === atm ? "hm-atm" : ""}"><th>${kTxt}${k === atm ? ' <span class="hm-now">≈ now</span>' : ""}</th>${cells}</tr>`;
    }).join("");
    el.innerHTML = head + `<tbody>${body}</tbody>`;
  }
  function bindSeg(id, set) {
    document.querySelectorAll(`#${id} button`).forEach((b) => b.addEventListener("click", () => {
      document.querySelectorAll(`#${id} button`).forEach((x) => x.classList.toggle("on", x === b));
      set(b.dataset.v); renderHeatmap();
    }));
  }
  bindSeg("hm-type", (v) => (hmType = v));
  bindSeg("hm-metric", (v) => (hmMetric = v));
  $("heatmap").addEventListener("click", (e) => {
    const td = e.target.closest("td.hm-cell");
    if (td && window.Calc && window.Calc.load) window.Calc.load(hmType, td.dataset.e, Number(td.dataset.k));
  });

  // ------------------------------------------------------------ news
  function ago(iso) {
    const t = new Date(iso); if (isNaN(t)) return "";
    const m = Math.round((Date.now() - t) / 60000);
    if (m < 60) return `${Math.max(1, m)} min ago`;
    if (m < 60 * 24) return `${Math.round(m / 60)} hr ago`;
    return t.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }
  function renderNews() {
    const N = D.news || [];
    $("news").innerHTML = N.length ? N.map((n) =>
      `<li><a href="${esc(n.url)}" target="_blank" rel="noopener noreferrer">${esc(n.title)}</a><span class="muted">${esc(n.publisher)}${n.time ? " · " + ago(n.time) : ""}</span></li>`).join("")
      : '<li class="muted">No headlines available right now.</li>';
  }

  // ------------------------------------------------------------ small charts
  const charts = {};
  const boxW = (el) => Math.max(200, Math.floor(el.getBoundingClientRect().width) || 320);
  function baseOpts(el, pctScale) {
    return {
      width: boxW(el), height: el.clientHeight || 240,
      layout: { background: { type: "solid", color: "rgba(0,0,0,0)" }, textColor: css("--muted"), fontSize: 11 },
      grid: { vertLines: { color: css("--chart-grid") }, horzLines: { color: css("--chart-grid") } },
      rightPriceScale: { borderColor: css("--line") }, timeScale: { borderColor: css("--line") },
      crosshair: { mode: 0 }, handleScroll: { vertTouchDrag: false },
      localization: pctScale ? { priceFormatter: (v) => (v > 0 ? "+" : "") + v.toFixed(0) + "%" } : undefined,
    };
  }
  function fresh(id) {
    const el = $(id);
    try { charts[id] && charts[id].remove(); } catch (e) { /* ignore */ }
    el.innerHTML = "";
    return el;
  }
  let cmpRange = 63;
  const SERIES = { gehc: ["GE HealthCare", "#2457d6"], phg: ["Philips", "#e0703a"], shl: ["Siemens Healthineers", "#8a5cf6"],
                   ihi: ["Medical devices ETF (IHI)", "#3aa17e"], spy: ["S&P 500 (SPY)", "#9aa3ae"] };
  function renderCompare() {
    const el = fresh("cmpchart");
    if (!window.LightweightCharts) { el.innerHTML = '<div class="empty">Chart library failed to load.</div>'; return; }
    const rows = ((O && O.compare) || []).slice(-cmpRange);
    if (rows.length < 2) { el.innerHTML = '<div class="empty">Not enough history yet.</div>'; return; }
    try {
      const ch = LightweightCharts.createChart(el, baseOpts(el, true));
      charts.cmpchart = ch;
      const last = {}, keys = Object.keys(SERIES).filter((k) => rows.some((r) => r[k] != null));
      keys.forEach((k) => {
        const base = rows.find((r) => r[k] != null);
        const data = rows.filter((r) => r[k] != null).map((r) => ({ time: r.t, value: (r[k] / base[k] - 1) * 100 }));
        const sel = D && D.key === k, etf = k === "ihi" || k === "spy";
        ch.addLineSeries({ color: SERIES[k][1], lineWidth: sel ? 4 : etf ? 1 : 2, lineStyle: etf ? 2 : 0, priceLineVisible: false, lastValueVisible: true }).setData(data);
        last[k] = data[data.length - 1].value;
      });
      ch.timeScale().fitContent();
      $("cmp-legend").innerHTML = keys.map((k) => `<span><i style="background:${SERIES[k][1]}"></i>${SERIES[k][0]}</span>`).join("");
      const label = { 21: "Over the last month", 63: "Over the last 3 months", 252: "Over the last year", 504: "Over the last 2 years" }[cmpRange];
      const order = keys.filter((k) => k !== "ihi" && k !== "spy").sort((a, b) => last[b] - last[a]);
      $("cmp-note").innerHTML = `${label}: ` + keys.map((k) => `${SERIES[k][0].replace(/ \(.*\)/, "")} <b class="${cls(last[k])}">${pct(last[k])}</b>`).join(", ") +
        (order.length > 1 ? `. Leader: <b>${SERIES[order[0]][0]}</b>.` : ".");
    } catch (e) { el.innerHTML = `<div class="empty">Chart couldn't be drawn (${esc(e.message)}).</div>`; }
  }
  document.querySelectorAll("#cmp-range button").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll("#cmp-range button").forEach((x) => x.classList.toggle("on", x === b));
    cmpRange = Number(b.dataset.r); renderCompare();
  }));

  function renderVolChart() {
    const el = fresh("volchart");
    if (!window.LightweightCharts) { el.innerHTML = '<div class="empty">Chart library failed to load.</div>'; return; }
    const rv = D.vol_history || [], iv = (D.iv_history || []).map((h) => ({ time: h.date, value: h.iv * 100 }));
    if (rv.length < 2) { el.innerHTML = '<div class="empty">Not enough history yet.</div>'; return; }
    try {
      const ch = LightweightCharts.createChart(el, baseOpts(el, false));
      charts.volchart = ch;
      const rvS = ch.addLineSeries({ color: "#8a95a5", lineWidth: 2, priceLineVisible: false, lastValueVisible: false,
        priceFormat: { type: "custom", formatter: (v) => v.toFixed(0) + "%" } });
      rvS.setData(rv.map((r) => ({ time: r.t, value: r.rv })));
      const ivS = ch.addLineSeries({ color: "#e0703a", lineWidth: 3, priceLineVisible: false, pointMarkersVisible: true,
        priceFormat: { type: "custom", formatter: (v) => v.toFixed(0) + "%" } });
      ivS.setData(iv);
      const days = new Set(rv.map((r) => r.t));
      const markers = (D.event_moves && D.event_moves.rows || []).filter((r) => days.has(r.date)).map((r) => ({
        time: r.date, position: "aboveBar", shape: "circle", color: css("--accent"), text: "E" })).sort((a, b) => (a.time < b.time ? -1 : 1));
      rvS.setMarkers(markers);
      ch.timeScale().fitContent();
      $("volchart-note").textContent = !D.has_options
        ? `How much ${D.short_name} has actually been moving (20-day volatility, yearly scale). E = earnings report.`
        : iv.length < 5
        ? `Implied volatility is collected once per trading day from the first run onward (${iv.length} so far), so the orange line grows over time. The gray line uses ${D.ticker}'s full price history. E = earnings.`
        : `Orange above gray means options are pricing in more movement than the stock has actually shown. E = earnings.`;
    } catch (e) { el.innerHTML = `<div class="empty">Chart couldn't be drawn (${esc(e.message)}).</div>`; }
  }
  let rt;
  window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(() => { if (D) { renderCompare(); renderVolChart(); } }, 200); });

  // decorate tables that get re-rendered (tabs, toggles)
  const mo = new MutationObserver(() => { clearTimeout(mo.t); mo.t = setTimeout(() => decorate(), 50); });

  let O = null;
  window.Extras = {
    init(data, overview) {
      D = data; O = overview;
      $("volchart-title").firstChild.textContent = D.has_options ? "Option prices over time " : "How much the stock moves ";
      $("volchart-legend").innerHTML = D.has_options
        ? '<span><i style="background:#e0703a"></i>Implied volatility (what options assume)</span><span><i style="background:#8a95a5"></i>Actual volatility (20-day)</span><span><i style="background:var(--accent)"></i>Earnings</span>'
        : '<span><i style="background:#8a95a5"></i>Actual volatility (20-day)</span><span><i style="background:var(--accent)"></i>Earnings</span>';
      for (const f of [renderHeatmap, renderNews, renderCompare, renderVolChart]) { try { f(); } catch (e) { console.error(e); } }
      decorate();
      mo.observe(document.querySelector(".wrap"), { childList: true, subtree: true });
    },
  };
})();
