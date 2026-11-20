"""backend/core.py - shared helpers: request-scoped DB, errors, auth, permissions, queues."""
import threading
from datetime import datetime, timedelta, date
from functools import wraps

from flask import g, jsonify, request, session

from . import database
from ds.queue import Queue

lock = threading.RLock()


# ------------------------------------------------------------------ queues
# PRIMARY DATA STRUCTURE (Group C): three custom FIFO queues.
inventory_q = Queue("Inventory Queue", labeler=lambda p: p["code"])
order_q = Queue("Order Queue", labeler=lambda o: o["order_no"])          # PENDING customer orders (FIFO)
dispatch_q = Queue("Dispatch Queue", labeler=lambda o: o["order_no"])    # PACKED orders waiting for dispatch (FIFO)
QUEUES = {"inventory": inventory_q, "orders": order_q, "dispatch": dispatch_q}


# ------------------------------------------------------------------ errors
class ApiError(Exception):
    def __init__(self, message, code=400, field=None):
        super().__init__(message)
        self.message, self.code, self.field = message, code, field


# ------------------------------------------------------------------ time
def now_dt():
    return datetime.now().replace(microsecond=0)


def now_s():
    return now_dt().strftime("%Y-%m-%d %H:%M:%S")


def today_s():
    return date.today().strftime("%Y-%m-%d")


# ------------------------------------------------------------------ db
def db():
    if "db" not in g:
        g.db = database.connect()
    return g.db


def rows(sql, args=()):
    return [dict(r) for r in db().execute(sql, args).fetchall()]


def one(sql, args=()):
    r = db().execute(sql, args).fetchone()
    return dict(r) if r else None


def scalar(sql, args=(), default=0):
    r = db().execute(sql, args).fetchone()
    return default if r is None or r[0] is None else r[0]


def get_setting(key, default=""):
    r = db().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r[0] if r else default


def log_activity(action, structure, detail):
    u = current_user()
    db().execute("INSERT INTO activity(ts,user,action,structure,detail) VALUES(?,?,?,?,?)",
                 (now_s(), u["full_name"] if u else "System", action, structure, detail))


# ------------------------------------------------------------------ auth / roles
PAGES = {  # page id -> roles allowed
    "overview": ("admin", "manager", "employee"),
    "inventory": ("admin", "manager", "employee"),
    "warehouses": ("admin", "manager"),
    "movements": ("admin", "manager", "employee"),
    "suppliers": ("admin", "manager"),
    "purchase": ("admin", "manager"),
    "orders": ("admin", "manager", "employee"),
    "shipments": ("admin", "manager", "employee"),
    "returns": ("admin", "manager", "employee"),
    "alerts": ("admin", "manager", "employee"),
    "analytics": ("admin", "manager"),
    "dsa": ("admin", "manager", "employee"),
    "settings": ("admin", "manager", "employee"),
}

PERMS = {
    "admin": {"*"},
    "manager": {"product.write", "warehouse.view", "stock.move", "stock.transfer", "supplier.write", "po.write", "order.write",
                "order.advance", "shipment.write", "return.write", "return.decide", "report.view", "reserve"},
    "employee": {"stock.move", "order.advance", "shipment.write", "return.write", "reserve"},
}


def current_user():
    if "user" in g:
        return g.user
    uid = session.get("uid")
    g.user = None
    if uid:
        r = db().execute("SELECT id,username,full_name,email,role,warehouse_id,active FROM users WHERE id=?", (uid,)).fetchone()
        if r and r["active"]:
            g.user = dict(r)
    return g.user


def can(perm):
    u = current_user()
    if not u:
        return False
    p = PERMS.get(u["role"], set())
    return "*" in p or perm in p


def require(perm=None):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if not current_user():
                return jsonify({"error": "Please sign in"}), 401
            if perm and not can(perm):
                return jsonify({"error": "You do not have permission to do this"}), 403
            return fn(*a, **kw)
        return wrapper
    return deco


