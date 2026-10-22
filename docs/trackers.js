// Peer scoreboard, valuation side by side, FDA activity and analyst price targets.
(function () {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const fmt = (x, d = 2) => Number(x).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
  const pct = (x, d = 1) => (x == null ? "—" : (x > 0 ? "+" : "") + fmt(x, d) + "%");
  const cls = (x) => (x > 0 ? "pos" : x < 0 ? "neg" : "muted");
  let SYM = "$";
  const money = (x, d = 2, sym = SYM) => (x == null ? "—" : sym + fmt(x, d));
  const big = (x, sym = "") => (x == null ? "—" : x >= 1e12 ? sym + fmt(x / 1e12, 2) + "T" : x >= 1e9 ? sym + fmt(x / 1e9, 1) + "B" : sym + fmt(x / 1e6, 0) + "M");
  const dateTxt = (s, opts = { month: "short", day: "numeric", year: "numeric" }) => {
    if (!s) return "—";
    const [y, m, d] = s.slice(0, 10).split("-").map(Number);
    return new Date(y, m - 1, d).toLocaleDateString(undefined, opts);
  };
  function table(el, head, rows, empty) {
    if (!el) return;
    if (!rows.length) { el.outerHTML = `<div class="empty" id="${el.id}">${empty}</div>`; return; }
    if (el.tagName !== "TABLE") { const t = document.createElement("table"); t.id = el.id; el.replaceWith(t); el = t; }
    el.innerHTML = `<thead><tr>${head.map(([h, n]) => `<th class="${n ? "n" : ""}">${h}</th>`).join("")}</tr></thead>` +
      `<tbody>${rows.map((r) => `<tr>${r.map((c, i) => `<td class="${head[i][1] ? "n" : ""}">${c}</td>`).join("")}</tr>`).join("")}</tbody>`;
  }

  // ------------------------------------------------------------ peer scoreboard
  function spark(vals) {
    const v = (vals || []).filter((x) => x != null);
    if (v.length < 2) return "";
    const lo = Math.min(...v), hi = Math.max(...v), W = 200, H = 34;
    const pts = v.map((x, i) => `${(i / (v.length - 1) * W).toFixed(1)},${(H - 3 - (hi > lo ? (x - lo) / (hi - lo) : 0.5) * (H - 6)).toFixed(1)}`).join(" ");
    const up = v[v.length - 1] >= v[0];
    return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true"><polyline points="${pts}" fill="none" stroke="var(${up ? "--up" : "--down"})" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>`;
  }
  function peers(O, key) {
    if (!O) return;
    $("peers").innerHTML = O.companies.map((c) => {
      const s = c.score, ne = c.next_earnings;
      const scoreCls = s >= 20 ? "up" : s <= -20 ? "down" : "";
      return `<button class="peer ${c.key === key ? "on" : ""}" data-co="${c.key}">
        <div class="peer-top"><span class="peer-name">${esc(c.short)}</span><span class="peer-tk">${esc(c.ticker)}${c.market_open ? ' · <span class="pos">open</span>' : ""}</span></div>
        <div class="peer-top"><span class="peer-px">${money(c.price, 2, c.currency_symbol)}</span><span class="${cls(c.change_pct)}"><b>${pct(c.change_pct, 2)}</b></span></div>
        ${spark(c.sparkline)}
        <div class="peer-row"><span class="chip ${scoreCls}">${esc(c.label)} ${s > 0 ? "+" : ""}${s}</span>${c.has_options ? `<span class="chip ${c.options_verdict === "expensive" ? "warn" : c.options_verdict === "cheap" ? "up" : "dim"}">Options ${esc(c.options_verdict)}</span>` : '<span class="chip dim">No US options</span>'}</div>
        <div class="peer-row"><span class="muted">Earnings</span><span>${ne ? `${dateTxt(ne.date, { month: "short", day: "numeric" })} <span class="muted">(${ne.days === 0 ? "today" : ne.days === 1 ? "tomorrow" : ne.days + "d"})</span>` : "—"}</span></div>
        <div class="peer-row"><span class="muted">1 month · this year</span><span><span class="${cls(c.chg_20d)}">${pct(c.chg_20d)}</span> · <span class="${cls(c.chg_ytd)}">${pct(c.chg_ytd)}</span></span></div>
        ${c.fda && c.fda.class1_12m ? `<div class="peer-row"><span class="muted">FDA Class I recalls (1y)</span><span class="neg"><b>${c.fda.class1_12m}</b></span></div>` : ""}
      </button>`;
    }).join("");
    const on = $("peers").querySelector(".peer.on");
    if (on && $("peers").scrollWidth > $("peers").clientWidth) $("peers").scrollLeft = Math.max(0, on.offsetLeft - 8);
  }

  // ------------------------------------------------------------ valuation side by side
  function valuation(O, key) {
    if (!O) return;
    const cs = O.companies;
    const rows = [
      ["Market value", (c) => c.valuation.market_cap, (v, c) => big(v, c.currency_symbol), null],
      ["P/E (last 12 months)", (c) => c.valuation.pe, (v) => (v == null ? "—" : fmt(v, 1)), "low"],
      ["Forward P/E", (c) => c.valuation.forward_pe, (v) => (v == null ? "—" : fmt(v, 1)), "low"],
      ["Price / sales", (c) => c.valuation.ps, (v) => (v == null ? "—" : fmt(v, 2)), "low"],
      ["EV / EBITDA", (c) => c.valuation.ev_ebitda, (v) => (v == null ? "—" : fmt(v, 1)), "low"],
      ["Revenue growth (yr/yr)", (c) => c.valuation.revenue_growth, (v) => (v == null ? "—" : pct(v * 100)), "high"],
      ["Operating margin", (c) => c.valuation.op_margin, (v) => (v == null ? "—" : fmt(v * 100, 1) + "%"), "high"],
      ["Dividend yield", (c) => c.valuation.div_yield, (v) => (v == null ? "—" : fmt(v, 2) + "%"), "high"],
      ["Beta", (c) => c.valuation.beta, (v) => (v == null ? "—" : fmt(v, 2)), null],
      ["Analyst target vs. price", (c) => c.analyst_upside, (v) => (v == null ? "—" : `<span class="${cls(v)}">${pct(v)}</span>`), null],
      ["Typical earnings move", (c) => c.avg_earnings_move, (v) => (v == null ? "—" : "±" + fmt(v, 1) + "%"), null],
    ];
    const el = $("val-table");
    el.innerHTML = `<thead><tr><th></th>${cs.map((c) => `<th class="n">${c.key === key ? "<u>" : ""}${esc(c.short)}${c.key === key ? "</u>" : ""}</th>`).join("")}</tr></thead><tbody>` +
      rows.map(([label, get, show, best]) => {
        const vals = cs.map(get);
        const ok = vals.filter((v) => v != null && (best !== "low" || v > 0));
        const target = best && ok.length > 1 ? (best === "low" ? Math.min(...ok) : Math.max(...ok)) : null;
        return `<tr><td>${label}</td>${cs.map((c, i) => `<td class="n${target != null && vals[i] === target ? " best" : ""}">${show(vals[i], c)}</td>`).join("")}</tr>`;
      }).join("") + "</tbody>";
  }

  // ------------------------------------------------------------ FDA
  function fda(d) {
    const F = d.fda;
    if (!F) {
      $("fda-summary").innerHTML = "";
      table($("fda-recalls"), [], [], "FDA data isn't available right now. It's retried every hour.");
      table($("fda-clear"), [], [], "—");
      return;
    }
    const s = F.summary || {};
    const chip = (t, c = "") => `<span class="chip ${c}">${t}</span>`;
    $("fda-summary").innerHTML = [
      chip(`${s.clearances_12m} new clearances in the last year`, "up"),
      chip(`${s.recalls_12m} recall events in the last year`, s.recalls_12m ? "warn" : ""),
      s.class1_12m ? chip(`${s.class1_12m} Class I (most serious)`, "down") : chip("No Class I recalls in the last year", "up"),
      s.recalls_90d ? chip(`${s.recalls_90d} posted in the last 90 days`, "warn") : "",
      s.last_class1 ? chip(`Last Class I: ${dateTxt(s.last_class1)}`, "dim") : "",
    ].join("");
    const clsCls = { "Class I": "down", "Class II": "warn", "Class III": "dim" };
    table($("fda-recalls"), [["Posted", 0], ["Class", 0], ["Product & reason", 0]],
      (F.recalls || []).slice(0, 10).map((r) => [dateTxt(r.date, { month: "short", day: "numeric", year: "2-digit" }),
        `<span class="chip ${clsCls[r.classification] || "dim"}">${esc((r.classification || "—").replace("Class ", ""))}</span>`,
        `<span class="ss-detail"><b>${esc(r.product.split(/[;,.]/)[0].slice(0, 90))}</b>${r.products > 1 ? ` <span class="muted">(+${r.products - 1} more products)</span>` : ""}<br>${esc(r.reason.slice(0, 170))}${r.reason.length > 170 ? "…" : ""}<br><span class="muted">${esc(r.firm || "")} · ${esc(r.status || "")}</span></span>`]),
      "No recalls posted for these company names in the last two years.");
    table($("fda-clear"), [["Decided", 0], ["Device", 0]],
      (F.clearances || []).slice(0, 10).map((c) => [dateTxt(c.date, { month: "short", day: "numeric", year: "2-digit" }),
        `<span class="ss-detail"><b>${esc(c.device)}</b><br><span class="muted">${esc(c.k_number || "")} · ${esc(c.panel || c.applicant || "")}</span></span>`]),
      "No recent 510(k) clearances found.");
  }

  // ------------------------------------------------------------ analysts
  function renderAnalysts(d) {
    const A = d.analysts;
    if (!A) {
      $("an-head").innerHTML = '<div class="empty">Analyst data isn\'t available from Yahoo right now. It\'s retried every hour.</div>';
      $("an-range").innerHTML = ""; $("an-mix").innerHTML = "";
      table($("an-changes"), [], [], "No recent rating changes.");
      return;
    }
    const t = A.targets || {}, p = A.price;
    const head = [];
    if (t.mean) head.push(`<div class="an-big"><span class="muted">Average target</span><b>${money(t.mean)}</b><span class="${cls(A.upside_mean_pct)}">${pct(A.upside_mean_pct)} from today</span></div>`);
    if (A.rating_text) head.push(`<div class="an-big"><span class="muted">Consensus <button class="ex" data-ex="rating" aria-label="Explain">i</button></span><b>${esc(A.rating_text)}</b><span class="muted">${A.rating_mean ? fmt(A.rating_mean, 1) + " on a 1–5 scale" : ""}</span></div>`);
    if (A.count) head.push(`<div class="an-big"><span class="muted">Analysts</span><b>${A.count}</b><span class="muted">covering it</span></div>`);
    $("an-head").innerHTML = `<div class="an-heads">${head.join("")}</div>`;

    if (t.low && t.high && t.high > t.low) {
      const lo = Math.min(t.low, p) * 0.95, hi = Math.max(t.high, p) * 1.03;
      const X = (v) => ((v - lo) / (hi - lo) * 100).toFixed(2) + "%";
      const mk = (v, label, c) => v ? `<div class="an-mark ${c}" style="left:${X(v)}"><i></i><span>${label}<br><b>${money(v, 0)}</b></span></div>` : "";
      $("an-range").innerHTML = `<div class="an-track"><div class="an-fill" style="left:${X(t.low)};width:calc(${X(t.high)} - ${X(t.low)})"></div>
        ${mk(t.low, "Low", "lo")}${mk(t.mean, "Average", "mid")}${mk(t.high, "High", "hi")}
        <div class="an-now" style="left:${X(p)}"><span>Today ${money(p, 0)}</span></div></div>`;
    } else $("an-range").innerHTML = "";

    const mix = A.mix;
    if (mix) {
      const parts = [["Strong buy", mix.strongBuy, "var(--up)"], ["Buy", mix.buy, "color-mix(in srgb, var(--up) 55%, var(--card))"],
        ["Hold", mix.hold, "var(--line)"], ["Sell", mix.sell, "color-mix(in srgb, var(--down) 55%, var(--card))"], ["Strong sell", mix.strongSell, "var(--down)"]];
      const tot = parts.reduce((a, x) => a + (x[1] || 0), 0);
      $("an-mix").innerHTML = tot ? `<h3 class="sub">Ratings this month</h3><div class="an-mixbar">${parts.filter((x) => x[1]).map(([n, v, c]) => `<div style="flex:${v};background:${c}" title="${n}: ${v}"><span>${v}</span></div>`).join("")}</div>
        <div class="legend">${parts.map(([n, v, c]) => `<span><i style="background:${c};height:10px"></i>${n}: ${v || 0}</span>`).join("")}</div>` : "";
    } else $("an-mix").innerHTML = "";

    const act = { up: "Upgrade", down: "Downgrade", main: "Maintained", init: "New coverage", reit: "Reiterated" };
    table($("an-changes"), [["Date", 0], ["Firm", 0], ["Rating", 0], ["Target", 1]],
      (A.changes || []).slice(0, 8).map((c) => [dateTxt(c.date, { month: "short", day: "numeric" }), esc(c.firm),
        `${esc(c.to || "—")}${c.action && act[c.action] ? ` <span class="chip ${c.action === "up" ? "up" : c.action === "down" ? "down" : "dim"}">${act[c.action]}</span>` : ""}`,
        c.target ? `${money(c.target, 0)}${c.prior_target && c.prior_target !== c.target ? ` <span class="${cls(c.target - c.prior_target)}">(${c.target > c.prior_target ? "↑" : "↓"} from ${money(c.prior_target, 0)})</span>` : ""}` : "—"]),
      "No recent rating changes.");
  }

  window.Trackers = {
    peers,
    init(d, O) {
      SYM = d.currency_symbol || "$";
      for (const f of [() => peers(O, d.key), () => valuation(O, d.key), () => fda(d), () => renderAnalysts(d)]) {
        try { f(); } catch (e) { console.error(e); }
      }
    },
  };
})();
