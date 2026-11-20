/* =====================================================================
   pages_a.js - Overview, Products & Inventory, Warehouses, Stock Movements
   ===================================================================== */
const Pages = {};
const whName = (id) => { const w = (App.meta.all_warehouses || []).find((x) => x.id === id); return w ? w.name : "-"; };
const whOptions = (list) => list.map((w) => ({ value: w.id, label: `${w.code} - ${w.name}` }));
const MOVE_TYPES = [["STOCK_IN", "Stock In"], ["STOCK_OUT", "Stock Out"], ["TRANSFER", "Warehouse Transfer"], ["RETURN", "Product Return"], ["DAMAGED", "Damaged Stock"]];

/* =============================================================== OVERVIEW */
Pages.overview = {
  async render(el) {
    const hour = new Date().getHours(), greet = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
    el.innerHTML = pageHead(`${greet}, ${esc(App.user.full_name.split(" ")[0])}`, `${esc(App.meta.settings.company_name)} · ${esc(App.user.warehouse_name)} · ${new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}`,
      `${can("order.write") ? `<button class="btn primary" id="qa-order">${ic("shopping-cart", 16)} New Order</button>` : ""}${can("stock.move") ? `<button class="btn" id="qa-move">${ic("repeat", 16)} Stock Movement</button>` : ""}`) +
      `<div id="rb"></div><div class="kpis" id="kpis">${'<div class="skeleton"></div>'.repeat(8)}</div>
      <div class="grid g-21">${chartCard("c-value", "Inventory Value Over Time", "Reconstructed from the stock movement history", "")}${chartCard("c-cat", "Stock by Category", "Units currently on hand")}</div>
      <div class="grid g-21">${chartCard("c-mixed", "Orders &amp; Revenue", "Orders (bars) with revenue (line)")}${chartCard("c-wh", "Inventory by Warehouse", "Share of units stored")}</div>
      <div class="grid g2">${chartCard("c-move", "Stock Movement Activity", "Transactions by type")}${chartCard("c-ostack", "Order Pipeline", "Pending, processing and delivered orders")}</div>
      <div class="grid g-21"><div class="card"><div class="card-head"><div><h3>Live Activity <span class="pill em" style="margin-left:6px">${ic("activity", 12)} LIVE</span></h3><small>Last 24 hours · refreshes every 10 seconds</small></div><span class="muted" id="live-clock"></span></div><div class="chart-box"><canvas id="c-live"></canvas></div></div>
        <div class="card" id="q-card"></div></div>
      <div class="grid g2"><div class="card"><div class="card-head"><div><h3>Low Stock Alerts</h3><small>Products at or below their reorder level</small></div><a href="#/alerts" class="btn sm">View all</a></div><div id="low-list"></div></div>
        <div class="card"><div class="card-head"><div><h3>Recent Orders</h3><small>Latest customer orders</small></div><a href="#/orders" class="btn sm">View all</a></div><div id="recent-orders"></div></div></div>`;
    const qo = $("#qa-order"), qm = $("#qa-move");
    if (qo) qo.onclick = () => (location.hash = "#/orders/new");
    if (qm) qm.onclick = () => openMovementForm({});
    const load = async () => {
      try {
        const [dash, ch, live] = await Promise.all([api("/api/dashboard?" + rangeQS()), api("/api/charts?" + rangeQS()), api("/api/live" + (App.wh && isAdmin() ? "?warehouse=" + App.wh : ""))]);
        renderKpis(dash.kpis);
        CH.inventoryValue("c-value", ch); CH.stockByCategory("c-cat", ch); CH.mixed("c-mixed", ch); CH.stockByWarehouse("c-wh", ch); CH.movementLines("c-move", ch); CH.orderStack("c-ostack", ch);
        const lc = CH.live("c-live", live);
        $("#live-clock").textContent = live.server_time;
        const q = dash.queues;
        $("#q-card").innerHTML = `<div class="card-head"><div><h3>FIFO Queues</h3><small>Live size of the custom Queue structures</small></div></div>
          ${[["Inventory Queue", q.inventory, "package", "products stored"], ["Order Queue", q.orders, "clock", "orders waiting (oldest served first)"], ["Dispatch Queue", q.dispatch, "truck", "packed orders waiting for a truck"]].map(([n, v, i, t]) => `<div class="act-feed"><div class="item"><span class="kpi-ic" style="--kc:var(--tq)">${ic(i, 18)}</span><div style="flex:1"><b>${n}</b><br><small class="muted">${t}</small></div><b style="font-size:22px">${v}</b></div></div>`).join("")}
          <a class="btn primary" style="width:100%;margin-top:10px" href="#/dsa">${ic("cpu", 16)} Open DSA Visualization</a>`;
        $("#low-list").innerHTML = dash.alerts.length ? dash.alerts.map((a) => `<div class="act-feed"><div class="item"><span class="pill ${a.status === "OUT" ? "red" : "or"}">${a.status === "OUT" ? "OUT" : a.available + " left"}</span><div style="flex:1"><b>${esc(a.name)}</b><br><small class="muted">${esc(a.code)} · reorder at ${a.reorder_level}</small></div></div></div>`).join("") : emptyState("check-circle", "All stock levels are healthy", "");
        $("#recent-orders").innerHTML = dash.recent_orders.length ? dash.recent_orders.map((o) => `<div class="act-feed"><a class="item" href="#/orders/${o.id}" style="color:inherit"><div style="flex:1"><b>${o.order_no}</b> ${pill(o.status)}<br><small class="muted">${esc(o.customer_name)} · ${fmt.ago(o.created_at)}</small></div><b>${fmt.money(o.total)}</b></a></div>`).join("") : emptyState("inbox", "No orders yet", "");
        App.timers.forEach(clearInterval); App.timers = [];
        App.timers.push(setInterval(async () => {
          if (!lc || !document.getElementById("c-live")) return;
          try { const d = await api("/api/live" + (App.wh && isAdmin() ? "?warehouse=" + App.wh : "")); lc.data.labels = d.labels; lc.data.datasets[0].data = d.movements; lc.data.datasets[1].data = d.orders; lc.data.datasets[2].data = d.processing; lc.update("none"); $("#live-clock").textContent = d.server_time; } catch (e) { }
        }, 10000));
      } catch (e) { fail(e); }
    };
    rangeBar($("#rb"), load);
    load();
  },
};
function renderKpis(list) {
  $("#kpis").innerHTML = list.map((k) => {
    const col = { emerald: "#119B78", turquoise: "#20B8B0", orange: "#F29A38", navy: "#3E5C84", red: "#DB5B50" }[k.color];
    const ch = k.change === null || k.change === undefined ? "" : `<span class="chg ${k.change > 0 ? "up" : k.change < 0 ? "down" : "flat"}">${ic(k.change >= 0 ? "trending-up" : "trending-down", 12)} ${k.change > 0 ? "+" : ""}${k.change}%</span>`;
    return `<div class="kpi c-${k.color}"><div class="kpi-top"><span class="kpi-ic">${ic(k.icon, 22)}</span>${ch}</div><div class="kpi-label">${k.label}</div><div class="kpi-val" data-to="${k.value}" data-fmt="${k.fmt}">0</div>
      <div class="kpi-foot"><span class="kpi-note">${k.note}</span>${sparkSVG(k.spark, col)}</div></div>`;
  }).join("");
  $$(".kpi-val").forEach((e) => {
    const to = +e.dataset.to, f = e.dataset.fmt === "money" ? (v) => "Rs " + fmt.compact(v) : (v) => Math.round(v).toLocaleString("en-US"), t0 = performance.now();
    (function tick(t) { const p = Math.min((t - t0) / 900, 1); e.textContent = f(to * (1 - Math.pow(1 - p, 3))); if (p < 1) requestAnimationFrame(tick); })(t0);
  });
}

