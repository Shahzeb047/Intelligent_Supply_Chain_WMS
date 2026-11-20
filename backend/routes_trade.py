"""backend/routes_trade.py - suppliers, purchase orders, customer orders (queue pipeline), shipments, returns."""
import re

from flask import jsonify, request

from . import services
from .core import (ApiError, body, db, dispatch_q, lock, need_int, need_str, now_s, one, order_q, require, rows, scalar, scope_wh,
                   today_s, wh_filter, log_activity)

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def wh_where(col, extra_wid=None):
    s = scope_wh() or extra_wid
    return (f" AND {col}=?", (s,)) if s else ("", ())


def register(app):
    # ================================================================ suppliers
    def clean_supplier(d, sid=None):
        name = need_str(d, "name", "Supplier name", 100)
        if one("SELECT id FROM suppliers WHERE lower(name)=? AND id!=?", (name.lower(), sid or 0)):
            raise ApiError("A supplier with this name already exists", field="name")
        email = need_str(d, "email", "Email", 120)
        if not EMAIL.match(email):
            raise ApiError("Enter a valid email address", field="email")
        phone = need_str(d, "phone", "Phone", 30)
        if not re.match(r"^[0-9+\-()\s]{7,20}$", phone):
            raise ApiError("Enter a valid phone number", field="phone")
        status = d.get("status", "Active")
        if status not in ("Active", "Inactive"):
            raise ApiError("Invalid status", field="status")
        return (name, need_str(d, "contact_person", "Contact person", 80), email, phone, str(d.get("address", "")).strip(),
                str(d.get("categories", "")).strip(), status)

    @app.get("/api/suppliers")
    @require("supplier.write")
    def suppliers():
        out = rows("SELECT * FROM suppliers ORDER BY id")
        stats = {r["supplier_id"]: r for r in rows("""SELECT supplier_id, COUNT(*) pos, SUM(CASE WHEN status='COMPLETED' THEN 1 ELSE 0 END) done,
                SUM(CASE WHEN status='COMPLETED' AND received_date<=expected_date THEN 1 ELSE 0 END) ontime FROM purchase_orders GROUP BY supplier_id""")}
        for s in out:
            a = stats.get(s["id"], {})
            s["po_count"], s["completed"] = a.get("pos", 0), a.get("done", 0) or 0
            s["on_time_pct"] = round((a.get("ontime") or 0) * 100 / a["done"]) if a.get("done") else None
            s["products"] = scalar("SELECT COUNT(*) FROM products WHERE supplier_id=?", (s["id"],))
        return jsonify(out)

    @app.post("/api/suppliers")
    @require("supplier.write")
    def supplier_create():
        v = clean_supplier(body())
        n = scalar("SELECT COALESCE(MAX(id),0) FROM suppliers") + 1
        db().execute("INSERT INTO suppliers(code,name,contact_person,email,phone,address,categories,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                     (f"SUP-{n:03d}",) + v + (now_s(),))
        return jsonify({"ok": True}), 201

    @app.put("/api/suppliers/<int:sid>")
    @require("supplier.write")
    def supplier_update(sid):
        if not one("SELECT id FROM suppliers WHERE id=?", (sid,)):
            raise ApiError("Supplier not found", 404)
        v = clean_supplier(body(), sid)
        db().execute("UPDATE suppliers SET name=?, contact_person=?, email=?, phone=?, address=?, categories=?, status=? WHERE id=?", v + (sid,))
        return jsonify({"ok": True})

    @app.delete("/api/suppliers/<int:sid>")
    @require("supplier.write")
    def supplier_delete(sid):
        if scalar("SELECT COUNT(*) FROM purchase_orders WHERE supplier_id=?", (sid,)):
            raise ApiError("This supplier has purchase history. Set the status to Inactive instead of deleting.")
        if scalar("SELECT COUNT(*) FROM products WHERE supplier_id=?", (sid,)):
            raise ApiError("Products are linked to this supplier. Reassign them first.")
        db().execute("DELETE FROM suppliers WHERE id=?", (sid,))
        return jsonify({"ok": True})

    # ================================================================ purchase orders
    @app.get("/api/purchase-orders")
    @require("po.write")
    def po_list():
        f, a = wh_where("po.warehouse_id", wh_filter(request.args.get("warehouse")))
        st = request.args.get("status")
        extra, args = (" AND po.status=?", (st,)) if st else ("", ())
        data = rows(f"""SELECT po.*, s.name supplier_name, w.name warehouse_name,
                        (SELECT COALESCE(SUM(quantity*unit_cost),0) FROM po_items WHERE po_id=po.id) total,
                        (SELECT COALESCE(SUM(quantity),0) FROM po_items WHERE po_id=po.id) units,
                        (SELECT COALESCE(SUM(received_qty),0) FROM po_items WHERE po_id=po.id) received_units
                        FROM purchase_orders po LEFT JOIN suppliers s ON s.id=po.supplier_id LEFT JOIN warehouses w ON w.id=po.warehouse_id
                        WHERE 1=1 {f}{extra} ORDER BY po.id DESC LIMIT 400""", a + args)
        return jsonify(data)

    @app.get("/api/purchase-orders/<int:pid>")
    @require("po.write")
    def po_get(pid):
        return jsonify(services.po_detail(pid))

    @app.post("/api/purchase-orders")
    @require("po.write")
    def po_create():
        pid = services.save_po(body())
        log_activity("CREATE", "Purchase Orders", f"Purchase order PO-{pid:05d} created")
        return jsonify({"id": pid}), 201

    @app.put("/api/purchase-orders/<int:pid>")
    @require("po.write")
    def po_update(pid):
        services.save_po(body(), pid)
        return jsonify({"id": pid})

    @app.post("/api/purchase-orders/<int:pid>/status")
    @require("po.write")
    def po_set_status(pid):
        services.po_status(pid, str(body().get("status", "")).upper())
        return jsonify({"ok": True})

    @app.post("/api/purchase-orders/<int:pid>/receive")
    @require("po.write")
    def po_receive(pid):
        got = services.po_receive(pid, body().get("lines"))
        return jsonify({"received": got})

    @app.delete("/api/purchase-orders/<int:pid>")
    @require("po.write")
    def po_delete(pid):
        po = services.po_detail(pid)
        if po["status"] not in ("DRAFT", "CANCELLED"):
            raise ApiError("Only draft or cancelled purchase orders can be deleted")
        db().execute("DELETE FROM po_items WHERE po_id=?", (pid,))
        db().execute("DELETE FROM purchase_orders WHERE id=?", (pid,))
        return jsonify({"ok": True})

    # ================================================================ customer orders
    @app.get("/api/orders")
    @require()
    def orders_list():
        a = request.args
        f, args = wh_where("o.warehouse_id", wh_filter(a.get("warehouse")))
        where = f
        if a.get("status"):
            where += " AND o.status=?"
            args += (a["status"],)
        if a.get("q"):
            where += " AND (lower(o.order_no) LIKE ? OR lower(o.customer_name) LIKE ?)"
            args += (f"%{a['q'].lower()}%",) * 2
        data = rows(f"""SELECT o.*, w.name warehouse_name,
                        (SELECT COALESCE(SUM(quantity),0) FROM order_items WHERE order_id=o.id) units,
                        (SELECT COUNT(*) FROM order_items WHERE order_id=o.id) lines
                        FROM orders o LEFT JOIN warehouses w ON w.id=o.warehouse_id WHERE 1=1 {where} ORDER BY o.id DESC LIMIT 500""", args)
        with lock:
            pos = {x["id"]: i + 1 for i, x in enumerate(order_q)}
            dpos = {x["id"]: i + 1 for i, x in enumerate(dispatch_q)}
        for o in data:
            o["queue_position"] = pos.get(o["id"]) or dpos.get(o["id"])
        return jsonify(data)

    @app.get("/api/orders/<int:oid>")
    @require()
    def order_get(oid):
        return jsonify(services.order_detail(oid))

    @app.post("/api/orders/check")
    @require()
    def order_check():
        d = body()
        wid = need_int(d, "warehouse_id", "Warehouse")
        out = []
        for it in d.get("items") or []:
            try:
                pid, q = int(it["product_id"]), int(it.get("quantity") or 0)
            except (KeyError, ValueError):
                continue
            s = services.stock_row(pid, wid)
            out.append({"product_id": pid, "requested": q, "available": s["quantity"] - s["reserved"], "ok": q <= s["quantity"] - s["reserved"]})
        return jsonify(out)

    @app.post("/api/orders")
    @require("order.write")
    def order_create():
        oid = services.create_order(body())
        return jsonify({"id": oid, "order_no": f"ORD-{oid:06d}"}), 201

    @app.post("/api/orders/process-next")
    @require("order.advance")
    def order_process_next():
        done = services.process_next(bool((request.get_json(silent=True) or {}).get("all")))
        return jsonify({"processed": done})

    @app.post("/api/orders/dispatch-next")
    @require("order.advance")
    def order_dispatch_next():
        d = request.get_json(silent=True) or {}
        done = services.dispatch_next(d.get("partner"), bool(d.get("all")))
        return jsonify({"dispatched": done})

    @app.post("/api/orders/<int:oid>/advance")
    @require("order.advance")
    def order_advance(oid):
        return jsonify({"status": services.advance_order(oid)})

    @app.post("/api/orders/<int:oid>/cancel")
    @require("order.write")
    def order_cancel(oid):
        services.cancel_order(oid)
        return jsonify({"ok": True})

    # ================================================================ shipments
    @app.get("/api/shipments")
    @require()
    def shipments_list():
        a = request.args
        f, args = wh_where("s.origin_wh", wh_filter(a.get("warehouse")))
        if a.get("status"):
            if a["status"] == "DELAYED":
                f += " AND s.status!='DELIVERED' AND s.expected_date<?"
                args += (today_s(),)
            else:
                f += " AND s.status=?"
                args += (a["status"],)
        data = rows(f"""SELECT s.*, w.name origin_name, o.order_no FROM shipments s LEFT JOIN warehouses w ON w.id=s.origin_wh
                        LEFT JOIN orders o ON o.id=s.order_id WHERE 1=1 {f} ORDER BY s.id DESC LIMIT 500""", args)
        t = today_s()
        for s in data:
            s["delayed"] = s["status"] != "DELIVERED" and s["expected_date"] < t
            s["late_delivery"] = bool(s["delivered_date"] and s["delivered_date"] > s["expected_date"])
        return jsonify(data)

    @app.get("/api/shipments/<int:sid>")
    @require()
    def shipment_get(sid):
        s = one("""SELECT s.*, w.name origin_name, o.order_no FROM shipments s LEFT JOIN warehouses w ON w.id=s.origin_wh
                   LEFT JOIN orders o ON o.id=s.order_id WHERE s.id=?""", (sid,))
        if not s or (scope_wh() and s["origin_wh"] != scope_wh()):
            raise ApiError("Shipment not found", 404)
        s["events"] = rows("SELECT status,ts FROM shipment_events WHERE shipment_id=? ORDER BY id", (sid,))
        s["delayed"] = s["status"] != "DELIVERED" and s["expected_date"] < today_s()
        s["items"] = rows("""SELECT i.quantity, i.unit_price, COALESCE(p.name,'(deleted product)') name FROM order_items i
                             LEFT JOIN products p ON p.id=i.product_id WHERE i.order_id=?""", (s["order_id"],))
        return jsonify(s)

    @app.post("/api/shipments/<int:sid>/advance")
    @require("shipment.write")
    def shipment_advance(sid):
        return jsonify({"status": services.advance_shipment(sid)})

    @app.put("/api/shipments/<int:sid>")
    @require("shipment.write")
    def shipment_update(sid):
        from .core import opt_date
        d = body()
        s = one("SELECT * FROM shipments WHERE id=?", (sid,))
        if not s:
            raise ApiError("Shipment not found", 404)
        partner = need_str(d, "partner", "Delivery partner", 60)
        exp = opt_date(d, "expected_date") or s["expected_date"]
        if exp < s["dispatch_date"]:
            raise ApiError("Expected delivery cannot be before the dispatch date", field="expected_date")
        db().execute("UPDATE shipments SET partner=?, expected_date=? WHERE id=?", (partner, exp, sid))
        return jsonify({"ok": True})

    # ================================================================ returns
    @app.get("/api/returns")
    @require()
    def returns_list():
        f, args = wh_where("r.warehouse_id", wh_filter(request.args.get("warehouse")))
        data = rows(f"""SELECT r.*, o.order_no, o.customer_name, COALESCE(p.name,'(deleted product)') product_name, p.code product_code, w.name warehouse_name
                        FROM returns r LEFT JOIN orders o ON o.id=r.order_id LEFT JOIN products p ON p.id=r.product_id
                        LEFT JOIN warehouses w ON w.id=r.warehouse_id WHERE 1=1 {f} ORDER BY r.id DESC LIMIT 400""", args)
        dmg = rows("SELECT COALESCE(SUM(damaged),0) d FROM stock" + (" WHERE warehouse_id=?" if scope_wh() else ""), (scope_wh(),) if scope_wh() else ())
        return jsonify({"items": data, "total_damaged": dmg[0]["d"]})

    @app.get("/api/returns/eligible-orders")
    @require()
    def returns_eligible():
        f, args = wh_where("o.warehouse_id")
        data = rows(f"SELECT o.id, o.order_no, o.customer_name, o.status FROM orders o WHERE o.status IN ('DELIVERED','RETURNED') {f} ORDER BY o.id DESC LIMIT 120", args)
        return jsonify(data)

    @app.post("/api/returns")
    @require("return.write")
    def return_create():
        rid = services.create_return(body())
        return jsonify({"id": rid}), 201

    @app.post("/api/returns/<int:rid>/decision")
    @require("return.decide")
    def return_decide(rid):
        d = str(body().get("decision", ""))
        if d not in ("approve", "reject"):
            raise ApiError("Choose approve or reject")
        return jsonify({"result": services.decide_return(rid, d)})
