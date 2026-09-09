"""
SIANNA - Panel web de seguimiento
==================================
Backend Flask que recibe datos en vivo del script de reconocimiento de
gestos (gestureRecognition.py -> metrics_client.py) y los guarda en Postgres
(Neon), para que las estadísticas históricas se puedan ver desde cualquier
lado, no solo mientras corre el script local:

  - Precisión del reconocimiento de gestos (pruebas guiadas por gesto)
  - Tiempos de respuesta (latencia por frame y por prueba de precisión)
  - Número de repeticiones por gesto
  - Vista en vivo del estado de los 5 dedos (solo mientras el script local
    con la cámara/ESP32 está corriendo y le habla a ESTE mismo proceso)

Este mismo archivo se despliega en Vercel como función serverless
(rewrites en vercel.json mandan /api/* y /panel acá) y se corre localmente
a través de WebApp/app.py.
"""

import json
import os
import statistics
import threading
import time
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
from flask import Flask, g, jsonify, redirect, request, send_from_directory

API_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(os.path.dirname(API_DIR), "public")

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")

# static_folder solo importa para correr localmente (python app.py): sirve
# /vendor/chart.umd.js igual que Vercel lo hace vía hosting estático de
# landing/public. En Vercel esta ruta nunca se usa para ese archivo, porque
# lo sirve directo el hosting estático antes de llegar a esta función.
app = Flask(__name__, static_folder=PUBLIC_DIR, static_url_path="")

# ---------------------------------------------------------------------------
# Base de datos (Postgres / Neon)
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id SERIAL PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS gesture_events (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    ts TEXT NOT NULL,
    gesture_name TEXT NOT NULL,
    fingers TEXT NOT NULL,
    latency_ms REAL,
    fps REAL,
    hand_detected INTEGER NOT NULL DEFAULT 1,
    is_transition INTEGER NOT NULL DEFAULT 0,
    captura_ms REAL,
    mediapipe_ms REAL,
    inferencia_ms REAL,
    serial_ms REAL,
    servo_ms REAL
);
CREATE INDEX IF NOT EXISTS idx_events_session ON gesture_events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_gesture ON gesture_events(gesture_name);
CREATE INDEX IF NOT EXISTS idx_events_ts ON gesture_events(ts);

