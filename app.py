"""
Eco Reest — Aanwezigheid & Werkplekken
Flask backend — gedeelde opslag via SQLite
"""

import json
import os
from datetime import datetime
from flask import Flask, jsonify, request, render_template

app = Flask(__name__)

DB_PATH = os.environ.get("DB_PATH", "ecoreest.db")


# ── Database helpers ──────────────────────────────────────────────────────────

def get_db():
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS data_store (
                key       TEXT PRIMARY KEY,
                value     TEXT,
                updated_at TEXT
            )
        """)
        conn.commit()


def db_get(key, default=None):
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT value FROM data_store WHERE key=?", (key,)
            ).fetchone()
            if row:
                return json.loads(row["value"])
    except Exception as e:
        app.logger.error(f"db_get({key}) fout: {e}")
    return default


def db_set(key, value):
    try:
        with get_db() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO data_store (key, value, updated_at)
                   VALUES (?, ?, ?)""",
                (key, json.dumps(value, ensure_ascii=False),
                 datetime.utcnow().isoformat()),
            )
            conn.commit()
    except Exception as e:
        app.logger.error(f"db_set({key}) fout: {e}")


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/data", methods=["GET"])
def get_data():
    """Laad alle gedeelde data in één keer."""
    return jsonify({
        "attendance": db_get("attendance", {}),
        "desk":       db_get("desk", {"absences": {}, "reservations": {}}),
        "adminCfg":   db_get("adminCfg", None),
    })


@app.route("/api/data", methods=["POST"])
def save_data():
    """Sla gewijzigde velden op (attendance, desk en/of adminCfg)."""
    data = request.get_json(force=True, silent=True) or {}
    if "attendance" in data:
        db_set("attendance", data["attendance"])
    if "desk" in data:
        db_set("desk", data["desk"])
    if "adminCfg" in data:
        db_set("adminCfg", data["adminCfg"])
    return jsonify({"ok": True})


@app.route("/api/reset-config", methods=["POST"])
def reset_config():
    """Admin: zet config terug naar standaard (verwijder override)."""
    db_set("adminCfg", None)
    return jsonify({"ok": True})


@app.route("/health")
def health():
    return jsonify({"status": "ok", "time": datetime.utcnow().isoformat()})


# ── Startup ───────────────────────────────────────────────────────────────────

init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
