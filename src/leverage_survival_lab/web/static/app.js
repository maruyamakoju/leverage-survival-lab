// Leverage Survival Lab — paper trading UI client.
// 接続: WebSocket /ws で state を受信、REST /api/* で操作。

const $ = (id) => document.getElementById(id);
const fmt = (n, d = 2) => n == null ? "—" : Number(n).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
const fmtMoney = (n, d = 2) => n == null ? "—" : "$" + fmt(n, d);
const fmtSigned = (n, d = 2) => n == null ? "—" : (n >= 0 ? "+" : "") + fmt(n, d);

let lastPrice = null;
const priceHistory = [];   // {ts, price}
const MAX_PRICE_HISTORY = 240;

const conn = {
  ws: null,
  status: "offline",
  setStatus(s) {
    this.status = s;
    $("conn-dot").className = "dot " + s;
    $("conn-text").innerText = s;
  },
};

function connect() {
  conn.setStatus("connecting");
  const url = (location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws";
  const ws = new WebSocket(url);
  conn.ws = ws;
  ws.onopen = () => conn.setStatus("online");
  ws.onclose = () => {
    conn.setStatus("offline");
    setTimeout(connect, 2000);
  };
  ws.onerror = () => conn.setStatus("offline");
  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data);
      if (msg.type === "state") {
        applyState(msg.data);
      }
    } catch (err) {
      console.error("ws msg parse failed", err);
    }
  };
}

function applyState(s) {
  // Price
  const priceEl = $("price");
  if (s.price != null && s.price > 0) {
    if (lastPrice != null && lastPrice !== s.price) {
      priceEl.classList.remove("up", "down");
      priceEl.classList.add(s.price > lastPrice ? "up" : "down");
      // remove direction class after a moment so next change re-flashes
      setTimeout(() => priceEl.classList.remove("up", "down"), 250);
    }
    priceEl.innerText = "$" + fmt(s.price, 2);
    lastPrice = s.price;
    priceHistory.push({ ts: s.ts, price: s.price });
    while (priceHistory.length > MAX_PRICE_HISTORY) priceHistory.shift();
    drawChart();
  }
  $("ts").innerText = s.ts ? `last update: ${s.ts}` : "—";

  // Price change vs first chart point
  if (priceHistory.length > 1) {
    const first = priceHistory[0].price;
    const ch = (s.price / first - 1) * 100;
    const el = $("price-change");
    el.innerText = `${ch >= 0 ? "+" : ""}${ch.toFixed(2)}% (${priceHistory.length} ticks)`;
    el.classList.toggle("up", ch >= 0);
    el.classList.toggle("down", ch < 0);
  }

  // Equity
  $("equity").innerText = fmtMoney(s.total_value, 0);
  const pnl = s.pnl_pct ?? 0;
  const pnlEl = $("pnl");
  pnlEl.innerText = `${fmtSigned(pnl, 2)}%`;
  pnlEl.classList.toggle("up", pnl >= 0);
  pnlEl.classList.toggle("down", pnl < 0);

  $("init-eq").innerText = fmtMoney(s.initial_equity, 0);
  $("unr").innerText = fmtSigned(s.unrealized_pnl, 2);
  $("n-trades").innerText = s.n_trades;
  $("n-liq").innerText = s.n_liquidations;

  // Position
  const pos = s.position;
  if (pos) {
    const isLong = pos.side === "long";
    $("pos-display").className = isLong ? "pos-long" : "pos-short";
    $("pos-display").innerText =
      `${isLong ? "▲ LONG" : "▼ SHORT"} ${pos.qty.toFixed(6)} BTC @ $${fmt(pos.entry, 2)}  •  ${pos.leverage.toFixed(0)}x`;
    $("pos-detail").style.display = "flex";
    $("pos-qty").innerText = pos.qty.toFixed(6);
    $("pos-entry").innerText = fmtMoney(pos.entry);
    $("pos-lev").innerText = pos.leverage.toFixed(0) + "x";
    $("pos-liq").innerText = fmtMoney(pos.liq_price);
    $("pos-liq-dist").innerText = `(${pos.liq_distance_pct.toFixed(2)}% away)`;
    // liq-bar: 0% (close to liq, danger) to 100% (far from liq, safe)
    const dist = Math.min(pos.liq_distance_pct, 10);
    $("liq-bar").style.width = (dist / 10 * 100).toFixed(0) + "%";
  } else {
    $("pos-display").className = "pos-flat";
    $("pos-display").innerText = "FLAT — no position";
    $("pos-detail").style.display = "none";
    $("liq-bar").style.width = "100%";
  }

  // Trades table
  const tbody = $("trades-body");
  tbody.innerHTML = "";
  for (const t of (s.trades_recent || []).slice().reverse()) {
    const tr = document.createElement("tr");
    const ts = (t.ts || "").split("T")[1]?.slice(0, 8) || "—";
    tr.innerHTML = `
      <td>${ts}</td>
      <td class="action ${t.action}">${t.action}</td>
      <td>${fmt(t.price)}</td>
      <td>${(t.qty ?? 0).toFixed(6)}</td>
      <td>${(t.leverage ?? 0).toFixed(0)}x</td>
      <td class="${t.pnl == null ? "" : (t.pnl >= 0 ? "pnl-pos" : "pnl-neg")}">${t.pnl == null ? "—" : fmtSigned(t.pnl, 2)}</td>`;
    tbody.appendChild(tr);
  }

  // Last event
  const ev = s.last_event;
  if (ev && ev.message) {
    $("last-msg").innerText = ev.message;
  } else if (ev && ev.messages && ev.messages.length) {
    $("last-msg").innerText = ev.messages.join(" · ");
    if (ev.messages.some((m) => m.includes("LIQUIDATED"))) {
      showLiqModal(ev.messages.filter((m) => m.includes("LIQUIDATED"))[0]);
    }
  }

  // Update form defaults
  if (document.activeElement?.id !== "inp-size") $("inp-size").value = (s.default_size_pct * 100).toFixed(0);
  if (document.activeElement?.id !== "inp-lev") $("inp-lev").value = s.default_leverage.toFixed(0);

  precheck();
}

