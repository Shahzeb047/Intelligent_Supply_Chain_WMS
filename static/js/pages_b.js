/* =====================================================================
   pages_b.js - Suppliers, Purchase Orders, Customer Orders, Shipments, Returns
   ===================================================================== */
function stepper(steps) {
  return `<div class="stepper">${steps.map((s) => `<div class="step ${s.state}"><div class="bub">${ic(s.state === "bad" ? "x" : s.state === "done" ? "check" : s.icon || "clock", 16)}</div><b>${s.label}</b><small>${s.ts ? fmt.dt(s.ts) : "&nbsp;"}</small></div>`).join("")}</div>`;
}

/* generic line-item editor used by purchase orders and customer orders */
function lineItems(root, { mode, getWh, onChange }) {
  const box = $("#li", root), prods = App.meta.products;
  const optHtml = (sel) => `<option value="">Select product</option>` + prods.map((p) => `<option value="${p.id}" ${+sel === p.id ? "selected" : ""}>${esc(p.code)} - ${esc(p.name)}</option>`).join("");
  let checkTimer;
  const addRow = (it = {}) => {
    const row = document.createElement("div");
    row.className = "li-row";
    row.innerHTML = `<div><select class="li-p">${optHtml(it.product_id)}</select></div><div><input class="li-q" type="number" min="1" value="${it.quantity || 1}" title="Quantity"></div>
      <div><input class="li-c" type="number" min="0" step="0.01" value="${it.unit_cost ?? ""}" ${mode === "order" ? "readonly" : ""} title="${mode === "order" ? "Selling price" : "Unit cost"}"></div><button type="button" class="ib del" title="Remove">${ic("x", 14)}</button><div class="meta muted"></div>`;
    box.appendChild(row);
    const sync = () => {
      const p = prods.find((x) => x.id === +$(".li-p", row).value);
      if (p && !$(".li-c", row).dataset.touched) $(".li-c", row).value = mode === "order" ? p.price : p.cost;
      totals(); clearTimeout(checkTimer); checkTimer = setTimeout(check, 250);
    };
    $(".li-p", row).onchange = () => { delete $(".li-c", row).dataset.touched; sync(); };
    $(".li-q", row).oninput = sync;
    $(".li-c", row).oninput = () => { $(".li-c", row).dataset.touched = 1; totals(); };
    $("button", row).onclick = () => { if ($$(".li-row", box).length > 1) { row.remove(); totals(); } else toast("An order needs at least one product", "warn"); };
    if (it.product_id) { $(".li-c", row).dataset.touched = it.unit_cost !== undefined ? 1 : ""; if (it.unit_cost === undefined) sync(); }
    return row;
  };
  const get = () => $$(".li-row", box).map((r) => ({ product_id: $(".li-p", r).value, quantity: $(".li-q", r).value, unit_cost: $(".li-c", r).value })).filter((x) => x.product_id);
  async function check() {
    if (mode !== "order") return;
    const wid = getWh(); if (!wid) return;
    try {
      const rows = $$(".li-row", box), items = rows.map((r) => ({ product_id: $(".li-p", r).value, quantity: $(".li-q", r).value })).filter((i) => i.product_id);
      if (!items.length) return;
      const res = await api("/api/orders/check", "POST", { warehouse_id: wid, items });
      rows.forEach((r) => { const pid = +$(".li-p", r).value, info = res.find((x) => x.product_id === pid), m = $(".meta", r); if (!info) { m.textContent = ""; return; } m.innerHTML = info.ok ? `<span style="color:var(--em)">${ic("check-circle", 13)} ${info.available} available - OK</span>` : `<span style="color:var(--red)">${ic("alert-triangle", 13)} Only ${info.available} available in this warehouse</span>`; });
    } catch (e) { }
  }
  function totals() {
    const items = get(), sum = items.reduce((s, i) => s + (+i.quantity || 0) * (+i.unit_cost || 0), 0), t = $("#li-total", root);
    if (!t) return;
    if (mode === "order") { const d = +($("[name=discount_pct]", root) || { value: 0 }).value || 0; t.innerHTML = `Subtotal <b>${fmt.money(sum)}</b> · Discount ${d}% · Total <b style="color:var(--em);font-size:17px">${fmt.money(sum * (1 - d / 100))}</b>`; }
    else t.innerHTML = `Order total <b style="color:var(--em);font-size:17px">${fmt.money(sum)}</b>`;
    onChange && onChange();
  }
  $("#li-add", root).onclick = () => { addRow(); };
  return { addRow, get, check, totals };
}
const liBlock = `<h4 style="margin:20px 0 10px">Products</h4><div class="muted" style="display:grid;grid-template-columns:minmax(0,3fr) 90px 120px 36px;gap:10px;font-size:11.5px;font-weight:700;margin-bottom:6px"><span>PRODUCT</span><span>QTY</span><span>PRICE (Rs)</span><span></span></div><div class="line-items" id="li"></div>
  <div style="display:flex;justify-content:space-between;align-items:center;margin-top:12px"><button type="button" class="btn sm" id="li-add">${ic("plus", 14)} Add product</button><div id="li-total"></div></div>`;

