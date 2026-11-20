/* =====================================================================
   pages_c.js - Low Stock Alerts + Notifications, Analytics & Reports,
                DSA Visualization (Queue + Algorithms), System Settings
   ===================================================================== */

/* =============================================================== ALERTS */
const NOTIF_ICON = { stock: "package", expiry: "calendar", purchase: "clipboard", shipment: "truck", capacity: "database", order: "shopping-cart", transfer: "repeat", return: "rotate-ccw" };
const NOTIF_PAGE = { inventory: "inventory", warehouses: "warehouses", purchase: "purchase", shipments: "shipments", orders: "orders", movements: "movements", returns: "returns" };
function notifItem(n, compact) {
  const col = { critical: "var(--red)", warning: "var(--or)", success: "var(--em)", info: "var(--tq)" }[n.severity];
  return `<div class="${compact ? "dd-item" : "act-feed"} ${n.is_read ? "" : "unread"}" data-n="${n.id}" data-link="${n.link || ""}" ${compact ? "" : 'style="cursor:pointer"'}>${compact ? "" : '<div class="item">'}<span class="kpi-ic" style="--kc:${col};width:38px;height:38px;flex-shrink:0">${ic(NOTIF_ICON[n.category] || "bell", 18)}</span>
    <div style="flex:1;min-width:0"><b>${esc(n.title)} ${n.is_read ? "" : '<span class="dot" style="display:inline-block;margin-left:4px"></span>'}</b><small class="muted" style="display:block">${esc(n.message)}</small><small class="muted">${fmt.ago(n.ts)} · ${fmt.title(n.category)}</small></div>${compact ? "" : "</div>"}</div>`;
}
Pages.alerts = {
  async render(el) {
    el.innerHTML = pageHead("Low Stock Alerts", "Rule-based smart alerts for stock, expiry, purchasing, shipments and capacity") + `<div class="tabs" id="al-tabs"><button data-t="low" class="on">${ic("alert-triangle", 16)} Low stock</button><button data-t="notif">${ic("bell", 16)} Notification center <span class="pill red" id="al-unread" hidden>0</span></button></div><div id="al-body"></div>`;
    const tab = async (t) => {
      $$("#al-tabs button").forEach((b) => b.classList.toggle("on", b.dataset.t === t));
      const body = $("#al-body");
      if (t === "low") {
        const [low, out] = await Promise.all([api("/api/products?status=LOW&sort=quantity&dir=asc&algo=insertion"), api("/api/products?status=OUT")]);
        const rows = [...out.items, ...low.items].map((p) => ({ ...p, suggest: Math.max(p.reorder_level * 3 - p.available, 0), short: Math.max(p.reorder_level - p.available, 0) }));
        body.innerHTML = `<div class="stat-tiles"><div class="tile"><small>Out of stock</small><b style="color:var(--red)">${out.items.length}</b></div><div class="tile"><small>Low stock</small><b style="color:var(--or)">${low.items.length}</b></div><div class="tile"><small>Suggested units to order</small><b>${fmt.num(rows.reduce((s, r) => s + r.suggest, 0))}</b></div></div><div class="card"><div id="al-low"></div></div>`;
        makeTable($("#al-low"), { rows, pageSize: 10, empty: emptyState("check-circle", "All products are above their reorder level", "Nothing needs restocking right now."), rowClick: (p) => productDetail(p.id),
          onAction: (a, p) => { if (a === "po") poForm(null, { values: { supplier_id: p.supplier_id || "" }, items: [{ product_id: p.id, quantity: p.suggest || p.reorder_level, unit_cost: p.purchase_price }] }); if (a === "in") openMovementForm({ type: "STOCK_IN", product_id: p.id }); },
          columns: [{ key: "name", label: "Product", sort: true, render: (p) => `<div class="prod-cell">${pimg(p)}<div><b>${esc(p.name)}</b><div class="pcode">${p.code} · ${esc(p.category)}</div></div></div>` }, { key: "available", label: "Available", sort: true, align: "r", render: (p) => `<b style="color:${p.status === "OUT" ? "var(--red)" : "var(--or)"}">${p.available}</b>` },
            { key: "reorder_level", label: "Reorder level", align: "r" }, { key: "short", label: "Shortfall", align: "r" }, { key: "suggest", label: "Suggested order", align: "r", sort: true, render: (p) => `<b>${p.suggest}</b>` }, { key: "supplier_name", label: "Supplier" }, { key: "status", label: "Status", render: (p) => pill(p.status) },
            { key: "act", label: "", render: (p) => `<div class="row-acts">${can("po.write") ? `<button class="btn sm primary" data-act="po" data-id="${p.id}">Create PO</button>` : ""}${can("stock.move") ? `<button class="btn sm" data-act="in" data-id="${p.id}">Stock in</button>` : ""}</div>` }] });
      } else {
        let cat = "all";
        const draw = async () => {
          const d = await api("/api/notifications" + (cat !== "all" ? "?category=" + cat : ""));
          const cats = ["all", ...Object.keys(NOTIF_ICON)];
          body.innerHTML = `<div class="card"><div class="toolbar"><div class="seg" id="nf-seg">${cats.map((c) => `<button data-c="${c}" class="${c === cat ? "on" : ""}">${c === "all" ? "All" : fmt.title(c)}</button>`).join("")}</div><span class="grow"></span><button class="btn sm" id="nf-read">${ic("check", 14)} Mark all as read</button><button class="btn sm danger" id="nf-clear">${ic("trash-2", 14)} Clear history</button></div>
            ${d.items.length ? d.items.map((n) => notifItem(n)).join("") : emptyState("bell", "No notifications", "You are all caught up.")}</div>`;
          $("#nf-seg").onclick = (e) => { const b = e.target.closest("[data-c]"); if (b) { cat = b.dataset.c; draw(); } };
          $("#nf-read").onclick = async () => { await api("/api/notifications/read", "POST", { all: true }); toast("All notifications marked as read"); draw(); pollNotifs(); };
          $("#nf-clear").onclick = async () => { if (await confirmBox({ title: "Clear notification history?", message: "All current notifications will be removed from the list.", okText: "Clear" })) { await api("/api/notifications/clear", "POST", {}); toast("Notification history cleared"); draw(); pollNotifs(); } };
          $$("[data-n]", body).forEach((n) => (n.onclick = async () => { await api("/api/notifications/read", "POST", { id: +n.dataset.n }); pollNotifs(); const p = NOTIF_PAGE[n.dataset.link]; if (p) location.hash = "#/" + p; else draw(); }));
        };
        draw();
      }
    };
    $("#al-tabs").onclick = (e) => { const b = e.target.closest("[data-t]"); if (b) tab(b.dataset.t).catch(fail); };
    tab("low").catch(fail);
  },
};

