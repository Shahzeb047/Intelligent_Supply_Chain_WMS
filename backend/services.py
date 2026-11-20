"""
backend/services.py - business rules of the warehouse.

Every product record lives in the custom Inventory Queue (ds/queue.py);
stock levels, batches and transactions are kept in SQLite.  Customer orders flow
through the Order Queue -> Dispatch Queue (FIFO).
"""
import random
import uuid
from datetime import date, datetime, timedelta

from .core import (ApiError, db, rows, one, scalar, now_s, today_s, current_user, lock, get_setting,
                   inventory_q, order_q, dispatch_q, log_activity, scope_wh)

PARTNERS = ["TCS", "Leopards Courier", "M&P Express", "BlueEx", "Trax Logistics"]
ORDER_FLOW = ["PENDING", "CONFIRMED", "PROCESSING", "PACKED", "DISPATCHED", "DELIVERED"]


def actor():
    u = current_user()
    return u["full_name"] if u else "System"


# ================================================================== products
def get_product(pid):
    """READ from the Inventory Queue by rotation (dequeue -> check -> enqueue)."""
    with lock:
        p = inventory_q.find(lambda x: x["id"] == pid)
    if not p:
        raise ApiError("Product not found", 404)
    return p


def get_wh(wid, must_be_active=False):
    w = one("SELECT * FROM warehouses WHERE id=?", (wid,))
    if not w:
        raise ApiError("Warehouse not found", 404)
    if must_be_active and w["status"] != "Active":
        raise ApiError(f"{w['name']} is {w['status']} and cannot receive stock", field="warehouse_id")
    return w


def enforce_scope(wid):
    s = scope_wh()
    if s and wid and int(wid) != int(s):
        raise ApiError("You can only work with your assigned warehouse", 403)


def occupied(wid):
    return scalar("SELECT COALESCE(SUM(quantity+damaged),0) FROM stock WHERE warehouse_id=?", (wid,))


def check_capacity(wid, add):
    w = get_wh(wid, must_be_active=True)
    free = w["capacity"] - occupied(wid)
    if add > free:
        raise ApiError(f"{w['name']} has only {max(free, 0)} free capacity units (needs {add})", field="quantity")


def stock_row(pid, wid, create=False):
    r = one("SELECT * FROM stock WHERE product_id=? AND warehouse_id=?", (pid, wid))
    if not r:
        if create:
            db().execute("INSERT INTO stock(product_id,warehouse_id,quantity,reserved,damaged) VALUES(?,?,0,0,0)", (pid, wid))
            return dict(product_id=pid, warehouse_id=wid, quantity=0, reserved=0, damaged=0)
        return dict(product_id=pid, warehouse_id=wid, quantity=0, reserved=0, damaged=0)
    return r


def product_rows(wid=None):
    """All products (traversing the Inventory Queue) enriched with stock figures."""
    with lock:
        items = [dict(p) for p in inventory_q]
    where, args = ("WHERE warehouse_id=?", (wid,)) if wid else ("", ())
    agg = {r["product_id"]: r for r in rows(f"SELECT product_id, SUM(quantity) q, SUM(reserved) r, SUM(damaged) d FROM stock {where} GROUP BY product_id", args)}
    sup = {s["id"]: s["name"] for s in rows("SELECT id,name FROM suppliers")}
    whs = {w["id"]: w["name"] for w in rows("SELECT id,name FROM warehouses")}
    out = []
    for p in items:
        a = agg.get(p["id"])
        if wid and not a:
            continue
        q, r, d = (a["q"], a["r"], a["d"]) if a else (0, 0, 0)
        p.update(on_hand=q, reserved=r, damaged=d, available=q - r, supplier_name=sup.get(p["supplier_id"], "-"),
                 warehouse_name=whs.get(p["warehouse_id"], "-"), value=q * p["purchase_price"])
        p["status"] = "OUT" if p["available"] <= 0 else ("LOW" if p["available"] <= p["reorder_level"] else "OK")
        out.append(p)
    return out


