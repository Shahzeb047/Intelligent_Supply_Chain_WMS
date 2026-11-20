"""
Intelligent Supply Chain & Warehouse Management System
OEL - SW 212 Data Structures & Algorithms  |  Group C : QUEUE
Run:  python app.py   ->   http://127.0.0.1:5000
"""
from datetime import timedelta

from flask import Flask, g, jsonify, render_template, request

from backend import database, services
from backend.core import ApiError, load_state
from backend import routes_core, routes_inventory, routes_trade, routes_insights

app = Flask(__name__)
app.config.update(SECRET_KEY="scwms-oel-dsa-secret-key-change-me", PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
                  JSON_SORT_KEYS=False, SESSION_COOKIE_SAMESITE="Lax")


@app.get("/")
def index():
    return render_template("index.html")


@app.errorhandler(ApiError)
def api_error(e):
    return jsonify({"error": e.message, "field": e.field}), e.code


@app.errorhandler(404)
def not_found(e):
    return (jsonify({"error": "Not found"}), 404) if request.path.startswith("/api") else (render_template("index.html"), 200)


@app.errorhandler(Exception)
def unexpected(e):
    app.logger.exception(e)
    return jsonify({"error": f"Unexpected server error: {e}"}), 500


@app.after_request
def finish(resp):
    mutating = request.method != "GET" and request.path.startswith("/api/")
    c = g.get("db")
    ok = resp.status_code < 400
    if c is not None and ok and mutating and request.path != "/api/system/reset":
        try:
            services.sync_notifications()
        except Exception as ex:                      # alerts must never break a transaction
            app.logger.warning("alert sync failed: %s", ex)
    c = g.pop("db", None)
    if c is not None:
        c.commit() if ok else c.rollback()
        c.close()
    if mutating and not ok:
        load_state()                                  # keep the queues identical to the database
    resp.headers["Cache-Control"] = "no-store" if request.path.startswith("/api/") else "no-cache"
    return resp


for mod in (routes_core, routes_inventory, routes_trade, routes_insights):
    mod.register(app)

database.init_db()
load_state()

if __name__ == "__main__":
    print("\n  Intelligent Supply Chain & Warehouse Management System")
    print("  Open  http://127.0.0.1:5000   (admin / admin123)\n")
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