/* =============================================================== ANALYTICS */
const REPORTS = [["valuation", "Inventory Valuation", "dollar-sign"], ["movements", "Stock Movement", "repeat"], ["warehouse", "Warehouse Performance", "home"], ["suppliers", "Supplier Performance", "truck"], ["purchases", "Purchase Report", "clipboard"],
  ["sales", "Sales Report", "trending-up"], ["fulfillment", "Order Fulfillment", "check-square"], ["returns", "Returns & Damaged Stock", "rotate-ccw"], ["lowstock", "Low Stock Report", "alert-triangle"]];
const sect = (n, t, inner, cls = "g2") => `<h3 style="margin:26px 0 12px;display:flex;gap:10px;align-items:center"><span class="pill navy">${n}</span>${t}</h3><div class="grid ${cls}">${inner}</div>`;
Pages.analytics = {
  async render(el, arg) {
    el.innerHTML = pageHead("Analytics & Reports", "Interactive charts and exportable reports - every number comes from the live database") + `<div class="tabs" id="an-tabs"><button data-t="charts" class="on">${ic("bar-chart-2", 16)} Charts</button><button data-t="reports">${ic("file-text", 16)} Reports</button></div><div id="rb"></div><div id="an-body"></div>`;
    const show = (t) => { $$("#an-tabs button").forEach((b) => b.classList.toggle("on", b.dataset.t === t)); App.tabAn = t; t === "charts" ? charts() : reports(); };
    const live = { timer: null };
    async function charts() {
      destroyCharts(); clearTimers();
      $("#an-body").innerHTML = sect(1, "Doughnut &amp; Pie", chartCard("a1", "Stock distribution by category", "Doughnut · units on hand") + chartCard("a2", "Inventory distribution across warehouses", "Pie · units on hand")) +
        sect(2, "Bar charts", chartCard("a3", "Products by category", "Number of products") + chartCard("a4", "Warehouse stock comparison", "Units stored vs capacity") + chartCard("a5", "Top-selling products", "Units sold in the selected period"), "g3") +
        sect(3, "Line charts", chartCard("a6", "Stock movement trend", "Transactions per type") + chartCard("a7", "Sales trend", "Revenue per period") + chartCard("a8", "Incoming vs outgoing inventory", "Units per period"), "g3") +
        sect(4, "Area charts", chartCard("a9", "Inventory value over time", "At purchase cost") + chartCard("a10", "Order volume trend", "Orders placed per period")) +
        sect(5, "Horizontal bar charts", chartCard("a11", "Top 10 products by quantity", "Units on hand now") + chartCard("a12", "Best-performing warehouses", "Units dispatched in the period")) +
        sect(6, "Stacked bar charts", chartCard("a13", "Available, reserved &amp; damaged stock", "Per warehouse") + chartCard("a14", "Order status breakdown", "Pending, processing and delivered per period")) +
        sect(7, "Radar &amp; polar area", chartCard("a15", "Warehouse performance radar", "Stock · free capacity · dispatch volume · on-time delivery") + chartCard("a16", "Product category distribution", "Polar area · inventory value")) +
        sect(8, "Mixed chart", chartCard("a17", "Orders (bars) and revenue (line)", "Dual axis"), "g-21").replace('<div class="grid g-21">', '<div class="grid" style="grid-template-columns:1fr">') +
        sect(9, "Real-time-style activity", `<div class="card"><div class="card-head"><div><h3>Stock movement &amp; order processing activity <span class="pill em" style="margin-left:6px">${ic("activity", 12)} LIVE</span></h3><small>Last 24 hours · refreshes every 10 seconds</small></div></div><div class="chart-box"><canvas id="a18"></canvas></div></div>`, "g2").replace('<div class="grid g2">', '<div class="grid" style="grid-template-columns:1fr">');
      try {
        const d = await api("/api/charts?" + rangeQS());
        CH.stockByCategory("a1", d); CH.stockByWarehouse("a2", d); CH.productsByCategory("a3", d); CH.warehouseCompare("a4", d); CH.topSelling("a5", d); CH.movementLines("a6", d); CH.salesTrend("a7", d); CH.inOut("a8", d);
        CH.inventoryValue("a9", d); CH.orderVolume("a10", d); CH.topQty("a11", d); CH.bestWarehouses("a12", d); CH.stockStack("a13", d); CH.orderStack("a14", d); CH.radar("a15", d); CH.polar("a16", d); CH.mixed("a17", d);
        const lv = await api("/api/live" + (App.wh && isAdmin() ? "?warehouse=" + App.wh : "")), lc = CH.live("a18", lv);
        App.timers.push(setInterval(async () => { if (!document.getElementById("a18")) return; try { const x = await api("/api/live" + (App.wh && isAdmin() ? "?warehouse=" + App.wh : "")); lc.data.labels = x.labels; lc.data.datasets[0].data = x.movements; lc.data.datasets[1].data = x.orders; lc.data.datasets[2].data = x.processing; lc.update("none"); } catch (e) { } }, 10000));
      } catch (e) { fail(e); }
    }
    let rep = arg && REPORTS.find((r) => r[0] === arg) ? arg : "valuation";
    function reports() {
      destroyCharts(); clearTimers();
      const list = REPORTS.filter((r) => r[0] !== "suppliers" || can("supplier.write"));
      $("#an-body").innerHTML = `<div class="grid" style="grid-template-columns:250px minmax(0,1fr);align-items:start"><div class="card" style="padding:10px" id="rp-list">${list.map(([k, l, i]) => `<button class="nav-item" style="color:var(--text)" data-r="${k}">${ic(i, 17)}<span class="nav-label">${l}</span></button>`).join("")}</div><div id="rp-view"></div></div>`;
      $$("#rp-list .nav-item").forEach((b) => { b.classList.toggle("active", b.dataset.r === rep); b.style.background = b.dataset.r === rep ? "var(--em-soft)" : ""; b.style.color = b.dataset.r === rep ? "var(--em)" : ""; });
      $("#rp-list").onclick = (e) => { const b = e.target.closest("[data-r]"); if (b) { rep = b.dataset.r; reports(); } };
      loadReport();
    }
    async function loadReport() {
      const v = $("#rp-view"); v.innerHTML = skeleton();
      try {
        const r = await api(`/api/reports/${rep}?` + rangeQS()), q = rangeQS();
        v.innerHTML = `<div class="print-area"><div class="card" style="margin-bottom:18px"><div class="card-head"><div><h3 style="font-size:19px">${esc(r.title)}</h3><small>Period ${esc(r.period)} · generated ${new Date().toLocaleString("en-GB")}</small></div>
          <div class="actions no-print"><a class="btn sm" href="/api/reports/${rep}?format=pdf&${q}">${ic("file-text", 14)} PDF</a><a class="btn sm" href="/api/reports/${rep}?format=xlsx&${q}">${ic("download", 14)} Excel</a><a class="btn sm" href="/api/reports/${rep}?format=csv&${q}">${ic("download", 14)} CSV</a><button class="btn sm navy" id="rp-print">${ic("printer", 14)} Print</button></div></div>
          <div class="stat-tiles" style="margin:0">${r.summary.map((s) => `<div class="tile"><small>${esc(s.label)}</small><b>${s.type === "money" ? fmt.money(s.value) : s.type === "num" ? fmt.num(s.value) : esc(s.value)}</b></div>`).join("")}</div></div>
          <div class="grid g-12"><div class="card"><div class="card-head"><h3>${esc(r.chart.title)}</h3></div><div class="chart-box sm"><canvas id="rp-chart"></canvas></div></div><div class="card" style="padding:8px 16px 16px"><div id="rp-table"></div></div></div></div>`;
        $("#rp-print").onclick = () => window.print();
        const cols = r.columns.map((c, i) => ({ key: "c" + i, label: c.label, sort: true, align: ["num", "money", "pct"].includes(c.type) ? "r" : "", render: (row) => { const x = row["c" + i]; return c.type === "money" ? fmt.money(x) : c.type === "pct" ? x + "%" : c.type === "num" ? fmt.num(x) : c.type === "date" ? fmt.date(x) : esc(x ?? ""); } }));
        makeTable($("#rp-table"), { columns: cols, pageSize: 10, rows: r.rows.map((row, n) => Object.fromEntries([["id", n], ...row.map((x, i) => ["c" + i, x])])), empty: emptyState("file-text", "No data for this period", "Try a longer date range.") });
        const ch = r.chart, pal = COLORS;
        const cfg = ch.type === "doughnut" ? { type: "doughnut", data: { labels: ch.labels, datasets: [{ data: ch.values, backgroundColor: pal, borderWidth: 3, borderColor: getComputedStyle(document.documentElement).getPropertyValue("--card").trim() }] }, options: { cutout: "62%", plugins: { legend: { position: "bottom" } } } }
          : ch.type === "line" ? { type: "line", data: { labels: ch.labels, datasets: [{ label: "Value", data: ch.values, borderColor: "#119B78", backgroundColor: "rgba(17,155,120,.15)", fill: true, tension: .38, borderWidth: 3, pointRadius: 2 }] }, options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, border: { display: false } }, x: { grid: { display: false }, ticks: { maxTicksLimit: 10 } } } } }
            : { type: "bar", data: { labels: ch.labels.map((l) => (String(l).length > 18 ? String(l).slice(0, 17) + "…" : l)), datasets: [{ label: ch.values2 ? "Available" : "Value", data: ch.values, backgroundColor: "#119B78", borderRadius: 7, maxBarThickness: 36 }].concat(ch.values2 ? [{ label: "Reorder level", data: ch.values2, backgroundColor: "#F29A38", borderRadius: 7, maxBarThickness: 36 }] : []) }, options: { plugins: { legend: { display: !!ch.values2, position: "bottom" } }, scales: { y: { beginAtZero: true, border: { display: false } }, x: { grid: { display: false }, ticks: { font: { size: 10 }, maxRotation: 45 } } } } };
        mk("rp-chart", cfg);
      } catch (e) { v.innerHTML = emptyState("alert-circle", "Could not load the report", esc(e.message)); }
    }
    $("#an-tabs").onclick = (e) => { const b = e.target.closest("[data-t]"); if (b) show(b.dataset.t); };
    rangeBar($("#rb"), () => (App.tabAn === "reports" ? loadReport() : charts()));
    show(arg && REPORTS.find((r) => r[0] === arg) ? "reports" : App.tabAn || "charts");
  },
};