# ------------------------------------------------------------ batches (FEFO)
def batch_add(p, wid, qty, expiry=None, batch_no=None):
    if not p["expiry_tracked"]:
        return
    expiry = expiry or (date.today() + timedelta(days=365)).strftime("%Y-%m-%d")
    batch_no = batch_no or f"B{datetime.now():%y%m%d%H%M%S}-{p['id']:02d}"
    db().execute("INSERT INTO batches(product_id,warehouse_id,batch_no,quantity,expiry_date,received_date) VALUES(?,?,?,?,?,?)",
                 (p["id"], wid, batch_no, qty, expiry, today_s()))


def batch_take(pid, wid, qty):
    """Consume `qty` from batches, earliest expiry first. Returns [(expiry, qty, batch_no)] taken."""
    taken = []
    for b in rows("SELECT * FROM batches WHERE product_id=? AND warehouse_id=? AND quantity>0 ORDER BY expiry_date, id", (pid, wid)):
        if qty <= 0:
            break
        t = min(b["quantity"], qty)
        db().execute("UPDATE batches SET quantity=quantity-? WHERE id=?", (t, b["id"]))
        taken.append((b["expiry_date"], t, b["batch_no"]))
        qty -= t
    db().execute("DELETE FROM batches WHERE quantity<=0")
    return taken


# ================================================================== movements
def apply_movement(typ, pid, qty, src=None, dst=None, ref="", note="", batch_no=None, expiry=None, from_reserved=False):
    """
    Single entry point that changes stock.  Validates, updates stock + batches,
    writes the transaction and returns it.
    """
    if typ not in ("STOCK_IN", "STOCK_OUT", "TRANSFER", "RETURN", "DAMAGED"):
        raise ApiError("Unknown movement type", field="type")
    try:
        qty = int(qty)
    except (TypeError, ValueError):
        raise ApiError("Quantity must be a whole number", field="quantity")
    if qty <= 0:
        raise ApiError("Quantity must be greater than zero", field="quantity")
    p = get_product(pid)
    c = db()
    if typ in ("STOCK_IN", "RETURN"):
        if not dst:
            raise ApiError("Destination warehouse is required", field="dest_wh")
        enforce_scope(dst)
        check_capacity(dst, qty)
        if p["expiry_tracked"] and not expiry and typ == "STOCK_IN":
            raise ApiError("Expiry date is required for this perishable product", field="expiry_date")
        stock_row(pid, dst, True)
        c.execute("UPDATE stock SET quantity=quantity+? WHERE product_id=? AND warehouse_id=?", (qty, pid, dst))
        batch_add(p, dst, qty, expiry, batch_no)
        src = None
    elif typ in ("STOCK_OUT", "DAMAGED"):
        if not src:
            raise ApiError("Source warehouse is required", field="source_wh")
        enforce_scope(src)
        get_wh(src)
        s = stock_row(pid, src)
        have = s["quantity"] if from_reserved else s["quantity"] - s["reserved"]
        if qty > have:
            raise ApiError(f"Only {have} units of {p['name']} are available in that warehouse", field="quantity")
        if from_reserved:
            c.execute("UPDATE stock SET quantity=quantity-?, reserved=MAX(reserved-?,0) WHERE product_id=? AND warehouse_id=?", (qty, qty, pid, src))
        else:
            c.execute("UPDATE stock SET quantity=quantity-? WHERE product_id=? AND warehouse_id=?", (qty, pid, src))
        if typ == "DAMAGED":
            c.execute("UPDATE stock SET damaged=damaged+? WHERE product_id=? AND warehouse_id=?", (qty, pid, src))
        batch_take(pid, src, qty)
        dst = None
    else:  # TRANSFER
        if not src or not dst:
            raise ApiError("Source and destination warehouses are required", field="dest_wh")
        if int(src) == int(dst):
            raise ApiError("Source and destination must be different", field="dest_wh")
        enforce_scope(src)
        get_wh(src)
        s = stock_row(pid, src)
        if qty > s["quantity"] - s["reserved"]:
            raise ApiError(f"Only {s['quantity'] - s['reserved']} units of {p['name']} are available at the source warehouse", field="quantity")
        check_capacity(dst, qty)
        stock_row(pid, dst, True)
        c.execute("UPDATE stock SET quantity=quantity-? WHERE product_id=? AND warehouse_id=?", (qty, pid, src))
        c.execute("UPDATE stock SET quantity=quantity+? WHERE product_id=? AND warehouse_id=?", (qty, pid, dst))
        for exp, t, bno in batch_take(pid, src, qty):
            batch_add(p, dst, t, exp, bno)
    n = scalar("SELECT COALESCE(MAX(id),0) FROM movements") + 1
    txn = f"TXN-{n:06d}"
    c.execute("INSERT INTO movements(txn_id,product_id,quantity,type,source_wh,dest_wh,ts,employee,reference,note) VALUES(?,?,?,?,?,?,?,?,?,?)",
              (txn, pid, qty, typ, src, dst, now_s(), actor(), ref, note))
    if typ == "TRANSFER":
        notify_event(f"xfer:{txn}", "transfer", "success", "Stock transfer completed",
                     f"{qty} x {p['name']} moved to {get_wh(dst)['name']} ({txn})", dst, "movements")
    return {"txn_id": txn, "type": typ, "product_id": pid, "quantity": qty}