/* =============================================================== SUPPLIERS */
Pages.suppliers = {
  async render(el) {
    el.innerHTML = pageHead("Supplier Management", "Vendors, contacts and delivery performance", `<button class="btn primary" id="s-add">${ic("plus", 16)} Add Supplier</button>`) + `<div class="card"><div class="toolbar"><input id="s-q" class="grow" placeholder="Search suppliers…"><div class="seg" id="s-seg"><button data-s="" class="on">All</button><button data-s="Active">Active</button><button data-s="Inactive">Inactive</button></div></div><div id="s-table"></div></div>`;
    let all = [], status = "", q = "";
    const table = makeTable($("#s-table"), { pageSize: 8, rows: [], empty: emptyState("truck", "No suppliers", "Add your first supplier."), onAction: (a, s) => { if (a === "edit") supplierForm(s); if (a === "del") delSup(s); }, rowClick: (s) => supplierForm(s),
      columns: [{ key: "name", label: "Supplier", sort: true, render: (s) => `<b>${esc(s.name)}</b><div class="pcode">${s.code} · ${esc(s.address || "")}</div>` },
        { key: "contact_person", label: "Contact", render: (s) => `${esc(s.contact_person)}<div class="pcode">${esc(s.email)} · ${esc(s.phone)}</div>` },
        { key: "categories", label: "Supplies", render: (s) => (s.categories || "").split(",").filter(Boolean).map((c) => `<span class="pill gray" style="margin:1px">${esc(c.trim())}</span>`).join("") },
        { key: "po_count", label: "Purchase orders", sort: true, align: "r", render: (s) => `${s.po_count}<div class="pcode">${s.completed} completed</div>` },
        { key: "on_time_pct", label: "On-time", sort: true, align: "r", render: (s) => (s.on_time_pct === null ? "-" : `<b style="color:${s.on_time_pct >= 80 ? "var(--em)" : "var(--or)"}">${s.on_time_pct}%</b>`) },
        { key: "status", label: "Status", render: (s) => pill(s.status) },
        { key: "act", label: "", render: (s) => `<div class="row-acts">${actBtn("edit", s.id, "edit-2", "Edit")}${actBtn("del", s.id, "trash-2", "Delete", "del")}</div>` }] });
    const draw = () => table.setRows(all.filter((s) => (!status || s.status === status) && (!q || (s.name + s.contact_person + s.categories).toLowerCase().includes(q))));
    const load = async () => { try { all = await api("/api/suppliers"); draw(); } catch (e) { fail(e); } };
    $("#s-q").oninput = debounce((e) => { q = e.target.value.toLowerCase(); draw(); }, 200);
    $("#s-seg").onclick = (e) => { const b = e.target.closest("[data-s]"); if (!b) return; status = b.dataset.s; $$("#s-seg button").forEach((x) => x.classList.toggle("on", x === b)); draw(); };
    $("#s-add").onclick = () => supplierForm();
    Pages.suppliers.reload = load; load();
  },
};
function supplierForm(s) {
  const e = !!s;
  formModal({ title: e ? "Edit supplier" : "Add supplier", fields: [{ name: "name", label: "Supplier name", required: true, full: true }, { name: "contact_person", label: "Contact person", required: true }, { name: "phone", label: "Phone", required: true, placeholder: "+92 300 1234567" },
    { name: "email", label: "Email", type: "email", required: true }, { name: "status", label: "Status", type: "select", options: ["Active", "Inactive"] }, { name: "address", label: "Address", full: true }, { name: "categories", label: "Supplied categories", full: true, hint: "Comma separated, e.g. Electronics, Home Appliances" }],
    values: s || { status: "Active" }, onSubmit: async (d) => { await api(e ? "/api/suppliers/" + s.id : "/api/suppliers", e ? "PUT" : "POST", d); toast(e ? "Supplier updated" : "Supplier added"); await refreshMeta(); Pages.suppliers.reload(); } });
}
async function delSup(s) {
  if (!(await confirmBox({ title: "Delete supplier?", message: `<b>${esc(s.name)}</b> will be removed permanently. Suppliers with purchase history can only be set to Inactive.`, okText: "Delete" }))) return;
  try { await api("/api/suppliers/" + s.id, "DELETE"); toast("Supplier deleted"); await refreshMeta(); Pages.suppliers.reload(); } catch (e) { fail(e); }
}