/* =============================================================== DSA VISUALIZATION */
const DS = { tab: "queue", frames: [], fi: 0, playing: false, timer: null, mode: "auto", speed: 700, algo: "bubble", algoFrames: [], af: 0, aTimer: null, info: [] };
function qvTrack(nodes, front, rear, opt = {}) {
  if (!nodes.length) return `<div class="qv-track"><div class="qv-end" style="min-width:300px;gap:10px"><span class="qv-null">FRONT = None</span><span class="qv-null">REAR = None</span><span class="muted" style="font-weight:600;letter-spacing:0;font-size:13px">The queue is empty</span></div></div>`;
  const shown = opt.limit ? nodes.slice(0, opt.limit) : nodes, more = nodes.length - shown.length;
  return `<div class="qv-track">${shown.map((n, i) => `<div class="qv-node ${n.uid === front ? "front" : ""} ${n.uid === rear ? "rear" : ""} ${opt.hl === n.uid ? (opt.kind === "match" ? "match" : "hl") : ""}" style="animation-delay:${opt.noAnim ? 0 : i * 40}ms">
      ${n.uid === front ? '<span class="qv-tag f">FRONT</span>' : ""}${n.uid === rear ? '<span class="qv-tag r">REAR</span>' : ""}
      <div class="qv-box"><div class="qv-data">${esc(n.label)}</div><div class="qv-ptr" title="next pointer">${n.next ? "next" : "None"}</div></div>
      ${n.next && i < shown.length - 1 ? '<div class="qv-arrow"></div>' : i === shown.length - 1 ? (more > 0 ? `<span class="muted" style="padding:0 12px">+${more} more</span>` : '<div class="qv-arrow"></div><span class="qv-null">None</span>') : ""}</div>`).join("")}</div>`;
}
function ptrBox(s) {
  const f = s.nodes.find((n) => n.uid === s.front), r = s.nodes.find((n) => n.uid === s.rear);
  return `<div class="ptr-box"><div><small>FRONT pointer</small><b>${f ? esc(f.label) : "None"}</b></div><div><small>REAR pointer</small><b>${r ? esc(r.label) : "None"}</b></div><div><small>Size</small><b>${s.size}</b></div></div>`;
}
Pages.dsa = {
  async render(el, arg) {
    if (arg && ["queue", "live", "algo", "theory"].includes(arg)) DS.tab = arg;
    el.innerHTML = pageHead("DSA Visualization", "Group C · QUEUE - watch the real data structure and algorithms execute step by step") + `<div class="tabs" id="ds-tabs"><button data-t="queue">${ic("layers", 16)} Queue visualizer</button><button data-t="live">${ic("activity", 16)} Live warehouse queues</button><button data-t="algo">${ic("bar-chart-2", 16)} Algorithms lab</button><button data-t="theory">${ic("book-open", 16)} Complexity &amp; theory</button></div><div id="ds-body"></div>`;
    $("#ds-tabs").onclick = (e) => { const b = e.target.closest("[data-t]"); if (b) { dsStop(); DS.tab = b.dataset.t; Pages.dsa.draw(); } };
    Pages.dsa.draw();
  },
  draw() {
    $$("#ds-tabs button").forEach((b) => b.classList.toggle("on", b.dataset.t === DS.tab));
    ({ queue: dsQueue, live: dsLive, algo: dsAlgo, theory: dsTheory })[DS.tab]().catch(fail);
  },
};
function dsStop() { clearInterval(DS.timer); clearInterval(DS.aTimer); DS.playing = false; DS.frames = []; DS.algoFrames = []; }