# ================================================================== notifications
STATE_CATS = ("stock", "expiry", "purchase", "shipment", "capacity")


def notify_event(key, category, severity, title, message, wid=None, link=None):
    db().execute("INSERT OR IGNORE INTO notifications(key,category,severity,title,message,ts,warehouse_id,link) VALUES(?,?,?,?,?,?,?,?)",
                 (key, category, severity, title, message, now_s(), wid, link))


def sync_notifications():
    """Create/refresh condition-based alerts (rule-based smart alerts)."""
    c = db()
    active = {}
    for r in rows("""SELECT p.id,p.name,p.reorder_level, COALESCE(SUM(s.quantity-s.reserved),0) av
                     FROM products p LEFT JOIN stock s ON s.product_id=p.id GROUP BY p.id"""):
        if r["av"] <= 0:
            active[f"out:{r['id']}"] = ("stock", "critical", "Out of stock", f"{r['name']} is out of stock.", None, "inventory")
        elif r["av"] <= r["reorder_level"]:
            active[f"low:{r['id']}"] = ("stock", "warning", "Low stock", f"{r['name']}: {r['av']} units left (reorder level {r['reorder_level']}).", None, "inventory")
    warn = int(get_setting("expiry_warning_days", "30") or 30)
    limit = (date.today() + timedelta(days=warn)).strftime("%Y-%m-%d")
    for b in rows("""SELECT b.id,b.quantity,b.expiry_date,b.batch_no,b.warehouse_id,p.name FROM batches b JOIN products p ON p.id=b.product_id
                     WHERE b.quantity>0 AND b.expiry_date<=?""", (limit,)):
        expired = b["expiry_date"] < today_s()
        active[f"exp:{b['id']}"] = ("expiry", "critical" if expired else "warning", "Batch expired" if expired else "Expiring soon",
                                    f"{b['name']} batch {b['batch_no']} ({b['quantity']} units) {'expired on' if expired else 'expires on'} {b['expiry_date']}.",
                                    b["warehouse_id"], "inventory")
    days = int(get_setting("po_pending_days", "3") or 3)
    lim = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    for r in rows("SELECT id,po_no,warehouse_id,created_at FROM purchase_orders WHERE status='PENDING' AND substr(created_at,1,10)<=?", (lim,)):
        active[f"po:{r['id']}"] = ("purchase", "warning", "Purchase order pending", f"{r['po_no']} has been pending since {r['created_at'][:10]}.", r["warehouse_id"], "purchase")
    for r in rows("SELECT id,shipment_no,order_id,origin_wh,expected_date,customer_name FROM shipments WHERE status!='DELIVERED' AND expected_date<?", (today_s(),)):
        active[f"ship:{r['id']}"] = ("shipment", "critical", "Delayed shipment", f"{r['shipment_no']} to {r['customer_name']} was expected on {r['expected_date']}.", r["origin_wh"], "shipments")
    pct = int(get_setting("capacity_warning_pct", "85") or 85)
    for w in rows("SELECT id,name,capacity FROM warehouses"):
        occ = occupied(w["id"])
        if w["capacity"] and occ * 100 / w["capacity"] >= pct:
            active[f"cap:{w['id']}"] = ("capacity", "warning", "Warehouse capacity warning", f"{w['name']} is {round(occ * 100 / w['capacity'])}% full.", w["id"], "warehouses")
    existing = {r["key"] for r in rows("SELECT key FROM notifications WHERE category IN (%s)" % ",".join("?" * len(STATE_CATS)), STATE_CATS)}
    for k, (cat, sev, title, msg, wid, link) in active.items():
        if k not in existing:
            c.execute("INSERT INTO notifications(key,category,severity,title,message,ts,warehouse_id,link) VALUES(?,?,?,?,?,?,?,?)",
                      (k, cat, sev, title, msg, now_s(), wid, link))
    for k in existing - set(active):
        c.execute("DELETE FROM notifications WHERE key=?", (k,))