/* =============================================================== INVENTORY */
const INV = { q: "", field: "any", salgo: "linear", cat: "", status: "", sort: "id", dir: "asc", algo: "merge", wh: "" };
Pages.inventory = {
  async render(el, arg) {
    const cats = App.meta.categories;
    el.innerHTML = pageHead("Products &amp; Inventory", "Every product lives in the custom Inventory Queue · search and sort use our own algorithms",
      `<a class="btn" href="#/dsa">${ic("cpu", 16)} How it works</a>${can("product.write") ? `<button class="btn primary" id="p-add">${ic("plus", 16)} Add Product</button>` : ""}`) +
      `<div class="card" style="padding:16px"><div class="toolbar" style="margin:0 0 12px">
        <div class="grow" style="position:relative"><input id="f-q" style="width:100%" placeholder="Search by name, product ID, SKU, barcode or category…" value="${esc(INV.q)}"></div>
        <select id="f-field" title="Search field"><option value="any">All fields</option><option value="name">Name</option><option value="code">Product ID</option><option value="sku">SKU</option><option value="barcode">Barcode</option><option value="category">Category</option></select>
        <select id="f-salgo" title="Search algorithm"><option value="linear">Linear search (contains)</option><option value="binary">Binary search (exact)</option></select></div>
      <div class="toolbar" style="margin:0">
        <select id="f-cat"><option value="">All categories</option>${cats.map((c) => `<option>${esc(c)}</option>`).join("")}</select>
        <select id="f-status"><option value="">All stock status</option><option value="OK">In stock</option><option value="LOW">Low stock</option><option value="OUT">Out of stock</option></select>
        ${isAdmin() ? `<select id="f-wh"><option value="">All warehouses</option>${App.meta.warehouses.map((w) => `<option value="${w.id}">${esc(w.name)}</option>`).join("")}</select>` : ""}
        <span class="grow"></span><span class="muted">Sort by</span>
        <select id="f-sort"><option value="id">Product ID</option><option value="name">Name</option><option value="quantity">Quantity</option><option value="price">Price</option><option value="category">Category</option></select>
        <select id="f-dir"><option value="asc">Ascending</option><option value="desc">Descending</option></select>
        <select id="f-algo" title="Sorting algorithm"><option value="merge">Merge sort</option><option value="insertion">Insertion sort</option><option value="selection">Selection sort</option><option value="bubble">Bubble sort</option></select></div></div>
      <div id="inv-strip" style="margin-top:16px"></div><div class="card" style="padding:8px 16px 16px"><div id="inv-table"></div></div>`;
    const set = (id, v) => { const e = $(id); if (e) e.value = v; };
    set("#f-field", INV.field); set("#f-salgo", INV.salgo); set("#f-cat", INV.cat); set("#f-status", INV.status); set("#f-sort", INV.sort); set("#f-dir", INV.dir); set("#f-algo", INV.algo); set("#f-wh", INV.wh);
    if (arg === "new" && can("product.write")) setTimeout(() => productForm(), 50);
    const table = makeTable($("#inv-table"), {
      pageSize: 10, rows: [], rowClick: (r) => productDetail(r.id),
      columns: [
        { key: "name", label: "Product", render: (p) => `<div class="prod-cell">${pimg(p)}<div><b>${esc(p.name)}</b><div class="pcode">${p.code} · ${esc(p.sku)}</div></div></div>` },
        { key: "category", label: "Category", render: (p) => `<span class="pill gray">${esc(p.category)}</span>` },
        { key: "available", label: "Available", render: (p) => { const mx = Math.max(p.reorder_level * 3, 1), w = Math.min(100, p.available * 100 / mx), c = p.status === "OK" ? "var(--em)" : p.status === "LOW" ? "var(--or)" : "var(--red)"; return `<b>${fmt.num(p.available)}</b><div class="pbar"><i style="width:${Math.max(w, 3)}%;background:${c}"></i></div>`; } },
        { key: "reserved", label: "Reserved", render: (p) => fmt.num(p.reserved) },
        { key: "selling_price", label: "Price", render: (p) => fmt.money(p.selling_price) },
        { key: "reorder_level", label: "Reorder" },
        { key: "bin", label: "Location", render: (p) => `${esc(p.warehouse_name)}<div class="pcode">Bin ${esc(p.bin || "-")}</div>` },
        { key: "status", label: "Status", render: (p) => pill(p.status) },
        { key: "act", label: "", render: (p) => `<div class="row-acts">${actBtn("view", p.id, "eye", "View")}${can("product.write") ? actBtn("edit", p.id, "edit-2", "Edit") + actBtn("del", p.id, "trash-2", "Delete", "del") : ""}</div>` },
      ],
      onAction: async (a, p) => { if (a === "view") productDetail(p.id); if (a === "edit") productForm(p); if (a === "del") deleteProduct(p); },
      empty: emptyState("package", "No products found", "Try a different search or clear the filters."),
    });
    Pages.inventory.table = table;
    const load = async () => {
      const q = new URLSearchParams({ sort: INV.sort, dir: INV.dir, algo: INV.algo });
      if (INV.q) { q.set("q", INV.q); q.set("search_field", INV.field); q.set("search_algo", INV.salgo); }
      if (INV.cat) q.set("category", INV.cat); if (INV.status) q.set("status", INV.status); if (INV.wh) q.set("warehouse", INV.wh);
      try {
        const d = await api("/api/products?" + q);
        table.setRows(d.items);
        const s = d.stats, parts = [];
        if (s.sort) parts.push(`${ic("bar-chart-2", 14)} <b>${fmt.title(s.sort.algorithm)} sort</b> on ${s.sort.n} items: <b>${fmt.num(s.sort.comparisons)}</b> comparisons, <b>${fmt.num(s.sort.moves)}</b> moves, ${s.sort.ms} ms`);
        if (s.search) parts.push(`${ic("search", 14)} <b>${fmt.title(s.search.algorithm)} search</b>: <b>${s.search.comparisons}</b> comparisons - ${esc(s.search.note)}`);
        $("#inv-strip").innerHTML = `<div class="stats-strip">${parts.join('<span class="muted">|</span>')}<span class="muted" style="margin-left:auto">${s.count} product${s.count === 1 ? "" : "s"} shown</span></div>`;
      } catch (e) { fail(e); }
    };
    Pages.inventory.reload = load;
    const dl = debounce(() => { INV.q = $("#f-q").value.trim(); load(); }, 280);
    $("#f-q").oninput = dl;
    [["#f-field", "field"], ["#f-salgo", "salgo"], ["#f-cat", "cat"], ["#f-status", "status"], ["#f-sort", "sort"], ["#f-dir", "dir"], ["#f-algo", "algo"], ["#f-wh", "wh"]].forEach(([s, k]) => { const e = $(s); if (e) e.onchange = () => { INV[k] = e.value; load(); }; });
    const pa = $("#p-add"); if (pa) pa.onclick = () => productForm();
    load();
  },
};
async function deleteProduct(p) {
  if (!(await confirmBox({ title: "Delete product?", message: `<b>${esc(p.name)}</b> will be removed from the Inventory Queue (the queue rotates and skips it). Transaction history is kept.`, okText: "Delete product" }))) return;
  try { await api("/api/products/" + p.id, "DELETE"); toast("Product deleted from the inventory queue"); await refreshMeta(); Pages.inventory.reload ? Pages.inventory.reload() : route(); } catch (e) { fail(e); }
}
function productForm(p) {
  const editing = !!p;
  const fields = [
    { name: "name", label: "Product name", required: true, full: true, maxlength: 120 },
    { name: "sku", label: "SKU", hint: "Leave empty to auto-generate", maxlength: 40 }, { name: "barcode", label: "Barcode", maxlength: 32 },
    { name: "category", label: "Category", type: "select", required: true, options: App.meta.categories, blank: "Select category" },
    { name: "supplier_id", label: "Supplier", type: "select", blank: "No supplier", options: App.meta.suppliers.filter((s) => s.status === "Active").map((s) => ({ value: s.id, label: s.name })) },
    { name: "purchase_price", label: "Purchase price (Rs)", type: "number", min: 0, step: "0.01", required: true }, { name: "selling_price", label: "Selling price (Rs)", type: "number", min: 0, step: "0.01", required: true },
    { name: "warehouse_id", label: editing ? "Primary warehouse" : "Warehouse location", type: "select", required: true, options: whOptions(App.meta.warehouses) }, { name: "bin", label: "Bin / shelf", placeholder: "e.g. A-03-2", maxlength: 20 },
    { name: "reorder_level", label: "Reorder level", type: "number", min: 0, required: true },
    ...(editing ? [] : [{ name: "quantity", label: "Opening quantity", type: "number", min: 0, hint: "Creates a Stock In transaction" }]),
    ...(editing ? [] : [{ name: "expiry_date", label: "Expiry date", type: "date", hint: "Required for perishable products with opening stock" }]),
    { name: "expiry_tracked", type: "checkbox", label: "", checkLabel: "Perishable - track batches & expiry dates" },
    { name: "description", label: "Description", type: "textarea", full: true }, { name: "image", label: "Product image", type: "image", full: true },
  ];
  const v = editing ? { ...p, supplier_id: p.supplier_id || "", expiry_tracked: !!p.expiry_tracked } : { reorder_level: 10, quantity: 0, warehouse_id: App.meta.warehouses[0].id, expiry_tracked: false };
  formModal({ title: editing ? "Edit product" : "Add product", size: "lg", fields, values: v, submitText: editing ? "Save changes" : "Add to inventory queue",
    onSubmit: async (d) => { await api(editing ? "/api/products/" + p.id : "/api/products", editing ? "PUT" : "POST", d); toast(editing ? "Product updated" : "Product enqueued at the REAR of the inventory queue"); await refreshMeta(); route(); } });
}
async function productDetail(id) {
  let p; try { p = await api("/api/products/" + id); } catch (e) { return fail(e); }
  const today = todayISO();
  const body = `<div style="display:flex;gap:18px;align-items:center;flex-wrap:wrap;margin-bottom:18px">${pimg(p, "lg")}<div style="flex:1;min-width:220px"><h2 style="font-size:22px">${esc(p.name)}</h2><div class="muted" style="margin:4px 0 8px">${p.code} · SKU ${esc(p.sku)} · Barcode ${esc(p.barcode || "-")}</div>${pill(p.status)} <span class="pill gray">${esc(p.category)}</span> ${p.expiry_tracked ? '<span class="pill tq">Perishable</span>' : ""}</div>
      <div class="actions no-print">${can("stock.move") ? `<button class="btn sm primary" data-mv="STOCK_IN">${ic("arrow-down", 14)} Stock In</button><button class="btn sm" data-mv="STOCK_OUT">${ic("arrow-up", 14)} Stock Out</button>` : ""}${can("product.write") ? `<button class="btn sm" data-edit>${ic("edit-2", 14)} Edit</button>` : ""}</div></div>
    <div class="stat-tiles"><div class="tile"><small>Available</small><b>${fmt.num(p.available)}</b></div><div class="tile"><small>Reserved</small><b>${fmt.num(p.reserved)}</b></div><div class="tile"><small>Damaged</small><b>${fmt.num(p.damaged)}</b></div><div class="tile"><small>Stock value</small><b>${fmt.money(p.value)}</b></div><div class="tile"><small>Units sold</small><b>${fmt.num(p.sold_units)}</b></div></div>
    <div class="grid g2"><div><h4 style="margin-bottom:10px">Stock by warehouse</h4><table class="tbl"><thead><tr><th>Warehouse</th><th class="r">On hand</th><th class="r">Reserved</th><th class="r">Damaged</th>${can("reserve") ? "<th></th>" : ""}</tr></thead><tbody>
      ${p.stock.map((s) => `<tr><td>${esc(s.warehouse_name)}</td><td class="r">${fmt.num(s.quantity)}</td><td class="r">${fmt.num(s.reserved)}</td><td class="r">${fmt.num(s.damaged)}</td>${can("reserve") ? `<td class="r"><button class="btn sm" data-res="${s.warehouse_id}">Reserve</button></td>` : ""}</tr>`).join("") || `<tr><td colspan="5" class="muted">No stock recorded</td></tr>`}</tbody></table>
      <div class="info-list" style="margin-top:16px"><div><span>Purchase price</span><b>${fmt.money(p.purchase_price)}</b></div><div><span>Selling price</span><b>${fmt.money(p.selling_price)}</b></div><div><span>Reorder level</span><b>${p.reorder_level}</b></div><div><span>Supplier</span><b>${esc(p.supplier_name)}</b></div><div><span>Primary location</span><b>${esc(p.warehouse_name)} · ${esc(p.bin || "-")}</b></div><div><span>Created</span><b>${fmt.date(p.created_at)}</b></div></div></div>
      <div><h4 style="margin-bottom:10px">Batches &amp; expiry</h4>${p.batches.length ? `<table class="tbl"><thead><tr><th>Batch</th><th>Warehouse</th><th class="r">Qty</th><th>Expiry</th></tr></thead><tbody>${p.batches.map((b) => `<tr><td class="mono">${esc(b.batch_no)}</td><td>${esc(b.warehouse_name)}</td><td class="r">${b.quantity}</td><td>${fmt.date(b.expiry_date)} ${b.expiry_date < today ? '<span class="pill red">Expired</span>' : ""}</td></tr>`).join("")}</tbody></table>` : `<p class="muted">${p.expiry_tracked ? "No batches in stock." : "This product does not use batch/expiry tracking."}</p>`}
      <h4 style="margin:18px 0 10px">Product description</h4><p class="muted">${esc(p.description || "No description.")}</p></div></div>
    <h4 style="margin:6px 0 10px">Movement history</h4>${p.history.length ? `<div class="tbl-wrap"><table class="tbl"><thead><tr><th>Transaction</th><th>Date</th><th>Type</th><th class="r">Qty</th><th>From</th><th>To</th><th>Employee</th></tr></thead><tbody>${p.history.slice(0, 12).map((m) => `<tr><td class="mono">${m.txn_id}</td><td>${fmt.dt(m.ts)}</td><td>${pill(m.type, fmt.title(m.type))}</td><td class="r">${m.quantity}</td><td>${esc(m.src_name || "-")}</td><td>${esc(m.dst_name || "-")}</td><td>${esc(m.employee)}</td></tr>`).join("")}</tbody></table></div>` : `<p class="muted">No movements yet.</p>`}`;
  openModal({ title: "Product details", size: "xl", body, onOpen: (m) => {
    $$("[data-mv]", m.el).forEach((b) => (b.onclick = () => { m.close(); openMovementForm({ type: b.dataset.mv, product_id: p.id }); }));
    const e = $("[data-edit]", m.el); if (e) e.onclick = () => { m.close(); productForm(p); };
    $$("[data-res]", m.el).forEach((b) => (b.onclick = () => { m.close(); reserveForm(p, +b.dataset.res); }));
  } });
}
function reserveForm(p, wid) {
  formModal({ title: `Reserve / release - ${p.name}`, size: "sm", submitText: "Apply", fields: [{ name: "action", label: "Action", type: "select", options: [{ value: "reserve", label: "Reserve stock" }, { value: "release", label: "Release reservation" }] }, { name: "quantity", label: "Quantity", type: "number", min: 1, required: true }],
    onSubmit: async (d) => { const r = await api("/api/stock/reserve", "POST", { ...d, product_id: p.id, warehouse_id: wid }); toast(r.message); route(); } });
}
async function refreshMeta() { App.meta = await api("/api/meta"); }