/* ------------------------------------------------ sandbox queue visualizer */
async function dsQueue() {
  const d = await api("/api/dsa/sandbox");
  $("#ds-body").innerHTML = `<div class="grid qv-split" style="grid-template-columns:minmax(340px,400px) minmax(0,1fr);align-items:start"><div class="card"><div class="card-head"><div><h3>Operations</h3><small>Each button runs the real Queue class on the server and returns every step it took</small></div></div>
    <div class="form-grid" style="grid-template-columns:1fr 1fr;margin-bottom:12px"><div class="field"><label>Value</label><input id="qv-val" value="ORD-104" maxlength="14"></div><div class="field"><label>New value (update)</label><input id="qv-new" value="ORD-777" maxlength="14"></div></div>
    <div class="ctrl-grid"><button class="btn primary" data-op="enqueue">${ic("plus", 15)} Enqueue</button><button class="btn" data-op="dequeue">${ic("minus", 15)} Dequeue</button><button class="btn" data-op="peek">${ic("eye", 15)} Peek</button><button class="btn" data-op="search">${ic("search", 15)} Search</button>
    <button class="btn" data-op="update">${ic("edit-2", 15)} Update</button><button class="btn danger" data-op="delete">${ic("trash-2", 15)} Delete</button><button class="btn danger" data-op="clear">${ic("x-circle", 15)} Clear</button><button class="btn" data-op="reset">${ic("refresh-cw", 15)} Reset</button></div>
    <div style="display:flex;gap:10px;margin-top:14px;align-items:center;flex-wrap:wrap"><div class="seg" id="qv-mode"><button data-m="auto" class="on">Auto-play</button><button data-m="step">Step-by-step</button></div><select id="qv-speed" title="Animation speed"><option value="1100">Slow</option><option value="700" selected>Normal</option><option value="320">Fast</option></select></div>
    <p class="muted" style="margin-top:12px;font-size:12.5px">Enqueue adds at the <b>REAR</b>, Dequeue removes from the <b>FRONT</b>. Search, Update and Delete are not native queue operations, so the queue is rotated (dequeue → check → enqueue) - you will see every rotation.</p></div>
    <div style="display:flex;flex-direction:column;gap:18px"><div class="card"><div class="card-head"><div><h3>Queue structure</h3><small id="qv-msg">Ready - choose an operation</small></div><div class="actions no-print"><button class="btn sm" id="qv-prev">${ic("skip-back", 14)}</button><button class="btn sm primary" id="qv-play">${ic("play", 14)} Play</button><button class="btn sm" id="qv-next">Next step ${ic("skip-forward", 14)}</button><button class="btn sm ghost" id="qv-skip">Skip</button></div></div>
      <div class="qv-hold" id="qv-hold"><span class="muted" style="font-size:12px;font-weight:700;letter-spacing:.6px">IN HAND:</span><span class="muted" id="qv-hold-empty">nothing</span></div><div class="qv-stage" id="qv-stage"></div><div style="margin-top:14px" id="qv-ptr"></div><div class="muted" style="margin-top:10px;font-size:12.5px" id="qv-count"></div></div></div></div>
    <div class="grid g2"><div class="card"><div class="card-head"><div><h3>Step-by-step execution</h3><small>What the queue code did, in order</small></div></div><div class="qv-log" id="qv-log"><div class="muted">Run an operation to see its steps.</div></div></div>
    <div style="display:flex;flex-direction:column;gap:18px"><div class="card" id="qv-cx"><div class="card-head"><h3>Time complexity</h3></div><div id="qv-cx-body" class="muted">Run an operation to see its complexity.</div></div><div class="card"><div class="card-head"><h3>Operation history</h3></div><div id="qv-hist" style="max-height:230px;overflow:auto"></div></div></div></div>`;
  let state = d.state;
  const drawState = (s, fr) => {
    $("#qv-stage").innerHTML = qvTrack(s.nodes, s.front, s.rear, { hl: fr && fr.hl, kind: fr && fr.kind, noAnim: !!fr }); $("#qv-ptr").innerHTML = ptrBox(s);
    $("#qv-count").innerHTML = `${s.name} · enqueue calls <b>${s.enqueue_calls}</b> · dequeue calls <b>${s.dequeue_calls}</b> <span class="muted">(rotations included)</span>`;
    const h = $("#qv-hold"); h.innerHTML = `<span class="muted" style="font-size:12px;font-weight:700;letter-spacing:.6px">IN HAND:</span>` + (fr && fr.hold ? `<span class="chip">${esc(fr.hold.label)}</span>` : `<span class="muted">nothing</span>`);
  };
  const drawHist = (h) => { $("#qv-hist").innerHTML = h.length ? `<table class="tbl compact"><tbody>${h.slice().reverse().map((x) => `<tr><td class="muted">${x.ts}</td><td><b>${x.op}</b></td><td>${esc(x.detail)}</td><td><span class="cx ${x.time === "O(1)" ? "" : "n"}">${x.time}</span></td></tr>`).join("")}</tbody></table>` : `<div class="muted">No operations yet.</div>`; };
  const showFrame = (i) => {
    DS.fi = i; const fr = DS.frames[i];
    drawState({ ...state, nodes: fr.nodes, front: fr.front, rear: fr.rear, size: fr.size }, fr); $("#qv-msg").innerHTML = `<b>Step ${i + 1}/${DS.frames.length}:</b> ${esc(fr.msg)}`;
    $("#qv-log").innerHTML = DS.frames.slice(0, i + 1).map((f, n) => `<div class="${n === i ? "cur" : ""}"><b>${n + 1}</b><span>${esc(f.msg)}</span></div>`).join(""); $("#qv-log").scrollTop = 1e6;
  };
  const finish = () => { clearInterval(DS.timer); DS.playing = false; $("#qv-play").innerHTML = `${ic("play", 14)} Play`; drawState(state); };
  const play = () => { if (!DS.frames.length) return; if (DS.fi >= DS.frames.length - 1) DS.fi = -1; DS.playing = true; $("#qv-play").innerHTML = `${ic("pause", 14)} Pause`; clearInterval(DS.timer);
    DS.timer = setInterval(() => { if (DS.fi + 1 >= DS.frames.length) return finish(); showFrame(DS.fi + 1); if (DS.fi + 1 >= DS.frames.length) setTimeout(finish, DS.speed * .6); }, DS.speed); };
  drawState(state); drawHist(d.history);
  $("#qv-mode").onclick = (e) => { const b = e.target.closest("[data-m]"); if (!b) return; DS.mode = b.dataset.m; $$("#qv-mode button").forEach((x) => x.classList.toggle("on", x === b)); };
  $("#qv-speed").onchange = (e) => { DS.speed = +e.target.value; if (DS.playing) play(); };
  $("#qv-play").onclick = () => { if (DS.playing) { clearInterval(DS.timer); DS.playing = false; $("#qv-play").innerHTML = `${ic("play", 14)} Play`; } else play(); };
  $("#qv-next").onclick = () => { if (DS.fi + 1 < DS.frames.length) showFrame(DS.fi + 1); else if (DS.frames.length) finish(); };
  $("#qv-prev").onclick = () => { if (DS.fi > 0) showFrame(DS.fi - 1); };
  $("#qv-skip").onclick = () => { if (DS.frames.length) { showFrame(DS.frames.length - 1); finish(); } };
  $$("[data-op]").forEach((b) => (b.onclick = async () => {
    if (DS.playing || (DS.frames.length && DS.fi < DS.frames.length - 1 && DS.mode === "step")) return toast("Finish or skip the current animation first", "warn");
    try {
      const r = await api("/api/dsa/sandbox", "POST", { op: b.dataset.op, value: $("#qv-val").value, new_value: $("#qv-new").value });
      state = r.state; drawHist(r.history);
      if (r.complexity && r.complexity.time) $("#qv-cx-body").innerHTML = `<div style="display:flex;gap:12px;align-items:center;margin-bottom:8px"><span class="cx ${r.complexity.time === "O(1)" ? "" : "n"}" style="font-size:16px;padding:5px 14px">${r.complexity.time}</span><b>${fmt.title(r.complexity.op)}</b></div><p class="muted">${esc(r.complexity.why)}</p>`;
      if (r.error) toast(r.error, "error"); else toast(r.message, "info");
      DS.frames = r.steps || [];
      if (!DS.frames.length) { drawState(state); $("#qv-msg").textContent = r.message; return; }
      DS.fi = -1; if (DS.mode === "auto") play(); else { showFrame(0); }
    } catch (e) { fail(e); }
  }));
}

