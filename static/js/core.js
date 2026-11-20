/* =====================================================================
   core.js - shared helpers: API, formatting, modal/form builder, table, filters
   ===================================================================== */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const App = { user: null, meta: null, range: { preset: "30d", from: "", to: "" }, wh: "", charts: {}, timers: [], page: "overview" };

function ic(name, size = 18, extra = "") {
  return `<svg class="ic ${extra}" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONS[name] || ""}</svg>`;
}
const fmt = {
  num: (n) => Number(n || 0).toLocaleString("en-US", { maximumFractionDigits: 1 }),
  money: (n) => "Rs\u00a0" + Math.round(Number(n || 0)).toLocaleString("en-US"),
  compact: (n) => new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(n || 0),
  date: (s) => { if (!s) return "-"; const d = new Date(String(s).slice(0, 10) + "T00:00:00"); return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }); },
  dt: (s) => { if (!s) return "-"; const d = new Date(String(s).replace(" ", "T")); return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" }) + ", " + d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }); },
  ago: (s) => { const m = Math.max(0, Math.round((Date.now() - new Date(String(s).replace(" ", "T")).getTime()) / 60000)); if (m < 1) return "just now"; if (m < 60) return m + " min ago"; if (m < 1440) return Math.round(m / 60) + " h ago"; return Math.round(m / 1440) + " d ago"; },
  title: (s) => String(s || "").replace(/_/g, " ").toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase()),
};
const debounce = (fn, ms = 300) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
const todayISO = () => new Date().toISOString().slice(0, 10);
const can = (p) => App.user && (App.user.perms.includes("*") || App.user.perms.includes(p));
const isAdmin = () => App.user && App.user.role === "admin";

const COLORS = ["#119B78", "#20B8B0", "#F29A38", "#3E5C84", "#DB5B50", "#C9A66B", "#7FA650", "#8A6FB0"];
const CAT_COLOR = { Electronics: "#3E7CB1", Groceries: "#7FA650", Pharmaceuticals: "#DB5B50", Apparel: "#8A6FB0", Industrial: "#F29A38", Furniture: "#C9A66B", "Home Appliances": "#20B8B0", Stationery: "#119B78" };
const catEmoji = (c) => (App.meta && App.meta.emoji[c]) || "📦";
function pimg(p, cls = "") {
  const img = p.image && p.image.startsWith("data:") ? `<img src="${p.image}" alt="">` : (p.image && p.image.length <= 8 ? esc(p.image) : catEmoji(p.category));
  return `<span class="pimg ${cls}" style="${p.image ? "" : `background:${(CAT_COLOR[p.category] || "#888")}22`}">${img}</span>`;
}

/* ---------------------------------------------------------------- pills */
const PILL = {
  PENDING: "or", CONFIRMED: "blue", PROCESSING: "tq", PACKED: "navy", DISPATCHED: "blue", IN_TRANSIT: "tq", DELIVERED: "em", CANCELLED: "gray", RETURNED: "or",
  DRAFT: "gray", APPROVED: "blue", PARTIALLY_RECEIVED: "tq", COMPLETED: "em", REJECTED: "red", OK: "em", LOW: "or", OUT: "red",
  Active: "em", Inactive: "gray", Maintenance: "or", STOCK_IN: "em", STOCK_OUT: "blue", TRANSFER: "tq", RETURN: "or", DAMAGED: "red",
  RESELLABLE: "em", critical: "red", warning: "or", info: "tq", success: "em",
};
const PILL_TEXT = { OK: "In stock", LOW: "Low stock", OUT: "Out of stock" };
const pill = (s, text) => `<span class="pill ${PILL[s] || "gray"}">${esc(text || PILL_TEXT[s] || fmt.title(s))}</span>`;

/* ---------------------------------------------------------------- API */
async function api(url, method = "GET", body) {
  let res;
  try {
    res = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: body !== undefined ? JSON.stringify(body) : undefined, credentials: "same-origin" });
  } catch (e) { throw new Error("Cannot reach the server. Is it running?"); }
  let data = null;
  if ((res.headers.get("content-type") || "").includes("json")) data = await res.json().catch(() => null);
  if (res.status === 401 && !url.includes("/auth/login")) { if (window.showLogin) window.showLogin(); throw new Error("Please sign in"); }
  if (!res.ok) { const e = new Error((data && data.error) || "Request failed"); e.field = data && data.field; e.data = data; throw e; }
  return data;
}

