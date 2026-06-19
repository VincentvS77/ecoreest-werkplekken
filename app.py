"""
Eco Reest — Aanwezigheid & Werkplekken
Flask backend — gedeelde opslag via SQLite
"""

import base64
import json
import os
from datetime import date, datetime, timedelta

import requests
from flask import Flask, jsonify, request, render_template

app = Flask(__name__)

DB_PATH    = os.environ.get("DB_PATH", "ecoreest.db")

# ── AFAS config ───────────────────────────────────────────────────────────────

AFAS_ENV   = os.environ.get("AFAS_ENV",   "82062")
AFAS_TOKEN = os.environ.get("AFAS_TOKEN", "")
AFAS_BASE  = os.environ.get("AFAS_BASE",  f"https://{AFAS_ENV}.rest.afas.online/profitrestservices")

AFAS_EMPLOYEES_CONNECTOR = "XCESS_PURE_GetEmployees"
AFAS_ABSENCES_CONNECTOR  = "XCESS_PURE_GetHolidayRequests"


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


# ── AFAS sync ─────────────────────────────────────────────────────────────────

def _afas_auth_header():
    xml = f"<token><version>1</version><data>{AFAS_TOKEN}</data></token>"
    return "AfasToken " + base64.b64encode(xml.encode()).decode()


def _afas_get_all(connector, extra_params=None):
    headers = {"Authorization": _afas_auth_header()}
    records, skip, take = [], 0, 100
    while True:
        params = {"skip": skip, "take": take}
        if extra_params:
            params.update(extra_params)
        resp = requests.get(
            f"{AFAS_BASE}/connectors/{connector}",
            headers=headers,
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        rows = resp.json().get("rows", [])
        records.extend(rows)
        if len(rows) < take:
            break
        skip += take
    return records


@app.route("/api/sync-afas", methods=["POST"])
def sync_afas():
    if not AFAS_TOKEN:
        return jsonify({"ok": False, "error": "AFAS_TOKEN niet geconfigureerd"}), 503

    try:
        # Fetch active employees from AFAS
        emp_rows = _afas_get_all(AFAS_EMPLOYEES_CONNECTOR, {
            "filterfieldids": "IsBlocked",
            "filtervalues":   "0",
            "operatortypes":  "1",
        })
        # ProfitCode → full name, sorted alphabetically
        id_to_name = {
            r["ProfitCode"]: f"{r['FirstName']} {r['LastName']}"
            for r in emp_rows
            if r.get("FirstName") and r.get("LastName") and r.get("ProfitCode")
        }
        afas_names = sorted(id_to_name.values())

        # Fetch all absence/holiday requests
        absence_rows = _afas_get_all(AFAS_ABSENCES_CONNECTOR)

        # Update adminCfg employee list from AFAS (preserve other settings)
        admin_cfg = db_get("adminCfg", {}) or {}
        admin_cfg["employees"] = afas_names
        db_set("adminCfg", admin_cfg)

        # Sync absences into attendance
        attendance = db_get("attendance", {})
        app_employees = set(afas_names)

        added = 0
        for row in absence_rows:
            emp_id    = row.get("EmployeeProfitCode")
            start_str = (row.get("StartDate") or "")[:10]
            end_str   = (row.get("EndDate")   or "")[:10]

            if not emp_id or not start_str or not end_str:
                continue

            full_name = id_to_name.get(emp_id)
            if not full_name or full_name not in app_employees:
                continue

            # Expand the date range, weekdays only
            d = date.fromisoformat(start_str)
            end = date.fromisoformat(end_str)
            while d <= end:
                if d.weekday() < 5:
                    dk = d.isoformat()
                    if dk not in attendance:
                        attendance[dk] = {}
                    if full_name not in attendance[dk]:
                        attendance[dk][full_name] = "vrij"
                        added += 1
                d += timedelta(days=1)

        db_set("attendance", attendance)
        return jsonify({
            "ok":               True,
            "employees_synced": len(afas_names),
            "absences_added":   added,
        })

    except Exception as e:
        app.logger.error(f"AFAS sync error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Startup ───────────────────────────────────────────────────────────────────

init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