# ================================================================== orders
def order_detail(oid):
    o = one("SELECT o.*, w.name warehouse_name FROM orders o LEFT JOIN warehouses w ON w.id=o.warehouse_id WHERE o.id=?", (oid,))
    if not o:
        raise ApiError("Order not found", 404)
    s = scope_wh()
    if s and o["warehouse_id"] != s:
        raise ApiError("Order not found", 404)
    o["items"] = rows("""SELECT i.*, COALESCE(p.name,'(deleted product)') name, p.code, p.sku FROM order_items i
                         LEFT JOIN products p ON p.id=i.product_id WHERE i.order_id=?""", (oid,))
    o["history"] = rows("SELECT status,ts,by_user FROM order_history WHERE order_id=? ORDER BY id", (oid,))
    o["shipment"] = one("SELECT * FROM shipments WHERE order_id=?", (oid,))
    o["returns"] = rows("SELECT r.*, p.name product_name FROM returns r LEFT JOIN products p ON p.id=r.product_id WHERE r.order_id=? ORDER BY r.id", (oid,))
    pos = None
    if o["status"] == "PENDING":
        with lock:
            pos = 1 + next((i for i, x in enumerate(order_q) if x["id"] == oid), -1)
    elif o["status"] == "PACKED":
        with lock:
            pos = 1 + next((i for i, x in enumerate(dispatch_q) if x["id"] == oid), -1)
    o["queue_position"] = pos if pos else None
    return o


def add_history(oid, status):
    db().execute("INSERT INTO order_history(order_id,status,ts,by_user) VALUES(?,?,?,?)", (oid, status, now_s(), actor()))
    db().execute("UPDATE orders SET status=?, updated_at=? WHERE id=?", (status, now_s(), oid))