CREATE TABLE IF NOT EXISTS accuracy_tests (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    ts TEXT NOT NULL,
    expected_gesture TEXT NOT NULL,
    detected_gesture TEXT,
    correct INTEGER NOT NULL,
    response_time_ms REAL,
    timed_out INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tests_session ON accuracy_tests(session_id);
CREATE INDEX IF NOT EXISTS idx_tests_gesture ON accuracy_tests(expected_gesture);
"""


class PgConnection:
    """Envoltorio mínimo para que el código (escrito originalmente para
    sqlite3) funcione igual sobre Postgres: placeholders '?' y filas
    accesibles como dict, tal como daba sqlite3.Row."""

    def __init__(self, dsn):
        self._conn = psycopg2.connect(dsn)

    def execute(self, sql, params=()):
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql.replace("?", "%s"), params)
        return cur

    def executescript(self, sql):
        cur = self._conn.cursor()
        cur.execute(sql)
        cur.close()

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def get_db():
    if "db" not in g:
        g.db = PgConnection(DATABASE_URL)
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = PgConnection(DATABASE_URL)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


init_db()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Estado "en vivo" en memoria (para el panel en tiempo real)
# ---------------------------------------------------------------------------
# Solo tiene sentido cuando gestureRecognition.py le habla a ESTE mismo
# proceso (es decir, corriendo localmente): en Vercel cada invocación
# serverless puede ser una instancia distinta, así que "En vivo" ahí
# simplemente va a mostrar "sin datos", nunca datos de otra instancia.

_live_lock = threading.Lock()
_live_state = {
    "session_id": None,
    "gesture_name": None,
    "fingers": None,
    "latency_ms": None,
    "fps": None,
    "hand_detected": False,
    "updated_at": None,
    "test_active": False,
    "test_prompt": None,
}


def update_live_state(**kwargs):
    with _live_lock:
        _live_state.update(kwargs)
        _live_state["updated_at"] = time.time()


def read_live_state():
    with _live_lock:
        state = dict(_live_state)
    if state["updated_at"] is None:
        state["connected"] = False
    else:
        state["connected"] = (time.time() - state["updated_at"]) < 2.0
    return state


# ---------------------------------------------------------------------------
# Rutas: página web
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    # En Vercel esta ruta nunca se usa para "/" (lo sirve el hosting estático
    # de la landing directamente). Localmente, "Inicio" manda a la landing
    # pública para no depender de tener el build de Vite a mano.
    return redirect("https://sianna.vercel.app")


@app.route("/panel")
def panel():
    return send_from_directory(PUBLIC_DIR, "panel.html")


# ---------------------------------------------------------------------------
# Rutas: sesiones
# ---------------------------------------------------------------------------


@app.route("/api/sessions", methods=["POST"])
def create_session():
    payload = request.get_json(silent=True) or {}
    notes = payload.get("notes", "")
    db = get_db()
    cur = db.execute(
        "INSERT INTO sessions (started_at, notes) VALUES (?, ?) RETURNING id",
        (now_iso(), notes),
    )
    session_id = cur.fetchone()["id"]
    db.commit()
    update_live_state(session_id=session_id, test_active=False, test_prompt=None)
    return jsonify({"id": session_id})


@app.route("/api/sessions/<int:session_id>/end", methods=["POST"])
def end_session(session_id):
    db = get_db()
    db.execute(
        "UPDATE sessions SET ended_at = ? WHERE id = ?", (now_iso(), session_id)
    )
    db.commit()
    with _live_lock:
        if _live_state.get("session_id") == session_id:
            _live_state["connected"] = False
    return jsonify({"ok": True})


@app.route("/api/sessions", methods=["GET"])
def list_sessions():
    db = get_db()
    rows = db.execute(
        """
        SELECT s.id, s.started_at, s.ended_at, s.notes,
               (SELECT COUNT(*) FROM gesture_events e WHERE e.session_id = s.id) AS n_events,
               (SELECT COUNT(*) FROM accuracy_tests t WHERE t.session_id = s.id) AS n_tests
        FROM sessions s
        ORDER BY s.id DESC
        """
    ).fetchall()
    return jsonify([dict(r) for r in rows])


# ---------------------------------------------------------------------------
# Rutas: eventos de gestos (usadas por gestureRecognition.py en cada frame)
# ---------------------------------------------------------------------------


@app.route("/api/events", methods=["POST"])
def add_event():
    payload = request.get_json(force=True)
    session_id = payload["session_id"]
    gesture_name = payload.get("gesture_name", "desconocido")
    fingers = payload.get("fingers", [])
    latency_ms = payload.get("latency_ms")
    fps = payload.get("fps")
    hand_detected = int(bool(payload.get("hand_detected", True)))
    is_transition = int(bool(payload.get("is_transition", False)))
    captura_ms = payload.get("captura_ms")
    mediapipe_ms = payload.get("mediapipe_ms")
    inferencia_ms = payload.get("inferencia_ms")
    serial_ms = payload.get("serial_ms")
    servo_ms = payload.get("servo_ms")

    db = get_db()
    db.execute(
        """
        INSERT INTO gesture_events
            (session_id, ts, gesture_name, fingers, latency_ms, fps, hand_detected, is_transition,
             captura_ms, mediapipe_ms, inferencia_ms, serial_ms, servo_ms)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            now_iso(),
            gesture_name,
            json.dumps(fingers),
            latency_ms,
            fps,
            hand_detected,
            is_transition,
            captura_ms,
            mediapipe_ms,
            inferencia_ms,
            serial_ms,
            servo_ms,
        ),
    )
    db.commit()

    update_live_state(
        session_id=session_id,
        gesture_name=gesture_name,
        fingers=fingers,
        latency_ms=latency_ms,
        fps=fps,
        hand_detected=bool(hand_detected),
    )
    return jsonify({"ok": True})


@app.route("/api/live", methods=["GET"])
def live():
    return jsonify(read_live_state())


@app.route("/api/live/test", methods=["POST"])
def set_live_test():
    """gestureRecognition.py llama esto para avisar que hay una prueba de
    precisión en curso, y qué gesto se está pidiendo (para mostrarlo también
    en la web, opcional)."""
    payload = request.get_json(silent=True) or {}
    update_live_state(
        test_active=bool(payload.get("active", False)),
        test_prompt=payload.get("prompt"),
    )
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Rutas: pruebas de precisión
# ---------------------------------------------------------------------------


