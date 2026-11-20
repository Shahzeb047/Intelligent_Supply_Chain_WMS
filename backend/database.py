"""
backend/database.py - SQLite schema + realistic demo data.

The seed SIMULATES one year of warehouse operations day by day (orders,
purchase receipts, damages, transfers, returns).  Stock levels are the real
result of that simulation, so stock, movements, orders and shipments are
fully consistent with each other.
"""
import os
import random
import sqlite3
from datetime import date, datetime, timedelta

from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "warehouse.db")


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
  full_name TEXT NOT NULL, email TEXT, role TEXT NOT NULL, warehouse_id INTEGER, active INTEGER DEFAULT 1, created_at TEXT);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS warehouses(id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE, name TEXT NOT NULL, location TEXT,
  manager TEXT, capacity INTEGER DEFAULT 1000, status TEXT DEFAULT 'Active', created_at TEXT);
CREATE TABLE IF NOT EXISTS suppliers(id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE, name TEXT NOT NULL, contact_person TEXT,
  email TEXT, phone TEXT, address TEXT, categories TEXT, status TEXT DEFAULT 'Active', created_at TEXT);
CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE, name TEXT NOT NULL, sku TEXT UNIQUE,
  barcode TEXT, category TEXT, description TEXT, purchase_price REAL DEFAULT 0, selling_price REAL DEFAULT 0, reorder_level INTEGER DEFAULT 10,
  supplier_id INTEGER, warehouse_id INTEGER, bin TEXT, image TEXT, expiry_tracked INTEGER DEFAULT 0, created_at TEXT);
CREATE TABLE IF NOT EXISTS stock(product_id INTEGER, warehouse_id INTEGER, quantity INTEGER DEFAULT 0, reserved INTEGER DEFAULT 0,
  damaged INTEGER DEFAULT 0, PRIMARY KEY(product_id, warehouse_id));
CREATE TABLE IF NOT EXISTS batches(id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER, warehouse_id INTEGER, batch_no TEXT,
  quantity INTEGER, expiry_date TEXT, received_date TEXT);
