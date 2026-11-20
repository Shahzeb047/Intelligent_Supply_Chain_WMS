"""backend/routes_insights.py - dashboard KPIs, chart data, live activity, reports/exports, DSA + algorithm APIs."""
import csv
import io
import random
import time
from bisect import bisect_right
from datetime import date, datetime, timedelta

from flask import Response, jsonify, request

from ds import algorithms as algo
from ds.queue import Queue
from . import services
from .core import (ApiError, QUEUES, body, can, current_user, date_range, db, day_s, dispatch_q, inventory_q, lock, log_activity,
                   now_s, one, order_q, require, rows, scalar, scope_wh, today_s, wh_filter)


# ================================================================== helpers
def make_buckets(f, t):
    days = (t - f).days + 1
    out, d = [], f
    if days <= 31:
        while d <= t:
            out.append((d.strftime("%d %b"), d, d))
            d += timedelta(days=1)
    elif days <= 100:
        while d <= t:
            e = min(d + timedelta(days=6), t)
            out.append((d.strftime("%d %b"), d, e))
            d = e + timedelta(days=1)
    else:
        while d <= t:
            nm = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
            e = min(nm - timedelta(days=1), t)
            out.append((d.strftime("%b %y"), d, e))
            d = e + timedelta(days=1)
    starts = [day_s(b[1]) for b in out]
    ends = [day_s(b[2]) for b in out]

    def idx(ds):
        i = bisect_right(starts, ds) - 1
        return i if 0 <= i < len(out) and ds <= ends[i] else None
    return out, idx


def net_delta(m, wid):
    """Change of on-hand units caused by a movement (for the selected scope)."""
    q, typ = m["quantity"], m["type"]
    if typ == "DAMAGED" and str(m["reference"] or "").startswith("RET-"):
        return 0                                    # damaged return never entered on-hand stock
    if wid is None:
        return q if typ in ("STOCK_IN", "RETURN") else (-q if typ in ("STOCK_OUT", "DAMAGED") else 0)
    d = 0
    if m["dest_wh"] == wid and typ in ("STOCK_IN", "RETURN", "TRANSFER"):
        d += q
    if m["source_wh"] == wid and typ in ("STOCK_OUT", "DAMAGED", "TRANSFER"):
        d -= q
    return d


def wh_sql(wid, cols):
    if not wid:
        return "", ()
    return " AND (" + " OR ".join(f"{c}=?" for c in cols) + ")", (wid,) * len(cols)


def current_stock(wid):
    a = rows(f"""SELECT SUM(s.quantity) u, SUM(s.quantity*p.purchase_price) v FROM stock s JOIN products p ON p.id=s.product_id
                 {'WHERE s.warehouse_id=?' if wid else ''}""", (wid,) if wid else ())[0]
    return a["u"] or 0, a["v"] or 0


def level_series(wid, buckets_end_dates, since):
    """Units/value at each given end date, reconstructed from movements."""
    mv = rows(f"""SELECT m.quantity,m.type,m.source_wh,m.dest_wh,m.reference,substr(m.ts,1,10) d, p.purchase_price cost FROM movements m
                  LEFT JOIN products p ON p.id=m.product_id WHERE substr(m.ts,1,10)>? {wh_sql(wid, ('m.source_wh', 'm.dest_wh'))[0]} ORDER BY m.ts""",
              (since,) + wh_sql(wid, ("m.source_wh", "m.dest_wh"))[1])
    u_now, v_now = current_stock(wid)
    res = []
    for e in buckets_end_dates:
        du = sum(net_delta(m, wid) for m in mv if m["d"] > e)
        dv = sum(net_delta(m, wid) * (m["cost"] or 0) for m in mv if m["d"] > e)
        res.append((u_now - du, v_now - dv))
    return res


def pct(cur, prev):
    if not prev:
        return None
    return round((cur - prev) * 100 / prev, 1)


def grp(status):
    return {"PENDING": 0, "CONFIRMED": 0, "PROCESSING": 1, "PACKED": 1, "DISPATCHED": 1, "DELIVERED": 2}.get(status, 3)