/* =============================================================== STOCK MOVEMENT FORM (shared) */
function openMovementForm(def = {}) {
  const types = MOVE_TYPES.filter(([k]) => k !== "TRANSFER" || can("stock.transfer"));
  const prodOpts = App.meta.products.map((p) => ({ value: p.id, label: `${p.code} - ${p.name}` }));
  const myWh = App.meta.warehouses, allWh = App.meta.all_warehouses;
  const fields = [
    { name: "type", label: "Movement type", type: "select", required: true, options: types.map(([v, l]) => ({ value: v, label: l })), full: true },
    { name: "product_id", label: "Product", type: "select", required: true, options: prodOpts, blank: "Select product", full: true },
    { name: "source_wh", label: "Source warehouse", type: "select", options: whOptions(myWh), blank: "Select warehouse" },
    { name: "dest_wh", label: "Destination warehouse", type: "select", options: whOptions(allWh), blank: "Select warehouse" },
    { name: "quantity", label: "Quantity", type: "number", min: 1, required: true, hint: '<span id="mv-avail"></span>' },
    { name: "reference", label: "Reference", placeholder: "Order / PO / note number" },
    { name: "expiry_date", label: "Expiry date", type: "date" }, { name: "batch_no", label: "Batch number", placeholder: "Auto if empty" },
    { name: "note", label: "Note", type: "textarea", rows: 2, full: true },
  ];
  formModal({ title: "New stock movement", size: "lg", fields, values: { type: def.type || types[0][0], product_id: def.product_id || "", source_wh: def.source_wh || (myWh[0] && myWh[0].id), dest_wh: def.dest_wh || (myWh[0] && myWh[0].id) }, submitText: "Process movement",
    onSubmit: async (d) => { const r = await api("/api/movements", "POST", d); toast(`${r.txn_id} recorded - inventory updated`); route(); },
    onOpen: (m, form) => {
      const $f = (n) => form.querySelector(`[name="${n}"]`), W = (n) => $f(n).closest(".field");
      const sync = async () => {
        const t = $f("type").value, pid = +$f("product_id").value, prod = App.meta.products.find((p) => p.id === pid);
        W("source_wh").hidden = !["STOCK_OUT", "TRANSFER", "DAMAGED"].includes(t); W("dest_wh").hidden = !["STOCK_IN", "TRANSFER", "RETURN"].includes(t);
        const perish = prod && prod.expiry_tracked && ["STOCK_IN"].includes(t);
        W("expiry_date").hidden = !perish; W("batch_no").hidden = !perish;
        const dest = $f("dest_wh"); const list = t === "TRANSFER" ? allWh : myWh; if (dest.dataset.t !== t) { dest.innerHTML = `<option value="">Select warehouse</option>` + whOptions(list).map((o) => `<option value="${o.value}">${esc(o.label)}</option>`).join(""); dest.dataset.t = t; if (t !== "TRANSFER" && list[0]) dest.value = list[0].id; }
        const av = $("#mv-avail", form), src = +$f("source_wh").value;
        if (["STOCK_OUT", "TRANSFER", "DAMAGED"].includes(t) && pid && src) { try { const r = await api("/api/orders/check", "POST", { warehouse_id: src, items: [{ product_id: pid, quantity: 1 }] }); av.innerHTML = `Available at source: <b>${r[0].available}</b> units`; } catch (e) { av.textContent = ""; } } else av.textContent = "";
      };
      ["type", "product_id", "source_wh"].forEach((n) => ($f(n).onchange = sync)); sync();
    } });
}