function drawChart() {
  const c = $("price-chart");
  const w = c.clientWidth || 800;
  c.width = w;
  const h = c.height;
  const ctx = c.getContext("2d");
  ctx.clearRect(0, 0, w, h);
  if (priceHistory.length < 2) return;
  const prices = priceHistory.map((p) => p.price);
  const lo = Math.min(...prices);
  const hi = Math.max(...prices);
  const rng = (hi - lo) || 1;
  const last = prices[prices.length - 1];
  const first = prices[0];
  const isUp = last >= first;

  // grid lines
  ctx.strokeStyle = "#21262d";
  ctx.lineWidth = 0.5;
  for (let i = 0; i < 4; i++) {
    const y = (h / 4) * i;
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
  }

  // line
  ctx.beginPath();
  ctx.strokeStyle = isUp ? "#2ea043" : "#da3633";
  ctx.lineWidth = 1.5;
  prices.forEach((p, i) => {
    const x = (i / (prices.length - 1)) * w;
    const y = h - ((p - lo) / rng) * (h - 6) - 3;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.stroke();

  // fill area
  ctx.lineTo(w, h); ctx.lineTo(0, h); ctx.closePath();
  ctx.fillStyle = isUp ? "rgba(46,160,67,0.12)" : "rgba(218,54,51,0.12)";
  ctx.fill();
}

window.addEventListener("resize", drawChart);

// ---- API helpers ----
async function api(path, body) {
  const res = await fetch("/api" + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : "{}",
  });
  return res.json();
}

async function precheck() {
  const lev = parseFloat($("inp-lev").value);
  const size = parseFloat($("inp-size").value);
  if (!lev || !size) return;
  try {
    const r = await fetch("/api/precheck", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ leverage: lev, size_pct: size }),
    }).then((r) => r.json());
    const el = $("precheck");
    if (r.ok) {
      el.className = "precheck ok";
      el.innerText = `notional $${fmt(r.notional, 0)} (mm ${(r.mm * 100).toFixed(2)}% < 1/lev ${(100 / lev).toFixed(2)}%) — OK`;
      $("btn-long").disabled = false;
      $("btn-short").disabled = false;
    } else {
      el.className = "precheck warn";
      el.innerText = `!! REJECTED: notional $${fmt(r.notional, 0)} requires mm ${(r.mm * 100).toFixed(2)}% but 1/lev=${(100 / lev).toFixed(2)}%. At this size, max lev ≈ ${r.max_lev_at_size}x.`;
      $("btn-long").disabled = true;
      $("btn-short").disabled = true;
    }
  } catch (e) {
    console.error(e);
  }
}

// ---- Wire up buttons ----
function bindButtons() {
  $("btn-long").onclick = async () => {
    const r = await api("/long", {
      size_pct: parseFloat($("inp-size").value) / 100,
      leverage: parseFloat($("inp-lev").value),
    });
    $("last-msg").innerText = r.message;
  };
  $("btn-short").onclick = async () => {
    const r = await api("/short", {
      size_pct: parseFloat($("inp-size").value) / 100,
      leverage: parseFloat($("inp-lev").value),
    });
    $("last-msg").innerText = r.message;
  };
  $("btn-close").onclick = async () => {
    const r = await api("/close");
    $("last-msg").innerText = r.message;
  };
  $("btn-set-sl").onclick = async () => {
    const v = $("inp-sl").value;
    const r = await api("/sl", { pct: v === "" ? null : parseFloat(v) });
    $("last-msg").innerText = r.message;
  };
  $("btn-set-tp").onclick = async () => {
    const v = $("inp-tp").value;
    const r = await api("/tp", { pct: v === "" ? null : parseFloat(v) });
    $("last-msg").innerText = r.message;
  };
  $("btn-clear-sl").onclick = async () => { $("inp-sl").value = ""; const r = await api("/sl", { pct: null }); $("last-msg").innerText = r.message; };
  $("btn-clear-tp").onclick = async () => { $("inp-tp").value = ""; const r = await api("/tp", { pct: null }); $("last-msg").innerText = r.message; };
  $("btn-reset").onclick = async () => {
    const eq = parseFloat($("reset-eq").value);
    const r = await api("/reset", { equity: eq, leverage: parseFloat($("inp-lev").value), size_pct: parseFloat($("inp-size").value) });
    $("last-msg").innerText = r.message || "reset";
    priceHistory.length = 0;
  };
  // Update default lev/size when inputs change
  let dt;
  const onParamChange = () => {
    clearTimeout(dt);
    dt = setTimeout(async () => {
      await api("/defaults", { leverage: parseFloat($("inp-lev").value), size_pct: parseFloat($("inp-size").value) });
      precheck();
    }, 250);
  };
  $("inp-size").addEventListener("input", onParamChange);
  $("inp-lev").addEventListener("input", onParamChange);

  // Liq modal close
  $("liq-ok").onclick = () => $("liq-modal").classList.add("hidden");
}

function showLiqModal(text) {
  $("liq-text").innerText = text;
  $("liq-modal").classList.remove("hidden");
  // 3秒後に自動で閉じない(ユーザがOKを押すまで)
}

window.addEventListener("DOMContentLoaded", () => {
  bindButtons();
  connect();
  precheck();
});