def create_order(d):
    from .core import need_str, need_int, need_num
    customer = need_str(d, "customer_name", "Customer name")
    wid = need_int(d, "warehouse_id", "Warehouse")
    enforce_scope(wid)
    get_wh(wid)
    disc = need_num(d, "discount_pct", "Discount", 0, default=0)
    if disc > 100:
        raise ApiError("Discount cannot exceed 100%", field="discount_pct")
    raw = d.get("items") or []
    if not raw:
        raise ApiError("Add at least one product to the order", field="items")
    merged = {}
    for it in raw:
        pid = need_int(it, "product_id", "Product")
        qty = need_int(it, "quantity", "Quantity", 1)
        merged[pid] = merged.get(pid, 0) + qty
    lines, problems = [], []
    for pid, qty in merged.items():
        p = get_product(pid)
        s = stock_row(pid, wid)
        av = s["quantity"] - s["reserved"]
        if qty > av:
            problems.append(f"{p['name']}: requested {qty}, only {av} available")
        lines.append((p, qty))
    if problems:
        raise ApiError("Insufficient stock - " + "; ".join(problems), field="items")
    c = db()
    sub = sum(p["selling_price"] * q for p, q in lines)
    total = round(sub * (1 - disc / 100), 2)
    tmp = "TMP-" + uuid.uuid4().hex[:10]
    cur = c.execute("""INSERT INTO orders(order_no,customer_name,phone,destination,warehouse_id,status,discount_pct,subtotal,total,created_at,updated_at,created_by,notes)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (tmp, customer, str(d.get("phone", "")).strip(), str(d.get("destination", "")).strip(), wid, "PENDING", disc, sub, total,
                     now_s(), now_s(), actor(), str(d.get("notes", "")).strip()))
    oid = cur.lastrowid
    no = f"ORD-{oid:06d}"
    c.execute("UPDATE orders SET order_no=? WHERE id=?", (no, oid))
    for p, q in lines:
        c.execute("INSERT INTO order_items(order_id,product_id,quantity,unit_price) VALUES(?,?,?,?)", (oid, p["id"], q, p["selling_price"]))
        c.execute("UPDATE stock SET reserved=reserved+? WHERE product_id=? AND warehouse_id=?", (q, p["id"], wid))
    c.execute("INSERT INTO order_history(order_id,status,ts,by_user) VALUES(?,?,?,?)", (oid, "PENDING", now_s(), actor()))
    row = one("SELECT * FROM orders WHERE id=?", (oid,))
    with lock:
        order_q.enqueue(row)                                  # ENQUEUE at REAR
    log_activity("ENQUEUE", "Order Queue", f"{no} for {customer} joined the REAR of the order queue")
    notify_event(f"neworder:{oid}", "order", "info", "New customer order", f"{no} from {customer} (Rs {total:,.0f}) is waiting in the order queue.", wid, "orders")
    return oid


def _release(oid):
    o = one("SELECT warehouse_id FROM orders WHERE id=?", (oid,))
    for i in rows("SELECT product_id, quantity FROM order_items WHERE order_id=?", (oid,)):
        db().execute("UPDATE stock SET reserved=MAX(reserved-?,0) WHERE product_id=? AND warehouse_id=?", (i["quantity"], i["product_id"], o["warehouse_id"]))


def process_next(all_=False):
    """DEQUEUE the oldest pending order(s): PENDING -> CONFIRMED."""
    s = scope_wh()
    done = []
    with lock:
        if order_q.is_empty():
            raise ApiError("The order queue is empty")
        while not order_q.is_empty():
            head = order_q.peek()
            if s and head["warehouse_id"] != s:
                if done:
                    break
                raise ApiError("The order at the FRONT of the queue belongs to another warehouse. FIFO means it must be served first.", 403)
            o = order_q.dequeue()                              # DEQUEUE from FRONT
            add_history(o["id"], "CONFIRMED")
            log_activity("DEQUEUE", "Order Queue", f"{o['order_no']} left the FRONT of the order queue and was confirmed")
            done.append(o["order_no"])
            if not all_:
                break
    return done


def advance_order(oid):
    """CONFIRMED -> PROCESSING -> PACKED (packed orders ENQUEUE into the dispatch queue)."""
    o = order_detail(oid)
    if o["status"] == "CONFIRMED":
        add_history(oid, "PROCESSING")
        return "PROCESSING"
    if o["status"] == "PROCESSING":
        add_history(oid, "PACKED")
        with lock:
            dispatch_q.enqueue(one("SELECT * FROM orders WHERE id=?", (oid,)))
        log_activity("ENQUEUE", "Dispatch Queue", f"{o['order_no']} packed and joined the dispatch queue")
        return "PACKED"
    if o["status"] == "PENDING":
        raise ApiError("This order is still waiting in the order queue. Use 'Process Next' - the oldest order is served first (FIFO).")
    raise ApiError(f"An order in status {o['status']} cannot be advanced here")


def dispatch_next(partner=None, all_=False):
    """DEQUEUE the oldest packed order: deduct stock, create the shipment."""
    s = scope_wh()
    done = []
    with lock:
        if dispatch_q.is_empty():
            raise ApiError("The dispatch queue is empty")
        while not dispatch_q.is_empty():
            head = dispatch_q.peek()
            if s and head["warehouse_id"] != s:
                if done:
                    break
                raise ApiError("The order at the FRONT of the dispatch queue belongs to another warehouse", 403)
            o = dispatch_q.dequeue()
            wid = o["warehouse_id"]
            for i in rows("SELECT product_id, quantity FROM order_items WHERE order_id=?", (o["id"],)):
                apply_movement("STOCK_OUT", i["product_id"], i["quantity"], src=wid, ref=o["order_no"], note="Customer order dispatch", from_reserved=True)
            add_history(o["id"], "DISPATCHED")
            sid = scalar("SELECT COALESCE(MAX(id),0) FROM shipments") + 1
            p = partner if partner in PARTNERS else random.Random(o["id"]).choice(PARTNERS)
            exp = (date.today() + timedelta(days=3)).strftime("%Y-%m-%d")
            db().execute("""INSERT INTO shipments(id,shipment_no,order_id,customer_name,origin_wh,destination,partner,tracking_no,dispatch_date,expected_date,status)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                         (sid, f"SHP-{sid:06d}", o["id"], o["customer_name"], wid, o["destination"], p, f"TRK{random.randint(10**9, 10**10 - 1)}", today_s(), exp, "DISPATCHED"))
            for st, delta in (("ORDER_CREATED", None), ("PROCESSING", None), ("PACKED", None), ("DISPATCHED", 0)):
                ts = one("SELECT MIN(ts) t FROM order_history WHERE order_id=? AND status=?", (o["id"], {"ORDER_CREATED": "PENDING"}.get(st, st)))
                db().execute("INSERT INTO shipment_events(shipment_id,status,ts) VALUES(?,?,?)", (sid, st, (ts or {}).get("t") or now_s()))
            log_activity("DEQUEUE", "Dispatch Queue", f"{o['order_no']} left the FRONT of the dispatch queue and was dispatched via {p}")
            done.append(o["order_no"])
            if not all_:
                break
    return done


