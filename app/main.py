"""Task Manager REST API with health probes, Prometheus metrics and structured JSON logs."""
import json
import logging
import os
import random
import sys
import time

from flask import Flask, g, jsonify, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

from app import __version__
from app.db import Database

VERSION = os.environ.get("APP_VERSION", __version__)
VALID_PRIORITIES = {"low", "medium", "high"}

REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "endpoint", "status", "version"])
LATENCY = Histogram("http_request_duration_seconds", "Request latency", ["endpoint", "version"],
                    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5))
TASKS = Gauge("tasks_total", "Number of tasks in the database")
INFO = Gauge("app_info", "Application build info", ["version"])


class JsonFormatter(logging.Formatter):
    def format(self, record):
        entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "level": record.levelname,
                 "logger": record.name, "msg": record.getMessage(), "version": VERSION}
        entry.update(getattr(record, "extra_fields", {}))
        return json.dumps(entry)


def setup_logging():
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
    logging.getLogger("werkzeug").setLevel(logging.WARNING)


def create_app(database_url=None):
    setup_logging()
    log = logging.getLogger("taskapi")
    app = Flask(__name__)
    db = Database(database_url)
    for attempt in range(1, 11):  # tolerate a briefly unavailable database at startup
        try:
            db.init_schema()
            break
        except Exception as exc:
            if attempt == 10:
                raise
            log.warning("database not ready, retrying", extra={"extra_fields": {"attempt": attempt, "error": str(exc)}})
            time.sleep(min(2 ** attempt, 10) * 0.5)
    INFO.labels(VERSION).set(1)
    # Fault injection is ONLY used to simulate a bad release in the canary demo.
    fault_rate = float(os.environ.get("FAULT_RATE", "0"))

    @app.before_request
    def start_timer():
        g.start = time.perf_counter()
        if fault_rate and request.path.startswith("/api/") and random.random() < fault_rate:  # nosec B311
            return jsonify(error="injected fault"), 500

    @app.after_request
    def record(resp):
        endpoint = request.url_rule.rule if request.url_rule else "unmatched"
        if endpoint not in ("/metrics", "/healthz", "/readyz"):
            dur = time.perf_counter() - g.get("start", time.perf_counter())
            REQUESTS.labels(request.method, endpoint, resp.status_code, VERSION).inc()
            LATENCY.labels(endpoint, VERSION).observe(dur)
            log.info("request", extra={"extra_fields": {
                "method": request.method, "path": request.path, "status": resp.status_code,
                "duration_ms": round(dur * 1000, 2), "client": request.headers.get("X-User-Id", "-")}})
        return resp

    @app.get("/healthz")
    def healthz():
        return jsonify(status="alive", version=VERSION)

    @app.get("/readyz")
    def readyz():
        try:
            db.ping()
            return jsonify(status="ready", database="ok")
        except Exception as exc:  # pragma: no cover - exercised in k8s
            log.error("readiness failed", extra={"extra_fields": {"error": str(exc)}})
            return jsonify(status="not ready", database="unreachable"), 503

    @app.get("/metrics")
    def metrics():
        try:
            TASKS.set(db.query("SELECT COUNT(*) AS n FROM tasks", one=True)["n"])
        except Exception:  # pragma: no cover
            pass
        return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}

    @app.get("/version")
    def version():
        return jsonify(version=VERSION, hostname=os.environ.get("HOSTNAME", "local"))

    @app.get("/api/tasks")
    def list_tasks():
        priority = request.args.get("priority")
        if priority:
            if priority not in VALID_PRIORITIES:
                return jsonify(error=f"priority must be one of {sorted(VALID_PRIORITIES)}"), 400
            rows = db.query("SELECT id, title, done, priority FROM tasks WHERE priority = ? ORDER BY id", (priority,))
            return jsonify(rows)
        return jsonify(db.query("SELECT id, title, done, priority FROM tasks ORDER BY id"))

    @app.post("/api/tasks")
    def create_task():
        data = request.get_json(silent=True) or {}
        title = str(data.get("title", "")).strip()
        priority = data.get("priority", "medium")
        if not title or len(title) > 200:
            return jsonify(error="title is required (max 200 chars)"), 400
        if priority not in VALID_PRIORITIES:
            return jsonify(error=f"priority must be one of {sorted(VALID_PRIORITIES)}"), 400
        row = db.query("INSERT INTO tasks (title, priority) VALUES (?, ?) RETURNING id, title, done, priority",
                       (title, priority), one=True, commit=True)
        log.info("task created", extra={"extra_fields": {"task_id": row["id"]}})
        return jsonify(row), 201

    @app.get("/api/tasks/<int:task_id>")
    def get_task(task_id):
        row = db.query("SELECT id, title, done, priority FROM tasks WHERE id = ?", (task_id,), one=True)
        return (jsonify(row), 200) if row else (jsonify(error="not found"), 404)

    @app.put("/api/tasks/<int:task_id>")
    def update_task(task_id):
        data = request.get_json(silent=True) or {}
        if "done" not in data or not isinstance(data["done"], bool):
            return jsonify(error="'done' (boolean) is required"), 400
        row = db.query("UPDATE tasks SET done = ? WHERE id = ? RETURNING id, title, done, priority",
                       (data["done"], task_id), one=True, commit=True)
        return (jsonify(row), 200) if row else (jsonify(error="not found"), 404)

    @app.delete("/api/tasks/<int:task_id>")
    def delete_task(task_id):
        row = db.query("DELETE FROM tasks WHERE id = ? RETURNING id", (task_id,), one=True, commit=True)
        return ("", 204) if row else (jsonify(error="not found"), 404)

    log.info("app started", extra={"extra_fields": {"database": "postgresql" if db.is_pg else "sqlite"}})
    return app


app = create_app() if os.environ.get("DATABASE_URL") else None