/* ---------------------------------------------------------------- toast */
function toast(msg, type = "success") {
  const icon = { success: "check-circle", error: "x-circle", info: "info", warn: "alert-triangle" }[type] || "check-circle";
  const t = document.createElement("div");
  t.className = "toast " + (type === "success" ? "" : type);
  t.innerHTML = `${ic(icon, 20)}<div>${esc(msg)}</div>`;
  $("#toasts").appendChild(t);
  setTimeout(() => { t.style.transition = ".3s"; t.style.opacity = 0; setTimeout(() => t.remove(), 300); }, type === "error" ? 5200 : 3200);
}
const fail = (e) => toast(e.message || "Something went wrong", "error");

/* ---------------------------------------------------------------- modal */
function openModal({ title, body, footer = "", size = "", onOpen, onClose, noClose }) {
  const ov = document.createElement("div");
  ov.className = "overlay";
  ov.innerHTML = `<div class="modal ${size}" role="dialog" aria-modal="true"><div class="modal-head"><h3>${title}</h3><button class="ib" data-close title="Close">${ic("x", 16)}</button></div>
    <div class="modal-body">${body}</div>${footer ? `<div class="modal-foot">${footer}</div>` : ""}</div>`;
  $("#modal-root").appendChild(ov);
  const ctrl = { el: ov.querySelector(".modal"), close() { ov.remove(); onClose && onClose(); document.removeEventListener("keydown", esc_); } };
  const esc_ = (e) => { if (e.key === "Escape" && ov === $("#modal-root").lastElementChild) ctrl.close(); };
  document.addEventListener("keydown", esc_);
  ov.addEventListener("mousedown", (e) => { if (e.target === ov && !noClose) ctrl.close(); });
  ov.querySelector("[data-close]").onclick = ctrl.close;
  onOpen && onOpen(ctrl);
  return ctrl;
}
function confirmBox({ title = "Are you sure?", message = "", okText = "Confirm", danger = true, icon }) {
  return new Promise((resolve) => {
    let done = false;
    const finish = (v) => { if (!done) { done = true; c.close(); resolve(v); } };
    const c = openModal({
      title, size: "sm", noClose: false,
      body: `<div style="text-align:center"><div class="confirm-ic ${danger ? "" : "info"}">${ic(icon || (danger ? "trash-2" : "help-circle" in ICONS ? "info" : "info"), 26)}</div><p class="muted">${message}</p></div>`,
      footer: `<button class="btn" data-no>Cancel</button><button class="btn ${danger ? "danger" : "primary"}" data-yes>${esc(okText)}</button>`,
      onOpen: (m) => { m.el.querySelector("[data-yes]").onclick = () => finish(true); m.el.querySelector("[data-no]").onclick = () => finish(false); m.el.querySelector("[data-yes]").focus(); },
      onClose: () => { if (!done) { done = true; resolve(false); } },
    });
  });
}

