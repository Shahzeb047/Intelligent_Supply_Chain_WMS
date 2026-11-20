/* =====================================================================
   app.js - shell: login, sidebar, router, search, notifications, theme
   ===================================================================== */
const NAV = [
  ["overview", "Overview Dashboard", "home"], ["inventory", "Products & Inventory", "package"], ["warehouses", "Warehouse Management", "database"], ["movements", "Stock Movements", "repeat"],
  ["suppliers", "Supplier Management", "users"], ["purchase", "Purchase Orders", "clipboard"], ["orders", "Customer Orders", "shopping-cart"], ["shipments", "Shipment & Delivery", "truck"],
  ["returns", "Returns Management", "rotate-ccw"], ["alerts", "Low Stock Alerts", "alert-triangle"], ["analytics", "Analytics & Reports", "bar-chart-2"], ["dsa", "DSA Visualization", "cpu"], ["settings", "System Settings", "settings"],
];

/* ------------------------------------------------------------ theme */
function applyThemeIcon() { $("#btn-theme").innerHTML = ic(document.documentElement.dataset.theme === "dark" ? "sun" : "moon", 19); }
function toggleTheme() {
  const t = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem("scwms-theme", t); } catch (e) { }
  chartTheme(); applyThemeIcon(); route();
}

/* ------------------------------------------------------------ login / boot */
function showLogin() {
  clearTimers(); destroyCharts();
  $("#app").hidden = true; $("#login-screen").hidden = false; App.user = null;
}
$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("#lg-btn"), err = $("#login-error");
  err.hidden = true; btn.disabled = true; btn.innerHTML = '<span class="spin"></span>';
  try {
    App.user = await api("/api/auth/login", "POST", { username: $("#lg-user").value, password: $("#lg-pass").value });
    $("#lg-pass").value = "";
    await boot();
  } catch (ex) { err.textContent = ex.message; err.hidden = false; }
  finally { btn.disabled = false; btn.textContent = "Sign in"; }
});
$$(".demo").forEach((b) => (b.onclick = () => { $("#lg-user").value = b.dataset.u; $("#lg-pass").value = b.dataset.p; $("#lg-user").focus(); }));

async function boot() {
  App.meta = await api("/api/meta");
  $("#login-screen").hidden = true; $("#app").hidden = false;
  $("#btn-menu").innerHTML = ic("menu", 19); $("#search-ic").innerHTML = ic("search", 18); $("#btn-bell").insertAdjacentHTML("afterbegin", ic("bell", 19)); applyThemeIcon();
  renderNav(); renderUser(); pollNotifs();
  clearInterval(App.pollT); App.pollT = setInterval(pollNotifs, 30000);
  if (!location.hash || location.hash === "#/") location.hash = "#/overview"; else route();
}
function renderNav() {
  $("#nav").innerHTML = NAV.filter(([k]) => App.user.pages.includes(k)).map(([k, l, i]) => `<a class="nav-item" href="#/${k}" data-p="${k}" title="${l}">${ic(i, 20)}<span class="nav-label">${l}</span>${k === "alerts" ? '<span class="nav-badge" id="nav-alert-badge" hidden>0</span>' : ""}</a>`).join("");
  $("#nav").onclick = () => document.body.classList.remove("drawer");
}
function renderUser() {
  const u = App.user, init = u.full_name.split(" ").map((x) => x[0]).slice(0, 2).join("").toUpperCase();
  $("#btn-user").innerHTML = `<span class="avatar">${esc(init)}</span><span class="user-meta"><b>${esc(u.full_name.split(" (")[0])}</b><small>${fmt.title(u.role)}</small></span>${ic("chevron-down", 15)}`;
  $("#user-dd").innerHTML = `<div class="u-head"><b>${esc(u.full_name)}</b><br><small class="muted">${esc(u.email || u.username)}</small><br><span class="pill tq" style="margin-top:8px">${ic("map-pin", 12)} ${esc(u.warehouse_name)}</span></div>
    <button class="u-item" data-go="settings">${ic("user", 17)} Profile &amp; settings</button><button class="u-item" data-th>${ic("moon", 17)} Light / dark mode</button><button class="u-item" data-out style="color:var(--red)">${ic("log-out", 17)} Sign out</button>`;
}