/* ------------------------------------------------ live warehouse queues */
async function dsLive() {
  const q = await api("/api/dsa/live");
  const defs = [["inventory", "Inventory Queue", "package", "Every product record is stored in this queue.", "CREATE = enqueue at REAR · READ / UPDATE / DELETE = rotate the queue"], ["orders", "Order Queue", "clock", "Pending customer orders. The oldest order is confirmed first.", "Place order = enqueue · Process next = dequeue · Cancel = remove by rotation"], ["dispatch", "Dispatch Queue", "truck", "Packed orders waiting for a truck. FIFO dispatch.", "Mark packed = enqueue · Dispatch next = dequeue"]];
  $("#ds-body").innerHTML = `<div class="card hero-card" style="margin-bottom:18px"><h3>These are the real queues running this application</h3><p class="muted" style="margin-top:6px">Everything you do in Products, Customer Orders and Shipments goes through the custom Queue class (<span class="mono">ds/queue.py</span>) - shown here exactly as stored in memory (FRONT → REAR).</p></div>` +
    defs.map(([k, t, i, desc, ops]) => { const s = q[k]; return `<div class="card live-q"><div class="card-head"><div><h3>${ic(i, 18)} ${t} <span class="pill tq">${s.size} node${s.size === 1 ? "" : "s"}</span></h3><small>${desc}<br><b>${ops}</b></small></div><div class="actions no-print">${k === "orders" && can("order.advance") ? `<button class="btn sm primary" data-lv="/api/orders/process-next">Dequeue (process next)</button>` : ""}${k === "dispatch" && can("order.advance") ? `<button class="btn sm orange" data-lv="/api/orders/dispatch-next">Dequeue (dispatch next)</button>` : ""}${k === "inventory" && can("product.write") ? `<a class="btn sm primary" href="#/inventory/new">Enqueue (add product)</a>` : ""}</div></div>
      <div class="qv-stage" style="padding:8px 14px 4px;min-height:0">${qvTrack(s.nodes, s.front, s.rear, { limit: 10, noAnim: true })}</div>${ptrBox({ ...s })}<p class="muted" style="margin-top:10px;font-size:12.5px">enqueue calls <b>${s.enqueue_calls}</b> · dequeue calls <b>${s.dequeue_calls}</b></p></div>`; }).join("") +
    `<div class="card"><div class="card-head"><div><h3>Recent queue activity</h3><small>Audit trail of enqueue / dequeue / rotation operations</small></div></div><div id="ds-act"></div></div>`;
  $$("[data-lv]").forEach((b) => (b.onclick = async () => { try { const r = await api(b.dataset.lv, "POST", {}); toast(r.processed ? `Dequeued ${r.processed[0]}` : `Dispatched ${r.dispatched[0]}`); dsLive(); } catch (e) { fail(e); } }));
  const act = await api("/api/activity?structure=Queue&limit=60");
  makeTable($("#ds-act"), { rows: act, pageSize: 8, columns: [{ key: "ts", label: "Time", render: (a) => fmt.dt(a.ts) }, { key: "action", label: "Operation", render: (a) => pill(a.action === "ENQUEUE" ? "STOCK_IN" : a.action === "DEQUEUE" ? "STOCK_OUT" : a.action === "DELETE" ? "DAMAGED" : "TRANSFER", a.action) }, { key: "structure", label: "Queue" }, { key: "detail", label: "Details" }, { key: "user", label: "User" }] });
}