/* ---------------------------------------------------------------- form builder */
function fieldHtml(f, v) {
  const val = v === undefined || v === null ? "" : v;
  const req = f.required ? "<i>*</i>" : "";
  let input;
  const a = `name="${f.name}" ${f.required ? "required" : ""} ${f.readonly ? "readonly" : ""} ${f.placeholder ? `placeholder="${esc(f.placeholder)}"` : ""}`;
  if (f.type === "select") {
    const opts = (f.options || []).map((o) => (typeof o === "object" ? o : { value: o, label: o }));
    input = `<select ${a}>${f.blank ? `<option value="">${esc(f.blank)}</option>` : ""}${opts.map((o) => `<option value="${esc(o.value)}" ${String(o.value) === String(val) ? "selected" : ""}>${esc(o.label)}</option>`).join("")}</select>`;
  } else if (f.type === "textarea") input = `<textarea ${a} rows="${f.rows || 3}">${esc(val)}</textarea>`;
  else if (f.type === "checkbox") input = `<label class="chk"><input type="checkbox" name="${f.name}" ${val ? "checked" : ""}> <span>${esc(f.checkLabel || f.label)}</span></label>`;
  else if (f.type === "image") input = `<div class="up-row"><span class="pimg lg" id="img-prev-${f.name}"></span><div><input type="hidden" name="${f.name}" value="${esc(val)}"><input type="file" accept="image/*" id="img-file-${f.name}" style="height:auto;padding:8px"><div class="hint">Optional. Picture is resized to keep the database small.</div></div></div>`;
  else input = `<input ${a} type="${f.type || "text"}" value="${esc(val)}" ${f.min !== undefined ? `min="${f.min}"` : ""} ${f.max !== undefined ? `max="${f.max}"` : ""} ${f.step ? `step="${f.step}"` : ""} ${f.maxlength ? `maxlength="${f.maxlength}"` : ""}>`;
  const lab = f.type === "checkbox" ? `<label>${esc(f.label)}</label>` : `<label>${esc(f.label)} ${req}</label>`;
  return `<div class="field ${f.full ? "full" : ""}" data-field="${f.name}">${f.type === "checkbox" && !f.label ? "" : lab}${input}${f.hint ? `<div class="hint">${f.hint}</div>` : ""}<div class="err"></div></div>`;
}
function setFieldError(root, name, msg) {
  const w = root.querySelector(`[data-field="${name}"]`);
  if (!w) return false;
  const inp = w.querySelector("input,select,textarea");
  inp && inp.classList.add("invalid");
  w.querySelector(".err").textContent = msg;
  inp && inp.focus();
  return true;
}
function formModal({ title, fields, values = {}, submitText = "Save", onSubmit, size = "", top = "", bottom = "", onOpen, beforeSubmit, extraFoot = "" }) {
  const body = `<form id="fm" novalidate><div class="form-banner" hidden></div>${top}<div class="form-grid">${fields.map((f) => fieldHtml(f, values[f.name])).join("")}</div>${bottom}</form>`;
  return openModal({
    title, body, size,
    footer: `${extraFoot}<button class="btn" data-cancel>Cancel</button><button class="btn primary" data-submit>${esc(submitText)}</button>`,
    onOpen: (m) => {
      const form = m.el.querySelector("#fm"), btn = m.el.querySelector("[data-submit]");
      m.el.querySelector("[data-cancel]").onclick = m.close;
      fields.filter((f) => f.type === "image").forEach((f) => {
        const hid = form.querySelector(`[name="${f.name}"]`), prev = form.querySelector(`#img-prev-${f.name}`), file = form.querySelector(`#img-file-${f.name}`);
        const draw = () => { prev.innerHTML = hid.value.startsWith("data:") ? `<img src="${hid.value}">` : catEmoji(form.querySelector('[name="category"]') ? form.querySelector('[name="category"]').value : ""); };
        draw();
        file.onchange = () => {
          const fl = file.files[0]; if (!fl) return;
          const rd = new FileReader();
          rd.onload = () => { const im = new Image(); im.onload = () => { const c = document.createElement("canvas"), s = Math.min(1, 220 / Math.max(im.width, im.height)); c.width = im.width * s; c.height = im.height * s; c.getContext("2d").drawImage(im, 0, 0, c.width, c.height); hid.value = c.toDataURL("image/jpeg", .82); draw(); }; im.src = rd.result; };
          rd.readAsDataURL(fl);
        };
      });
      const clear = () => { form.querySelector(".form-banner").hidden = true; $$(".invalid", form).forEach((e) => e.classList.remove("invalid")); $$(".err", form).forEach((e) => (e.textContent = "")); };
      const submit = async () => {
        clear();
        const data = {};
        let bad = false;
        for (const f of fields) {
          const el = form.querySelector(`[name="${f.name}"]`);
          if (!el) continue;
          const wrap = el.closest(".field");
          if (wrap && wrap.hidden) continue;
          let v = f.type === "checkbox" ? el.checked : el.value.trim();
          data[f.name] = v;
          let msg = "";
          if (f.required && v === "") msg = `${f.label} is required`;
          else if (v !== "" && f.type === "number") { const n = Number(v); if (isNaN(n)) msg = `${f.label} must be a number`; else if (f.min !== undefined && n < f.min) msg = `${f.label} must be at least ${f.min}`; else if (f.max !== undefined && n > f.max) msg = `${f.label} must be at most ${f.max}`; }
          else if (v !== "" && f.type === "email" && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v)) msg = "Enter a valid email address";
          if (msg) { setFieldError(form, f.name, msg); bad = true; }
        }
        if (bad) return;
        btn.disabled = true; const old = btn.innerHTML; btn.innerHTML = `<span class="spin"></span>`;
        try {
          if (beforeSubmit) beforeSubmit(data, form);
          await onSubmit(data, m);
          m.close();
        } catch (e) {
          if (!(e.field && setFieldError(form, e.field, e.message))) { const b = form.querySelector(".form-banner"); b.textContent = e.message; b.hidden = false; b.scrollIntoView({ block: "nearest" }); }
        } finally { btn.disabled = false; btn.innerHTML = old; }
      };
      btn.onclick = submit;
      form.addEventListener("submit", (e) => { e.preventDefault(); submit(); });
      onOpen && onOpen(m, form);
    },
  });
}