# ================================================================== dashboard KPIs
def kpis(f, t, wid):
    n = (t - f).days + 1
    pf, pt = f - timedelta(days=n), f - timedelta(days=1)
    ow, oa = wh_sql(wid, ("o.warehouse_id",))
    u_now, v_now = current_stock(wid)
    lv = level_series(wid, [day_s(t), day_s(pf - timedelta(days=0)) if False else day_s(f - timedelta(days=1))], day_s(pf - timedelta(days=1)))
    (u_end, v_end), (u_prev, v_prev) = lv[0], lv[1]
    placed = lambda a, b: scalar(f"SELECT COUNT(*) FROM orders o WHERE substr(o.created_at,1,10) BETWEEN ? AND ? AND o.status!='CANCELLED' {ow}", (day_s(a), day_s(b)) + oa)
    delivered = lambda a, b: scalar(f"""SELECT COUNT(*) FROM order_history h JOIN orders o ON o.id=h.order_id WHERE h.status='DELIVERED'
                                        AND substr(h.ts,1,10) BETWEEN ? AND ? {ow}""", (day_s(a), day_s(b)) + oa)
    open_orders = scalar(f"SELECT COUNT(*) FROM orders o WHERE o.status IN ('PENDING','CONFIRMED','PROCESSING','PACKED') {ow}", oa)
    prods = services.product_rows(wid)
    low = sum(1 for p in prods if p["status"] in ("LOW", "OUT"))
    B, idx = make_buckets(f, t)
    sp_o, sp_d = [0] * len(B), [0] * len(B)
    for r in rows(f"SELECT substr(o.created_at,1,10) d, COUNT(*) c FROM orders o WHERE substr(o.created_at,1,10) BETWEEN ? AND ? AND o.status!='CANCELLED' {ow} GROUP BY d", (day_s(f), day_s(t)) + oa):
        i = idx(r["d"])
        if i is not None:
            sp_o[i] += r["c"]
    for r in rows(f"SELECT substr(h.ts,1,10) d, COUNT(*) c FROM order_history h JOIN orders o ON o.id=h.order_id WHERE h.status='DELIVERED' AND substr(h.ts,1,10) BETWEEN ? AND ? {ow} GROUP BY d", (day_s(f), day_s(t)) + oa):
        i = idx(r["d"])
        if i is not None:
            sp_d[i] += r["c"]
    lvl = level_series(wid, [day_s(b[2]) for b in B], day_s(f - timedelta(days=1)))
    wcount = scalar("SELECT COUNT(*) FROM warehouses" + (" WHERE id=?" if wid else ""), (wid,) if wid else ())
    return [
        {"key": "products", "label": "Total Products", "value": len(prods), "fmt": "num", "icon": "package", "color": "emerald", "change": None, "spark": None, "note": "in inventory queue"},
        {"key": "warehouses", "label": "Total Warehouses", "value": wcount, "fmt": "num", "icon": "home", "color": "navy", "change": None, "spark": None, "note": "active locations"},
        {"key": "units", "label": "Total Stock Units", "value": u_now, "fmt": "num", "icon": "layers", "color": "turquoise", "change": pct(u_end, u_prev), "spark": [x[0] for x in lvl], "note": "vs previous period"},
        {"key": "value", "label": "Inventory Value", "value": v_now, "fmt": "money", "icon": "dollar-sign", "color": "orange", "change": pct(v_end, v_prev), "spark": [x[1] for x in lvl], "note": "at purchase cost"},
        {"key": "pending", "label": "Pending Orders", "value": open_orders, "fmt": "num", "icon": "clock", "color": "orange", "change": pct(placed(f, t), placed(pf, pt)), "spark": sp_o, "note": "orders placed vs previous"},
        {"key": "delivered", "label": "Delivered Orders", "value": delivered(f, t), "fmt": "num", "icon": "check-circle", "color": "emerald", "change": pct(delivered(f, t), delivered(pf, pt)), "spark": sp_d, "note": "in selected period"},
        {"key": "low", "label": "Low Stock Products", "value": low, "fmt": "num", "icon": "alert-triangle", "color": "red", "change": None, "spark": None, "note": "at or below reorder level"},
        {"key": "suppliers", "label": "Active Suppliers", "value": scalar("SELECT COUNT(*) FROM suppliers WHERE status='Active'"), "fmt": "num", "icon": "truck", "color": "turquoise", "change": None, "spark": None, "note": "trading partners"},
    ]