/* ------------------------------------------------ algorithms lab */
async function dsAlgo() {
  if (!DS.info.length) DS.info = await api("/api/algo/info");
  const body = $("#ds-body");
  const info = () => DS.info.find((a) => a.id === DS.algo);
  body.innerHTML = `<div class="algo-pick" id="al-pick">${DS.info.map((a) => `<button class="algo-card ${a.id === DS.algo ? "on" : ""}" data-a="${a.id}"><b>${a.name}</b><small>${a.type === "sort" ? "Sorting" : "Searching"} · avg ${a.avg}</small></button>`).join("")}</div>
    <div class="grid g-12" style="margin-top:18px;align-items:start"><div class="card" id="al-info"></div><div class="card"><div class="card-head"><div><h3>Demonstration</h3><small id="al-msg">Enter numbers and press Run</small></div></div>
      <div class="toolbar"><input id="al-data" class="grow" value="42, 17, 8, 93, 25, 61, 4, 38"><input id="al-target" type="number" placeholder="Target" style="width:100px"><label class="chk" style="display:flex;gap:6px;align-items:center" id="al-desc-w"><input type="checkbox" id="al-desc" style="height:16px;width:16px"> Descending</label><button class="btn" id="al-rand">${ic("shuffle", 15)} Random</button><button class="btn primary" id="al-run">${ic("play", 15)} Run</button></div>
      <div id="al-warn"></div><div class="bars" id="al-bars"></div>
      <div class="legend" style="margin-top:10px"><span><i style="background:var(--tq)"></i>Element</span><span><i style="background:var(--or)"></i>Comparing</span><span><i style="background:var(--red)"></i>Swap / move</span><span><i style="background:var(--em)"></i>Found / sorted</span></div>
      <div style="display:flex;gap:8px;margin-top:14px;align-items:center;flex-wrap:wrap"><button class="btn sm" id="al-prev">${ic("skip-back", 14)}</button><button class="btn sm primary" id="al-play">${ic("play", 14)} Play</button><button class="btn sm" id="al-next">${ic("skip-forward", 14)}</button><select id="al-speed"><option value="800">Slow</option><option value="400" selected>Normal</option><option value="120">Fast</option></select><span class="muted" id="al-stats"></span></div></div></div>
    <div class="card" style="margin-top:18px"><div class="card-head"><div><h3>Performance benchmark</h3><small>Run all four sorts and both searches on the same random data - counted comparisons are real</small></div><div class="actions"><select id="bm-n"><option>100</option><option selected>300</option><option>600</option><option>1000</option></select><button class="btn primary" id="bm-run">${ic("zap", 15)} Run benchmark</button></div></div><div id="bm-out" class="muted">Press "Run benchmark" to compare the algorithms.</div></div>`;
  const drawInfo = () => { const a = info(); $("#al-info").innerHTML = `<div class="card-head"><div><h3>${a.name}</h3><small>${a.purpose}</small></div></div><div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px"><span class="cx">Best ${a.best}</span><span class="cx n">Average ${a.avg}</span><span class="cx n">Worst ${a.worst}</span><span class="cx">Space ${a.space}</span></div><h4>Step-by-step working</h4><ol class="steps-list">${a.steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>${a.id === "binary" ? '<div class="stats-strip" style="margin-top:12px">' + ic("alert-triangle", 15) + ' Binary search only works on <b>sorted</b> data - try an unsorted list to see the guard.</div>' : ""}`; $("#al-target").style.display = a.type === "search" ? "" : "none"; $("#al-desc-w").style.display = a.type === "sort" ? "" : "none"; };
  drawInfo();
  const parse = () => $("#al-data").value.split(/[,\s]+/).filter(Boolean);
  const bars = (arr, fr) => { const mx = Math.max(...arr, 1), mn = Math.min(...arr, 0), rg = mx - Math.min(mn, 0) || 1; $("#al-bars").innerHTML = arr.map((v, i) => { const hl = fr && fr.hl.includes(i), dim = fr && fr.lo !== undefined && (i < fr.lo || i > fr.hi); const cls = hl ? (fr.kind === "swap" ? "swap" : fr.kind === "found" ? "found" : fr.kind === "done" ? "done" : "cmp") : fr && fr.kind === "done" ? "done" : ""; return `<div class="bar ${cls} ${dim ? "dim" : ""}" style="height:${Math.max(6, ((v - Math.min(mn, 0)) / rg) * 205)}px"><span>${v}</span></div>`; }).join(""); };
  const showA = (i) => { DS.af = i; const fr = DS.algoFrames[i]; bars(fr.arr, fr); $("#al-msg").innerHTML = `<b>Step ${i + 1}/${DS.algoFrames.length}:</b> ${esc(fr.msg)}`; };
  const stopA = () => { clearInterval(DS.aTimer); DS.playing = false; $("#al-play").innerHTML = `${ic("play", 14)} Play`; };
  const playA = () => { if (!DS.algoFrames.length) return; if (DS.af >= DS.algoFrames.length - 1) DS.af = -1; DS.playing = true; $("#al-play").innerHTML = `${ic("pause", 14)} Pause`; clearInterval(DS.aTimer); DS.aTimer = setInterval(() => { if (DS.af + 1 >= DS.algoFrames.length) return stopA(); showA(DS.af + 1); }, +$("#al-speed").value); };
  bars([42, 17, 8, 93, 25, 61, 4, 38]);
  const run = async (dataOverride) => {
    stopA(); $("#al-warn").innerHTML = "";
    const a = info(), data = dataOverride || parse();
    try {
      const r = await api("/api/algo/demo", "POST", { algo: a.id, data, target: $("#al-target").value, desc: $("#al-desc").checked });
      DS.algoFrames = r.frames; DS.af = -1; $("#al-stats").innerHTML = `Comparisons: <b>${r.comparisons}</b>${r.moves !== undefined ? ` · Moves: <b>${r.moves}</b>` : ""}${a.type === "search" ? (r.found ? ` · <b style="color:var(--em)">Found at index ${r.index}</b>` : ' · <b style="color:var(--red)">Not found</b>') : ""}`;
      bars(r.frames[0].arr, r.frames[0]); playA();
    } catch (e) {
      if (e.data && e.data.needs_sort) { $("#al-warn").innerHTML = `<div class="form-banner">${esc(e.message)} <button class="btn sm primary" id="al-fix" style="margin-left:10px">Sort with merge sort, then search</button></div>`; $("#al-fix").onclick = () => { $("#al-data").value = e.data.sorted.join(", "); run(e.data.sorted); }; } else fail(e);
    }
  };
  $("#al-pick").onclick = (e) => { const b = e.target.closest("[data-a]"); if (!b) return; stopA(); DS.algo = b.dataset.a; $$(".algo-card").forEach((x) => x.classList.toggle("on", x === b)); drawInfo(); $("#al-warn").innerHTML = ""; if (info().id === "binary" && !$("#al-target").value) $("#al-target").value = 25; };
  $("#al-run").onclick = () => run();
  $("#al-rand").onclick = () => { $("#al-data").value = Array.from({ length: 9 }, () => 1 + Math.floor(Math.random() * 99)).join(", "); bars(parse().map(Number)); };
  $("#al-play").onclick = () => (DS.playing ? stopA() : playA());
  $("#al-next").onclick = () => { if (DS.af + 1 < DS.algoFrames.length) showA(DS.af + 1); }; $("#al-prev").onclick = () => { if (DS.af > 0) showA(DS.af - 1); };
  $("#al-speed").onchange = () => { if (DS.playing) playA(); };
  $("#bm-run").onclick = async () => {
    try {
      const r = await api("/api/algo/benchmark", "POST", { n: +$("#bm-n").value }), mx = Math.max(...r.sorts.map((s) => s.comparisons));
      $("#bm-out").innerHTML = `<div class="grid g2"><div class="chart-box sm"><canvas id="bm-ch"></canvas></div><div><table class="tbl compact"><thead><tr><th>Algorithm</th><th class="r">Comparisons</th><th class="r">Moves</th><th class="r">Time</th></tr></thead><tbody>${r.sorts.map((s) => `<tr><td><b>${fmt.title(s.algorithm)} sort</b></td><td class="r">${fmt.num(s.comparisons)}</td><td class="r">${fmt.num(s.moves)}</td><td class="r">${s.ms} ms</td></tr>`).join("")}</tbody></table>
        <div class="stats-strip" style="margin-top:12px">Searching ${r.n} numbers: linear search <b>${r.linear_comparisons}</b> comparisons · binary search <b>${r.binary_comparisons}</b> comparisons</div></div></div>`;
      mk("bm-ch", { type: "bar", data: { labels: r.sorts.map((s) => fmt.title(s.algorithm)), datasets: [{ label: `Comparisons for n = ${r.n}`, data: r.sorts.map((s) => s.comparisons), backgroundColor: ["#DB5B50", "#F29A38", "#20B8B0", "#119B78"], borderRadius: 8 }] }, options: { plugins: { legend: { position: "bottom" } }, scales: { y: { type: "logarithmic", border: { display: false } }, x: { grid: { display: false } } } } });
    } catch (e) { fail(e); }
  };
}