CREATE TABLE IF NOT EXISTS movements(id INTEGER PRIMARY KEY AUTOINCREMENT, txn_id TEXT, product_id INTEGER, quantity INTEGER, type TEXT,
  source_wh INTEGER, dest_wh INTEGER, ts TEXT, employee TEXT, reference TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS purchase_orders(id INTEGER PRIMARY KEY AUTOINCREMENT, po_no TEXT UNIQUE, supplier_id INTEGER, warehouse_id INTEGER,
  status TEXT, created_at TEXT, expected_date TEXT, received_date TEXT, notes TEXT, created_by TEXT);
CREATE TABLE IF NOT EXISTS po_items(id INTEGER PRIMARY KEY AUTOINCREMENT, po_id INTEGER, product_id INTEGER, quantity INTEGER,
  received_qty INTEGER DEFAULT 0, unit_cost REAL);
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT, order_no TEXT UNIQUE, customer_name TEXT, phone TEXT, destination TEXT,
  warehouse_id INTEGER, status TEXT, discount_pct REAL DEFAULT 0, subtotal REAL DEFAULT 0, total REAL DEFAULT 0, created_at TEXT,
  updated_at TEXT, created_by TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS order_items(id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER, product_id INTEGER, quantity INTEGER, unit_price REAL);
CREATE TABLE IF NOT EXISTS order_history(id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER, status TEXT, ts TEXT, by_user TEXT);
CREATE TABLE IF NOT EXISTS shipments(id INTEGER PRIMARY KEY AUTOINCREMENT, shipment_no TEXT UNIQUE, order_id INTEGER, customer_name TEXT,
  origin_wh INTEGER, destination TEXT, partner TEXT, tracking_no TEXT, dispatch_date TEXT, expected_date TEXT, delivered_date TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS shipment_events(id INTEGER PRIMARY KEY AUTOINCREMENT, shipment_id INTEGER, status TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS returns(id INTEGER PRIMARY KEY AUTOINCREMENT, return_no TEXT UNIQUE, order_id INTEGER, product_id INTEGER, quantity INTEGER,
  reason TEXT, condition TEXT, status TEXT, warehouse_id INTEGER, refund_amount REAL, created_at TEXT, decided_at TEXT, note TEXT, created_by TEXT);
CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT UNIQUE, category TEXT, severity TEXT, title TEXT,
  message TEXT, ts TEXT, is_read INTEGER DEFAULT 0, dismissed INTEGER DEFAULT 0, warehouse_id INTEGER, link TEXT);
CREATE TABLE IF NOT EXISTS activity(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, user TEXT, action TEXT, structure TEXT, detail TEXT);
CREATE INDEX IF NOT EXISTS ix_mov_ts ON movements(ts);
CREATE INDEX IF NOT EXISTS ix_mov_prod ON movements(product_id);
CREATE INDEX IF NOT EXISTS ix_ord_created ON orders(created_at);
CREATE INDEX IF NOT EXISTS ix_ord_status ON orders(status);
CREATE INDEX IF NOT EXISTS ix_oi_order ON order_items(order_id);
CREATE INDEX IF NOT EXISTS ix_oh_order ON order_history(order_id);
"""

TABLES = ["users", "settings", "warehouses", "suppliers", "products", "stock", "batches", "movements", "purchase_orders",
          "po_items", "orders", "order_items", "order_history", "shipments", "shipment_events", "returns", "notifications", "activity"]

CATEGORY_EMOJI = {"Electronics": "💻", "Groceries": "🛒", "Pharmaceuticals": "💊", "Apparel": "👕", "Industrial": "🛠️",
                  "Furniture": "🪑", "Home Appliances": "🔌", "Stationery": "✏️"}

WAREHOUSES = [  # code, name, location, manager, target utilisation
    ("WH-01", "Karachi Central DC", "Karachi, Sindh", "Imran Qureshi", .66),
    ("WH-02", "Hyderabad Distribution Hub", "Hyderabad, Sindh", "Farhan Siddiqui", .79),
    ("WH-03", "Sukkur Regional Depot", "Sukkur, Sindh", "Sana Ahmed", .91),
    ("WH-04", "Lahore North Warehouse", "Lahore, Punjab", "Usman Tariq", .55),
    ("WH-05", "Islamabad Pharma & Cold Store", "Islamabad, ICT", "Ayesha Raza", .88),
]

SUPPLIERS = [  # name, contact, email, phone, address, categories, status
    ("TechSource Karachi", "Adeel Hussain", "sales@techsource.pk", "+92 21 3456 7801", "Saddar, Karachi", "Electronics", "Active"),
    ("Samsung Pakistan Distribution", "Nida Farooq", "b2b@samsungpk.example", "+92 21 3567 2200", "Clifton, Karachi", "Electronics, Home Appliances", "Active"),
    ("Sindh Agro Mills", "Ghulam Rasool", "orders@sindhagro.pk", "+92 22 2780 111", "Kotri, Jamshoro", "Groceries", "Active"),
    ("Getz Pharma Distribution", "Dr. Maria Khan", "supply@getzdist.example", "+92 21 3510 4400", "Korangi, Karachi", "Pharmaceuticals", "Active"),
    ("Gul Ahmed Textiles", "Rizwan Shaikh", "wholesale@gultex.example", "+92 21 3250 9000", "SITE Area, Karachi", "Apparel", "Active"),
    ("Ittefaq Steel & Tools", "Khalid Mehmood", "info@ittefaqsteel.example", "+92 42 3532 1100", "Badami Bagh, Lahore", "Industrial", "Active"),
    ("Interwood Furniture", "Saima Iqbal", "trade@interwood.example", "+92 42 3590 7700", "Ferozepur Road, Lahore", "Furniture", "Active"),
    ("Orient Appliances", "Tariq Jameel", "dealers@orient.example", "+92 42 3577 6600", "Gulberg, Lahore", "Home Appliances", "Active"),
    ("PaperLink Stationers", "Hina Baloch", "sales@paperlink.example", "+92 21 3478 5500", "Burns Road, Karachi", "Stationery", "Active"),
    ("Karachi Packaging Co.", "Zubair Ali", "hello@khipack.example", "+92 21 3555 1212", "Landhi, Karachi", "Industrial", "Inactive"),
]

# name, category, cost, price, reorder, supplier idx, base quantity per warehouse
PRODUCTS = [
    ("Dell Latitude 5540 Laptop", "Electronics", 118000, 145000, 8, 0, 25), ("Samsung 43\" Smart TV", "Electronics", 68000, 89000, 8, 1, 30),
    ("Wireless Mouse", "Electronics", 1100, 1800, 40, 0, 160), ("Mechanical Keyboard", "Electronics", 5200, 7500, 15, 0, 60),
    ("Power Bank 20000mAh", "Electronics", 2900, 4200, 25, 0, 90), ("Wi-Fi Router AX1800", "Electronics", 7800, 10500, 15, 0, 55),
    ("Basmati Rice 5kg", "Groceries", 1180, 1450, 80, 2, 260), ("Cooking Oil 5L", "Groceries", 2450, 2850, 50, 2, 150),
    ("Sugar 1kg", "Groceries", 125, 160, 100, 2, 420), ("Tea Pack 950g", "Groceries", 1380, 1650, 60, 2, 190),
    ("Iodized Salt 800g", "Groceries", 48, 70, 60, 2, 300), ("Red Lentils (Masoor) 1kg", "Groceries", 280, 340, 70, 2, 210),
    ("Paracetamol 500mg (Box)", "Pharmaceuticals", 85, 120, 100, 3, 400), ("Cough Syrup 120ml", "Pharmaceuticals", 200, 280, 40, 3, 140),
    ("Digital Thermometer", "Pharmaceuticals", 480, 650, 20, 3, 70), ("Surgical Masks (Box)", "Pharmaceuticals", 330, 450, 30, 3, 110),
    ("Insulin Pen", "Pharmaceuticals", 1900, 2400, 25, 3, 80), ("Vitamin C Tablets 60s", "Pharmaceuticals", 450, 620, 40, 3, 130),
    ("Cotton Shirt", "Apparel", 1350, 1900, 60, 4, 200), ("Denim Jeans", "Apparel", 2300, 3200, 40, 4, 130),
    ("Winter Jacket", "Apparel", 4900, 6800, 20, 4, 60), ("Sports Shoes", "Apparel", 3900, 5400, 25, 4, 90),
    ("School Backpack", "Apparel", 1800, 2600, 20, 4, 85), ("Lawn 3-Piece Suit", "Apparel", 3200, 4500, 30, 4, 100),
    ("Steel Pipe 2in (6m)", "Industrial", 3900, 4800, 30, 5, 100), ("Safety Helmet", "Industrial", 700, 950, 50, 5, 150),
    ("Welding Rod Pack", "Industrial", 1350, 1700, 25, 5, 90), ("Industrial Gloves (Pair)", "Industrial", 260, 380, 60, 5, 230),
    ("Hydraulic Jack 3T", "Industrial", 9800, 12500, 10, 5, 35), ("Cable Drum 100m", "Industrial", 6200, 7900, 12, 5, 45),
    ("Office Chair", "Furniture", 11800, 15500, 15, 6, 50), ("Study Desk", "Furniture", 14200, 18900, 10, 6, 35),
    ("Steel Almirah", "Furniture", 24500, 32000, 6, 6, 18), ("Bookshelf 5-Tier", "Furniture", 9300, 12400, 8, 6, 25),
    ("Dining Table Set", "Furniture", 43000, 58000, 5, 6, 12), ("Sofa 3-Seater", "Furniture", 38000, 49500, 5, 6, 14),
    ("Ceiling Fan 56in", "Home Appliances", 7200, 9400, 20, 7, 70), ("Microwave Oven 20L", "Home Appliances", 15500, 19800, 10, 7, 30),
    ("Electric Kettle 1.7L", "Home Appliances", 2100, 2900, 25, 7, 85), ("Air Cooler 60L", "Home Appliances", 26000, 32500, 8, 1, 20),
    ("Steam Iron 2200W", "Home Appliances", 2300, 3200, 20, 7, 75), ("Inverter Refrigerator 12cft", "Home Appliances", 62000, 78000, 6, 1, 14),
    ("A4 Paper Ream 80gsm", "Stationery", 780, 980, 100, 8, 380), ("Ball Pens Box of 50", "Stationery", 420, 600, 60, 8, 220),
    ("Spiral Notebook Pack of 10", "Stationery", 760, 1050, 50, 8, 190), ("Whiteboard Marker Box of 12", "Stationery", 520, 740, 40, 8, 150),
    ("Heavy Duty Stapler", "Stationery", 650, 950, 25, 8, 95), ("File Folder Pack of 25", "Stationery", 480, 690, 45, 8, 160),
]

CUSTOMERS = [("Karachi Mart", "Karachi"), ("Hyderabad Traders", "Hyderabad"), ("Sukkur Electronics", "Sukkur"), ("Khairpur Pharmacy", "Khairpur"),
             ("Lahore Retail Hub", "Lahore"), ("Indus Distributors", "Hyderabad"), ("Sindh Supplies", "Larkana"), ("Quetta Wholesale", "Quetta"),
             ("Mehran Stores", "Jamshoro"), ("Larkana Depot", "Larkana"), ("Faisalabad Textile Outlet", "Faisalabad"), ("Multan Home Store", "Multan"),
             ("Peshawar Trading Co.", "Peshawar"), ("Islamabad Medico", "Islamabad"), ("Rawalpindi Electronics Hub", "Rawalpindi"),
             ("Gwadar Marine Supplies", "Gwadar"), ("Sialkot Sports House", "Sialkot"), ("Bahawalpur Mart", "Bahawalpur"),
             ("Nawabshah Wholesale", "Nawabshah"), ("Jacobabad Stores", "Jacobabad")]

PARTNERS = ["TCS", "Leopards Courier", "M&P Express", "BlueEx", "Trax Logistics"]
RETURN_REASONS = ["Damaged in transit", "Wrong item delivered", "Defective product", "Customer changed mind", "Expired / near expiry", "Quantity mismatch"]
PIPELINE = ["PENDING", "CONFIRMED", "PROCESSING", "PACKED", "DISPATCHED", "DELIVERED"]

USERS = [  # username, password, full name, email, role, warehouse idx
    ("admin", "admin123", "Ahsan Raza (Admin)", "admin@scwms.example", "admin", None),
    ("manager1", "manager123", "Imran Qureshi", "imran@scwms.example", "manager", 0),
    ("manager2", "manager123", "Sana Ahmed", "sana@scwms.example", "manager", 2),
    ("employee1", "employee123", "Bilal Khan", "bilal@scwms.example", "employee", 0),
    ("employee2", "employee123", "Hira Memon", "hira@scwms.example", "employee", 1),
]


def S(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def D(d):
    return d.strftime("%Y-%m-%d")


def init_db(force=False):
    conn = connect()
    if force:
        for t in TABLES:
            conn.execute(f"DROP TABLE IF EXISTS {t}")
    conn.executescript(SCHEMA)
    if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
        seed(conn)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
def seed(conn):
    rnd = random.Random(42)
    now = datetime.now().replace(microsecond=0)
    today = date.today()
    DAYS = 365

    # ---------- users / settings ----------
    for u, pw, name, email, role, wi in USERS:
        conn.execute("INSERT INTO users(username,password_hash,full_name,email,role,warehouse_id,created_at) VALUES(?,?,?,?,?,?,?)",
                     (u, generate_password_hash(pw), name, email, role, None if wi is None else wi + 1, S(now - timedelta(days=400))))
    for k, v in {"company_name": "Intelligent Supply Chain Co.", "currency": "Rs", "expiry_warning_days": "30",
                 "capacity_warning_pct": "85", "po_pending_days": "3"}.items():
        conn.execute("INSERT INTO settings VALUES(?,?)", (k, v))
    staff = [u[2] for u in USERS if u[4] != "admin"]

    # ---------- master data ----------
    for i, (code, name, loc, mgr, _t) in enumerate(WAREHOUSES, 1):
        conn.execute("INSERT INTO warehouses(code,name,location,manager,capacity,status,created_at) VALUES(?,?,?,?,?,?,?)",
                     (code, name, loc, mgr, 10000, "Active", S(now - timedelta(days=500))))
    for i, (name, contact, email, phone, addr, cats, st) in enumerate(SUPPLIERS, 1):
        conn.execute("INSERT INTO suppliers(code,name,contact_person,email,phone,address,categories,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                     (f"SUP-{i:03d}", name, contact, email, phone, addr, cats, st, S(now - timedelta(days=450))))
    prod = []   # in-memory product dicts
    for i, (name, cat, cost, price, reorder, sup, base) in enumerate(PRODUCTS, 1):
        tracked = 1 if cat in ("Groceries", "Pharmaceuticals") else 0
        zone = "ABCDEFGH"[list(CATEGORY_EMOJI).index(cat)]
        # which warehouses stock this product (first = primary)
        whs = rnd.sample(range(1, 6), rnd.choice([2, 3]))
        if cat == "Pharmaceuticals":
            whs = [5, 1] + ([rnd.choice([2, 3, 4])] if rnd.random() < .5 else [])
        p = dict(id=i, name=name, cat=cat, cost=cost, price=price, reorder=reorder, sup=sup + 1, base=base, tracked=tracked, whs=whs)
        prod.append(p)
        conn.execute("INSERT INTO products(code,name,sku,barcode,category,description,purchase_price,selling_price,reorder_level,supplier_id,"
                     "warehouse_id,bin,image,expiry_tracked,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (f"P-{i:04d}", name, f"{cat[:3].upper()}-{i:04d}", f"8960{rnd.randint(10**8, 10**9 - 1)}", cat,
                      f"{name} - quality {cat.lower()} item for wholesale distribution.", cost, price, reorder, sup + 1, whs[0],
                      f"{zone}-{rnd.randint(1, 20):02d}-{rnd.randint(1, 4)}", "", tracked, S(now - timedelta(days=rnd.randint(380, 480)))))

    # ---------- simulation state ----------
    stock = {}      # (pid,wid) -> [qty, reserved, damaged]
    batches = {}    # (pid,wid) -> list of [batch_no, qty, expiry, received]
    for p in prod:
        for w in p["whs"]:
            q = max(6, int(p["base"] * rnd.uniform(.7, 1.5)))
            stock[(p["id"], w)] = [q, 0, 0]
            if p["tracked"]:
                batches[(p["id"], w)] = [[f"OPEN-{p['id']:02d}{w}", q, D(today + timedelta(days=rnd.randint(60, 420))), D(today - timedelta(days=DAYS))]]

    mov, orders, items, hist, ships, sevents, rets, pos, poitems = [], [], [], [], [], [], [], [], []
    ctr = dict(txn=0, order=0, po=0, ship=0, ret=0)
    receipts = {}   # day index -> list of (po_id, supplier, wid, [(pid, qty)])

    def txn():
        ctr["txn"] += 1
        return f"TXN-{ctr['txn']:06d}"

    def add_batch(pid, wid, qty, day, expiry_days):
        if not prod[pid - 1]["tracked"]:
            return
        batches.setdefault((pid, wid), []).append([f"B{day.strftime('%y%m%d')}-{pid:02d}", qty, D(day + timedelta(days=expiry_days)), D(day)])

    def consume(pid, wid, qty):
        for b in sorted(batches.get((pid, wid), []), key=lambda x: x[2]):
            if qty <= 0:
                break
            t = min(b[1], qty)
            b[1] -= t
            qty -= t
        batches[(pid, wid)] = [b for b in batches.get((pid, wid), []) if b[1] > 0]

    def avail(pid, wid):
        s = stock.get((pid, wid))
        return 0 if not s else s[0] - s[1]

    def movement(ts, pid, qty, typ, src, dst, ref="", note=""):
        mov.append((txn(), pid, qty, typ, src, dst, S(min(ts, now)), rnd.choice(staff), ref, note))

    def rand_ts(day, h0=8, h1=18):
        return datetime.combine(day, datetime.min.time()) + timedelta(hours=rnd.randint(h0, h1), minutes=rnd.randint(0, 59), seconds=rnd.randint(0, 59))

    def pick_status(age, k):
        r = rnd.random()
        if age == 0:
            return "PENDING" if k < 5 else "CONFIRMED"
        if age == 1:
            return "PACKED" if k < 3 else ("PROCESSING" if k < 5 else "CONFIRMED")
        if age <= 3:
            return "DISPATCHED" if r < .6 else ("PACKED" if r < .8 else "DELIVERED")
        if age <= 8:
            return "DELIVERED" if r < .72 else ("DISPATCHED" if r < .96 else "CANCELLED")
        return "DELIVERED" if r < .87 else ("RETURNED" if r < .94 else "CANCELLED")

    blocked = {p["id"] for p in rnd.sample(prod, 8)}      # products whose restocking stops 25 days ago

    # ---------- day by day ----------
    for off in range(DAYS, -1, -1):
        day = today - timedelta(days=off)
        # receipts due today
        for (po_id, sup, wid, lines) in receipts.pop(off, []):
            for pid, q in lines:
                stock.setdefault((pid, wid), [0, 0, 0])[0] += q
                add_batch(pid, wid, q, day, rnd.randint(150, 520) if prod[pid - 1]["cat"] == "Groceries" else rnd.randint(250, 700))
                movement(rand_ts(day, 9, 15), pid, q, "STOCK_IN", None, wid, f"PO-{po_id:05d}", "Purchase receipt")
        # replenishment POs (evaluated every 3 days)
        if off % 3 == 0 and off > 0:
            groups = {}
            for p in prod:
                if p["id"] in blocked and off < 25:
                    continue
                for w in p["whs"]:
                    s = stock[(p["id"], w)]
                    if s[0] - s[1] < p["reorder"] * 1.6 and rnd.random() < .7:
                        groups.setdefault((p["sup"], w), []).append((p["id"], int(p["base"] * rnd.uniform(.9, 1.6))))
            for (sup, w), lines in groups.items():
                ctr["po"] += 1
                po_id = ctr["po"]
                lead = rnd.randint(3, 7)
                due = off - lead
                created = rand_ts(day, 9, 12)
                exp = day + timedelta(days=rnd.choice([lead - 1, lead, lead + 1]))
                if due >= 0:
                    receipts.setdefault(due, []).append((po_id, sup, w, lines))
                    status, rec = "COMPLETED", D(today - timedelta(days=due))
                else:
                    status, rec = rnd.choice(["PENDING", "APPROVED"]), None
                pos.append((po_id, f"PO-{po_id:05d}", sup, w, status, S(created), D(exp), rec, "Auto-planned replenishment", "System"))
                for pid, q in lines:
                    poitems.append((po_id, pid, q, q if status == "COMPLETED" else 0, prod[pid - 1]["cost"]))
        # customer orders
        n_orders = max(1, int(rnd.gauss(3 + 1.2 * (1 - off / DAYS) + (1 if day.weekday() < 5 else -0.8), 1.2)))
        if off == 0:
            n_orders = 9
        if off == 1:
            n_orders = 6
        for k in range(n_orders):
            wid = rnd.choice(range(1, 6))
            cand = [p for p in prod if (p["id"], wid) in stock and avail(p["id"], wid) > 3]
            if not cand:
                continue
            status = pick_status(off, k)
            created = rand_ts(day, 8, 19) if off else now - timedelta(minutes=rnd.randint(5, 600))
            lines = []
            for p in rnd.sample(cand, min(len(cand), rnd.choice([1, 1, 2, 2, 3, 4]))):
                q = min(rnd.randint(1, max(2, int(p["base"] * .12))), avail(p["id"], wid))
                if q > 0:
                    lines.append((p, q))
            if not lines:
                continue
            ctr["order"] += 1
            oid = ctr["order"]
            cust, city = rnd.choice(CUSTOMERS)
            disc = rnd.choice([0, 0, 0, 5, 5, 10])
            sub = sum(p["price"] * q for p, q in lines)
            total = round(sub * (1 - disc / 100), 2)
            dispatch_ts = created + timedelta(days=1, hours=rnd.randint(0, 4))
            level = PIPELINE.index(status) if status in PIPELINE else (5 if status == "RETURNED" else -1)
            # stock effects
            for p, q in lines:
                s = stock[(p["id"], wid)]
                if status in ("DISPATCHED", "DELIVERED", "RETURNED"):
                    s[0] -= q
                    consume(p["id"], wid, q)
                    movement(dispatch_ts, p["id"], q, "STOCK_OUT", wid, None, f"ORD-{oid:06d}", "Customer order dispatch")
                elif status in ("PENDING", "CONFIRMED", "PROCESSING", "PACKED"):
                    s[1] += q
            orders.append((oid, f"ORD-{oid:06d}", cust, f"+92 3{rnd.randint(0, 4)}{rnd.randint(0, 9)} {rnd.randint(1000000, 9999999)}", city, wid,
                           status, disc, sub, total, S(created), S(min(now, created + timedelta(days=min(off, 6)))), rnd.choice(staff), ""))
            for p, q in lines:
                items.append((oid, p["id"], q, p["price"]))
            # history
            offsets = [0, 1, 3, 6, 26, 26 + rnd.randint(24, 120)]
            for li in range(0, max(level, 0) + 1):
                if status == "CANCELLED":
                    break
                hist.append((oid, PIPELINE[li], S(min(now, created + timedelta(hours=offsets[li]))), rnd.choice(staff)))
            if status == "RETURNED":
                hist.append((oid, "RETURNED", S(min(now, created + timedelta(days=9))), rnd.choice(staff)))
            if status == "CANCELLED":
                hist.append((oid, "PENDING", S(created), rnd.choice(staff)))
                hist.append((oid, "CANCELLED", S(created + timedelta(hours=rnd.randint(1, 20))), rnd.choice(staff)))
            # shipment
            if level >= 4 or status == "RETURNED":
                ctr["ship"] += 1
                sid = ctr["ship"]
                d_date = dispatch_ts
                exp = d_date + timedelta(days=rnd.randint(2, 4))
                transit = rnd.randint(1, 6)
                delivered = d_date + timedelta(days=transit) if (status in ("DELIVERED", "RETURNED")) else None
                if delivered and delivered > now:
                    delivered = now - timedelta(hours=2)
                sstatus = "DELIVERED" if delivered else ("IN_TRANSIT" if off >= 2 else "DISPATCHED")
                ships.append((sid, f"SHP-{sid:06d}", oid, cust, wid, city, rnd.choice(PARTNERS), f"TRK{rnd.randint(10**9, 10**10 - 1)}",
                              D(d_date), D(exp), D(delivered) if delivered else None, sstatus))
                sevents.append((sid, "ORDER_CREATED", S(created)))
                sevents.append((sid, "PROCESSING", S(created + timedelta(hours=3))))
                sevents.append((sid, "PACKED", S(created + timedelta(hours=6))))
                sevents.append((sid, "DISPATCHED", S(min(now, d_date))))
                if sstatus in ("IN_TRANSIT", "DELIVERED"):
                    sevents.append((sid, "IN_TRANSIT", S(min(now, d_date + timedelta(hours=10)))))
                if delivered:
                    sevents.append((sid, "DELIVERED", S(delivered)))
            # returns
            if status == "RETURNED":
                p, q = lines[0]
                rq = min(q, rnd.randint(1, 4))
                ctr["ret"] += 1
                cond = "RESELLABLE" if rnd.random() < .6 else "DAMAGED"
                rets.append((ctr["ret"], f"RET-{ctr['ret']:05d}", oid, p["id"], rq, rnd.choice(RETURN_REASONS), cond, "APPROVED", wid,
                             round(rq * p["price"] * (1 - disc / 100), 2), S(created + timedelta(days=8)), S(created + timedelta(days=9)), "", rnd.choice(staff)))
                ts = created + timedelta(days=9)
                if cond == "RESELLABLE":
                    stock[(p["id"], wid)][0] += rq
                    add_batch(p["id"], wid, rq, ts.date(), 200)
                    movement(ts, p["id"], rq, "RETURN", None, wid, f"RET-{ctr['ret']:05d}", "Returned - restocked")
                else:
                    stock[(p["id"], wid)][2] += rq
                    movement(ts, p["id"], rq, "DAMAGED", wid, None, f"RET-{ctr['ret']:05d}", "Returned - damaged")
        # random damage
        if rnd.random() < .3:
            p = rnd.choice(prod)
            w = rnd.choice(p["whs"])
            if avail(p["id"], w) > 40:
                q = rnd.randint(1, 6)
                stock[(p["id"], w)][0] -= q
                stock[(p["id"], w)][2] += q
                consume(p["id"], w, q)
                movement(rand_ts(day), p["id"], q, "DAMAGED", w, None, "", rnd.choice(["Handling damage", "Water damage", "Packaging defect"]))
        # weekly transfer
        if off % 6 == 0 and off > 0:
            p = rnd.choice(prod)
            src = max(p["whs"], key=lambda w: avail(p["id"], w))
            dst = rnd.choice([w for w in range(1, 6) if w != src])
            q = min(rnd.randint(15, 60), avail(p["id"], src) // 3)
            if q > 5:
                stock[(p["id"], src)][0] -= q
                stock.setdefault((p["id"], dst), [0, 0, 0])[0] += q
                consume(p["id"], src, q)
                add_batch(p["id"], dst, q, day, 240)
                movement(rand_ts(day), p["id"], q, "TRANSFER", src, dst, "", "Stock rebalancing")

    # ---------- handpicked recent purchase orders (Draft / Pending / Approved / Partial / Cancelled) ----------
    def manual_po(status, sup_idx, wid, pids, days_ago, received_frac=0.0):
        ctr["po"] += 1
        po_id = ctr["po"]
        created = now - timedelta(days=days_ago)
        pos.append((po_id, f"PO-{po_id:05d}", sup_idx, wid, status, S(created), D(today + timedelta(days=rnd.randint(2, 6) - (days_ago // 2))),
                    None, "Manually created order", rnd.choice(staff)))
        for pid in pids:
            q = int(prod[pid - 1]["base"] * 1.2)
            rq = int(q * received_frac)
            poitems.append((po_id, pid, q, rq, prod[pid - 1]["cost"]))
            if rq:
                stock.setdefault((pid, wid), [0, 0, 0])[0] += rq
                add_batch(pid, wid, rq, today - timedelta(days=1), 300)
                movement(now - timedelta(days=1), pid, rq, "STOCK_IN", None, wid, f"PO-{po_id:05d}", "Partial receipt")

    manual_po("DRAFT", 1, 1, [3, 4], 1)
    manual_po("PENDING", 3, 1, [7, 8, 10], 6)
    manual_po("PENDING", 4, 5, [13, 16], 5)
    manual_po("APPROVED", 5, 2, [19, 21], 3)
    manual_po("PARTIALLY_RECEIVED", 6, 4, [25, 28], 4, .5)
    manual_po("CANCELLED", 7, 1, [38], 10)

    # ---------- engineered alerts: low stock / out of stock / expiring ----------
    def reduce_to(pid, target_avail):
        total_av = sum(avail(pid, w) for w in prod[pid - 1]["whs"])
        need = total_av - target_avail
        for w in prod[pid - 1]["whs"]:
            if need <= 0:
                break
            t = min(need, avail(pid, w))
            if t > 0:
                stock[(pid, w)][0] -= t
                consume(pid, w, t)
                movement(now - timedelta(days=rnd.randint(1, 12), hours=rnd.randint(0, 20)), pid, t, "STOCK_OUT", w, None, "", "Bulk dispatch")
                need -= t

    for pid in (4, 9, 20, 24, 36, 47):         # low stock
        reduce_to(pid, max(1, int(prod[pid - 1]["reorder"] * .6)))
    for pid in (11, 34):                         # out of stock
        reduce_to(pid, 0)
    tracked_batches = [b for key, bl in batches.items() for b in bl if b[1] > 0]
    for b in rnd.sample(tracked_batches, 5):
        b[2] = D(today + timedelta(days=rnd.randint(4, 24)))
    for b in rnd.sample([b for b in tracked_batches if not b[2] < D(today)], 2):
        b[2] = D(today - timedelta(days=3))

    # ---------- capacities: choose so utilisation matches targets ----------
    occ = {w: sum(v[0] + v[2] for (pid, ww), v in stock.items() if ww == w) for w in range(1, 6)}
    caps = {w: int(round(occ[w] / WAREHOUSES[w - 1][4] / 100.0)) * 100 for w in range(1, 6)}

    # ---------- write everything ----------
    for w, cap in caps.items():
        conn.execute("UPDATE warehouses SET capacity=? WHERE id=?", (cap, w))
    conn.executemany("INSERT INTO stock VALUES(?,?,?,?,?)", [(p, w, v[0], v[1], v[2]) for (p, w), v in stock.items()])
    conn.executemany("INSERT INTO batches(product_id,warehouse_id,batch_no,quantity,expiry_date,received_date) VALUES(?,?,?,?,?,?)",
                     [(p, w, b[0], b[1], b[2], b[3]) for (p, w), bl in batches.items() for b in bl])
    mov.sort(key=lambda m: m[7])
    conn.executemany("INSERT INTO movements(txn_id,product_id,quantity,type,source_wh,dest_wh,ts,employee,reference,note) VALUES(?,?,?,?,?,?,?,?,?,?)",
                     [(f"TXN-{i:06d}",) + m[1:] for i, m in enumerate(mov, 1)])
    conn.executemany("INSERT INTO purchase_orders(id,po_no,supplier_id,warehouse_id,status,created_at,expected_date,received_date,notes,created_by) VALUES(?,?,?,?,?,?,?,?,?,?)", pos)
    conn.executemany("INSERT INTO po_items(po_id,product_id,quantity,received_qty,unit_cost) VALUES(?,?,?,?,?)", poitems)
    conn.executemany("INSERT INTO orders(id,order_no,customer_name,phone,destination,warehouse_id,status,discount_pct,subtotal,total,created_at,updated_at,created_by,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", orders)
    conn.executemany("INSERT INTO order_items(order_id,product_id,quantity,unit_price) VALUES(?,?,?,?)", items)
    conn.executemany("INSERT INTO order_history(order_id,status,ts,by_user) VALUES(?,?,?,?)", hist)
    conn.executemany("INSERT INTO shipments(id,shipment_no,order_id,customer_name,origin_wh,destination,partner,tracking_no,dispatch_date,expected_date,delivered_date,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", ships)
    conn.executemany("INSERT INTO shipment_events(shipment_id,status,ts) VALUES(?,?,?)", sevents)
    conn.executemany("INSERT INTO returns(id,return_no,order_id,product_id,quantity,reason,condition,status,warehouse_id,refund_amount,created_at,decided_at,note,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rets)

    # a few recent pending returns on delivered orders
    delivered = conn.execute("SELECT o.id,o.warehouse_id,o.discount_pct,i.product_id,i.quantity,i.unit_price FROM orders o JOIN order_items i ON i.order_id=o.id "
                             "WHERE o.status='DELIVERED' ORDER BY o.id DESC LIMIT 40").fetchall()
    n = ctr["ret"]
    for r in rnd.sample(list(delivered), 4):
        n += 1
        conn.execute("INSERT INTO returns(return_no,order_id,product_id,quantity,reason,condition,status,warehouse_id,refund_amount,created_at,note,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                     (f"RET-{n:05d}", r["id"], r["product_id"], 1, rnd.choice(RETURN_REASONS), rnd.choice(["RESELLABLE", "DAMAGED"]), "PENDING",
                      r["warehouse_id"], r["unit_price"], S(now - timedelta(hours=rnd.randint(3, 60))), "", rnd.choice(staff)))
    conn.execute("INSERT INTO activity(ts,user,action,structure,detail) VALUES(?,?,?,?,?)", (S(now), "System", "SEED", "System", "Demo data generated: 12 months of operations"))