/* =============================================================== WAREHOUSES */
function ring(pct, color) {
  const r = 34, c = 2 * Math.PI * r;
  return `<div class="ring"><svg width="86" height="86" viewBox="0 0 86 86"><circle cx="43" cy="43" r="${r}" fill="none" stroke="var(--soft)" stroke-width="9"/><circle cx="43" cy="43" r="${r}" fill="none" stroke="${color}" stroke-width="9" stroke-linecap="round" stroke-dasharray="${c}" stroke-dashoffset="${c * (1 - Math.min(pct, 100) / 100)}"/></svg><b>${Math.round(pct)}%</b></div>`;
}
Pages.warehouses = {
  async render(el) {
    el.innerHTML = pageHead("Warehouse Management", "Capacity, inventory and performance of every location",
      `${can("stock.transfer") ? `<button class="btn" id="w-transfer">${ic("repeat", 16)} Transfer Stock</button>` : ""}${isAdmin() ? `<button class="btn primary" id="w-add">${ic("plus", 16)} Add Warehouse</button>` : ""}`) + `<div id="w-cards" class="grid g3">${'<div class="skeleton"></div>'.repeat(3)}</div><div id="rb"></div>
      <div class="grid g2">${chartCard("c-radar", "Warehouse Performance Comparison", "Stock level, free capacity, dispatch volume and on-time delivery (0-100)")}${chartCard("c-best", "Best Performing Warehouses", "Units dispatched in the selected period")}</div>
      <div class="card"><div class="card-head"><div><h3>Recent Stock Transfers</h3><small>Transfers between warehouses</small></div></div><div id="w-transfers"></div></div>`;
    const loadCards = async () => {
      const ws = await api("/api/warehouses");
      $("#w-cards").innerHTML = ws.map((w) => { const col = w.utilization >= 85 ? "#DB5B50" : w.utilization >= 70 ? "#F29A38" : "#119B78";
        return `<div class="card wh-card"><div class="wh-top"><div><div style="display:flex;gap:8px;align-items:center;margin-bottom:6px"><span class="pill navy">${w.code}</span>${pill(w.status)}</div><h3 style="font-size:17px">${esc(w.name)}</h3><div class="meta-row" style="margin-top:6px">${ic("map-pin", 14)} ${esc(w.location)}</div><div class="meta-row">${ic("user", 14)} ${esc(w.manager)}</div></div>${ring(w.utilization, col)}</div>
        <div class="wh-stats"><div><b>${fmt.num(w.units)}</b><small>Units stored</small></div><div><b>${w.products}</b><small>Products</small></div><div><b>${w.open_orders}</b><small>Open orders</small></div><div><b>${fmt.num(w.capacity)}</b><small>Total capacity</small></div><div><b>${fmt.num(w.occupied)}</b><small>Occupied</small></div><div><b>${fmt.num(w.available_capacity)}</b><small>Free capacity</small></div></div>
        <div class="row-acts" style="justify-content:flex-start"><button class="btn sm" data-view="${w.id}">${ic("eye", 14)} Inventory</button>${can("stock.transfer") ? `<button class="btn sm" data-tr="${w.id}">${ic("repeat", 14)} Transfer</button>` : ""}${isAdmin() ? `<button class="btn sm" data-edit="${w.id}">${ic("edit-2", 14)}</button><button class="btn sm danger" data-del="${w.id}">${ic("trash-2", 14)}</button>` : ""}</div></div>`; }).join("");
      const find = (id) => ws.find((w) => w.id === +id);
      $$("[data-view]").forEach((b) => (b.onclick = () => warehouseDetail(+b.dataset.view)));
      $$("[data-tr]").forEach((b) => (b.onclick = () => openMovementForm({ type: "TRANSFER", source_wh: +b.dataset.tr })));
      $$("[data-edit]").forEach((b) => (b.onclick = () => warehouseForm(find(b.dataset.edit))));
      $$("[data-del]").forEach((b) => (b.onclick = async () => { const w = find(b.dataset.del); if (await confirmBox({ title: "Delete warehouse?", message: `<b>${esc(w.name)}</b> will be removed. Warehouses that still hold stock cannot be deleted.`, okText: "Delete" })) try { await api("/api/warehouses/" + w.id, "DELETE"); toast("Warehouse deleted"); await refreshMeta(); route(); } catch (e) { fail(e); } }));
    };
    const loadCharts = async () => { const ch = await api("/api/charts?" + rangeQS()); CH.radar("c-radar", ch); CH.bestWarehouses("c-best", ch); };
    const loadTransfers = async () => {
      const d = await api("/api/movements?type=TRANSFER&limit=40");
      makeTable($("#w-transfers"), { pageSize: 6, rows: d.items.map((m) => ({ ...m, id: m.id })), empty: emptyState("repeat", "No transfers yet", "Use Transfer Stock to move products between warehouses."),
        columns: [{ key: "txn_id", label: "Transaction", cls: "mono" }, { key: "ts", label: "Date", render: (m) => fmt.dt(m.ts) }, { key: "product_name", label: "Product" }, { key: "quantity", label: "Qty", align: "r" }, { key: "src_name", label: "From" }, { key: "dst_name", label: "To" }, { key: "employee", label: "By" }] });
    };
    try { await loadCards(); await loadTransfers(); } catch (e) { fail(e); }
    rangeBar($("#rb"), loadCharts, { warehouse: false }); loadCharts();
    const a = $("#w-add"); if (a) a.onclick = () => warehouseForm();
    const t = $("#w-transfer"); if (t) t.onclick = () => openMovementForm({ type: "TRANSFER" });
  },
};
function warehouseForm(w) {
  const e = !!w;
  formModal({ title: e ? "Edit warehouse" : "Add warehouse", fields: [{ name: "name", label: "Warehouse name", required: true, full: true }, { name: "location", label: "Location", required: true }, { name: "manager", label: "Manager", required: true },
    { name: "capacity", label: "Total capacity (units)", type: "number", min: 1, required: true }, { name: "status", label: "Status", type: "select", options: ["Active", "Inactive", "Maintenance"] }], values: w || { capacity: 5000, status: "Active" },
    onSubmit: async (d) => { await api(e ? "/api/warehouses/" + w.id : "/api/warehouses", e ? "PUT" : "POST", d); toast(e ? "Warehouse updated" : "Warehouse added"); await refreshMeta(); route(); } });
}
async function warehouseDetail(id) {
  let w; try { w = await api("/api/warehouses/" + id); } catch (e) { return fail(e); }
  openModal({ title: `${esc(w.name)} - inventory`, size: "xl", body: `<div class="stat-tiles"><div class="tile"><small>Units stored</small><b>${fmt.num(w.units)}</b></div><div class="tile"><small>Capacity used</small><b>${w.utilization}%</b></div><div class="tile"><small>Stock value</small><b>${fmt.money(w.value)}</b></div><div class="tile"><small>Damaged units</small><b>${w.damaged}</b></div></div>
    <table class="tbl"><thead><tr><th>Product</th><th>Category</th><th class="r">Available</th><th class="r">Reserved</th><th class="r">Damaged</th><th>Status</th></tr></thead><tbody>${w.inventory.map((p) => `<tr><td><div class="prod-cell">${pimg(p)}<div><b>${esc(p.name)}</b><div class="pcode">${p.code}</div></div></div></td><td>${esc(p.category)}</td><td class="r">${fmt.num(p.available)}</td><td class="r">${p.reserved}</td><td class="r">${p.damaged}</td><td>${pill(p.status)}</td></tr>`).join("")}</tbody></table>` });
}