/* ------------------------------------------------ theory */
async function dsTheory() {
  if (!DS.info.length) DS.info = await api("/api/algo/info");
  $("#ds-body").innerHTML = `<div class="grid g2" style="align-items:start"><div class="card"><div class="card-head"><div><h3>Queue operations in this project</h3><small>Implemented in <span class="mono">ds/queue.py</span> with linked nodes (FRONT / REAR pointers)</small></div></div>
    <table class="tbl compact"><thead><tr><th>Operation</th><th>Used for</th><th>Time</th></tr></thead><tbody>
    <tr><td class="mono">enqueue(x)</td><td>CREATE: add product · place order · pack order</td><td><span class="cx">O(1)</span></td></tr><tr><td class="mono">dequeue()</td><td>Process next order · dispatch next order</td><td><span class="cx">O(1)</span></td></tr><tr><td class="mono">peek()</td><td>See who is next in line</td><td><span class="cx">O(1)</span></td></tr><tr><td class="mono">is_empty() / size()</td><td>Underflow guard · counters</td><td><span class="cx">O(1)</span></td></tr>
    <tr><td class="mono">find(pred)</td><td>READ a product by ID</td><td><span class="cx n">O(n)</span></td></tr><tr><td class="mono">update(pred, fn)</td><td>UPDATE a product</td><td><span class="cx n">O(n)</span></td></tr><tr><td class="mono">remove(pred)</td><td>DELETE a product · cancel an order</td><td><span class="cx n">O(n)</span></td></tr></tbody></table>
    <h4 style="margin:18px 0 8px">Why rotation?</h4><p class="muted">A queue only lets you touch the FRONT. To read, update or delete an item in the middle we dequeue every item, inspect it, and enqueue it again at the REAR - after <i>n</i> steps the original FIFO order is restored. This is honest queue behaviour: it is O(n) because a queue is not designed for random access.</p></div>
    <div class="card"><div class="card-head"><h3>Why a Queue fits a warehouse</h3></div><ul class="steps-list"><li><b>Fairness:</b> customer orders are confirmed and dispatched strictly in the order they arrive.</li><li><b>Dock operations:</b> trucks and packed orders are handled first-come, first-served.</li><li><b>FIFO stock:</b> perishable batches are consumed earliest-expiry-first (FEFO) which follows the same idea.</li><li><b>Pipeline:</b> Order Queue → (confirm, process, pack) → Dispatch Queue → shipment.</li></ul>
      <h4 style="margin:16px 0 8px">Algorithms used in the app</h4><ul class="steps-list"><li>Inventory <b>sorting</b> (Product ID, Name, Quantity, Price, Category): merge / insertion / selection / bubble sort - your choice.</li><li>Inventory <b>search</b>: linear search (contains) or binary search (exact, after sorting).</li></ul></div></div>
    <div class="card" style="margin-top:18px"><div class="card-head"><h3>Algorithm complexity table</h3></div><table class="tbl"><thead><tr><th>Algorithm</th><th>Type</th><th>Best</th><th>Average</th><th>Worst</th><th>Space</th><th>Purpose</th></tr></thead><tbody>${DS.info.map((a) => `<tr><td><b>${a.name}</b></td><td>${a.type === "sort" ? "Sorting" : "Searching"}</td><td><span class="cx">${a.best}</span></td><td><span class="cx n">${a.avg}</span></td><td><span class="cx n">${a.worst}</span></td><td>${a.space}</td><td class="muted">${esc(a.purpose)}</td></tr>`).join("")}</tbody></table></div>`;
}