def cancel_order(oid):
    o = order_detail(oid)
    if o["status"] not in ("PENDING", "CONFIRMED", "PROCESSING", "PACKED"):
        raise ApiError(f"An order that is {o['status'].title()} cannot be cancelled")
    with lock:
        if o["status"] == "PENDING":
            order_q.remove(lambda x: x["id"] == oid)           # DELETE from the middle by rotation
            log_activity("DELETE", "Order Queue", f"{o['order_no']} was removed from the order queue (cancelled)")
        elif o["status"] == "PACKED":
            dispatch_q.remove(lambda x: x["id"] == oid)
            log_activity("DELETE", "Dispatch Queue", f"{o['order_no']} was removed from the dispatch queue (cancelled)")
    _release(oid)
    add_history(oid, "CANCELLED")


def advance_shipment(sid):
    s = one("SELECT * FROM shipments WHERE id=?", (sid,))
    if not s:
        raise ApiError("Shipment not found", 404)
    sc = scope_wh()
    if sc and s["origin_wh"] != sc:
        raise ApiError("Shipment not found", 404)
    nxt = {"DISPATCHED": "IN_TRANSIT", "IN_TRANSIT": "DELIVERED"}.get(s["status"])
    if not nxt:
        raise ApiError("This shipment is already delivered")
    db().execute("UPDATE shipments SET status=? WHERE id=?", (nxt, sid))
    db().execute("INSERT INTO shipment_events(shipment_id,status,ts) VALUES(?,?,?)", (sid, nxt, now_s()))
    if nxt == "DELIVERED":
        db().execute("UPDATE shipments SET delivered_date=? WHERE id=?", (today_s(), sid))
        add_history(s["order_id"], "DELIVERED")
    return nxt