def scope_wh():
    """Warehouse id the current user is restricted to (None = all warehouses)."""
    u = current_user()
    if not u or u["role"] == "admin":
        return None
    return u["warehouse_id"]


def wh_filter(request_wh=None):
    """Effective warehouse filter: restricted users are forced to their own warehouse."""
    s = scope_wh()
    if s:
        return s
    try:
        return int(request_wh) if request_wh not in (None, "", "all") else None
    except ValueError:
        return None


# ------------------------------------------------------------------ validation helpers
def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Invalid request body")
    return data


def need_str(d, k, label=None, maxlen=200):
    v = str(d.get(k, "") or "").strip()
    if not v:
        raise ApiError(f"{label or k.replace('_', ' ').title()} is required", field=k)
    if len(v) > maxlen:
        raise ApiError(f"{label or k} is too long", field=k)
    return v


def need_int(d, k, label=None, minv=None, maxv=None, default=None):
    raw = d.get(k, default)
    if raw in (None, "") and default is None:
        raise ApiError(f"{label or k.replace('_', ' ').title()} is required", field=k)
    try:
        v = int(float(raw if raw not in (None, "") else default))
    except (TypeError, ValueError):
        raise ApiError(f"{label or k} must be a whole number", field=k)
    if minv is not None and v < minv:
        raise ApiError(f"{label or k.replace('_', ' ').title()} must be at least {minv}", field=k)
    if maxv is not None and v > maxv:
        raise ApiError(f"{label or k.replace('_', ' ').title()} must be at most {maxv}", field=k)
    return v


def need_num(d, k, label=None, minv=0, default=None):
    raw = d.get(k, default)
    if raw in (None, ""):
        if default is None:
            raise ApiError(f"{label or k.replace('_', ' ').title()} is required", field=k)
        raw = default
    try:
        v = float(raw)
    except (TypeError, ValueError):
        raise ApiError(f"{label or k} must be a number", field=k)
    if v < minv:
        raise ApiError(f"{label or k.replace('_', ' ').title()} cannot be less than {minv}", field=k)
    return v


def opt_date(d, k):
    v = str(d.get(k, "") or "").strip()
    if not v:
        return None
    try:
        datetime.strptime(v, "%Y-%m-%d")
    except ValueError:
        raise ApiError("Invalid date (use YYYY-MM-DD)", field=k)
    return v


# ------------------------------------------------------------------ date range
PRESETS = {"7d": 7, "30d": 30, "3m": 90, "6m": 182}


def date_range():
    """Parse ?range=7d|30d|3m|6m|year|custom&from=&to= into (from_date, to_date) inclusive."""
    r = request.args.get("range", "30d")
    today = date.today()
    if r == "year":
        return date(today.year, 1, 1), today
    if r == "custom":
        try:
            f = datetime.strptime(request.args.get("from", ""), "%Y-%m-%d").date()
            t = datetime.strptime(request.args.get("to", ""), "%Y-%m-%d").date()
        except ValueError:
            raise ApiError("Choose a valid custom date range")
        if f > t:
            raise ApiError("Start date must be before end date")
        return f, min(t, today)
    n = PRESETS.get(r, 30)
    return today - timedelta(days=n - 1), today


def day_s(d):
    return d.strftime("%Y-%m-%d")


# ------------------------------------------------------------------ queue state
def load_state():
    """Rebuild the three queues from the database in FIFO order."""
    c = database.connect()
    c.row_factory = database.sqlite3.Row
    with lock:
        for q in QUEUES.values():
            q.clear()
        for r in c.execute("SELECT * FROM products ORDER BY id"):
            inventory_q.enqueue(dict(r))
        for r in c.execute("SELECT * FROM orders WHERE status='PENDING' ORDER BY created_at, id"):
            order_q.enqueue(dict(r))
        for r in c.execute("""SELECT o.*, (SELECT MAX(ts) FROM order_history h WHERE h.order_id=o.id AND h.status='PACKED') AS packed_at
                              FROM orders o WHERE status='PACKED' ORDER BY packed_at, id"""):
            dispatch_q.enqueue(dict(r))
    c.close()
