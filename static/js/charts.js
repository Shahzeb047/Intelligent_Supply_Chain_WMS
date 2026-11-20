/* =====================================================================
   charts.js - every chart is built from real data returned by /api/charts
   ===================================================================== */
function chartTheme() {
  const cs = getComputedStyle(document.documentElement);
  Chart.defaults.color = cs.getPropertyValue("--muted").trim();
  Chart.defaults.borderColor = cs.getPropertyValue("--grid").trim();
  Chart.defaults.font.family = 'Inter, "Segoe UI", system-ui, sans-serif';
  Chart.defaults.font.size = 12;
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.boxWidth = 8;
  Chart.defaults.plugins.legend.labels.padding = 14;
  Chart.defaults.plugins.tooltip.backgroundColor = "#14243A";
  Chart.defaults.plugins.tooltip.padding = 11;
  Chart.defaults.plugins.tooltip.cornerRadius = 9;
  Chart.defaults.plugins.tooltip.titleFont = { weight: "700" };
  Chart.defaults.animation.duration = 900;
  Chart.defaults.animation.easing = "easeOutQuart";
  Chart.defaults.maintainAspectRatio = false;
  Chart.defaults.responsive = true;
}
chartTheme();

function mk(id, cfg) {
  const el = document.getElementById(id);
  if (!el) return null;
  if (App.charts[id]) App.charts[id].destroy();
  App.charts[id] = new Chart(el, cfg);
  return App.charts[id];
}
function destroyCharts() { Object.values(App.charts).forEach((c) => c.destroy()); App.charts = {}; }
const hexA = (hex, a) => { const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`; };
function grad(id, color, a1 = .38) {
  const ctx = document.getElementById(id).getContext("2d");
  const g = ctx.createLinearGradient(0, 0, 0, 300);
  g.addColorStop(0, hexA(color, a1)); g.addColorStop(1, hexA(color, 0));
  return g;
}
const TYPE_COLOR = { STOCK_IN: "#119B78", STOCK_OUT: "#3E7CB1", TRANSFER: "#20B8B0", RETURN: "#F29A38", DAMAGED: "#DB5B50" };
const moneyTip = { callbacks: { label: (c) => ` ${c.dataset.label || ""}: ${fmt.money(c.parsed.y ?? c.parsed)}` } };
const yGrid = { beginAtZero: true, border: { display: false } };
const xClean = { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 12 } };
const legendB = { position: "bottom" };

const CH = {
  inventoryValue(id, d) {
    mk(id, { type: "line", data: { labels: d.labels, datasets: [{ label: "Inventory value", data: d.inventory_value, borderColor: "#119B78", backgroundColor: grad(id, "#119B78"), fill: true, tension: .38, borderWidth: 3, pointRadius: 0, pointHoverRadius: 6 }] },
      options: { interaction: { mode: "index", intersect: false }, plugins: { legend: { display: false }, tooltip: moneyTip }, scales: { y: { ...yGrid, beginAtZero: false, ticks: { callback: (v) => "Rs " + fmt.compact(v) } }, x: xClean } } });
  },
  orderVolume(id, d) {
    mk(id, { type: "line", data: { labels: d.labels, datasets: [{ label: "Orders", data: d.order_volume, borderColor: "#F29A38", backgroundColor: grad(id, "#F29A38"), fill: true, tension: .38, borderWidth: 3, pointRadius: 2, pointHoverRadius: 6 }] },
      options: { interaction: { mode: "index", intersect: false }, plugins: { legend: { display: false } }, scales: { y: { ...yGrid, ticks: { precision: 0 } }, x: xClean } } });
  },
  stockByCategory(id, d) {
    mk(id, { type: "doughnut", data: { labels: d.stock_by_category.labels, datasets: [{ data: d.stock_by_category.values, backgroundColor: COLORS, borderWidth: 3, borderColor: getComputedStyle(document.documentElement).getPropertyValue("--card").trim(), hoverOffset: 10 }] },
      options: { cutout: "64%", plugins: { legend: { position: "right", labels: { font: { size: 11.5 } } }, tooltip: { callbacks: { label: (c) => ` ${c.label}: ${fmt.num(c.parsed)} units` } } } } });
  },
  stockByWarehouse(id, d) {
    mk(id, { type: "pie", data: { labels: d.stock_by_warehouse.labels, datasets: [{ data: d.stock_by_warehouse.values, backgroundColor: ["#14243A", "#119B78", "#20B8B0", "#F29A38", "#C9A66B", "#3E7CB1"], borderWidth: 3, borderColor: getComputedStyle(document.documentElement).getPropertyValue("--card").trim(), hoverOffset: 10 }] },
      options: { plugins: { legend: legendB, tooltip: { callbacks: { label: (c) => ` ${c.label}: ${fmt.num(c.parsed)} units` } } } } });
  },
  productsByCategory(id, d) {
    mk(id, { type: "bar", data: { labels: d.products_by_category.labels, datasets: [{ label: "Products", data: d.products_by_category.values, backgroundColor: d.products_by_category.labels.map((_, i) => COLORS[i % 8]), borderRadius: 8, maxBarThickness: 38 }] },
      options: { plugins: { legend: { display: false } }, scales: { y: { ...yGrid, ticks: { precision: 0 } }, x: { grid: { display: false }, ticks: { font: { size: 10.5 } } } } } });
  },
  warehouseCompare(id, d) {
    mk(id, { type: "bar", data: { labels: d.warehouse_compare.labels, datasets: [{ label: "Units in stock", data: d.warehouse_compare.units, backgroundColor: "#119B78", borderRadius: 7, maxBarThickness: 34 }, { label: "Capacity", data: d.warehouse_compare.capacity, backgroundColor: hexA("#14243A", .22), borderRadius: 7, maxBarThickness: 34 }] },
      options: { plugins: { legend: legendB }, scales: { y: { ...yGrid, ticks: { callback: (v) => fmt.compact(v) } }, x: { grid: { display: false } } } } });
  },
  topSelling(id, d) {
    mk(id, { type: "bar", data: { labels: d.top_selling.labels.map((l) => (l.length > 16 ? l.slice(0, 15) + "…" : l)), datasets: [{ label: "Units sold", data: d.top_selling.values, backgroundColor: "#20B8B0", borderRadius: 8, maxBarThickness: 36 }] },
      options: { plugins: { legend: { display: false } }, scales: { y: { ...yGrid, ticks: { precision: 0 } }, x: { grid: { display: false }, ticks: { font: { size: 10 }, maxRotation: 40 } } } } });
  },
  movementLines(id, d) {
    const names = { STOCK_IN: "Stock in", STOCK_OUT: "Stock out", TRANSFER: "Transfer", RETURN: "Return", DAMAGED: "Damaged" };
    mk(id, { type: "line", data: { labels: d.labels, datasets: Object.keys(d.movement_lines).map((k) => ({ label: names[k], data: d.movement_lines[k], borderColor: TYPE_COLOR[k], backgroundColor: TYPE_COLOR[k], tension: .35, borderWidth: 2.5, pointRadius: 0, pointHoverRadius: 5 })) },
      options: { interaction: { mode: "index", intersect: false }, plugins: { legend: legendB }, scales: { y: { ...yGrid, ticks: { precision: 0 } }, x: xClean } } });
  },
  salesTrend(id, d) {
    mk(id, { type: "line", data: { labels: d.labels, datasets: [{ label: "Revenue", data: d.sales_trend, borderColor: "#3E7CB1", backgroundColor: "#3E7CB1", tension: .38, borderWidth: 3, pointRadius: 3, pointBackgroundColor: "#fff", pointBorderWidth: 2 }] },
      options: { interaction: { mode: "index", intersect: false }, plugins: { legend: { display: false }, tooltip: moneyTip }, scales: { y: { ...yGrid, ticks: { callback: (v) => "Rs " + fmt.compact(v) } }, x: xClean } } });
  },
  inOut(id, d) {
    mk(id, { type: "line", data: { labels: d.labels, datasets: [{ label: "Incoming units", data: d.in_out.in, borderColor: "#119B78", backgroundColor: "#119B78", tension: .38, borderWidth: 3, pointRadius: 0, pointHoverRadius: 5 }, { label: "Outgoing units", data: d.in_out.out, borderColor: "#F29A38", backgroundColor: "#F29A38", tension: .38, borderWidth: 3, pointRadius: 0, pointHoverRadius: 5 }] },
      options: { interaction: { mode: "index", intersect: false }, plugins: { legend: legendB }, scales: { y: yGrid, x: xClean } } });
  },
  topQty(id, d) {
    mk(id, { type: "bar", data: { labels: d.top_qty.labels, datasets: [{ label: "Units on hand", data: d.top_qty.values, backgroundColor: d.top_qty.labels.map((_, i) => hexA("#119B78", 1 - i * .07)), borderRadius: 7, barThickness: 16 }] },
      options: { indexAxis: "y", plugins: { legend: { display: false } }, scales: { x: yGrid, y: { grid: { display: false }, ticks: { font: { size: 11 } } } } } });
  },
  bestWarehouses(id, d) {
    mk(id, { type: "bar", data: { labels: d.best_warehouses.labels, datasets: [{ label: "Units dispatched", data: d.best_warehouses.values, backgroundColor: ["#14243A", "#119B78", "#20B8B0", "#F29A38", "#C9A66B"], borderRadius: 8, barThickness: 24 }] },
      options: { indexAxis: "y", plugins: { legend: { display: false } }, scales: { x: yGrid, y: { grid: { display: false } } } } });
  },
  stockStack(id, d) {
    const s = d.stock_stack;
    mk(id, { type: "bar", data: { labels: s.labels, datasets: [{ label: "Available", data: s.available, backgroundColor: "#119B78" }, { label: "Reserved", data: s.reserved, backgroundColor: "#F29A38" }, { label: "Damaged", data: s.damaged, backgroundColor: "#DB5B50", borderRadius: { topLeft: 7, topRight: 7 } }] },
      options: { plugins: { legend: legendB }, scales: { x: { stacked: true, grid: { display: false } }, y: { ...yGrid, stacked: true, ticks: { callback: (v) => fmt.compact(v) } } } } });
  },
  orderStack(id, d) {
    const s = d.order_stack;
    mk(id, { type: "bar", data: { labels: d.labels, datasets: [{ label: "Pending", data: s.pending, backgroundColor: "#F29A38" }, { label: "Processing / shipped", data: s.processing, backgroundColor: "#20B8B0" }, { label: "Delivered", data: s.delivered, backgroundColor: "#119B78" }, { label: "Cancelled / returned", data: s.cancelled_returned, backgroundColor: "#DB5B50", borderRadius: { topLeft: 6, topRight: 6 } }] },
      options: { interaction: { mode: "index", intersect: false }, plugins: { legend: legendB }, scales: { x: { stacked: true, grid: { display: false }, ticks: { maxTicksLimit: 12, maxRotation: 0 } }, y: { ...yGrid, stacked: true, ticks: { precision: 0 } } } } });
  },
  radar(id, d) {
    const cols = ["#119B78", "#F29A38", "#3E7CB1", "#DB5B50", "#8A6FB0"];
    mk(id, { type: "radar", data: { labels: d.radar.axes, datasets: d.radar.warehouses.map((w, i) => ({ label: w.label, data: w.data, borderColor: cols[i % 5], backgroundColor: hexA(cols[i % 5], .12), borderWidth: 2.5, pointRadius: 3 })) },
      options: { scales: { r: { min: 0, max: 100, ticks: { display: false, stepSize: 25 }, grid: { color: Chart.defaults.borderColor }, angleLines: { color: Chart.defaults.borderColor }, pointLabels: { font: { size: 11.5, weight: "600" } } } }, plugins: { legend: legendB, tooltip: { callbacks: { label: (c) => ` ${c.dataset.label}: ${c.parsed.r}%` } } } } });
  },
  polar(id, d) {
    mk(id, { type: "polarArea", data: { labels: d.category_value.labels, datasets: [{ data: d.category_value.values, backgroundColor: COLORS.map((c) => hexA(c, .72)), borderWidth: 0 }] },
      options: { scales: { r: { ticks: { display: false }, grid: { color: Chart.defaults.borderColor } } }, plugins: { legend: { position: "right", labels: { font: { size: 11.5 } } }, tooltip: { callbacks: { label: (c) => ` ${c.label}: ${fmt.money(c.parsed.r)}` } } } } });
  },
  mixed(id, d) {
    mk(id, { type: "bar", data: { labels: d.labels, datasets: [{ type: "line", label: "Revenue", data: d.mixed.revenue, borderColor: "#F29A38", backgroundColor: "#F29A38", yAxisID: "y1", tension: .38, borderWidth: 3, pointRadius: 3, order: 1 }, { label: "Orders", data: d.mixed.orders, backgroundColor: "#119B78", borderRadius: 7, maxBarThickness: 30, order: 2 }] },
      options: { interaction: { mode: "index", intersect: false }, plugins: { legend: legendB, tooltip: { callbacks: { label: (c) => c.dataset.label === "Revenue" ? ` Revenue: ${fmt.money(c.parsed.y)}` : ` Orders: ${c.parsed.y}` } } },
        scales: { y: { ...yGrid, ticks: { precision: 0 }, title: { display: true, text: "Orders" } }, y1: { position: "right", beginAtZero: true, grid: { display: false }, ticks: { callback: (v) => "Rs " + fmt.compact(v) }, title: { display: true, text: "Revenue" } }, x: xClean } } });
  },
  live(id, d) {
    const ch = mk(id, { type: "line", data: { labels: d.labels, datasets: [{ label: "Stock movements", data: d.movements, borderColor: "#119B78", backgroundColor: grad(id, "#119B78", .3), fill: true, tension: .4, borderWidth: 3, pointRadius: 0, pointHoverRadius: 5 }, { label: "New orders", data: d.orders, borderColor: "#F29A38", tension: .4, borderWidth: 2.5, pointRadius: 0, pointHoverRadius: 5 }, { label: "Order status changes", data: d.processing, borderColor: "#3E7CB1", borderDash: [5, 4], tension: .4, borderWidth: 2, pointRadius: 0 }] },
      options: { interaction: { mode: "index", intersect: false }, plugins: { legend: legendB }, scales: { y: { ...yGrid, ticks: { precision: 0 } }, x: { grid: { display: false }, ticks: { maxTicksLimit: 8, maxRotation: 0 } } } } });
    return ch;
  },
};

function sparkSVG(vals, color) {
  if (!vals || vals.length < 2) return "";
  const w = 96, h = 34, mn = Math.min(...vals), mx = Math.max(...vals), rg = mx - mn || 1;
  const pts = vals.map((v, i) => [(i / (vals.length - 1)) * w, h - 4 - ((v - mn) / rg) * (h - 10)]);
  const line = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" ");
  const gid = "sg" + Math.random().toString(36).slice(2, 7);
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${color}" stop-opacity=".32"/><stop offset="1" stop-color="${color}" stop-opacity="0"/></linearGradient></defs>
    <path d="${line} L${w} ${h} L0 ${h}Z" fill="url(#${gid})"/><path d="${line}" fill="none" stroke="${color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}
const chartCard = (id, title, sub = "", cls = "", extra = "") => `<div class="card ${cls}"><div class="card-head"><div><h3>${title}</h3>${sub ? `<small>${sub}</small>` : ""}</div>${extra}</div><div class="chart-box"><canvas id="${id}"></canvas></div></div>`;