/* =============================================================== STOCK MOVEMENTS */
const MV = { type: "", q: "", from: "", to: "" };
Pages.movements = {
  async render(el) {
    el.innerHTML = pageHead("Stock Movements", "Complete transaction history · every valid movement updates inventory automatically", can("stock.move") ? `<button class="btn primary" id="m-new">${ic("plus", 16)} New Movement</button>` : "") +
      `<div id="m-tiles" class="stat-tiles"></div><div class="card"><div class="toolbar"><div class="seg" id="m-seg"><button data-t="" class="on">All</button>${MOVE_TYPES.map(([k, l]) => `<button data-t="${k}">${l}</button>`).join("")}</div><span class="grow"></span>
      <input id="m-q" placeholder="Search transaction, product, reference…" value="${esc(MV.q)}" style="min-width:250px"><input type="date" id="m-from" value="${MV.from}" title="From"><input type="date" id="m-to" value="${MV.to}" title="To"></div><div id="m-table"></div></div>`;
    const table = makeTable($("#m-table"), { pageSize: 12, rows: [], rowClass: () => "", empty: emptyState("repeat", "No movements found", "Change the filters or record a new movement."),
      columns: [{ key: "txn_id", label: "Transaction", cls: "mono", sort: true }, { key: "ts", label: "Date & time", sort: true, render: (m) => fmt.dt(m.ts) }, { key: "type", label: "Type", render: (m) => pill(m.type, fmt.title(m.type)) },
        { key: "product_name", label: "Product", sort: true, render: (m) => `<b>${esc(m.product_name)}</b><div class="pcode">${esc(m.product_code || "")}</div>` },
        { key: "quantity", label: "Qty", align: "r", sort: true, render: (m) => `<b style="color:${["STOCK_IN", "RETURN"].includes(m.type) ? "var(--em)" : m.type === "TRANSFER" ? "var(--tq)" : "var(--red)"}">${["STOCK_IN", "RETURN"].includes(m.type) ? "+" : m.type === "TRANSFER" ? "⇄" : "-"}${fmt.num(m.quantity)}</b>` },
        { key: "src_name", label: "From", render: (m) => esc(m.src_name || "-") }, { key: "dst_name", label: "To", render: (m) => esc(m.dst_name || "-") }, { key: "employee", label: "Employee" }, { key: "reference", label: "Reference", render: (m) => esc(m.reference || "") }] });
    const load = async () => {
      const q = new URLSearchParams({ limit: 1500 }); if (MV.type) q.set("type", MV.type); if (MV.q) q.set("q", MV.q); if (MV.from) q.set("from", MV.from); if (MV.to) q.set("to", MV.to);
      try {
        const d = await api("/api/movements?" + q); table.setRows(d.items);
        $("#m-tiles").innerHTML = MOVE_TYPES.map(([k, l]) => `<div class="tile"><small>${l}</small><b>${fmt.num((d.totals[k] || {}).count || 0)}</b> <span class="muted">${fmt.num((d.totals[k] || {}).units || 0)} units</span></div>`).join("");
      } catch (e) { fail(e); }
    };
    $("#m-seg").onclick = (e) => { const b = e.target.closest("[data-t]"); if (!b) return; MV.type = b.dataset.t; $$("#m-seg button").forEach((x) => x.classList.toggle("on", x === b)); load(); };
    $("#m-q").oninput = debounce((e) => { MV.q = e.target.value.trim(); load(); }, 300);
    $("#m-from").onchange = (e) => { MV.from = e.target.value; load(); }; $("#m-to").onchange = (e) => { MV.to = e.target.value; load(); };
    const n = $("#m-new"); if (n) n.onclick = () => openMovementForm({});
    $$("#m-seg button").forEach((x) => x.classList.toggle("on", x.dataset.t === MV.type));
    load();
  },
};