@app.route("/api/accuracy_tests", methods=["POST"])
def add_accuracy_test():
    payload = request.get_json(force=True)
    db = get_db()
    db.execute(
        """
        INSERT INTO accuracy_tests
            (session_id, ts, expected_gesture, detected_gesture, correct, response_time_ms, timed_out)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload["session_id"],
            now_iso(),
            payload["expected_gesture"],
            payload.get("detected_gesture"),
            int(bool(payload.get("correct", False))),
            payload.get("response_time_ms"),
            int(bool(payload.get("timed_out", False))),
        ),
    )
    db.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Rutas: estadísticas para las gráficas
# ---------------------------------------------------------------------------


def _session_filter_clause(param_name="session_id"):
    session_id = request.args.get(param_name)
    if session_id and session_id != "all":
        return " AND session_id = ? ", [int(session_id)]
    return "", []


@app.route("/api/stats/repetitions", methods=["GET"])
def stats_repetitions():
    db = get_db()
    clause, params = _session_filter_clause()
    rows = db.execute(
        f"""
        SELECT gesture_name, COUNT(*) AS repeticiones
        FROM gesture_events
        WHERE is_transition = 1 {clause}
        GROUP BY gesture_name
        ORDER BY repeticiones DESC
        """,
        params,
    ).fetchall()
    return jsonify([dict(r) for r in rows])


STAGE_COLUMNS = ["captura_ms", "mediapipe_ms", "inferencia_ms", "serial_ms", "servo_ms"]


@app.route("/api/stats/latency", methods=["GET"])
def stats_latency():
    db = get_db()
    clause, params = _session_filter_clause()
    rows = db.execute(
        f"""
        SELECT ts, gesture_name, latency_ms
        FROM gesture_events
        WHERE latency_ms IS NOT NULL {clause}
        ORDER BY id ASC
        LIMIT 2000
        """,
        params,
    ).fetchall()
    values = [r["latency_ms"] for r in rows if r["latency_ms"] is not None]
    summary = {}
    if values:
        sorted_vals = sorted(values)
        summary = {
            "avg": round(statistics.mean(values), 2),
            "median": round(statistics.median(values), 2),
            "min": round(min(values), 2),
            "max": round(max(values), 2),
            "p95": round(sorted_vals[int(len(sorted_vals) * 0.95) - 1], 2)
            if sorted_vals
            else None,
            "n": len(values),
        }

    stages = {}
    for col in STAGE_COLUMNS:
        col_rows = db.execute(
            f"SELECT {col} AS v FROM gesture_events WHERE {col} IS NOT NULL {clause}",
            params,
        ).fetchall()
        col_values = [r["v"] for r in col_rows]
        stages[col] = round(statistics.mean(col_values), 2) if col_values else None

    return jsonify({"points": [dict(r) for r in rows], "summary": summary, "stages": stages})


@app.route("/api/stats/accuracy", methods=["GET"])
def stats_accuracy():
    db = get_db()
    clause, params = _session_filter_clause()
    rows = db.execute(
        f"""
        SELECT expected_gesture, detected_gesture, correct, response_time_ms, timed_out
        FROM accuracy_tests
        WHERE 1 = 1 {clause}
        """,
        params,
    ).fetchall()

    per_gesture = {}
    confusion = {}
    response_times = []
    for r in rows:
        exp = r["expected_gesture"]
        det = r["detected_gesture"] or "(sin detección / tiempo agotado)"
        per_gesture.setdefault(exp, {"total": 0, "correctas": 0})
        per_gesture[exp]["total"] += 1
        if r["correct"]:
            per_gesture[exp]["correctas"] += 1
        confusion.setdefault(exp, {})
        confusion[exp][det] = confusion[exp].get(det, 0) + 1
        if r["response_time_ms"] is not None:
            response_times.append(r["response_time_ms"])

    per_gesture_out = [
        {
            "gesture_name": g,
            "total": v["total"],
            "correctas": v["correctas"],
            "accuracy_pct": round(100.0 * v["correctas"] / v["total"], 1)
            if v["total"]
            else None,
        }
        for g, v in sorted(per_gesture.items())
    ]

    total = sum(v["total"] for v in per_gesture.values())
    correct_total = sum(v["correctas"] for v in per_gesture.values())

    return jsonify(
        {
            "per_gesture": per_gesture_out,
            "confusion": confusion,
            "overall_accuracy_pct": round(100.0 * correct_total / total, 1)
            if total
            else None,
            "avg_response_time_ms": round(statistics.mean(response_times), 2)
            if response_times
            else None,
            "n_tests": total,
        }
    )


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "time": now_iso()})