/* ---------------------------------------------------------------- table with paging + sorting */
function makeTable(container, opts) {
  const st = { rows: opts.rows || [], page: 1, sortKey: opts.sortKey || null, sortDir: opts.sortDir || "asc", size: opts.pageSize || 10 };
  const cols = opts.columns;
  function view() {
    let rows = st.rows.slice();
    if (st.sortKey) {
      const c = cols.find((x) => x.key === st.sortKey);
      const val = (r) => (c.val ? c.val(r) : r[c.key]);
      rows.sort((a, b) => { const x = val(a), y = val(b); const r = typeof x === "number" && typeof y === "number" ? x - y : String(x ?? "").localeCompare(String(y ?? "")); return st.sortDir === "asc" ? r : -r; });
    }
    return rows;
  }
  function render() {
    const rows = view(), total = rows.length, pages = Math.max(1, Math.ceil(total / st.size));
    st.page = Math.min(st.page, pages);
    const slice = rows.slice((st.page - 1) * st.size, st.page * st.size);
    if (!total) { container.innerHTML = opts.empty || `<div class="empty">${ic("inbox", 40)}<h4>Nothing to show</h4><p>No records match your filters.</p></div>`; return; }
    const head = cols.map((c) => `<th class="${c.sort ? "sortable" : ""} ${c.align === "r" ? "r" : ""}" ${c.sort ? `data-sort="${c.key}"` : ""}>${c.label}${st.sortKey === c.key ? ` ${ic(st.sortDir === "asc" ? "arrow-up" : "arrow-down", 12)}` : ""}</th>`).join("");
    const body = slice.map((r) => `<tr class="${opts.rowClick ? "clickable" : ""} ${opts.rowClass ? opts.rowClass(r) : ""}" data-id="${r.id ?? ""}">${cols.map((c) => `<td class="${c.align === "r" ? "r" : c.align === "c" ? "c" : ""} ${c.cls || ""}">${c.render ? c.render(r) : esc(r[c.key] ?? "-")}</td>`).join("")}</tr>`).join("");
    let pg = "";
    if (pages > 1) {
      const nums = []; for (let i = 1; i <= pages; i++) if (i === 1 || i === pages || Math.abs(i - st.page) <= 1) nums.push(i); else if (nums[nums.length - 1] !== "…") nums.push("…");
      pg = `<div class="pager"><button data-pg="${st.page - 1}" ${st.page === 1 ? "disabled" : ""}>${ic("chevron-left", 14)}</button>${nums.map((n) => (n === "…" ? `<button disabled>…</button>` : `<button data-pg="${n}" class="${n === st.page ? "on" : ""}">${n}</button>`)).join("")}<button data-pg="${st.page + 1}" ${st.page === pages ? "disabled" : ""}>${ic("chevron-right", 14)}</button></div>`;
    }
    container.innerHTML = `<div class="tbl-wrap"><table class="tbl"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>
      <div class="tbl-foot"><span>Showing ${(st.page - 1) * st.size + 1}-${Math.min(st.page * st.size, total)} of ${fmt.num(total)}</span>${pg}</div>`;
  }
  container.onclick = (e) => {
    const pg = e.target.closest("[data-pg]"); if (pg) { st.page = +pg.dataset.pg; render(); return; }
    const so = e.target.closest("[data-sort]");
    if (so) { const k = so.dataset.sort; if (st.sortKey === k) st.sortDir = st.sortDir === "asc" ? "desc" : "asc"; else { st.sortKey = k; st.sortDir = "asc"; } render(); return; }
    const act = e.target.closest("[data-act]");
    if (act) { e.stopPropagation(); opts.onAction && opts.onAction(act.dataset.act, st.rows.find((r) => String(r.id) === act.dataset.id), act); return; }
    const tr = e.target.closest("tr.clickable");
    if (tr && opts.rowClick) opts.rowClick(st.rows.find((r) => String(r.id) === tr.dataset.id));
  };
  render();
  return { setRows(r) { st.rows = r; st.page = 1; render(); }, rows: () => st.rows, render };
}
const actBtn = (act, id, icon, title, cls = "") => `<button class="ib ${cls}" data-act="${act}" data-id="${id}" title="${title}">${ic(icon, 15)}</button>`;

