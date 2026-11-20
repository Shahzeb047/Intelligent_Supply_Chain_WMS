"""backend/routes_inventory.py - products (Inventory Queue CRUD), stock reservation, warehouses, stock movements."""
import re

from flask import jsonify, request

from ds import algorithms as algo
from . import services
from .core import (ApiError, body, can, current_user, db, inventory_q, lock, log_activity, need_int, need_num, need_str, now_s, one,
                   opt_date, require, rows, scalar, scope_wh, wh_filter)

SORT_KEYS = {"id": lambda p: p["id"], "name": lambda p: p["name"], "quantity": lambda p: p["available"],
             "price": lambda p: p["selling_price"], "category": lambda p: p["category"], "code": lambda p: p["code"]}
SEARCH_FIELDS = {"name": lambda p: p["name"], "code": lambda p: p["code"], "sku": lambda p: p["sku"],
                 "barcode": lambda p: p["barcode"] or "", "category": lambda p: p["category"]}


def clean_product(d, pid=None):
    name = need_str(d, "name", "Product name", 120)
    category = need_str(d, "category", "Category", 60)
    sku = str(d.get("sku", "")).strip().upper()
    if sku and not re.match(r"^[A-Z0-9][A-Z0-9\-_.]{1,39}$", sku):
        raise ApiError("SKU may contain letters, numbers, - _ . only", field="sku")
    if sku and one("SELECT id FROM products WHERE sku=? AND id!=?", (sku, pid or 0)):
        raise ApiError(f"SKU {sku} is already used by another product", field="sku")
    barcode = str(d.get("barcode", "")).strip()
    if barcode and not re.match(r"^[0-9A-Za-z\-]{4,32}$", barcode):
        raise ApiError("Barcode must be 4-32 letters/digits", field="barcode")
    cost = need_num(d, "purchase_price", "Purchase price", 0)
    price = need_num(d, "selling_price", "Selling price", 0)
    if price < cost:
        raise ApiError("Selling price is lower than the purchase price", field="selling_price")
    img = str(d.get("image", "") or "")
    if img and not (img.startswith("data:image/") or len(img) <= 8):
        raise ApiError("Image must be an uploaded picture or an emoji", field="image")
    if len(img) > 400000:
        raise ApiError("Image is too large (max ~250 KB)", field="image")
    sup = d.get("supplier_id") or None
    if sup and not one("SELECT id FROM suppliers WHERE id=?", (int(sup),)):
        raise ApiError("Supplier not found", field="supplier_id")
    return dict(name=name, category=category, sku=sku, barcode=barcode, description=str(d.get("description", "")).strip()[:500],
                purchase_price=cost, selling_price=price, reorder_level=need_int(d, "reorder_level", "Reorder level", 0, 100000, default=10),
                supplier_id=int(sup) if sup else None, bin=str(d.get("bin", "")).strip()[:20], image=img,
                expiry_tracked=1 if d.get("expiry_tracked") in (True, 1, "1", "true", "on") else 0)