/* =============================================================== PURCHASE ORDERS */
Pages.purchase = {
  async render(el) {
    el.innerHTML = pageHead("Purchase Orders", "Order from suppliers, approve, receive goods and update stock", `<button class="btn primary" id="po-new">${ic("plus", 16)} New Purchase Order</button>`) +
      `<div id="po-tiles" class="stat-tiles"></div><div class="card"><div class="toolbar"><div class="seg" id="po-seg"><button data-s="" class="on">All</button>${["DRAFT", "PENDING", "APPROVED", "PARTIALLY_RECEIVED", "COMPLETED", "CANCELLED"].map((s) => `<button data-s="${s}">${fmt.title(s)}</button>`).join("")}</div></div><div id="po-table"></div></div>`;
    let status = "";
    const table = makeTable($("#po-table"), { pageSize: 10, rows: [], empty: emptyState("clipboard", "No purchase orders", "Create a purchase order to restock products."), rowClick: (p) => poDetail(p.id),
      onAction: (a, p) => poAction(a, p),
      columns: [{ key: "po_no", label: "PO number", sort: true, cls: "mono" }, { key: "supplier_name", label: "Supplier", sort: true }, { key: "warehouse_name", label: "Deliver to" }, { key: "status", label: "Status", render: (p) => pill(p.status) },
        { key: "units", label: "Units", align: "r", sort: true, render: (p) => `${p.received_units}/${p.units}` }, { key: "total", label: "Value", align: "r", sort: true, render: (p) => fmt.money(p.total) },
        { key: "expected_date", label: "Expected", sort: true, render: (p) => fmt.date(p.expected_date) }, { key: "created_at", label: "Created", sort: true, render: (p) => fmt.date(p.created_at) },
        { key: "act", label: "", render: (p) => `<div class="row-acts">${poButtons(p)}</div>` }] });
    const load = async () => { try { const d = await api("/api/purchase-orders" + (status ? "?status=" + status : "")); table.setRows(d);
      const cnt = (s) => d.filter((x) => x.status === s).length; $("#po-tiles").innerHTML = `<div class="tile"><small>Open orders</small><b>${cnt("PENDING") + cnt("APPROVED") + cnt("PARTIALLY_RECEIVED")}</b></div><div class="tile"><small>Awaiting approval</small><b>${cnt("PENDING")}</b></div><div class="tile"><small>Ready to receive</small><b>${cnt("APPROVED") + cnt("PARTIALLY_RECEIVED")}</b></div><div class="tile"><small>Completed</small><b>${cnt("COMPLETED")}</b></div><div class="tile"><small>Value (listed)</small><b>${fmt.compact(d.filter((x) => x.status !== "CANCELLED").reduce((s, x) => s + x.total, 0))}</b></div>`; } catch (e) { fail(e); } };
    Pages.purchase.reload = load;
    $("#po-seg").onclick = (e) => { const b = e.target.closest("[data-s]"); if (!b) return; status = b.dataset.s; $$("#po-seg button").forEach((x) => x.classList.toggle("on", x === b)); load(); };
    $("#po-new").onclick = () => poForm();
    load();
  },
};
function poButtons(p) {
  const b = [actBtn("view", p.id, "eye", "View")];
  if (p.status === "DRAFT") b.push(actBtn("edit", p.id, "edit-2", "Edit"), actBtn("submit", p.id, "send", "Submit for approval"));
  if (p.status === "PENDING") b.push(actBtn("approve", p.id, "check-circle", "Approve"));
  if (["APPROVED", "PARTIALLY_RECEIVED"].includes(p.status)) b.push(actBtn("receive", p.id, "inbox", "Receive goods"));
  if (["DRAFT", "PENDING", "APPROVED"].includes(p.status)) b.push(actBtn("cancel", p.id, "x-circle", "Cancel order", "del"));
  if (["DRAFT", "CANCELLED"].includes(p.status)) b.push(actBtn("del", p.id, "trash-2", "Delete", "del"));
  return b.join("");
}
async function poAction(a, p) {
  try {
    if (a === "view") return poDetail(p.id);
    if (a === "edit") return poForm(await api("/api/purchase-orders/" + p.id));
    if (a === "receive") return poReceive(await api("/api/purchase-orders/" + p.id));
    if (a === "submit") { await api(`/api/purchase-orders/${p.id}/status`, "POST", { status: "PENDING" }); toast(`${p.po_no} submitted for approval`); }
    if (a === "approve") { await api(`/api/purchase-orders/${p.id}/status`, "POST", { status: "APPROVED" }); toast(`${p.po_no} approved - ready to receive`); }
    if (a === "cancel") { if (!(await confirmBox({ title: "Cancel purchase order?", message: `${p.po_no} will be cancelled.`, okText: "Cancel order" }))) return; await api(`/api/purchase-orders/${p.id}/status`, "POST", { status: "CANCELLED" }); toast(`${p.po_no} cancelled`); }
    if (a === "del") { if (!(await confirmBox({ title: "Delete purchase order?", message: `${p.po_no} will be deleted.`, okText: "Delete" }))) return; await api("/api/purchase-orders/" + p.id, "DELETE"); toast("Purchase order deleted"); }
    Pages.purchase.reload();
  } catch (e) { fail(e); }
}
function poForm(po, prefill) {
  const e = !!po;
  let draft = false;
  const sups = App.meta.suppliers.filter((s) => s.status === "Active");
  let li;
  formModal({ title: e ? `Edit ${po.po_no}` : "New purchase order", size: "xl", submitText: "Submit for approval", extraFoot: `<button class="btn" id="po-draft" type="button">Save as draft</button>`,
    fields: [{ name: "supplier_id", label: "Supplier", type: "select", required: true, options: sups.map((s) => ({ value: s.id, label: s.name })), blank: "Select supplier" }, { name: "warehouse_id", label: "Deliver to warehouse", type: "select", required: true, options: whOptions(App.meta.warehouses) },
      { name: "expected_date", label: "Expected delivery", type: "date" }, { name: "notes", label: "Notes" }],
    values: e ? po : { warehouse_id: App.meta.warehouses[0].id, ...((prefill && prefill.values) || {}) }, bottom: liBlock,
    beforeSubmit: (d) => { d.items = li.get(); d.submit = !draft; if (!d.items.length) throw Object.assign(new Error("Add at least one product"), { field: null }); },
    onSubmit: async (d) => { const r = await api(e ? "/api/purchase-orders/" + po.id : "/api/purchase-orders", e ? "PUT" : "POST", d); toast(d.submit ? "Purchase order submitted for approval" : "Purchase order saved as draft"); Pages.purchase.reload && Pages.purchase.reload(); },
    onOpen: (m, form) => { li = lineItems(form, { mode: "po", getWh: () => 0 }); if (e && po.items.length) po.items.forEach((i) => li.addRow({ product_id: i.product_id, quantity: i.quantity, unit_cost: i.unit_cost })); else if (prefill && prefill.items) prefill.items.forEach((i) => li.addRow(i)); else li.addRow(); li.totals();
      $("#po-draft", m.el).onclick = () => { draft = true; $("[data-submit]", m.el).click(); draft = false; }; } });
}
async function poDetail(id) {
  let po; try { po = await api("/api/purchase-orders/" + id); } catch (e) { return fail(e); }
  const flow = ["DRAFT", "PENDING", "APPROVED", "PARTIALLY_RECEIVED", "COMPLETED"], idx = flow.indexOf(po.status);
  const steps = flow.map((s, i) => ({ label: fmt.title(s), state: po.status === "CANCELLED" ? (i === 0 ? "done" : "") : i < idx ? "done" : i === idx ? (s === "COMPLETED" ? "done" : "now") : "", icon: "clock" }));
  if (po.status === "CANCELLED") steps.push({ label: "Cancelled", state: "bad" });
  openModal({ title: `${po.po_no} ${pill(po.status)}`, size: "lg", body: `${stepper(steps)}<div class="grid g3" style="margin-top:14px"><div class="tile"><small>Supplier</small><b style="font-size:16px">${esc(po.supplier_name)}</b></div><div class="tile"><small>Deliver to</small><b style="font-size:16px">${esc(po.warehouse_name)}</b></div><div class="tile"><small>Expected</small><b style="font-size:16px">${fmt.date(po.expected_date)}</b></div></div>
    <table class="tbl" style="margin-top:8px"><thead><tr><th>Product</th><th class="r">Ordered</th><th class="r">Received</th><th class="r">Unit cost</th><th class="r">Line total</th></tr></thead><tbody>${po.items.map((i) => `<tr><td><b>${esc(i.name)}</b><div class="pcode">${esc(i.code || "")}</div></td><td class="r">${i.quantity}</td><td class="r">${i.received_qty}</td><td class="r">${fmt.money(i.unit_cost)}</td><td class="r">${fmt.money(i.quantity * i.unit_cost)}</td></tr>`).join("")}<tr><td colspan="4" class="r"><b>Total</b></td><td class="r"><b>${fmt.money(po.total)}</b></td></tr></tbody></table>
    <p class="muted" style="margin-top:10px">Created ${fmt.dt(po.created_at)} by ${esc(po.created_by || "-")}${po.received_date ? ` · Fully received ${fmt.date(po.received_date)}` : ""}${po.notes ? ` · ${esc(po.notes)}` : ""}</p>` });
}
function poReceive(po) {
  const open = po.items.filter((i) => i.quantity > i.received_qty);
  const rows = open.map((i) => `<tr><td><b>${esc(i.name)}</b><div class="pcode">Outstanding ${i.quantity - i.received_qty}</div></td><td><input type="number" min="0" max="${i.quantity - i.received_qty}" value="${i.quantity - i.received_qty}" data-q="${i.id}" style="width:90px"></td>
    <td>${i.expiry_tracked ? `<input type="date" data-e="${i.id}" value="${new Date(Date.now() + 365 * 864e5).toISOString().slice(0, 10)}"> <input data-b="${i.id}" placeholder="Batch no" style="width:110px">` : '<span class="muted">-</span>'}</td></tr>`).join("");
  openModal({ title: `Receive goods - ${po.po_no}`, size: "lg", body: `<p class="muted" style="margin-bottom:12px">Enter the quantity that arrived. Stock is added to <b>${esc(po.warehouse_name)}</b> immediately; partial deliveries are allowed.</p><div class="form-banner" id="rv-err" hidden></div><table class="tbl"><thead><tr><th>Product</th><th>Qty received</th><th>Batch / expiry (perishable)</th></tr></thead><tbody>${rows}</tbody></table>`,
    footer: `<button class="btn" data-x>Cancel</button><button class="btn primary" data-ok>${ic("inbox", 16)} Receive into stock</button>`,
    onOpen: (m) => { $("[data-x]", m.el).onclick = m.close; $("[data-ok]", m.el).onclick = async () => {
      const lines = open.map((i) => ({ item_id: i.id, quantity: +($(`[data-q="${i.id}"]`, m.el).value || 0), expiry_date: (($(`[data-e="${i.id}"]`, m.el) || {}).value) || "", batch_no: (($(`[data-b="${i.id}"]`, m.el) || {}).value) || "" }));
      try { const r = await api(`/api/purchase-orders/${po.id}/receive`, "POST", { lines }); toast(`${r.received} units received into stock`); m.close(); Pages.purchase.reload && Pages.purchase.reload(); } catch (e) { const b = $("#rv-err", m.el); b.textContent = e.message; b.hidden = false; } }; } });
}

