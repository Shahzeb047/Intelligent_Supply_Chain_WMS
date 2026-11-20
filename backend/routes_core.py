"""backend/routes_core.py - auth, users, settings, meta data, notifications, global search."""
import re
import time

from flask import jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from . import database, services
from .core import (ApiError, PAGES, body, can, current_user, db, get_setting, log_activity, need_str, now_s, one, require, rows,
                   scalar, scope_wh, wh_filter, PERMS, load_state)
from .database import CATEGORY_EMOJI

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_last_sync = {"t": 0}


def sync_throttled(force=False):
    if force or time.time() - _last_sync["t"] > 15:
        services.sync_notifications()
        _last_sync["t"] = time.time()


def user_payload(u):
    wh = one("SELECT name FROM warehouses WHERE id=?", (u["warehouse_id"],)) if u["warehouse_id"] else None
    return {"id": u["id"], "username": u["username"], "full_name": u["full_name"], "email": u["email"], "role": u["role"],
            "warehouse_id": u["warehouse_id"], "warehouse_name": wh["name"] if wh else "All warehouses",
            "pages": [p for p, roles in PAGES.items() if u["role"] in roles],
            "perms": ["*"] if u["role"] == "admin" else sorted(PERMS[u["role"]])}


def register(app):
    @app.post("/api/auth/login")
    def login():
        d = body()
        u = one("SELECT * FROM users WHERE username=?", (str(d.get("username", "")).strip().lower(),))
        if not u or not check_password_hash(u["password_hash"], str(d.get("password", ""))):
            raise ApiError("Incorrect username or password", 401)
        if not u["active"]:
            raise ApiError("This account has been deactivated", 403)
        session.clear()
        session["uid"] = u["id"]
        session.permanent = True
        from flask import g
        g.user = u
        log_activity("LOGIN", "Auth", f"{u['full_name']} signed in ({u['role']})")
        return jsonify(user_payload(u))

    @app.post("/api/auth/logout")
    def logout():
        session.clear()
        return jsonify({"ok": True})

    @app.get("/api/auth/me")
    @require()
    def me():
        return jsonify(user_payload(current_user()))

    @app.put("/api/auth/profile")
    @require()
    def profile():
        d, u = body(), current_user()
        name = need_str(d, "full_name", "Full name")
        email = str(d.get("email", "")).strip()
        if email and not EMAIL.match(email):
            raise ApiError("Enter a valid email address", field="email")
        db().execute("UPDATE users SET full_name=?, email=? WHERE id=?", (name, email, u["id"]))
        pw = str(d.get("password", ""))
        if pw:
            if len(pw) < 6:
                raise ApiError("Password must be at least 6 characters", field="password")
            db().execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(pw), u["id"]))
        return jsonify({"ok": True})

    # ------------------------------------------------------------- meta
    @app.get("/api/meta")
    @require()
    def meta():
        s = scope_wh()
        whs = rows("SELECT id,code,name,status FROM warehouses" + (" WHERE id=?" if s else "") + " ORDER BY id", (s,) if s else ())
        cats = sorted(set(CATEGORY_EMOJI) | {r["category"] for r in rows("SELECT DISTINCT category FROM products") if r["category"]})
        prods = [{"id": p["id"], "code": p["code"], "name": p["name"], "sku": p["sku"], "category": p["category"], "price": p["selling_price"],
                  "cost": p["purchase_price"], "expiry_tracked": p["expiry_tracked"]} for p in services.product_rows()]
        return jsonify({"warehouses": whs, "all_warehouses": rows("SELECT id,code,name,status FROM warehouses ORDER BY id"),
                        "categories": cats, "emoji": CATEGORY_EMOJI, "products": prods,
                        "suppliers": rows("SELECT id,code,name,status FROM suppliers ORDER BY name"),
                        "settings": {k: get_setting(k) for k in ("company_name", "currency", "expiry_warning_days", "capacity_warning_pct", "po_pending_days")}})

    # ------------------------------------------------------------- users (admin)
    @app.get("/api/users")
    @require("*")
    def users():
        return jsonify(rows("SELECT u.id,u.username,u.full_name,u.email,u.role,u.warehouse_id,u.active,u.created_at,w.name warehouse_name "
                            "FROM users u LEFT JOIN warehouses w ON w.id=u.warehouse_id ORDER BY u.id"))

    def clean_user(d, uid=None):
        username = need_str(d, "username", "Username", 40).lower()
        if not re.match(r"^[a-z0-9_.-]{3,}$", username):
            raise ApiError("Username needs 3+ letters/numbers (no spaces)", field="username")
        if one("SELECT id FROM users WHERE username=? AND id!=?", (username, uid or 0)):
            raise ApiError("This username is already taken", field="username")
        role = d.get("role")
        if role not in ("admin", "manager", "employee"):
            raise ApiError("Choose a role", field="role")
        wid = d.get("warehouse_id") or None
        if role != "admin" and not wid:
            raise ApiError("Managers and employees must be assigned to a warehouse", field="warehouse_id")
        email = str(d.get("email", "")).strip()
        if email and not EMAIL.match(email):
            raise ApiError("Enter a valid email address", field="email")
        return username, need_str(d, "full_name", "Full name"), email, role, (int(wid) if wid and role != "admin" else None)

    @app.post("/api/users")
    @require("*")
    def user_create():
        d = body()
        username, name, email, role, wid = clean_user(d)
        pw = str(d.get("password", ""))
        if len(pw) < 6:
            raise ApiError("Password must be at least 6 characters", field="password")
        db().execute("INSERT INTO users(username,password_hash,full_name,email,role,warehouse_id,created_at) VALUES(?,?,?,?,?,?,?)",
                     (username, generate_password_hash(pw), name, email, role, wid, now_s()))
        log_activity("CREATE", "Users", f"User {username} created ({role})")
        return jsonify({"ok": True}), 201

    @app.put("/api/users/<int:uid>")
    @require("*")
    def user_update(uid):
        d = body()
        if not one("SELECT id FROM users WHERE id=?", (uid,)):
            raise ApiError("User not found", 404)
        username, name, email, role, wid = clean_user(d, uid)
        active = 1 if d.get("active", True) else 0
        if uid == current_user()["id"] and (role != "admin" or not active):
            raise ApiError("You cannot remove your own admin access")
        db().execute("UPDATE users SET username=?, full_name=?, email=?, role=?, warehouse_id=?, active=? WHERE id=?", (username, name, email, role, wid, active, uid))
        pw = str(d.get("password", ""))
        if pw:
            if len(pw) < 6:
                raise ApiError("Password must be at least 6 characters", field="password")
            db().execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(pw), uid))
        return jsonify({"ok": True})

    @app.delete("/api/users/<int:uid>")
    @require("*")
    def user_delete(uid):
        if uid == current_user()["id"]:
            raise ApiError("You cannot delete your own account")
        db().execute("DELETE FROM users WHERE id=?", (uid,))
        return jsonify({"ok": True})

    # ------------------------------------------------------------- settings
    @app.put("/api/settings")
    @require("*")
    def settings_save():
        d = body()
        for k in ("company_name", "currency", "expiry_warning_days", "capacity_warning_pct", "po_pending_days"):
            if k in d:
                v = str(d[k]).strip()
                if k != "company_name" and k != "currency" and (not v.isdigit() or int(v) < 1):
                    raise ApiError("Alert thresholds must be positive whole numbers", field=k)
                db().execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (k, v))
        sync_throttled(True)
        return jsonify({"ok": True})

    @app.post("/api/system/reset")
    @require("*")
    def system_reset():
        from flask import g
        uid = current_user()["id"]
        db().commit()
        db().close()
        g.pop("db", None)
        database.init_db(force=True)
        load_state()
        session["uid"] = 1
        return jsonify({"ok": True})

    # ------------------------------------------------------------- notifications
    def notif_filter():
        s = scope_wh()
        return ("AND (warehouse_id IS NULL OR warehouse_id=?)", (s,)) if s else ("", ())

    @app.get("/api/notifications")
    @require()
    def notifications():
        sync_throttled()
        f, a = notif_filter()
        cat = request.args.get("category")
        extra, args = ("AND category=?", (cat,)) if cat and cat != "all" else ("", ())
        items = rows(f"SELECT * FROM notifications WHERE dismissed=0 {f} {extra} ORDER BY is_read, "
                     f"CASE severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END, ts DESC LIMIT 200", a + args)
        unread = scalar(f"SELECT COUNT(*) FROM notifications WHERE dismissed=0 AND is_read=0 {f}", a)
        counts = {r["category"]: r["c"] for r in rows(f"SELECT category, COUNT(*) c FROM notifications WHERE dismissed=0 {f} GROUP BY category", a)}
        return jsonify({"items": items, "unread": unread, "counts": counts})

    @app.post("/api/notifications/read")
    @require()
    def notif_read():
        d = body()
        f, a = notif_filter()
        if d.get("all"):
            db().execute(f"UPDATE notifications SET is_read=1 WHERE 1=1 {f}", a)
        else:
            db().execute("UPDATE notifications SET is_read=? WHERE id=?", (0 if d.get("unread") else 1, int(d.get("id", 0))))
        return jsonify({"ok": True})

    @app.post("/api/notifications/clear")
    @require()
    def notif_clear():
        f, a = notif_filter()
        db().execute(f"UPDATE notifications SET dismissed=1, is_read=1 WHERE 1=1 {f}", a)
        return jsonify({"ok": True})

    # ------------------------------------------------------------- global search
    @app.get("/api/search")
    @require()
    def search():
        q = request.args.get("q", "").strip()
        if len(q) < 2:
            return jsonify({"results": []})
        like, out = f"%{q.lower()}%", []
        wid = scope_wh()
        for p in services.product_rows(wid):
            if q.lower() in " ".join([p["name"], p["code"], p["sku"], p["barcode"] or "", p["category"]]).lower():
                out.append({"type": "Product", "title": p["name"], "sub": f"{p['sku']} - {p['available']} available", "page": "inventory", "id": p["id"]})
            if len(out) >= 6:
                break
        ws = "AND warehouse_id=?" if wid else ""
        wa = (wid,) if wid else ()
        for o in rows(f"SELECT id,order_no,customer_name,status FROM orders WHERE (lower(order_no) LIKE ? OR lower(customer_name) LIKE ?) {ws} ORDER BY id DESC LIMIT 5", (like, like) + wa):
            out.append({"type": "Order", "title": o["order_no"], "sub": f"{o['customer_name']} - {o['status'].title()}", "page": "orders", "id": o["id"]})
        if can("supplier.write"):
            for s in rows("SELECT id,name,categories FROM suppliers WHERE lower(name) LIKE ? LIMIT 3", (like,)):
                out.append({"type": "Supplier", "title": s["name"], "sub": s["categories"], "page": "suppliers", "id": s["id"]})
        for s in rows(f"SELECT id,shipment_no,customer_name FROM shipments WHERE (lower(shipment_no) LIKE ? OR lower(tracking_no) LIKE ?) {'AND origin_wh=?' if wid else ''} LIMIT 3", (like, like) + wa):
            out.append({"type": "Shipment", "title": s["shipment_no"], "sub": s["customer_name"], "page": "shipments", "id": s["id"]})
        return jsonify({"results": out[:14]})

    @app.get("/api/activity")
    @require()
    def activity():
        limit = min(int(request.args.get("limit", 100)), 500)
        s = request.args.get("structure")
        if s:
            return jsonify(rows("SELECT * FROM activity WHERE structure LIKE ? ORDER BY id DESC LIMIT ?", (f"%{s}%", limit)))
        return jsonify(rows("SELECT * FROM activity ORDER BY id DESC LIMIT ?", (limit,)))