def register(app):
    @app.get("/api/dashboard")
    @require()
    def dashboard():
        f, t = date_range()
        wid = wh_filter(request.args.get("warehouse"))
        prods = services.product_rows(wid)
        alerts = sorted([p for p in prods if p["status"] != "OK"], key=lambda p: p["available"] / max(p["reorder_level"], 1))[:6]
        ow, oa = wh_sql(wid, ("o.warehouse_id",))
        recent_orders = rows(f"SELECT o.id,o.order_no,o.customer_name,o.status,o.total,o.created_at FROM orders o WHERE 1=1 {ow} ORDER BY o.id DESC LIMIT 6", oa)
        mw, ma = wh_sql(wid, ("m.source_wh", "m.dest_wh"))
        recent_mv = rows(f"""SELECT m.txn_id,m.type,m.quantity,m.ts,COALESCE(p.name,'') product_name FROM movements m LEFT JOIN products p ON p.id=m.product_id
                             WHERE 1=1 {mw} ORDER BY m.id DESC LIMIT 6""", ma)
        return jsonify({"kpis": kpis(f, t, wid), "alerts": [{"id": p["id"], "name": p["name"], "code": p["code"], "available": p["available"],
                                                              "reorder_level": p["reorder_level"], "status": p["status"], "category": p["category"]} for p in alerts],
                        "recent_orders": recent_orders, "recent_movements": recent_mv,
                        "queues": {k: q.size() for k, q in QUEUES.items()}, "range": [day_s(f), day_s(t)]})

    # ================================================================== charts
    @app.get("/api/charts")
    @require()
    def charts():
        f, t = date_range()
        wid = wh_filter(request.args.get("warehouse"))
        B, idx = make_buckets(f, t)
        labels, n = [b[0] for b in B], len(B)
        zeros = lambda: [0] * n
        fs, ts_ = day_s(f), day_s(t)
        mw, ma = wh_sql(wid, ("m.source_wh", "m.dest_wh"))
        ow, oa = wh_sql(wid, ("o.warehouse_id",))
        sw = "AND s.warehouse_id=?" if wid else ""
        sa = (wid,) if wid else ()

        # --- movements in range
        types = ["STOCK_IN", "STOCK_OUT", "TRANSFER", "RETURN", "DAMAGED"]
        cnt = {k: zeros() for k in types}
        inu, outu = zeros(), zeros()
        for m in rows(f"SELECT m.type,m.quantity,m.source_wh,m.dest_wh,m.reference,substr(m.ts,1,10) d FROM movements m WHERE substr(m.ts,1,10) BETWEEN ? AND ? {mw}", (fs, ts_) + ma):
            i = idx(m["d"])
            if i is None:
                continue
            cnt[m["type"]][i] += 1
            dl = net_delta(m, wid) if wid else None
            if m["type"] in ("STOCK_IN", "RETURN"):
                inu[i] += m["quantity"]
            elif m["type"] in ("STOCK_OUT",) or (m["type"] == "DAMAGED" and not str(m["reference"] or "").startswith("RET-")):
                outu[i] += m["quantity"]
        # --- orders in range
        orders_n, revenue, stack = zeros(), zeros(), [zeros() for _ in range(4)]
        for o in rows(f"SELECT o.status,o.total,substr(o.created_at,1,10) d FROM orders o WHERE substr(o.created_at,1,10) BETWEEN ? AND ? {ow}", (fs, ts_) + oa):
            i = idx(o["d"])
            if i is None:
                continue
            stack[grp(o["status"])][i] += 1
            if o["status"] != "CANCELLED":
                orders_n[i] += 1
                revenue[i] += o["total"]
        revenue = [round(x) for x in revenue]
        # --- inventory value area
        lvl = level_series(wid, [day_s(b[2]) for b in B], day_s(f - timedelta(days=1)))
        # --- current stock distributions
        prods = services.product_rows(wid)
        cat_u, cat_v, cat_n = {}, {}, {}
        for p in prods:
            cat_u[p["category"]] = cat_u.get(p["category"], 0) + p["on_hand"]
            cat_v[p["category"]] = cat_v.get(p["category"], 0) + p["on_hand"] * p["purchase_price"]
            cat_n[p["category"]] = cat_n.get(p["category"], 0) + 1
        whs = rows("SELECT id,name,capacity FROM warehouses" + (" WHERE id=?" if wid else "") + " ORDER BY id", (wid,) if wid else ())
        agg = {r["warehouse_id"]: r for r in rows("SELECT warehouse_id, SUM(quantity) q, SUM(reserved) r, SUM(damaged) d FROM stock GROUP BY warehouse_id")}
        short = lambda s: s.replace(" Distribution Hub", "").replace(" Regional Depot", "").replace(" Central DC", "").replace(" North Warehouse", "").replace(" Pharma & Cold Store", "")
        wl = [short(w["name"]) for w in whs]
        # --- top selling in range
        top_sell = rows(f"""SELECT COALESCE(p.name,'(deleted)') name, SUM(i.quantity) q FROM order_items i JOIN orders o ON o.id=i.order_id LEFT JOIN products p ON p.id=i.product_id
                            WHERE o.status!='CANCELLED' AND substr(o.created_at,1,10) BETWEEN ? AND ? {ow} GROUP BY i.product_id ORDER BY q DESC LIMIT 8""", (fs, ts_) + oa)
        top_qty = sorted(prods, key=lambda p: p["on_hand"], reverse=True)[:10]
        # --- warehouse performance (radar + best warehouses)
        ship = {r["warehouse_id"]: r["q"] for r in rows(f"""SELECT m.source_wh warehouse_id, SUM(m.quantity) q FROM movements m WHERE m.type='STOCK_OUT'
                                                           AND substr(m.ts,1,10) BETWEEN ? AND ? GROUP BY m.source_wh""", (fs, ts_))}
        dl = {r["origin_wh"]: r for r in rows("""SELECT origin_wh, COUNT(*) c, SUM(CASE WHEN delivered_date<=expected_date THEN 1 ELSE 0 END) ok FROM shipments
                                                  WHERE status='DELIVERED' AND delivered_date BETWEEN ? AND ? GROUP BY origin_wh""", (fs, ts_))}
        max_units = max([(agg.get(w["id"]) or {"q": 0})["q"] or 0 for w in whs] + [1])
        max_ship = max([ship.get(w["id"], 0) for w in whs] + [1])
        radar = []
        for w, lab in zip(whs, wl):
            a = agg.get(w["id"], {"q": 0, "d": 0})
            occ = (a["q"] or 0) + (a["d"] or 0)
            d_ = dl.get(w["id"])
            radar.append({"label": lab, "data": [round((a["q"] or 0) * 100 / max_units), round(max(0, 100 - occ * 100 / w["capacity"])) if w["capacity"] else 0,
                                                  round(ship.get(w["id"], 0) * 100 / max_ship), round(d_["ok"] * 100 / d_["c"]) if d_ and d_["c"] else 0]})
        out = {
            "labels": labels,
            "granularity": "day" if (t - f).days + 1 <= 31 else ("week" if (t - f).days + 1 <= 100 else "month"),
            "stock_by_category": {"labels": list(cat_u), "values": list(cat_u.values())},
            "stock_by_warehouse": {"labels": wl, "values": [(agg.get(w["id"]) or {"q": 0})["q"] or 0 for w in whs]},
            "products_by_category": {"labels": list(cat_n), "values": list(cat_n.values())},
            "warehouse_compare": {"labels": wl, "units": [(agg.get(w["id"]) or {"q": 0})["q"] or 0 for w in whs], "capacity": [w["capacity"] for w in whs]},
            "top_selling": {"labels": [x["name"] for x in top_sell], "values": [x["q"] for x in top_sell]},
            "movement_lines": {t_: cnt[t_] for t_ in types},
            "sales_trend": revenue,
            "in_out": {"in": inu, "out": outu},
            "inventory_value": [round(x[1]) for x in lvl],
            "order_volume": orders_n,
            "top_qty": {"labels": [p["name"] for p in top_qty], "values": [p["on_hand"] for p in top_qty]},
            "best_warehouses": {"labels": wl, "values": [ship.get(w["id"], 0) for w in whs]},
            "stock_stack": {"labels": wl, "available": [((agg.get(w["id"]) or {"q": 0, "r": 0})["q"] or 0) - ((agg.get(w["id"]) or {"r": 0})["r"] or 0) for w in whs],
                            "reserved": [(agg.get(w["id"]) or {"r": 0})["r"] or 0 for w in whs], "damaged": [(agg.get(w["id"]) or {"d": 0})["d"] or 0 for w in whs]},
            "order_stack": {"pending": stack[0], "processing": stack[1], "delivered": stack[2], "cancelled_returned": stack[3]},
            "radar": {"axes": ["Stock level", "Free capacity", "Dispatch volume", "On-time delivery"], "warehouses": radar},
            "category_value": {"labels": list(cat_v), "values": [round(v) for v in cat_v.values()]},
            "mixed": {"orders": orders_n, "revenue": revenue},
        }
        return jsonify(out)

    @app.get("/api/live")
    @require()
    def live():
        wid = wh_filter(request.args.get("warehouse"))
        now = datetime.now()
        hours = [(now - timedelta(hours=i)).strftime("%Y-%m-%d %H") for i in range(23, -1, -1)]
        mw, ma = wh_sql(wid, ("m.source_wh", "m.dest_wh"))
        ow, oa = wh_sql(wid, ("o.warehouse_id",))
        since = (now - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        mv = {r["h"]: r["c"] for r in rows(f"SELECT substr(m.ts,1,13) h, COUNT(*) c FROM movements m WHERE m.ts>=? {mw} GROUP BY h", (since,) + ma)}
        od = {r["h"]: r["c"] for r in rows(f"SELECT substr(o.created_at,1,13) h, COUNT(*) c FROM orders o WHERE o.created_at>=? {ow} GROUP BY h", (since,) + oa)}
        hp = {r["h"]: r["c"] for r in rows("SELECT substr(h.ts,1,13) h, COUNT(*) c FROM order_history h WHERE h.ts>=? GROUP BY h", (since,))}
        events = rows(f"""SELECT m.ts, m.type, m.quantity, m.txn_id, COALESCE(p.name,'') name FROM movements m LEFT JOIN products p ON p.id=m.product_id
                          WHERE 1=1 {mw} ORDER BY m.id DESC LIMIT 8""", ma)
        return jsonify({"labels": [h[11:] + ":00" for h in hours], "movements": [mv.get(h, 0) for h in hours], "orders": [od.get(h, 0) for h in hours],
                        "processing": [hp.get(h, 0) for h in hours], "events": events, "server_time": now.strftime("%H:%M:%S")})

    # ================================================================== reports
    def build_report(key, f, t, wid):
        fs, ts_ = day_s(f), day_s(t)
        ow, oa = wh_sql(wid, ("o.warehouse_id",))
        mw, ma = wh_sql(wid, ("m.source_wh", "m.dest_wh"))
        money = lambda v: round(v or 0, 2)
        prods = services.product_rows(wid)
        if key == "valuation":
            data = [[p["code"], p["name"], p["category"], p["on_hand"], p["purchase_price"], p["on_hand"] * p["purchase_price"], p["selling_price"], p["on_hand"] * p["selling_price"]] for p in prods]
            tot_c, tot_r = sum(r[5] for r in data), sum(r[7] for r in data)
            cats = {}
            for r in data:
                cats[r[2]] = cats.get(r[2], 0) + r[5]
            return dict(title="Inventory Valuation Report", summary=[("Units on hand", sum(r[3] for r in data), "num"), ("Value at cost", tot_c, "money"),
                        ("Value at selling price", tot_r, "money"), ("Potential margin", tot_r - tot_c, "money")],
                        columns=[("Code", "text"), ("Product", "text"), ("Category", "text"), ("On hand", "num"), ("Unit cost", "money"), ("Value at cost", "money"), ("Sell price", "money"), ("Retail value", "money")],
                        rows=data, chart={"type": "bar", "title": "Value at cost by category", "labels": list(cats), "values": [round(v) for v in cats.values()]})
        if key == "movements":
            data = rows(f"""SELECT m.txn_id, m.ts, m.type, COALESCE(p.name,'') name, m.quantity, ws.name s, wd.name d, m.employee, m.reference FROM movements m LEFT JOIN products p ON p.id=m.product_id
                            LEFT JOIN warehouses ws ON ws.id=m.source_wh LEFT JOIN warehouses wd ON wd.id=m.dest_wh WHERE substr(m.ts,1,10) BETWEEN ? AND ? {mw} ORDER BY m.id DESC LIMIT 1500""", (fs, ts_) + ma)
            by = {}
            for m in data:
                by[m["type"]] = by.get(m["type"], 0) + m["quantity"]
            return dict(title="Stock Movement Report", summary=[("Transactions", len(data), "num")] + [(k.replace("_", " ").title() + " units", v, "num") for k, v in by.items()],
                        columns=[("Transaction", "text"), ("Date & time", "text"), ("Type", "text"), ("Product", "text"), ("Qty", "num"), ("From", "text"), ("To", "text"), ("Employee", "text"), ("Reference", "text")],
                        rows=[[m["txn_id"], m["ts"], m["type"].replace("_", " ").title(), m["name"], m["quantity"], m["s"] or "-", m["d"] or "-", m["employee"], m["reference"] or ""] for m in data],
                        chart={"type": "doughnut", "title": "Units by movement type", "labels": [k.replace("_", " ").title() for k in by], "values": list(by.values())})
        if key == "warehouse":
            whs = rows("SELECT * FROM warehouses" + (" WHERE id=?" if wid else "") + " ORDER BY id", (wid,) if wid else ())
            data = []
            for w in whs:
                a = one("SELECT COALESCE(SUM(quantity),0) q, COALESCE(SUM(damaged),0) d FROM stock WHERE warehouse_id=?", (w["id"],))
                shipped = scalar("SELECT COALESCE(SUM(quantity),0) FROM movements WHERE type='STOCK_OUT' AND source_wh=? AND substr(ts,1,10) BETWEEN ? AND ?", (w["id"], fs, ts_))
                sh = one("SELECT COUNT(*) c, SUM(CASE WHEN delivered_date<=expected_date THEN 1 ELSE 0 END) ok FROM shipments WHERE origin_wh=? AND status='DELIVERED' AND delivered_date BETWEEN ? AND ?", (w["id"], fs, ts_))
                data.append([w["code"], w["name"], w["status"], w["capacity"], a["q"] + a["d"], round((a["q"] + a["d"]) * 100 / w["capacity"], 1) if w["capacity"] else 0, shipped,
                             sh["c"], round((sh["ok"] or 0) * 100 / sh["c"], 1) if sh["c"] else 0, a["d"]])
            return dict(title="Warehouse Performance Report", summary=[("Warehouses", len(data), "num"), ("Units stored", sum(r[4] for r in data), "num"), ("Units dispatched", sum(r[6] for r in data), "num"), ("Damaged units", sum(r[9] for r in data), "num")],
                        columns=[("Code", "text"), ("Warehouse", "text"), ("Status", "text"), ("Capacity", "num"), ("Occupied", "num"), ("Used %", "pct"), ("Dispatched units", "num"), ("Deliveries", "num"), ("On-time %", "pct"), ("Damaged", "num")],
                        rows=data, chart={"type": "bar", "title": "Capacity utilisation %", "labels": [r[1] for r in data], "values": [r[5] for r in data]})
        if key == "suppliers":
            data = []
            for s in rows("SELECT * FROM suppliers ORDER BY id"):
                a = one("""SELECT COUNT(*) n, SUM(CASE WHEN status='COMPLETED' THEN 1 ELSE 0 END) done, SUM(CASE WHEN status='COMPLETED' AND received_date<=expected_date THEN 1 ELSE 0 END) ok,
                           SUM(CASE WHEN status IN ('PENDING','APPROVED','PARTIALLY_RECEIVED') THEN 1 ELSE 0 END) open FROM purchase_orders WHERE supplier_id=? AND substr(created_at,1,10) BETWEEN ? AND ?""", (s["id"], fs, ts_))
                spend = scalar("""SELECT COALESCE(SUM(i.quantity*i.unit_cost),0) FROM po_items i JOIN purchase_orders po ON po.id=i.po_id WHERE po.supplier_id=? AND po.status!='CANCELLED' AND substr(po.created_at,1,10) BETWEEN ? AND ?""", (s["id"], fs, ts_))
                lead = scalar("SELECT AVG(julianday(received_date)-julianday(substr(created_at,1,10))) FROM purchase_orders WHERE supplier_id=? AND status='COMPLETED' AND substr(created_at,1,10) BETWEEN ? AND ?", (s["id"], fs, ts_), None)
                data.append([s["code"], s["name"], s["status"], a["n"], a["done"] or 0, a["open"] or 0, round((a["ok"] or 0) * 100 / a["done"], 1) if a["done"] else 0, round(lead, 1) if lead is not None else 0, spend])
            return dict(title="Supplier Performance Report", summary=[("Suppliers", len(data), "num"), ("Purchase orders", sum(r[3] for r in data), "num"), ("Total spend", sum(r[8] for r in data), "money")],
                        columns=[("Code", "text"), ("Supplier", "text"), ("Status", "text"), ("POs", "num"), ("Completed", "num"), ("Open", "num"), ("On-time %", "pct"), ("Avg lead days", "num"), ("Spend", "money")],
                        rows=data, chart={"type": "bar", "title": "Spend by supplier", "labels": [r[1] for r in data if r[8]], "values": [round(r[8]) for r in data if r[8]]})
        if key == "purchases":
            pw, pa = wh_sql(wid, ("po.warehouse_id",))
            data = rows(f"""SELECT po.po_no, s.name sup, w.name wh, po.status, po.created_at, po.expected_date, po.received_date,
                            (SELECT COALESCE(SUM(quantity),0) FROM po_items WHERE po_id=po.id) units, (SELECT COALESCE(SUM(quantity*unit_cost),0) FROM po_items WHERE po_id=po.id) total
                            FROM purchase_orders po LEFT JOIN suppliers s ON s.id=po.supplier_id LEFT JOIN warehouses w ON w.id=po.warehouse_id
                            WHERE substr(po.created_at,1,10) BETWEEN ? AND ? {pw} ORDER BY po.id DESC LIMIT 1500""", (fs, ts_) + pa)
            st = {}
            for r in data:
                st[r["status"]] = st.get(r["status"], 0) + 1
            return dict(title="Purchase Report", summary=[("Purchase orders", len(data), "num"), ("Units ordered", sum(r["units"] for r in data), "num"), ("Total value", sum(r["total"] for r in data if r["status"] != "CANCELLED"), "money")],
                        columns=[("PO", "text"), ("Supplier", "text"), ("Warehouse", "text"), ("Status", "text"), ("Created", "date"), ("Expected", "date"), ("Received", "date"), ("Units", "num"), ("Value", "money")],
                        rows=[[r["po_no"], r["sup"], r["wh"], r["status"].replace("_", " ").title(), r["created_at"][:10], r["expected_date"] or "-", r["received_date"] or "-", r["units"], r["total"]] for r in data],
                        chart={"type": "doughnut", "title": "Purchase orders by status", "labels": [k.replace("_", " ").title() for k in st], "values": list(st.values())})
        if key == "sales":
            data = rows(f"""SELECT o.order_no, o.customer_name, w.name wh, o.status, substr(o.created_at,1,10) d, o.discount_pct, o.total,
                            (SELECT COALESCE(SUM(quantity),0) FROM order_items WHERE order_id=o.id) units FROM orders o LEFT JOIN warehouses w ON w.id=o.warehouse_id
                            WHERE o.status!='CANCELLED' AND substr(o.created_at,1,10) BETWEEN ? AND ? {ow} ORDER BY o.id DESC LIMIT 2000""", (fs, ts_) + oa)
            B, idx = make_buckets(f, t)
            ser = [0] * len(B)
            for r in data:
                i = idx(r["d"])
                if i is not None:
                    ser[i] += r["total"]
            rev = sum(r["total"] for r in data)
            return dict(title="Sales Report", summary=[("Orders", len(data), "num"), ("Revenue", rev, "money"), ("Average order", rev / len(data) if data else 0, "money"), ("Units sold", sum(r["units"] for r in data), "num")],
                        columns=[("Order", "text"), ("Customer", "text"), ("Warehouse", "text"), ("Status", "text"), ("Date", "date"), ("Discount %", "pct"), ("Units", "num"), ("Total", "money")],
                        rows=[[r["order_no"], r["customer_name"], r["wh"], r["status"].title(), r["d"], r["discount_pct"], r["units"], r["total"]] for r in data],
                        chart={"type": "line", "title": "Revenue over time", "labels": [b[0] for b in B], "values": [round(x) for x in ser]})
        if key == "fulfillment":
            data = rows(f"""SELECT o.order_no, o.customer_name, o.created_at, s.dispatch_date, s.delivered_date, s.expected_date FROM orders o JOIN shipments s ON s.order_id=o.id
                            WHERE s.status='DELIVERED' AND s.delivered_date BETWEEN ? AND ? {ow} ORDER BY s.delivered_date DESC LIMIT 1500""", (fs, ts_) + oa)
            ok = sum(1 for r in data if r["delivered_date"] <= r["expected_date"])
            st = {r["status"]: r["c"] for r in rows(f"SELECT o.status, COUNT(*) c FROM orders o WHERE substr(o.created_at,1,10) BETWEEN ? AND ? {ow} GROUP BY o.status", (fs, ts_) + oa)}
            days = [(datetime.strptime(r["delivered_date"], "%Y-%m-%d") - datetime.strptime(r["created_at"][:10], "%Y-%m-%d")).days for r in data]
            return dict(title="Order Fulfillment Report", summary=[("Orders delivered", len(data), "num"), ("On-time deliveries", f"{round(ok * 100 / len(data)) if data else 0}%", "text"),
                        ("Avg days to deliver", round(sum(days) / len(days), 1) if days else 0, "num"), ("Cancelled", st.get("CANCELLED", 0), "num")],
                        columns=[("Order", "text"), ("Customer", "text"), ("Placed", "date"), ("Dispatched", "date"), ("Expected", "date"), ("Delivered", "date"), ("Days", "num"), ("On time", "text")],
                        rows=[[r["order_no"], r["customer_name"], r["created_at"][:10], r["dispatch_date"], r["expected_date"], r["delivered_date"], d, "Yes" if r["delivered_date"] <= r["expected_date"] else "Late"] for r, d in zip(data, days)],
                        chart={"type": "doughnut", "title": "Orders by status (period)", "labels": [k.title() for k in st], "values": list(st.values())})
        if key == "returns":
            rw, ra = wh_sql(wid, ("r.warehouse_id",))
            data = rows(f"""SELECT r.return_no, o.order_no, COALESCE(p.name,'') name, r.quantity, r.reason, r.condition, r.status, r.refund_amount, substr(r.created_at,1,10) d
                            FROM returns r LEFT JOIN orders o ON o.id=r.order_id LEFT JOIN products p ON p.id=r.product_id WHERE substr(r.created_at,1,10) BETWEEN ? AND ? {rw} ORDER BY r.id DESC LIMIT 1000""", (fs, ts_) + ra)
            reasons = {}
            for r in data:
                reasons[r["reason"]] = reasons.get(r["reason"], 0) + r["quantity"]
            dmg_units = scalar("SELECT COALESCE(SUM(damaged),0) FROM stock" + (" WHERE warehouse_id=?" if wid else ""), (wid,) if wid else ())
            return dict(title="Returns & Damaged Stock Report", summary=[("Returns", len(data), "num"), ("Approved", sum(1 for r in data if r["status"] == "APPROVED"), "num"),
                        ("Refund value", sum(r["refund_amount"] for r in data if r["status"] == "APPROVED"), "money"), ("Damaged units in stock", dmg_units, "num")],
                        columns=[("Return", "text"), ("Order", "text"), ("Product", "text"), ("Qty", "num"), ("Reason", "text"), ("Condition", "text"), ("Status", "text"), ("Refund", "money"), ("Date", "date")],
                        rows=[[r["return_no"], r["order_no"], r["name"], r["quantity"], r["reason"], r["condition"].title(), r["status"].title(), r["refund_amount"], r["d"]] for r in data],
                        chart={"type": "bar", "title": "Returned units by reason", "labels": list(reasons), "values": list(reasons.values())})
        if key == "lowstock":
            low = [p for p in prods if p["status"] != "OK"]
            data = [[p["code"], p["name"], p["category"], p["available"], p["reorder_level"], max(p["reorder_level"] - p["available"], 0), max(p["reorder_level"] * 3 - p["available"], 0), p["supplier_name"], p["status"].replace("OUT", "Out of stock").replace("LOW", "Low")] for p in low]
            data.sort(key=lambda r: r[3] / max(r[4], 1))
            return dict(title="Low Stock Report", summary=[("Products below reorder level", len(low), "num"), ("Out of stock", sum(1 for p in low if p["status"] == "OUT"), "num"),
                        ("Suggested units to order", sum(r[6] for r in data), "num")],
                        columns=[("Code", "text"), ("Product", "text"), ("Category", "text"), ("Available", "num"), ("Reorder level", "num"), ("Shortfall", "num"), ("Suggested order", "num"), ("Supplier", "text"), ("Status", "text")],
                        rows=data, chart={"type": "bar", "title": "Available vs reorder level", "labels": [r[1] for r in data], "values": [r[3] for r in data], "values2": [r[4] for r in data]})
        raise ApiError("Unknown report", 404)

    REPORT_KEYS = ["valuation", "movements", "warehouse", "suppliers", "purchases", "sales", "fulfillment", "returns", "lowstock"]

    def fmt_cell(v, typ):
        if typ == "money":
            return f"Rs {v:,.0f}"
        if typ == "pct":
            return f"{v}%"
        if typ == "num" and isinstance(v, (int, float)):
            return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.1f}"
        return "" if v is None else str(v)

    @app.get("/api/reports/<key>")
    @require("report.view")
    def report(key):
        if key == "suppliers" and not can("supplier.write"):
            raise ApiError("Not allowed", 403)
        f, t = date_range()
        wid = wh_filter(request.args.get("warehouse"))
        rep = build_report(key, f, t, wid)
        rep["period"] = f"{day_s(f)} to {day_s(t)}"
        rep["key"] = key
        fmt = request.args.get("format", "json")
        stamp = datetime.now().strftime("%Y%m%d")
        if fmt == "json":
            return jsonify({**rep, "summary": [{"label": a, "value": b, "type": c} for a, b, c in rep["summary"]],
                            "columns": [{"label": a, "type": b} for a, b in rep["columns"]], "keys": REPORT_KEYS})
        if fmt == "csv":
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow([rep["title"], rep["period"]])
            for a, b, c in rep["summary"]:
                w.writerow([a, fmt_cell(b, c)])
            w.writerow([])
            w.writerow([c[0] for c in rep["columns"]])
            w.writerows(rep["rows"])
            return Response("\ufeff" + buf.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename={key}_{stamp}.csv"})
        if fmt == "xlsx":
            from openpyxl import Workbook
            from openpyxl.styles import Alignment, Font, PatternFill
            wb = Workbook()
            ws = wb.active
            ws.title = rep["title"][:30]
            ws.append([rep["title"]])
            ws["A1"].font = Font(size=15, bold=True, color="14243A")
            ws.append([f"Period: {rep['period']}"])
            for a, b, c in rep["summary"]:
                ws.append([a, b])
                ws.cell(ws.max_row, 1).font = Font(bold=True)
            ws.append([])
            hr = ws.max_row + 1
            ws.append([c[0] for c in rep["columns"]])
            for cell in ws[hr]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="14243A")
                cell.alignment = Alignment(horizontal="center")
            for r in rep["rows"]:
                ws.append(r)
            for i, col in enumerate(rep["columns"], 1):
                ws.column_dimensions[ws.cell(hr, i).column_letter].width = max(12, min(40, len(col[0]) + 6))
                for rr in range(hr + 1, ws.max_row + 1):
                    if col[1] == "money":
                        ws.cell(rr, i).number_format = '#,##0'
            bio = io.BytesIO()
            wb.save(bio)
            return Response(bio.getvalue(), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            headers={"Content-Disposition": f"attachment; filename={key}_{stamp}.xlsx"})
        if fmt == "pdf":
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
            bio = io.BytesIO()
            doc = SimpleDocTemplate(bio, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=26, bottomMargin=26, title=rep["title"])
            ss = getSampleStyleSheet()
            story = [Paragraph(f"<b>{rep['title']}</b>", ss["Title"]), Paragraph(f"Period: {rep['period']} &nbsp;|&nbsp; Generated {now_s()}", ss["Normal"]), Spacer(1, 10)]
            st = Table([[a for a, _, _ in rep["summary"]], [fmt_cell(b, c) for _, b, c in rep["summary"]]])
            st.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#119B78")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                    ("FONTSIZE", (0, 0), (-1, -1), 9), ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("BOX", (0, 0), (-1, -1), .5, colors.grey),
                                    ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold")]))
            story += [st, Spacer(1, 12)]
            data = [[c[0] for c in rep["columns"]]] + [[fmt_cell(v, rep["columns"][i][1])[:34] for i, v in enumerate(r)] for r in rep["rows"][:600]]
            tb = Table(data, repeatRows=1)
            tb.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#14243A")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 7),
                                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F6")]), ("GRID", (0, 0), (-1, -1), .25, colors.HexColor("#D5DDE0")),
                                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
            story.append(tb)
            if len(rep["rows"]) > 600:
                story.append(Paragraph(f"... {len(rep['rows']) - 600} more rows not shown. Use CSV or Excel for the full list.", ss["Italic"]))
            doc.build(story)
            return Response(bio.getvalue(), mimetype="application/pdf", headers={"Content-Disposition": f"attachment; filename={key}_{stamp}.pdf"})
        raise ApiError("Unknown format")

    # ================================================================== DSA - live queues + sandbox
    def snap(q, limit=40):
        nodes = q.snapshot()
        return {"name": q.name, "size": q.size(), "nodes": nodes[:limit], "more": max(len(nodes) - limit, 0),
                "front": q.front.uid if q.front else None, "rear": q.rear.uid if q.rear else None,
                "enqueue_calls": q.enqueue_calls, "dequeue_calls": q.dequeue_calls}

    @app.get("/api/dsa/live")
    @require()
    def dsa_live():
        with lock:
            return jsonify({k: snap(q) for k, q in QUEUES.items()})

    sandbox = {"q": Queue("Sandbox Queue", labeler=lambda d: d["value"]), "history": []}

    def sandbox_seed():
        q = sandbox["q"]
        q.clear()
        for v in ("ORD-101", "ORD-102", "ORD-103"):
            q.enqueue({"value": v})
        sandbox["history"].clear()

    sandbox_seed()
    COMPLEX = {"enqueue": ("O(1)", "Create a node and link it after REAR. No traversal needed."),
               "dequeue": ("O(1)", "Only the FRONT pointer moves."),
               "peek": ("O(1)", "Read the FRONT node without changing anything."),
               "search": ("O(n)", "A queue only exposes the FRONT, so we rotate through up to n items."),
               "update": ("O(n)", "Rotate until the item is found, change it, keep rotating to restore order."),
               "delete": ("O(n)", "Rotate through all items and skip (do not re-enqueue) the match."),
               "clear": ("O(n)", "Unlink every node."), "reset": ("O(n)", "Rebuild the sample queue.")}

    @app.get("/api/dsa/sandbox")
    @require()
    def sandbox_state():
        return jsonify({"state": snap(sandbox["q"]), "history": sandbox["history"][-40:], "complexity": COMPLEX})

    @app.post("/api/dsa/sandbox")
    @require()
    def sandbox_op():
        d = body()
        op = d.get("op")
        val = str(d.get("value", "")).strip()
        new = str(d.get("new_value", "")).strip()
        q = sandbox["q"]
        if op in ("enqueue", "search", "update", "delete") and not val:
            raise ApiError("Enter a value first", field="value")
        if len(val) > 14 or len(new) > 14:
            raise ApiError("Values can have up to 14 characters", field="value")
        if op == "update" and not new:
            raise ApiError("Enter the new value", field="new_value")
        result, error = None, None
        with lock:
            before = snap(q)
            q.start_trace()
            try:
                if op == "enqueue":
                    if q.size() >= 12:
                        raise ApiError("The sandbox queue is full (max 12 nodes) so it stays readable", field="value")
                    q.enqueue({"value": val})
                    msg = f"Enqueued '{val}' at the REAR"
                elif op == "dequeue":
                    r = q.dequeue()
                    msg = f"Dequeued '{r['value']}' from the FRONT"
                elif op == "peek":
                    r = q.peek()
                    msg = "Queue is empty" if r is None else f"FRONT item is '{r['value']}' (not removed)"
                elif op == "search":
                    r = q.find(lambda x: x["value"] == val)
                    msg = f"Found '{val}' (queue order unchanged)" if r else f"'{val}' was not found"
                elif op == "update":
                    r = q.update(lambda x: x["value"] == val, lambda x: x.update(value=new))
                    msg = f"Updated '{val}' to '{new}'" if r else f"'{val}' was not found - nothing updated"
                elif op == "delete":
                    r = q.remove(lambda x: x["value"] == val)
                    msg = f"Deleted '{val}' from the queue" if r else f"'{val}' was not found - nothing deleted"
                elif op == "clear":
                    q.clear()
                    msg = "Queue cleared: FRONT = REAR = None"
                elif op == "reset":
                    q.stop_trace()
                    sandbox_seed()
                    msg = "Sample queue restored"
                    return jsonify({"steps": [], "message": msg, "state": snap(q), "history": [], "complexity": COMPLEX})
                else:
                    raise ApiError("Unknown operation")
            except IndexError as e:
                error, msg = str(e), str(e)
            finally:
                steps = q.stop_trace()
            if op == "clear":
                steps = [{"msg": "Unlink all nodes; FRONT and REAR become None", "kind": "delete", "nodes": [], "front": None, "rear": None, "size": 0, "hold": None, "hl": None}]
            t, why = COMPLEX[op]
            sandbox["history"].append({"ts": datetime.now().strftime("%H:%M:%S"), "op": op, "detail": msg, "time": t, "ok": error is None})
            log_activity(op.upper(), "DSA Sandbox", msg)
            return jsonify({"steps": steps, "before": before, "message": msg, "error": error, "state": snap(q), "history": sandbox["history"][-40:],
                            "complexity": {"op": op, "time": t, "why": why}})

    # ================================================================== algorithms
    @app.get("/api/algo/info")
    @require()
    def algo_info():
        return jsonify(algo.ALGO_INFO)

    @app.post("/api/algo/demo")
    @require()
    def algo_demo():
        d = body()
        name = d.get("algo")
        try:
            data = [float(x) if "." in str(x) else int(x) for x in d.get("data", [])]
        except (TypeError, ValueError):
            raise ApiError("Enter numbers only, separated by commas", field="data")
        if not 2 <= len(data) <= 16:
            raise ApiError("Use between 2 and 16 numbers so the animation stays readable", field="data")
        rec = []
        if name in algo.SORTERS:
            out, st = algo.SORTERS[name](data, lambda x: x, bool(d.get("desc")), rec)
            return jsonify({"frames": rec, "result": out, "comparisons": st.comparisons, "moves": st.swaps})
        if name in ("linear", "binary"):
            try:
                target = float(d.get("target")) if "." in str(d.get("target")) else int(d.get("target"))
            except (TypeError, ValueError):
                raise ApiError("Enter a number to search for", field="target")
            if name == "linear":
                hits, st = algo.linear_search(data, target, lambda x: x, rec)
            else:
                if not algo.is_sorted(data, lambda x: x):
                    return jsonify({"needs_sort": True, "error": "Binary search only works on sorted data. This list is not sorted - sort it first (merge sort) or use linear search.",
                                    "sorted": algo.merge_sort(data)[0]}), 400
                hits, st = algo.binary_search(data, target, lambda x: x, rec)
            return jsonify({"frames": rec, "found": bool(hits), "index": hits[0] if hits else None, "comparisons": st.comparisons, "result": data})
        raise ApiError("Choose an algorithm")

    @app.post("/api/algo/benchmark")
    @require()
    def algo_benchmark():
        n = max(20, min(int(body().get("n", 300)), 1200))
        rnd = random.Random(time.time())
        data = [rnd.randint(1, 100000) for _ in range(n)]
        out = []
        for name in ("bubble", "selection", "insertion", "merge"):
            _, info = algo.sort_records(data, lambda x: x, name)
            out.append(info)
        s_sorted, _ = algo.sort_records(data, lambda x: x, "merge")
        target = rnd.choice(data)
        _, lin = algo.linear_search(data, target)
        _, binr = algo.binary_search(s_sorted, target)
        return jsonify({"n": n, "sorts": out, "linear_comparisons": lin.comparisons, "binary_comparisons": binr.comparisons})