/* =============================================================== CUSTOMER ORDERS */
const ORDER_FLOW = [["PENDING", "Order Created", "file-text"], ["CONFIRMED", "Confirmed", "check-square"], ["PROCESSING", "Processing", "cpu"], ["PACKED", "Packed", "package"], ["DISPATCHED", "Dispatched", "truck"], ["DELIVERED", "Delivered", "check-circle"]];
function queueStrip(snap, kind) {
  const nodes = snap.nodes.slice(0, 9), more = snap.size - nodes.length;
  if (!snap.size) return `<div class="muted" style="padding:10px 2px">Queue is empty - FRONT = REAR = None</div>`;
  return `<div class="q-mini">${nodes.map((n, i) => `<span class="n ${i === 0 ? "f" : ""} ${i === nodes.length - 1 && more <= 0 ? "r" : ""}" title="${i === 0 ? "FRONT" : ""}">${i === 0 ? "FRONT · " : ""}${esc(n.label)}${i === nodes.length - 1 && more <= 0 && nodes.length > 1 ? " · REAR" : ""}</span>${i < nodes.length - 1 || more > 0 ? '<span class="a">→</span>' : ""}`).join("")}${more > 0 ? `<span class="muted">+${more} more</span>` : ""}<span class="a">→ None</span></div>`;
}
Pages.orders = {
  async render(el, arg) {
    if (arg && arg !== "new") return orderPage(el, arg);
    el.innerHTML = pageHead("Customer Orders", "Orders join the REAR of the Order Queue and are served from the FRONT (FIFO)", can("order.write") ? `<button class="btn primary" id="o-new">${ic("plus", 16)} New Order</button>` : "") +
      `<div class="grid g2"><div class="card live-q" style="margin:0"><div class="card-head"><div><h3>${ic("clock", 17)} Order Queue</h3><small>Pending orders waiting to be confirmed</small></div><div class="actions"><button class="btn sm primary" id="q-next">Process Next <span style="opacity:.75">(Dequeue)</span></button><button class="btn sm" id="q-all">Process All</button></div></div><div id="q-orders"></div></div>
      <div class="card live-q" style="margin:0"><div class="card-head"><div><h3>${ic("truck", 17)} Dispatch Queue</h3><small>Packed orders waiting for a truck</small></div><div class="actions"><button class="btn sm orange" id="d-next">Dispatch Next <span style="opacity:.75">(Dequeue)</span></button><button class="btn sm" id="d-all">Dispatch All</button></div></div><div id="q-dispatch"></div></div></div>
      <div class="card" style="margin-top:18px"><div class="toolbar"><div class="seg" id="o-seg"><button data-s="" class="on">All</button>${["PENDING", "CONFIRMED", "PROCESSING", "PACKED", "DISPATCHED", "DELIVERED", "CANCELLED", "RETURNED"].map((s) => `<button data-s="${s}">${fmt.title(s)}</button>`).join("")}</div><span class="grow"></span><input id="o-q" placeholder="Search order or customer…" style="min-width:240px"></div><div id="o-table"></div></div>`;
    let status = "", q = "";
    const table = makeTable($("#o-table"), { pageSize: 10, rows: [], empty: emptyState("shopping-cart", "No orders found", "Create a customer order to get started."), rowClick: (o) => (location.hash = "#/orders/" + o.id),
      onAction: async (a, o) => { try { if (a === "view") location.hash = "#/orders/" + o.id; if (a === "adv") { const r = await api(`/api/orders/${o.id}/advance`, "POST"); toast(`${o.order_no} is now ${fmt.title(r.status)}`); load(); } if (a === "cancel") cancelOrder(o, load); } catch (e) { fail(e); } },
      columns: [{ key: "order_no", label: "Order", sort: true, render: (o) => `<b class="mono">${o.order_no}</b>${o.queue_position ? `<div><span class="pill ${o.queue_position === 1 ? "em" : "gray"}" style="margin-top:3px">${o.status === "PENDING" ? "Order" : "Dispatch"} queue #${o.queue_position}${o.queue_position === 1 ? " · next" : ""}</span></div>` : ""}` },
        { key: "customer_name", label: "Customer", sort: true, render: (o) => `<b>${esc(o.customer_name)}</b><div class="pcode">${esc(o.destination || "")}</div>` }, { key: "warehouse_name", label: "Warehouse" }, { key: "units", label: "Items", align: "r", render: (o) => `${o.units} <span class="pcode">(${o.lines} line${o.lines > 1 ? "s" : ""})</span>` },
        { key: "total", label: "Total", align: "r", sort: true, render: (o) => fmt.money(o.total) }, { key: "status", label: "Status", render: (o) => pill(o.status) }, { key: "created_at", label: "Placed", sort: true, render: (o) => fmt.dt(o.created_at) },
        { key: "act", label: "", render: (o) => `<div class="row-acts">${actBtn("view", o.id, "eye", "View")}${can("order.advance") && ["CONFIRMED", "PROCESSING"].includes(o.status) ? actBtn("adv", o.id, "skip-forward", o.status === "CONFIRMED" ? "Start processing" : "Mark as packed") : ""}${can("order.write") && ["PENDING", "CONFIRMED", "PROCESSING", "PACKED"].includes(o.status) ? actBtn("cancel", o.id, "x-circle", "Cancel", "del") : ""}</div>` }] });
    const load = async () => {
      try {
        const qs = new URLSearchParams(); if (status) qs.set("status", status); if (q) qs.set("q", q);
        const [rows, live] = await Promise.all([api("/api/orders?" + qs), api("/api/dsa/live")]);
        table.setRows(rows); $("#q-orders").innerHTML = queueStrip(live.orders); $("#q-dispatch").innerHTML = queueStrip(live.dispatch);
      } catch (e) { fail(e); }
    };
    Pages.orders.reload = load;
    const run = (url, body, msg) => async () => { try { const r = await api(url, "POST", body); toast(msg(r)); load(); } catch (e) { fail(e); } };
    $("#q-next").onclick = run("/api/orders/process-next", {}, (r) => `Dequeued ${r.processed[0]} from the FRONT - order confirmed`);
    $("#q-all").onclick = run("/api/orders/process-next", { all: true }, (r) => `${r.processed.length} order(s) dequeued in FIFO order`);
    $("#d-next").onclick = run("/api/orders/dispatch-next", {}, (r) => `${r.dispatched[0]} dispatched - shipment created`);
    $("#d-all").onclick = run("/api/orders/dispatch-next", { all: true }, (r) => `${r.dispatched.length} order(s) dispatched in FIFO order`);
    $("#o-seg").onclick = (e) => { const b = e.target.closest("[data-s]"); if (!b) return; status = b.dataset.s; $$("#o-seg button").forEach((x) => x.classList.toggle("on", x === b)); load(); };
    $("#o-q").oninput = debounce((e) => { q = e.target.value.trim(); load(); }, 250);
    const n = $("#o-new"); if (n) n.onclick = () => orderForm();
    await load();
    if (arg === "new" && can("order.write")) orderForm();
  },
};
async function cancelOrder(o, after) {
  if (!(await confirmBox({ title: "Cancel this order?", message: `<b>${o.order_no}</b> will be removed from its queue and the reserved stock will be released.`, okText: "Cancel order" }))) return;
  try { await api(`/api/orders/${o.id}/cancel`, "POST"); toast(`${o.order_no} cancelled - stock released`); after && after(); } catch (e) { fail(e); }
}
function orderForm() {
  let li;
  formModal({ title: "New customer order", size: "xl", submitText: "Place order (Enqueue)",
    fields: [{ name: "customer_name", label: "Customer name", required: true }, { name: "phone", label: "Phone" }, { name: "destination", label: "Delivery city / destination" }, { name: "warehouse_id", label: "Ship from warehouse", type: "select", required: true, options: whOptions(App.meta.warehouses) },
      { name: "discount_pct", label: "Discount %", type: "number", min: 0, max: 100, step: "0.5" }, { name: "notes", label: "Notes" }], values: { warehouse_id: App.meta.warehouses[0].id, discount_pct: 0 }, bottom: liBlock,
    beforeSubmit: (d) => { d.items = li.get().map((i) => ({ product_id: i.product_id, quantity: i.quantity })); if (!d.items.length) throw new Error("Add at least one product to the order"); },
    onSubmit: async (d) => { const r = await api("/api/orders", "POST", d); toast(`${r.order_no} placed - enqueued at the REAR of the order queue`); if (location.hash.startsWith("#/orders")) { location.hash = "#/orders"; Pages.orders.reload ? Pages.orders.reload() : route(); } else route(); },
    onOpen: (m, form) => { li = lineItems(form, { mode: "order", getWh: () => +form.querySelector("[name=warehouse_id]").value }); li.addRow();
      form.querySelector("[name=warehouse_id]").onchange = () => li.check(); form.querySelector("[name=discount_pct]").oninput = () => li.totals(); } });
}
async function orderPage(el, id) {
  let o; try { o = await api("/api/orders/" + id); } catch (e) { el.innerHTML = emptyState("alert-circle", "Order not found", `<a href="#/orders">Back to orders</a>`); return; }
  const hist = {}; o.history.forEach((h) => (hist[h.status] = h.ts));
  const idx = ORDER_FLOW.findIndex((s) => s[0] === o.status);
  let steps = ORDER_FLOW.map(([k, l, i], n) => ({ label: l, icon: i, ts: hist[k], state: o.status === "CANCELLED" ? (hist[k] ? "done" : "") : o.status === "RETURNED" ? "done" : n < idx ? "done" : n === idx ? (k === "DELIVERED" ? "done" : "now") : "" }));
  if (o.status === "CANCELLED") steps = steps.filter((s) => s.state === "done").concat([{ label: "Cancelled", ts: hist.CANCELLED, state: "bad" }]);
  if (o.status === "RETURNED") steps.push({ label: "Returned", ts: hist.RETURNED, state: "now", icon: "rotate-ccw" });
  const next = o.status === "CONFIRMED" ? "Start processing" : o.status === "PROCESSING" ? "Mark as packed" : null;
  el.innerHTML = `<a href="#/orders" class="muted" style="display:inline-flex;gap:6px;align-items:center;margin-bottom:12px">${ic("chevron-left", 16)} Back to orders</a>` + pageHead(`${o.order_no} ${pill(o.status)}`, `${esc(o.customer_name)} · placed ${fmt.dt(o.created_at)} by ${esc(o.created_by || "-")}`,
    `${can("order.advance") && next ? `<button class="btn primary" id="od-adv">${ic("skip-forward", 16)} ${next}</button>` : ""}${o.status === "DELIVERED" && can("return.write") ? `<button class="btn" id="od-ret">${ic("rotate-ccw", 16)} Create return</button>` : ""}${can("order.write") && ["PENDING", "CONFIRMED", "PROCESSING", "PACKED"].includes(o.status) ? `<button class="btn danger" id="od-cancel">${ic("x-circle", 16)} Cancel order</button>` : ""}<button class="btn" onclick="window.print()">${ic("printer", 16)} Print</button>`) +
    `<div class="print-area"><div class="card">${o.queue_position ? `<div class="stats-strip">${ic("clock", 15)} This order is <b>#${o.queue_position}</b> in the ${o.status === "PENDING" ? "Order" : "Dispatch"} Queue ${o.queue_position === 1 ? "- it is at the FRONT and will be served next." : "- orders ahead of it are served first (FIFO)."}</div>` : ""}${stepper(steps)}</div>
    <div class="grid g-21" style="margin-top:18px"><div class="card"><div class="card-head"><h3>Order items</h3></div><table class="tbl"><thead><tr><th>Product</th><th class="r">Qty</th><th class="r">Unit price</th><th class="r">Line total</th></tr></thead><tbody>${o.items.map((i) => `<tr><td><b>${esc(i.name)}</b><div class="pcode">${esc(i.code || "")} · ${esc(i.sku || "")}</div></td><td class="r">${i.quantity}</td><td class="r">${fmt.money(i.unit_price)}</td><td class="r">${fmt.money(i.quantity * i.unit_price)}</td></tr>`).join("")}</tbody></table>
      <div class="info-list" style="margin:16px 0 0 auto;max-width:320px"><div><span>Subtotal</span><b>${fmt.money(o.subtotal)}</b></div><div><span>Discount (${o.discount_pct}%)</span><b>- ${fmt.money(o.subtotal - o.total)}</b></div><div><span><b>Total</b></span><b style="font-size:18px;color:var(--em)">${fmt.money(o.total)}</b></div></div></div>
      <div style="display:flex;flex-direction:column;gap:18px"><div class="card"><div class="card-head"><h3>Customer &amp; delivery</h3></div><div class="info-list"><div><span>Customer</span><b>${esc(o.customer_name)}</b></div><div><span>Phone</span><b>${esc(o.phone || "-")}</b></div><div><span>Destination</span><b>${esc(o.destination || "-")}</b></div><div><span>Ships from</span><b>${esc(o.warehouse_name)}</b></div></div>
      ${o.shipment ? `<div class="stats-strip" style="margin:14px 0 0">${ic("truck", 15)} <b>${o.shipment.shipment_no}</b> · ${esc(o.shipment.partner)} · ${esc(o.shipment.tracking_no)} · ${pill(o.shipment.status)}</div>` : ""}</div>
      <div class="card"><div class="card-head"><h3>Status history</h3></div><ul class="tl">${o.history.map((h) => `<li><b>${fmt.title(h.status)}</b><small>${fmt.dt(h.ts)} · ${esc(h.by_user || "")}</small></li>`).join("")}</ul></div></div></div>
    ${o.returns.length ? `<div class="card" style="margin-top:18px"><div class="card-head"><h3>Returns for this order</h3></div><table class="tbl"><thead><tr><th>Return</th><th>Product</th><th class="r">Qty</th><th>Reason</th><th>Condition</th><th>Status</th></tr></thead><tbody>${o.returns.map((r) => `<tr><td class="mono">${r.return_no}</td><td>${esc(r.product_name)}</td><td class="r">${r.quantity}</td><td>${esc(r.reason)}</td><td>${pill(r.condition)}</td><td>${pill(r.status)}</td></tr>`).join("")}</tbody></table></div>` : ""}</div>`;
  const run = (b, fn) => { const e = $(b); if (e) e.onclick = fn; };
  run("#od-adv", async () => { try { const r = await api(`/api/orders/${o.id}/advance`, "POST"); toast(`Order is now ${fmt.title(r.status)}`); route(); } catch (e) { fail(e); } });
  run("#od-cancel", () => cancelOrder(o, route)); run("#od-ret", () => returnForm({ order_id: o.id }));
}

/* =============================================================== SHIPMENTS */
const SHIP_FLOW = [["ORDER_CREATED", "Order Created", "file-text"], ["PROCESSING", "Processing", "cpu"], ["PACKED", "Packed", "package"], ["DISPATCHED", "Dispatched", "truck"], ["IN_TRANSIT", "In Transit", "navigation"], ["DELIVERED", "Delivered", "check-circle"]];
Pages.shipments = {
  async render(el) {
    el.innerHTML = pageHead("Shipment & Delivery", "Track every dispatched order from warehouse to customer") + `<div id="sh-tiles" class="stat-tiles"></div><div class="grid g2">${chartCard("c-ship1", "On-time Delivery Performance", "Delivered shipments vs expected date", "")}${chartCard("c-ship2", "Shipments by Delivery Partner", "Delivered on time vs late vs in progress")}</div>
      <div class="card"><div class="toolbar"><div class="seg" id="sh-seg"><button data-s="" class="on">All</button><button data-s="DISPATCHED">Dispatched</button><button data-s="IN_TRANSIT">In Transit</button><button data-s="DELAYED">Delayed</button><button data-s="DELIVERED">Delivered</button></div></div><div id="sh-table"></div></div>`;
    let status = "";
    const table = makeTable($("#sh-table"), { pageSize: 10, rows: [], empty: emptyState("truck", "No shipments", "Dispatch an order to create a shipment."), rowClick: (s) => shipDetail(s.id),
      onAction: async (a, s) => { try { if (a === "view") shipDetail(s.id); if (a === "adv") { const r = await api(`/api/shipments/${s.id}/advance`, "POST"); toast(`${s.shipment_no} is now ${fmt.title(r.status)}`); load(); } if (a === "edit") shipForm(s, load); } catch (e) { fail(e); } },
      columns: [{ key: "shipment_no", label: "Shipment", sort: true, cls: "mono" }, { key: "order_no", label: "Order", cls: "mono" }, { key: "customer_name", label: "Customer", sort: true }, { key: "origin_name", label: "Origin" }, { key: "destination", label: "Destination" },
        { key: "partner", label: "Partner", sort: true, render: (s) => `${esc(s.partner)}<div class="pcode">${esc(s.tracking_no)}</div>` }, { key: "dispatch_date", label: "Dispatched", sort: true, render: (s) => fmt.date(s.dispatch_date) },
        { key: "expected_date", label: "Expected", sort: true, render: (s) => `${fmt.date(s.expected_date)}${s.delayed ? ' <span class="pill red">Delayed</span>' : s.late_delivery ? ' <span class="pill or">Late</span>' : ""}` },
        { key: "status", label: "Status", render: (s) => pill(s.status) },
        { key: "act", label: "", render: (s) => `<div class="row-acts">${actBtn("view", s.id, "eye", "Timeline")}${can("shipment.write") && s.status !== "DELIVERED" ? actBtn("adv", s.id, "skip-forward", s.status === "DISPATCHED" ? "Mark in transit" : "Mark delivered") + actBtn("edit", s.id, "edit-2", "Edit") : ""}</div>` }] });
    const load = async () => {
      try {
        const all = await api("/api/shipments"), list = status ? await api("/api/shipments?status=" + status) : all; table.setRows(list);
        const del = all.filter((s) => s.status === "DELIVERED"), ontime = del.filter((s) => !s.late_delivery).length, transit = all.filter((s) => s.status !== "DELIVERED");
        $("#sh-tiles").innerHTML = `<div class="tile"><small>Total shipments</small><b>${fmt.num(all.length)}</b></div><div class="tile"><small>In progress</small><b>${transit.length}</b></div><div class="tile"><small>Delayed</small><b style="color:var(--red)">${all.filter((s) => s.delayed).length}</b></div><div class="tile"><small>Delivered</small><b>${fmt.num(del.length)}</b></div><div class="tile"><small>On-time rate</small><b style="color:var(--em)">${del.length ? Math.round(ontime * 100 / del.length) : 0}%</b></div>`;
        mk("c-ship1", { type: "doughnut", data: { labels: ["On time", "Late", "In progress", "Delayed"], datasets: [{ data: [ontime, del.length - ontime, transit.length - all.filter((s) => s.delayed).length, all.filter((s) => s.delayed).length], backgroundColor: ["#119B78", "#F29A38", "#20B8B0", "#DB5B50"], borderWidth: 3, borderColor: getComputedStyle(document.documentElement).getPropertyValue("--card").trim() }] }, options: { cutout: "66%", plugins: { legend: { position: "right" } } } });
        const partners = [...new Set(all.map((s) => s.partner))], by = (f) => partners.map((p) => all.filter((s) => s.partner === p && f(s)).length);
        mk("c-ship2", { type: "bar", data: { labels: partners, datasets: [{ label: "On time", data: by((s) => s.status === "DELIVERED" && !s.late_delivery), backgroundColor: "#119B78" }, { label: "Late", data: by((s) => s.late_delivery), backgroundColor: "#F29A38" }, { label: "In progress", data: by((s) => s.status !== "DELIVERED"), backgroundColor: "#20B8B0", borderRadius: { topLeft: 6, topRight: 6 } }] }, options: { plugins: { legend: { position: "bottom" } }, scales: { x: { stacked: true, grid: { display: false } }, y: { stacked: true, border: { display: false } } } } });
      } catch (e) { fail(e); }
    };
    $("#sh-seg").onclick = (e) => { const b = e.target.closest("[data-s]"); if (!b) return; status = b.dataset.s; $$("#sh-seg button").forEach((x) => x.classList.toggle("on", x === b)); load(); };
    Pages.shipments.reload = load; load();
  },
};
async function shipDetail(id) {
  let s; try { s = await api("/api/shipments/" + id); } catch (e) { return fail(e); }
  const ev = {}; s.events.forEach((e) => (ev[e.status] = e.ts));
  const idx = SHIP_FLOW.findIndex((x) => x[0] === s.status);
  const steps = SHIP_FLOW.map(([k, l, i], n) => ({ label: l, icon: i, ts: ev[k], state: n < idx || s.status === "DELIVERED" ? "done" : n === idx ? "now" : "" }));
  openModal({ title: `${s.shipment_no} ${pill(s.status)} ${s.delayed ? '<span class="pill red">Delayed</span>' : ""}`, size: "lg", body: `${stepper(steps)}<div class="grid g2" style="margin-top:16px"><div class="info-list"><div><span>Order</span><b class="mono">${s.order_no}</b></div><div><span>Customer</span><b>${esc(s.customer_name)}</b></div><div><span>Origin warehouse</span><b>${esc(s.origin_name)}</b></div><div><span>Destination</span><b>${esc(s.destination || "-")}</b></div></div>
    <div class="info-list"><div><span>Delivery partner</span><b>${esc(s.partner)}</b></div><div><span>Tracking number</span><b class="mono">${esc(s.tracking_no)}</b></div><div><span>Dispatched</span><b>${fmt.date(s.dispatch_date)}</b></div><div><span>Expected delivery</span><b>${fmt.date(s.expected_date)}</b></div>${s.delivered_date ? `<div><span>Delivered</span><b>${fmt.date(s.delivered_date)}</b></div>` : ""}</div></div>
    <h4 style="margin:18px 0 8px">Items in this shipment</h4><table class="tbl"><tbody>${s.items.map((i) => `<tr><td>${esc(i.name)}</td><td class="r">${i.quantity} units</td></tr>`).join("")}</tbody></table>` });
}
function shipForm(s, after) {
  formModal({ title: `Edit ${s.shipment_no}`, size: "sm", fields: [{ name: "partner", label: "Delivery partner", type: "select", required: true, options: ["TCS", "Leopards Courier", "M&P Express", "BlueEx", "Trax Logistics"], full: true }, { name: "expected_date", label: "Expected delivery", type: "date", full: true }], values: s,
    onSubmit: async (d) => { await api("/api/shipments/" + s.id, "PUT", d); toast("Shipment updated"); after(); } });
}

/* =============================================================== RETURNS */
Pages.returns = {
  async render(el) {
    el.innerHTML = pageHead("Returns & Damage Management", "Approve returns, restock resellable items and track damaged stock", can("return.write") ? `<button class="btn primary" id="r-new">${ic("plus", 16)} Record Return</button>` : "") + `<div id="r-tiles" class="stat-tiles"></div><div class="card"><div class="toolbar"><div class="seg" id="r-seg"><button data-s="" class="on">All</button><button data-s="PENDING">Pending</button><button data-s="APPROVED">Approved</button><button data-s="REJECTED">Rejected</button></div></div><div id="r-table"></div></div>`;
    let status = "", all = [];
    const table = makeTable($("#r-table"), { pageSize: 10, rows: [], empty: emptyState("rotate-ccw", "No returns", "Returned products will appear here."),
      onAction: async (a, r) => { if (!(await confirmBox({ title: a === "approve" ? "Approve return?" : "Reject return?", message: a === "approve" ? (r.condition === "RESELLABLE" ? `${r.quantity} x <b>${esc(r.product_name)}</b> will be restocked into the warehouse.` : `${r.quantity} x <b>${esc(r.product_name)}</b> is damaged and will be added to damaged stock (not restocked).`) : "The customer return will be rejected.", okText: a === "approve" ? "Approve" : "Reject", danger: a === "reject", icon: "info" }))) return;
        try { await api(`/api/returns/${r.id}/decision`, "POST", { decision: a }); toast(a === "approve" ? "Return approved" : "Return rejected"); load(); } catch (e) { fail(e); } },
      columns: [{ key: "return_no", label: "Return", sort: true, cls: "mono" }, { key: "order_no", label: "Order", render: (r) => `<a class="mono" href="#/orders/${r.order_id}">${r.order_no}</a><div class="pcode">${esc(r.customer_name || "")}</div>` }, { key: "product_name", label: "Product", sort: true }, { key: "quantity", label: "Qty", align: "r" },
        { key: "reason", label: "Reason" }, { key: "condition", label: "Condition", render: (r) => pill(r.condition) }, { key: "refund_amount", label: "Refund", align: "r", sort: true, render: (r) => fmt.money(r.refund_amount) }, { key: "status", label: "Status", render: (r) => pill(r.status) }, { key: "created_at", label: "Date", sort: true, render: (r) => fmt.date(r.created_at) },
        { key: "act", label: "", render: (r) => (r.status === "PENDING" && can("return.decide") ? `<div class="row-acts"><button class="btn sm primary" data-act="approve" data-id="${r.id}">Approve</button><button class="btn sm danger" data-act="reject" data-id="${r.id}">Reject</button></div>` : "") }] });
    const draw = () => table.setRows(all.filter((r) => !status || r.status === status));
    const load = async () => { try { const d = await api("/api/returns"); all = d.items; draw(); const ap = all.filter((r) => r.status === "APPROVED");
      $("#r-tiles").innerHTML = `<div class="tile"><small>Total returns</small><b>${all.length}</b></div><div class="tile"><small>Pending approval</small><b style="color:var(--or)">${all.filter((r) => r.status === "PENDING").length}</b></div><div class="tile"><small>Approved</small><b>${ap.length}</b></div><div class="tile"><small>Refund value</small><b>${fmt.compact(ap.reduce((s, r) => s + r.refund_amount, 0))}</b></div><div class="tile"><small>Total damaged stock</small><b style="color:var(--red)">${fmt.num(d.total_damaged)} units</b></div>`; } catch (e) { fail(e); } };
    $("#r-seg").onclick = (e) => { const b = e.target.closest("[data-s]"); if (!b) return; status = b.dataset.s; $$("#r-seg button").forEach((x) => x.classList.toggle("on", x === b)); draw(); };
    const n = $("#r-new"); if (n) n.onclick = () => returnForm({});
    Pages.returns.reload = load; load();
  },
};
async function returnForm(def) {
  let orders = []; try { orders = await api("/api/returns/eligible-orders"); } catch (e) { return fail(e); }
  if (!orders.length) return toast("There are no delivered orders to return yet", "warn");
  formModal({ title: "Record product return", fields: [{ name: "order_id", label: "Delivered order", type: "select", required: true, full: true, options: orders.map((o) => ({ value: o.id, label: `${o.order_no} - ${o.customer_name}` })), blank: "Select order" },
    { name: "product_id", label: "Product", type: "select", required: true, options: [], blank: "Select an order first" }, { name: "quantity", label: "Quantity returned", type: "number", min: 1, required: true },
    { name: "reason", label: "Return reason", type: "select", required: true, options: ["Damaged in transit", "Wrong item delivered", "Defective product", "Customer changed mind", "Expired / near expiry", "Quantity mismatch"], blank: "Select reason" },
    { name: "condition", label: "Product condition", type: "select", options: [{ value: "RESELLABLE", label: "Resellable - restock if approved" }, { value: "DAMAGED", label: "Damaged - add to damaged stock" }] }, { name: "note", label: "Note", type: "textarea", rows: 2, full: true }], values: { order_id: def.order_id || "", condition: "RESELLABLE" },
    onSubmit: async (d) => { await api("/api/returns", "POST", d); toast("Return recorded - waiting for approval"); Pages.returns.reload ? Pages.returns.reload() : route(); },
    onOpen: (m, form) => { const os = form.querySelector("[name=order_id]"), ps = form.querySelector("[name=product_id]");
      const fill = async () => { if (!os.value) { ps.innerHTML = `<option value="">Select an order first</option>`; return; } try { const o = await api("/api/orders/" + os.value); ps.innerHTML = `<option value="">Select product</option>` + o.items.map((i) => `<option value="${i.product_id}">${esc(i.name)} (ordered ${i.quantity})</option>`).join(""); } catch (e) { } };
      os.onchange = fill; fill(); } });
}