/* =============================================================== SETTINGS */
Pages.settings = {
  async render(el, arg) {
    const tabs = [["profile", "Profile", "user"], ...(isAdmin() ? [["users", "Users & roles", "users"], ["system", "System", "sliders"]] : []), ["about", "About", "info"]];
    let tab = tabs.find((t) => t[0] === arg) ? arg : "profile";
    el.innerHTML = pageHead("System Settings", "Account, users, alert thresholds and project information") + `<div class="tabs" id="st-tabs">${tabs.map(([k, l, i]) => `<button data-t="${k}">${ic(i, 16)} ${l}</button>`).join("")}</div><div id="st-body"></div>`;
    const draw = async () => {
      $$("#st-tabs button").forEach((b) => b.classList.toggle("on", b.dataset.t === tab));
      const b = $("#st-body");
      if (tab === "profile") {
        b.innerHTML = `<div class="grid g2" style="align-items:start"><div class="card"><div class="card-head"><h3>My profile</h3></div><div class="info-list" style="margin-bottom:16px"><div><span>Username</span><b>${esc(App.user.username)}</b></div><div><span>Role</span><b>${fmt.title(App.user.role)}</b></div><div><span>Warehouse</span><b>${esc(App.user.warehouse_name)}</b></div></div><form id="pf" novalidate></form></div>
          <div class="card"><div class="card-head"><h3>Appearance</h3></div><p class="muted" style="margin-bottom:12px">Switch between the light and dark interface. Charts adapt automatically.</p><button class="btn" id="st-theme">${ic("moon", 16)} Toggle light / dark mode</button>
          <h4 style="margin:22px 0 10px">What you can do</h4><div style="display:flex;gap:6px;flex-wrap:wrap">${App.user.pages.map((p) => `<span class="pill tq">${fmt.title(p)}</span>`).join("")}</div></div></div>`;
        const holder = $("#pf");
        holder.innerHTML = [{ name: "full_name", label: "Full name", required: true, full: true }, { name: "email", label: "Email", type: "email", full: true }, { name: "password", label: "New password", type: "password", full: true, hint: "Leave empty to keep your current password" }].map((f) => fieldHtml(f, App.user[f.name])).join("") + `<button class="btn primary" style="margin-top:14px" type="submit">Save profile</button>`;
        holder.className = "form-grid"; holder.querySelectorAll(".field").forEach((f) => (f.style.gridColumn = "1/-1"));
        holder.onsubmit = async (e) => { e.preventDefault(); const d = Object.fromEntries(new FormData(holder).entries()); try { await api("/api/auth/profile", "PUT", d); toast("Profile saved"); App.user = await api("/api/auth/me"); renderUser(); } catch (er) { if (!(er.field && setFieldError(holder, er.field, er.message))) fail(er); } };
        $("#st-theme").onclick = toggleTheme;
      } else if (tab === "users") {
        const users = await api("/api/users");
        b.innerHTML = `<div class="card"><div class="toolbar"><div class="muted">Administrators have full access · Managers run one warehouse · Employees process stock and orders</div><span class="grow"></span><button class="btn primary" id="u-add">${ic("plus", 16)} Add user</button></div><div id="u-table"></div></div>`;
        makeTable($("#u-table"), { rows: users, pageSize: 8, onAction: async (a, u) => { if (a === "edit") userForm(u, draw); if (a === "del" && (await confirmBox({ title: "Delete user?", message: `<b>${esc(u.full_name)}</b> will lose access immediately.`, okText: "Delete" }))) try { await api("/api/users/" + u.id, "DELETE"); toast("User deleted"); draw(); } catch (e) { fail(e); } },
          columns: [{ key: "full_name", label: "Name", render: (u) => `<div class="prod-cell"><span class="avatar">${esc(u.full_name[0])}</span><div><b>${esc(u.full_name)}</b><div class="pcode">@${esc(u.username)} · ${esc(u.email || "")}</div></div></div>` }, { key: "role", label: "Role", render: (u) => `<span class="pill ${u.role === "admin" ? "navy" : u.role === "manager" ? "em" : "tq"}">${fmt.title(u.role)}</span>` }, { key: "warehouse_name", label: "Warehouse", render: (u) => esc(u.warehouse_name || "All") },
            { key: "active", label: "Status", render: (u) => pill(u.active ? "Active" : "Inactive") }, { key: "act", label: "", render: (u) => `<div class="row-acts">${actBtn("edit", u.id, "edit-2", "Edit")}${u.id !== App.user.id ? actBtn("del", u.id, "trash-2", "Delete", "del") : ""}</div>` }] });
        $("#u-add").onclick = () => userForm(null, draw);
      } else if (tab === "system") {
        const s = App.meta.settings;
        b.innerHTML = `<div class="grid g2" style="align-items:start"><div class="card"><div class="card-head"><div><h3>Company &amp; alert thresholds</h3><small>Used by the smart alert rules</small></div></div><form id="sf"></form></div><div class="card"><div class="card-head"><h3>Demo data</h3></div><p class="muted" style="margin-bottom:14px">Reset the database to the original demo dataset (12 months of simulated warehouse operations). All changes you made will be lost.</p><button class="btn danger" id="st-reset">${ic("refresh-cw", 16)} Reset demo data</button></div></div>`;
        const f = $("#sf"); f.className = "form-grid";
        f.innerHTML = [{ name: "company_name", label: "Company name", full: true }, { name: "expiry_warning_days", label: "Expiry warning (days before)", type: "number", min: 1 }, { name: "capacity_warning_pct", label: "Capacity warning (%)", type: "number", min: 1 }, { name: "po_pending_days", label: "Pending PO alert after (days)", type: "number", min: 1 }].map((x) => fieldHtml(x, s[x.name])).join("") + `<div class="field full"><button class="btn primary" type="submit">Save settings</button></div>`;
        f.onsubmit = async (e) => { e.preventDefault(); try { await api("/api/settings", "PUT", Object.fromEntries(new FormData(f).entries())); toast("Settings saved - alerts recalculated"); await refreshMeta(); pollNotifs(); } catch (er) { if (!(er.field && setFieldError(f, er.field, er.message))) fail(er); } };
        $("#st-reset").onclick = async () => { if (await confirmBox({ title: "Reset all data?", message: "The database will be rebuilt with fresh demo data. This cannot be undone.", okText: "Reset everything" })) try { await api("/api/system/reset", "POST", {}); toast("Demo data restored"); await refreshMeta(); App.user = await api("/api/auth/me"); renderUser(); location.hash = "#/overview"; route(); } catch (e) { fail(e); } };
      } else {
        b.innerHTML = `<div class="card hero-card"><h2>Intelligent Supply Chain &amp; Warehouse Management System</h2><p class="muted" style="margin-top:8px">Mehran University of Engineering &amp; Technology · Software Engineering · SW 212 Data Structures &amp; Algorithms · Open Ended Lab</p></div><div class="grid g2" style="margin-top:18px"><div class="card"><h3 style="margin-bottom:12px">Project</h3><div class="info-list"><div><span>Assigned group</span><b>Group C - Queue</b></div><div><span>Primary data structure</span><b>Custom linked Queue (FRONT / REAR)</b></div><div><span>Algorithms</span><b>Linear / binary search · bubble, selection, insertion, merge sort</b></div><div><span>Backend</span><b>Python · Flask · SQLite</b></div><div><span>Frontend</span><b>HTML · CSS · JavaScript · Chart.js</b></div></div></div>
          <div class="card"><h3 style="margin-bottom:12px">Where the DSA code lives</h3><div class="info-list"><div><span>Queue</span><b class="mono">ds/queue.py</b></div><div><span>Algorithms</span><b class="mono">ds/algorithms.py</b></div><div><span>Queue in use</span><b class="mono">backend/services.py</b></div><div><span>Visualization</span><b>DSA Visualization page</b></div></div></div></div>`;
      }
    };
    $("#st-tabs").onclick = (e) => { const x = e.target.closest("[data-t]"); if (x) { tab = x.dataset.t; draw(); } };
    draw().catch(fail);
  },
};
function userForm(u, after) {
  const e = !!u;
  formModal({ title: e ? "Edit user" : "Add user", fields: [{ name: "full_name", label: "Full name", required: true, full: true }, { name: "username", label: "Username", required: true }, { name: "email", label: "Email", type: "email" },
    { name: "role", label: "Role", type: "select", required: true, options: [{ value: "admin", label: "Administrator" }, { value: "manager", label: "Warehouse Manager" }, { value: "employee", label: "Warehouse Employee" }] },
    { name: "warehouse_id", label: "Assigned warehouse", type: "select", options: whOptions(App.meta.all_warehouses), blank: "All warehouses (admin)" }, { name: "password", label: e ? "New password" : "Password", type: "password", required: !e, hint: e ? "Leave empty to keep the current password" : "At least 6 characters" },
    ...(e ? [{ name: "active", type: "checkbox", label: "", checkLabel: "Account is active" }] : [])], values: e ? { ...u, warehouse_id: u.warehouse_id || "", active: !!u.active } : { role: "employee", warehouse_id: App.meta.all_warehouses[0].id },
    onSubmit: async (d) => { await api(e ? "/api/users/" + u.id : "/api/users", e ? "PUT" : "POST", d); toast(e ? "User updated" : "User created"); after(); } });
}