/* ---------------------------------------------------------------- page chrome helpers */
const pageHead = (title, sub, actions = "") => `<div class="page-head"><div><h1>${title}</h1>${sub ? `<p>${sub}</p>` : ""}</div><div class="actions">${actions}</div></div>`;
const skeleton = () => `<div class="loading-wrap"><div class="skeleton" style="height:70px"></div><div class="grid g4"><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div></div><div class="skeleton" style="height:300px"></div></div>`;
const emptyState = (icon, title, text) => `<div class="empty">${ic(icon, 44)}<h4>${title}</h4><p>${text || ""}</p></div>`;
function clearTimers() { App.timers.forEach(clearInterval); App.timers = []; }

/* ---------------------------------------------------------------- global range / warehouse filter */
const PRESETS = [["7d", "Last 7 Days"], ["30d", "Last 30 Days"], ["3m", "Last 3 Months"], ["6m", "Last 6 Months"], ["year", "This Year"], ["custom", "Custom Range"]];
function rangeQS() {
  const r = App.range;
  let q = `range=${r.preset}`;
  if (r.preset === "custom") q += `&from=${r.from}&to=${r.to}`;
  if (App.wh && isAdmin()) q += `&warehouse=${App.wh}`;
  return q;
}
function rangeBar(container, onChange, { warehouse = true } = {}) {
  const r = App.range;
  const whOpts = isAdmin() && warehouse ? `<select id="rb-wh" title="Warehouse"><option value="">All warehouses</option>${App.meta.warehouses.map((w) => `<option value="${w.id}" ${String(App.wh) === String(w.id) ? "selected" : ""}>${esc(w.name)}</option>`).join("")}</select>` : "";
  const scope = !isAdmin() ? `<span class="pill tq">${ic("map-pin", 12)} ${esc(App.user.warehouse_name)}</span>` : "";
  container.innerHTML = `<div class="range-bar no-print"><div class="seg" id="rb-seg">${PRESETS.map(([k, l]) => `<button data-p="${k}" class="${r.preset === k ? "on" : ""}">${l}</button>`).join("")}</div>
    <div class="dates" id="rb-dates" ${r.preset === "custom" ? "" : "hidden"}><input type="date" id="rb-from" value="${r.from}" max="${todayISO()}"><span class="muted">to</span><input type="date" id="rb-to" value="${r.to}" max="${todayISO()}"><button class="btn sm primary" id="rb-apply">Apply</button></div>
    ${whOpts}${scope}</div>`;
  $("#rb-seg", container).onclick = (e) => {
    const b = e.target.closest("[data-p]"); if (!b) return;
    r.preset = b.dataset.p;
    if (r.preset === "custom") { if (!r.from) { r.to = todayISO(); r.from = new Date(Date.now() - 29 * 864e5).toISOString().slice(0, 10); } rangeBar(container, onChange, { warehouse }); return; }
    rangeBar(container, onChange, { warehouse }); onChange();
  };
  const ap = $("#rb-apply", container);
  if (ap) ap.onclick = () => {
    const f = $("#rb-from", container).value, t = $("#rb-to", container).value;
    if (!f || !t) return toast("Choose both dates", "warn");
    if (f > t) return toast("Start date must be before the end date", "warn");
    r.from = f; r.to = t; onChange();
  };
  const w = $("#rb-wh", container);
  if (w) w.onchange = () => { App.wh = w.value; onChange(); };
}