# ================================================================== returns
def create_return(d):
    from .core import need_str, need_int
    oid = need_int(d, "order_id", "Order")
    o = order_detail(oid)
    if o["status"] not in ("DELIVERED", "RETURNED"):
        raise ApiError("Only delivered orders can have returns", field="order_id")
    pid = need_int(d, "product_id", "Product")
    line = next((i for i in o["items"] if i["product_id"] == pid), None)
    if not line:
        raise ApiError("This product is not part of the selected order", field="product_id")
    qty = need_int(d, "quantity", "Quantity", 1)
    done = scalar("SELECT COALESCE(SUM(quantity),0) FROM returns WHERE order_id=? AND product_id=? AND status!='REJECTED'", (oid, pid))
    if qty > line["quantity"] - done:
        raise ApiError(f"Only {line['quantity'] - done} unit(s) of this product can still be returned", field="quantity")
    reason = need_str(d, "reason", "Reason")
    cond = d.get("condition", "RESELLABLE")
    if cond not in ("RESELLABLE", "DAMAGED"):
        raise ApiError("Choose the product condition", field="condition")
    tmp = "TMP-" + uuid.uuid4().hex[:8]
    cur = db().execute("""INSERT INTO returns(return_no,order_id,product_id,quantity,reason,condition,status,warehouse_id,refund_amount,created_at,note,created_by)
                          VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                       (tmp, oid, pid, qty, reason, cond, "PENDING", o["warehouse_id"], round(qty * line["unit_price"] * (1 - o["discount_pct"] / 100), 2),
                        now_s(), str(d.get("note", "")).strip(), actor()))
    db().execute("UPDATE returns SET return_no=? WHERE id=?", (f"RET-{cur.lastrowid:05d}", cur.lastrowid))
    notify_event(f"ret:{cur.lastrowid}", "return", "info", "New return request", f"RET-{cur.lastrowid:05d} for {o['order_no']} awaits approval.", o["warehouse_id"], "returns")
    return cur.lastrowid


def decide_return(rid, decision):
    r = one("SELECT * FROM returns WHERE id=?", (rid,))
    if not r:
        raise ApiError("Return not found", 404)
    sc = scope_wh()
    if sc and r["warehouse_id"] != sc:
        raise ApiError("Return not found", 404)
    if r["status"] != "PENDING":
        raise ApiError("This return has already been decided")
    c = db()
    if decision == "reject":
        c.execute("UPDATE returns SET status='REJECTED', decided_at=? WHERE id=?", (now_s(), rid))
        return "REJECTED"
    if r["condition"] == "RESELLABLE":
        apply_movement("RETURN", r["product_id"], r["quantity"], dst=r["warehouse_id"], ref=r["return_no"], note="Returned - restocked")
        restocked = 1
    else:
        stock_row(r["product_id"], r["warehouse_id"], True)
        c.execute("UPDATE stock SET damaged=damaged+? WHERE product_id=? AND warehouse_id=?", (r["quantity"], r["product_id"], r["warehouse_id"]))
        n = scalar("SELECT COALESCE(MAX(id),0) FROM movements") + 1
        c.execute("INSERT INTO movements(txn_id,product_id,quantity,type,source_wh,dest_wh,ts,employee,reference,note) VALUES(?,?,?,?,?,?,?,?,?,?)",
                  (f"TXN-{n:06d}", r["product_id"], r["quantity"], "DAMAGED", r["warehouse_id"], None, now_s(), actor(), r["return_no"], "Returned - damaged, not restocked"))
        restocked = 0
    c.execute("UPDATE returns SET status='APPROVED', decided_at=? WHERE id=?", (now_s(), rid))
    total_items = scalar("SELECT SUM(quantity) FROM order_items WHERE order_id=?", (r["order_id"],))
    total_ret = scalar("SELECT COALESCE(SUM(quantity),0) FROM returns WHERE order_id=? AND status='APPROVED'", (r["order_id"],))
    if total_ret >= total_items:
        add_history(r["order_id"], "RETURNED")
    return "APPROVED" if restocked else "APPROVED_DAMAGED"


# ================================================================== purchase orders
def po_detail(pid):
    po = one("""SELECT po.*, s.name supplier_name, w.name warehouse_name FROM purchase_orders po
                LEFT JOIN suppliers s ON s.id=po.supplier_id LEFT JOIN warehouses w ON w.id=po.warehouse_id WHERE po.id=?""", (pid,))
    if not po:
        raise ApiError("Purchase order not found", 404)
    sc = scope_wh()
    if sc and po["warehouse_id"] != sc:
        raise ApiError("Purchase order not found", 404)
    po["items"] = rows("""SELECT i.*, COALESCE(p.name,'(deleted product)') name, p.code, p.expiry_tracked FROM po_items i
                          LEFT JOIN products p ON p.id=i.product_id WHERE i.po_id=?""", (pid,))
    po["total"] = sum(i["quantity"] * i["unit_cost"] for i in po["items"])
    return po


def _po_items(d):
    from .core import need_int, need_num
    raw = d.get("items") or []
    if not raw:
        raise ApiError("Add at least one product to the purchase order", field="items")
    out = {}
    for it in raw:
        pid = need_int(it, "product_id", "Product")
        p = get_product(pid)
        q = need_int(it, "quantity", "Quantity", 1)
        cost = need_num(it, "unit_cost", "Unit cost", 0, default=p["purchase_price"])
        if pid in out:
            out[pid][0] += q
        else:
            out[pid] = [q, cost]
    return out


def save_po(d, pid=None):
    from .core import need_int, opt_date
    sup = need_int(d, "supplier_id", "Supplier")
    s = one("SELECT * FROM suppliers WHERE id=?", (sup,))
    if not s:
        raise ApiError("Supplier not found", field="supplier_id")
    if s["status"] != "Active":
        raise ApiError("This supplier is inactive", field="supplier_id")
    wid = need_int(d, "warehouse_id", "Destination warehouse")
    enforce_scope(wid)
    get_wh(wid)
    exp = opt_date(d, "expected_date")
    status = "PENDING" if d.get("submit") else "DRAFT"
    items = _po_items(d)
    c = db()
    if pid is None:
        tmp = "TMP-" + uuid.uuid4().hex[:8]
        cur = c.execute("INSERT INTO purchase_orders(po_no,supplier_id,warehouse_id,status,created_at,expected_date,notes,created_by) VALUES(?,?,?,?,?,?,?,?)",
                        (tmp, sup, wid, status, now_s(), exp, str(d.get("notes", "")).strip(), actor()))
        pid = cur.lastrowid
        c.execute("UPDATE purchase_orders SET po_no=? WHERE id=?", (f"PO-{pid:05d}", pid))
    else:
        po = po_detail(pid)
        if po["status"] != "DRAFT":
            raise ApiError("Only draft purchase orders can be edited")
        c.execute("UPDATE purchase_orders SET supplier_id=?, warehouse_id=?, expected_date=?, notes=?, status=? WHERE id=?",
                  (sup, wid, exp, str(d.get("notes", "")).strip(), status, pid))
        c.execute("DELETE FROM po_items WHERE po_id=?", (pid,))
    for prod_id, (q, cost) in items.items():
        c.execute("INSERT INTO po_items(po_id,product_id,quantity,received_qty,unit_cost) VALUES(?,?,?,0,?)", (pid, prod_id, q, cost))
    return pid


def po_status(pid, new):
    po = po_detail(pid)
    allowed = {"DRAFT": ("PENDING", "CANCELLED"), "PENDING": ("APPROVED", "CANCELLED"), "APPROVED": ("CANCELLED",)}
    if new not in allowed.get(po["status"], ()):
        raise ApiError(f"A {po['status'].replace('_', ' ').title()} order cannot become {new.replace('_', ' ').title()}")
    db().execute("UPDATE purchase_orders SET status=? WHERE id=?", (new, pid))


def po_receive(pid, lines):
    po = po_detail(pid)
    if po["status"] not in ("APPROVED", "PARTIALLY_RECEIVED"):
        raise ApiError("Only approved purchase orders can receive stock")
    by_id = {i["id"]: i for i in po["items"]}
    got = 0
    for ln in lines or []:
        it = by_id.get(int(ln.get("item_id", 0)))
        q = int(ln.get("quantity") or 0)
        if not it or q <= 0:
            continue
        if q > it["quantity"] - it["received_qty"]:
            raise ApiError(f"{it['name']}: only {it['quantity'] - it['received_qty']} units are still outstanding")
        apply_movement("STOCK_IN", it["product_id"], q, dst=po["warehouse_id"], ref=po["po_no"], note="Purchase receipt",
                       batch_no=ln.get("batch_no") or None, expiry=ln.get("expiry_date") or None)
        db().execute("UPDATE po_items SET received_qty=received_qty+? WHERE id=?", (q, it["id"]))
        got += q
    if not got:
        raise ApiError("Enter the quantity received for at least one item")
    left = scalar("SELECT SUM(quantity-received_qty) FROM po_items WHERE po_id=?", (pid,))
    if left <= 0:
        db().execute("UPDATE purchase_orders SET status='COMPLETED', received_date=? WHERE id=?", (today_s(), pid))
    else:
        db().execute("UPDATE purchase_orders SET status='PARTIALLY_RECEIVED' WHERE id=?", (pid,))
    return got