/* ------------------------------------------------------------ router */
async function route() {
  if (!App.user) return;
  const parts = location.hash.replace(/^#\/?/, "").split("/"), page = parts[0] || "overview", arg = parts[1];
  if (!App.user.pages.includes(page) || !Pages[page]) { toast("You do not have access to that page", "warn"); location.hash = "#/overview"; return; }
  clearTimers(); destroyCharts(); dsStopSafe();
  App.page = page;
  $$(".nav-item").forEach((a) => a.classList.toggle("active", a.dataset.p === page));
  const view = $("#view"); view.style.animation = "none"; void view.offsetWidth; view.style.animation = ""; view.innerHTML = skeleton();
  try { await Pages[page].render(view, arg); } catch (e) { view.innerHTML = emptyState("alert-circle", "Something went wrong", esc(e.message)); }
  window.scrollTo({ top: 0 });
}
function dsStopSafe() { try { dsStop(); } catch (e) { } }
window.addEventListener("hashchange", route);

/* ------------------------------------------------------------ topbar widgets */
const closeDDs = () => { $("#notif-dd").hidden = true; $("#user-dd").hidden = true; };
$("#btn-menu").onclick = () => { if (innerWidth <= 900) document.body.classList.toggle("drawer"); else { document.body.classList.toggle("collapsed"); try { localStorage.setItem("scwms-collapsed", document.body.classList.contains("collapsed") ? "1" : ""); } catch (e) { } } };
$("#scrim").onclick = () => document.body.classList.remove("drawer");
$("#btn-theme").onclick = toggleTheme;
try { if (localStorage.getItem("scwms-collapsed")) document.body.classList.add("collapsed"); } catch (e) { }
$("#btn-user").onclick = (e) => { e.stopPropagation(); const h = $("#user-dd").hidden; closeDDs(); $("#user-dd").hidden = !h; };
$("#user-dd").onclick = async (e) => {
  if (e.target.closest("[data-go]")) { location.hash = "#/settings"; closeDDs(); }
  if (e.target.closest("[data-th]")) { closeDDs(); toggleTheme(); }
  if (e.target.closest("[data-out]")) { closeDDs(); await api("/api/auth/logout", "POST"); clearInterval(App.pollT); showLogin(); location.hash = ""; toast("You have been signed out", "info"); }
};
document.addEventListener("click", (e) => { if (!e.target.closest(".dd-wrap")) closeDDs(); if (!e.target.closest(".search-wrap")) $("#search-drop").hidden = true; });

async function pollNotifs() {
  if (!App.user) return;
  try {
    const d = await api("/api/notifications"); App.notifs = d;
    const b = $("#bell-badge"); b.hidden = !d.unread; b.textContent = d.unread > 99 ? "99+" : d.unread;
    const nb = $("#nav-alert-badge"); if (nb) { nb.hidden = !d.unread; nb.textContent = d.unread; }
  } catch (e) { }
}
$("#btn-bell").onclick = async (e) => {
  e.stopPropagation(); const wasHidden = $("#notif-dd").hidden; closeDDs(); if (!wasHidden) return;
  await pollNotifs(); const d = App.notifs || { items: [], unread: 0 };
  $("#notif-dd").innerHTML = `<div class="dd-head"><div><b>Notifications</b> <span class="pill red">${d.unread} new</span></div><button class="btn sm ghost" id="dd-read">Mark all read</button></div>
    <div class="dd-list">${d.items.length ? d.items.slice(0, 9).map((n) => notifItem(n, true)).join("") : emptyState("bell", "No notifications", "")}</div><div class="dd-foot"><a href="#/alerts" id="dd-all">View all notifications</a></div>`;
  $("#notif-dd").hidden = false;
  $("#dd-read").onclick = async (ev) => { ev.stopPropagation(); await api("/api/notifications/read", "POST", { all: true }); await pollNotifs(); closeDDs(); toast("All notifications marked as read"); if (App.page === "alerts") route(); };
  $("#dd-all").onclick = closeDDs;
  $$("#notif-dd [data-n]").forEach((n) => (n.onclick = async () => { await api("/api/notifications/read", "POST", { id: +n.dataset.n }); pollNotifs(); closeDDs(); const p = NOTIF_PAGE[n.dataset.link]; if (p && App.user.pages.includes(p)) location.hash = "#/" + p; }));
};

/* ------------------------------------------------------------ global search */
const doSearch = debounce(async () => {
  const q = $("#global-search").value.trim(), dd = $("#search-drop");
  if (q.length < 2) { dd.hidden = true; return; }
  try {
    const { results } = await api("/api/search?q=" + encodeURIComponent(q));
    dd.innerHTML = results.length ? results.map((r, i) => `<div class="sr-item" data-i="${i}"><span class="sr-type">${r.type}</span><div><b>${esc(r.title)}</b><small>${esc(r.sub)}</small></div></div>`).join("") : `<div class="empty" style="padding:22px">No results for "${esc(q)}"</div>`;
    dd.hidden = false;
    $$(".sr-item", dd).forEach((it) => (it.onclick = () => {
      const r = results[+it.dataset.i]; dd.hidden = true; $("#global-search").value = "";
      if (r.type === "Product") productDetail(r.id); else if (r.type === "Order") location.hash = "#/orders/" + r.id; else if (r.type === "Shipment") { location.hash = "#/shipments"; setTimeout(() => shipDetail(r.id), 350); } else location.hash = "#/" + r.page;
    }));
  } catch (e) { }
}, 250);
$("#global-search").addEventListener("input", doSearch);
$("#global-search").addEventListener("focus", doSearch);
$("#global-search").addEventListener("keydown", (e) => { if (e.key === "Escape") $("#search-drop").hidden = true; });

/* ------------------------------------------------------------ start */
(async function init() {
  try { App.user = await api("/api/auth/me"); await boot(); }
  catch (e) { showLogin(); }
})();