def register(app):
    # ================================================================ products
    @app.get("/api/products")
    @require()
    def products():
        a = request.args
        wid = wh_filter(a.get("warehouse"))
        items = services.product_rows(wid)
        if a.get("category"):
            items = [p for p in items if p["category"] == a["category"]]
        if a.get("status"):
            items = [p for p in items if p["status"] == a["status"]]
        stats = {"total_before": len(items)}
        q = a.get("q", "").strip()
        if q:
            field, how = a.get("search_field", "any"), a.get("search_algo", "linear")
            if how == "binary":
                if field == "any":
                    field = "name"
                key = SEARCH_FIELDS.get(field, SEARCH_FIELDS["name"])
                ordered, sinfo = algo.sort_records(items, key, "merge")       # binary search needs sorted data
                hits, st = algo.binary_search(ordered, q, key)
                items = [ordered[i] for i in hits]
                stats["search"] = {"algorithm": "binary", "field": field, "comparisons": st.comparisons, "n": len(ordered),
                                   "note": f"Data sorted by {field} with merge sort ({sinfo['comparisons']} comparisons), then binary search (exact match)."}
            else:
                key = SEARCH_FIELDS[field] if field in SEARCH_FIELDS else (lambda p: " ".join([p["name"], p["code"], p["sku"], p["barcode"] or "", p["category"]]))
                hits, st = algo.linear_search(items, q, key, contains=True)
                items = [items[i] for i in hits]
                stats["search"] = {"algorithm": "linear", "field": field, "comparisons": st.comparisons, "n": stats["total_before"],
                                   "note": "Linear search checked every product (contains match)."}
        sk = a.get("sort", "id")
        if sk in SORT_KEYS:
            items, info = algo.sort_records(items, SORT_KEYS[sk], a.get("algo", "merge"), a.get("dir") == "desc")
            stats["sort"] = info
        stats["count"] = len(items)
        return jsonify({"items": items, "stats": stats})

    @app.get("/api/products/<int:pid>")
    @require()
    def product_detail(pid):
        p = services.get_product(pid)
        wid = scope_wh()
        row = next((r for r in services.product_rows(wid) if r["id"] == pid), None)
        if not row:
            raise ApiError("Product not found in your warehouse", 404)
        row["stock"] = rows("""SELECT s.*, w.name warehouse_name, w.code warehouse_code FROM stock s JOIN warehouses w ON w.id=s.warehouse_id
                               WHERE s.product_id=? ORDER BY w.id""", (pid,)) if not wid else rows(
            "SELECT s.*, w.name warehouse_name, w.code warehouse_code FROM stock s JOIN warehouses w ON w.id=s.warehouse_id WHERE s.product_id=? AND s.warehouse_id=?", (pid, wid))
        row["batches"] = rows("SELECT b.*, w.name warehouse_name FROM batches b JOIN warehouses w ON w.id=b.warehouse_id WHERE b.product_id=? "
                              + ("AND b.warehouse_id=? " if wid else "") + "ORDER BY b.expiry_date", (pid, wid) if wid else (pid,))
        row["history"] = rows("""SELECT m.*, ws.name src_name, wd.name dst_name FROM movements m LEFT JOIN warehouses ws ON ws.id=m.source_wh
                                 LEFT JOIN warehouses wd ON wd.id=m.dest_wh WHERE m.product_id=? ORDER BY m.id DESC LIMIT 40""", (pid,))
        row["sold_units"] = scalar("SELECT COALESCE(SUM(i.quantity),0) FROM order_items i JOIN orders o ON o.id=i.order_id WHERE i.product_id=? AND o.status IN ('DISPATCHED','DELIVERED')", (pid,))
        return jsonify(row)

    @app.post("/api/products")
    @require("product.write")
    def product_create():
        d = body()
        f = clean_product(d)
        wid = need_int(d, "warehouse_id", "Warehouse")
        services.enforce_scope(wid)
        services.get_wh(wid)
        qty = need_int(d, "quantity", "Opening quantity", 0, default=0)
        if qty and f["expiry_tracked"] and not d.get("expiry_date"):
            raise ApiError("Expiry date is required for perishable products with opening stock", field="expiry_date")
        c = db()
        cur = c.execute("""INSERT INTO products(code,name,sku,barcode,category,description,purchase_price,selling_price,reorder_level,supplier_id,
                           warehouse_id,bin,image,expiry_tracked,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        ("TMP", f["name"], f["sku"] or f"TMP{now_s()}", f["barcode"], f["category"], f["description"], f["purchase_price"],
                         f["selling_price"], f["reorder_level"], f["supplier_id"], wid, f["bin"], f["image"], f["expiry_tracked"], now_s()))
        pid = cur.lastrowid
        sku = f["sku"] or f"{f['category'][:3].upper()}-{pid:04d}"
        c.execute("UPDATE products SET code=?, sku=? WHERE id=?", (f"P-{pid:04d}", sku, pid))
        row = one("SELECT * FROM products WHERE id=?", (pid,))
        with lock:
            inventory_q.enqueue(row)                                      # CREATE = ENQUEUE at REAR
        log_activity("ENQUEUE", "Inventory Queue", f"{row['name']} ({row['code']}) added at the REAR of the inventory queue")
        services.stock_row(pid, wid, True)
        if qty:
            services.apply_movement("STOCK_IN", pid, qty, dst=wid, ref="OPENING", note="Opening stock", expiry=opt_date(d, "expiry_date"))
        return jsonify({"id": pid}), 201

    @app.put("/api/products/<int:pid>")
    @require("product.write")
    def product_update(pid):
        d = body()
        services.get_product(pid)
        f = clean_product(d, pid)
        wid = d.get("warehouse_id")
        if wid:
            services.get_wh(int(wid))
            f["warehouse_id"] = int(wid)
        cur = one("SELECT sku FROM products WHERE id=?", (pid,))
        if not f["sku"]:
            f["sku"] = cur["sku"]
        with lock:
            item = inventory_q.update(lambda x: x["id"] == pid, lambda x: x.update(f))    # UPDATE by rotation
        cols = ", ".join(f"{k}=?" for k in f)
        db().execute(f"UPDATE products SET {cols} WHERE id=?", tuple(f.values()) + (pid,))
        log_activity("UPDATE", "Inventory Queue", f"{item['name']} ({item['code']}) updated by queue rotation")
        return jsonify({"ok": True})

    @app.delete("/api/products/<int:pid>")
    @require("product.write")
    def product_delete(pid):
        p = services.get_product(pid)
        if scalar("SELECT COALESCE(SUM(reserved),0) FROM stock WHERE product_id=?", (pid,)):
            raise ApiError("This product has stock reserved by open customer orders and cannot be deleted")
        if scalar("SELECT COUNT(*) FROM po_items i JOIN purchase_orders po ON po.id=i.po_id WHERE i.product_id=? AND po.status IN ('PENDING','APPROVED','PARTIALLY_RECEIVED')", (pid,)):
            raise ApiError("This product is on an open purchase order and cannot be deleted")
        with lock:
            inventory_q.remove(lambda x: x["id"] == pid)                  # DELETE by rotation (skip target)
        for t in ("products", "stock", "batches"):
            db().execute(f"DELETE FROM {t} WHERE {'id' if t == 'products' else 'product_id'}=?", (pid,))
        log_activity("DELETE", "Inventory Queue", f"{p['name']} ({p['code']}) removed from the inventory queue")
        return jsonify({"ok": True})

    @app.post("/api/stock/reserve")
    @require("reserve")
    def reserve():
        d = body()
        pid, wid = need_int(d, "product_id", "Product"), need_int(d, "warehouse_id", "Warehouse")
        qty = need_int(d, "quantity", "Quantity", 1)
        services.enforce_scope(wid)
        p = services.get_product(pid)
        s = services.stock_row(pid, wid)
        if d.get("action") == "release":
            if qty > s["reserved"]:
                raise ApiError(f"Only {s['reserved']} units are reserved", field="quantity")
            db().execute("UPDATE stock SET reserved=reserved-? WHERE product_id=? AND warehouse_id=?", (qty, pid, wid))
            msg = f"Released {qty} reserved units of {p['name']}"
        else:
            if qty > s["quantity"] - s["reserved"]:
                raise ApiError(f"Only {s['quantity'] - s['reserved']} units are available to reserve", field="quantity")
            db().execute("UPDATE stock SET reserved=reserved+? WHERE product_id=? AND warehouse_id=?", (qty, pid, wid))
            msg = f"Reserved {qty} units of {p['name']}"
        log_activity("RESERVE", "Inventory", msg)
        return jsonify({"message": msg})

    # ================================================================ warehouses
    def wh_stats():
        s = scope_wh()
        out = rows("SELECT * FROM warehouses" + (" WHERE id=?" if s else "") + " ORDER BY id", (s,) if s else ())
        agg = {r["warehouse_id"]: r for r in rows("""SELECT s.warehouse_id, SUM(s.quantity) units, SUM(s.reserved) reserved, SUM(s.damaged) damaged,
                      COUNT(CASE WHEN s.quantity>0 THEN 1 END) products, SUM(s.quantity*p.purchase_price) value
                      FROM stock s JOIN products p ON p.id=s.product_id GROUP BY s.warehouse_id""")}
        pend = {r["warehouse_id"]: r["c"] for r in rows("SELECT warehouse_id, COUNT(*) c FROM orders WHERE status IN ('PENDING','CONFIRMED','PROCESSING','PACKED') GROUP BY warehouse_id")}
        for w in out:
            a = agg.get(w["id"], {})
            w.update(units=a.get("units") or 0, reserved=a.get("reserved") or 0, damaged=a.get("damaged") or 0, products=a.get("products") or 0,
                     value=a.get("value") or 0, open_orders=pend.get(w["id"], 0))
            w["occupied"] = w["units"] + w["damaged"]
            w["available_capacity"] = max(w["capacity"] - w["occupied"], 0)
            w["utilization"] = round(w["occupied"] * 100 / w["capacity"], 1) if w["capacity"] else 0
        return out

    @app.get("/api/warehouses")
    @require()
    def warehouses():
        return jsonify(wh_stats())

    @app.get("/api/warehouses/<int:wid>")
    @require()
    def warehouse_detail(wid):
        services.enforce_scope(wid)
        w = next((x for x in wh_stats() if x["id"] == wid), None)
        if not w:
            raise ApiError("Warehouse not found", 404)
        w["inventory"] = services.product_rows(wid)
        w["recent"] = rows("""SELECT m.*, p.name product_name FROM movements m LEFT JOIN products p ON p.id=m.product_id
                              WHERE m.source_wh=? OR m.dest_wh=? ORDER BY m.id DESC LIMIT 15""", (wid, wid))
        return jsonify(w)

    def clean_wh(d, wid=None):
        name = need_str(d, "name", "Warehouse name", 80)
        loc = need_str(d, "location", "Location", 120)
        mgr = need_str(d, "manager", "Manager", 80)
        cap = need_int(d, "capacity", "Capacity", 1, 10000000)
        status = d.get("status", "Active")
        if status not in ("Active", "Inactive", "Maintenance"):
            raise ApiError("Invalid status", field="status")
        if wid and cap < services.occupied(wid):
            raise ApiError(f"Capacity cannot be lower than the {services.occupied(wid)} units currently stored", field="capacity")
        return name, loc, mgr, cap, status

    @app.post("/api/warehouses")
    @require("*")
    def warehouse_create():
        name, loc, mgr, cap, status = clean_wh(body())
        n = scalar("SELECT COALESCE(MAX(id),0) FROM warehouses") + 1
        db().execute("INSERT INTO warehouses(code,name,location,manager,capacity,status,created_at) VALUES(?,?,?,?,?,?,?)", (f"WH-{n:02d}", name, loc, mgr, cap, status, now_s()))
        return jsonify({"ok": True}), 201

    @app.put("/api/warehouses/<int:wid>")
    @require("*")
    def warehouse_update(wid):
        services.get_wh(wid)
        name, loc, mgr, cap, status = clean_wh(body(), wid)
        db().execute("UPDATE warehouses SET name=?, location=?, manager=?, capacity=?, status=? WHERE id=?", (name, loc, mgr, cap, status, wid))
        return jsonify({"ok": True})

    @app.delete("/api/warehouses/<int:wid>")
    @require("*")
    def warehouse_delete(wid):
        services.get_wh(wid)
        if scalar("SELECT COALESCE(SUM(quantity+reserved+damaged),0) FROM stock WHERE warehouse_id=?", (wid,)):
            raise ApiError("This warehouse still holds stock. Transfer it to another warehouse first.")
        if scalar("SELECT COUNT(*) FROM orders WHERE warehouse_id=? AND status IN ('PENDING','CONFIRMED','PROCESSING','PACKED')", (wid,)):
            raise ApiError("This warehouse has open customer orders")
        if scalar("SELECT COUNT(*) FROM users WHERE warehouse_id=?", (wid,)):
            raise ApiError("Staff accounts are assigned to this warehouse. Reassign them first.")
        db().execute("DELETE FROM warehouses WHERE id=?", (wid,))
        db().execute("DELETE FROM stock WHERE warehouse_id=?", (wid,))
        return jsonify({"ok": True})

    # ================================================================ movements
    @app.get("/api/movements")
    @require()
    def movements():
        a = request.args
        where, args = ["1=1"], []
        wid = wh_filter(a.get("warehouse"))
        if wid:
            where.append("(m.source_wh=? OR m.dest_wh=?)")
            args += [wid, wid]
        if a.get("type"):
            where.append("m.type=?")
            args.append(a["type"])
        if a.get("from"):
            where.append("substr(m.ts,1,10)>=?")
            args.append(a["from"])
        if a.get("to"):
            where.append("substr(m.ts,1,10)<=?")
            args.append(a["to"])
        if a.get("q"):
            where.append("(lower(m.txn_id) LIKE ? OR lower(p.name) LIKE ? OR lower(p.code) LIKE ? OR lower(m.reference) LIKE ?)")
            args += [f"%{a['q'].lower()}%"] * 4
        limit = min(int(a.get("limit", 400)), 2000)
        data = rows(f"""SELECT m.*, COALESCE(p.name,'(deleted product)') product_name, p.code product_code, ws.name src_name, wd.name dst_name
                        FROM movements m LEFT JOIN products p ON p.id=m.product_id LEFT JOIN warehouses ws ON ws.id=m.source_wh
                        LEFT JOIN warehouses wd ON wd.id=m.dest_wh WHERE {' AND '.join(where)} ORDER BY m.id DESC LIMIT ?""", tuple(args) + (limit,))
        totals = rows(f"SELECT m.type, COUNT(*) c, SUM(m.quantity) q FROM movements m LEFT JOIN products p ON p.id=m.product_id WHERE {' AND '.join(where)} GROUP BY m.type", tuple(args))
        return jsonify({"items": data, "totals": {t["type"]: {"count": t["c"], "units": t["q"]} for t in totals}})

    @app.post("/api/movements")
    @require("stock.move")
    def movement_create():
        d = body()
        typ = d.get("type")
        if typ == "TRANSFER" and not can("stock.transfer"):
            raise ApiError("Only warehouse managers and administrators can process transfers", 403)
        pid = need_int(d, "product_id", "Product")
        qty = need_int(d, "quantity", "Quantity", 1)
        m = services.apply_movement(typ, pid, qty, src=int(d["source_wh"]) if d.get("source_wh") else None,
                                    dst=int(d["dest_wh"]) if d.get("dest_wh") else None, ref=str(d.get("reference", "")).strip(),
                                    note=str(d.get("note", "")).strip(), batch_no=d.get("batch_no") or None, expiry=opt_date(d, "expiry_date"))
        return jsonify(m), 201
