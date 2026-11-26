"""Integration tests: real HTTP calls against a running deployment backed by PostgreSQL.
Run with: BASE_URL=http://host:port pytest tests/test_integration.py"""
import os
import uuid

import pytest
import requests

BASE = os.environ.get("BASE_URL")
pytestmark = pytest.mark.skipif(not BASE, reason="BASE_URL not set (needs a running deployment)")


def test_ready_with_database():
    r = requests.get(f"{BASE}/readyz", timeout=5)
    assert r.status_code == 200 and r.json()["database"] == "ok"


def test_task_lifecycle_persists():
    title = f"integration-{uuid.uuid4().hex[:8]}"
    created = requests.post(f"{BASE}/api/tasks", json={"title": title}, timeout=5)
    assert created.status_code == 201
    tid = created.json()["id"]
    assert any(t["title"] == title for t in requests.get(f"{BASE}/api/tasks", timeout=5).json())
    assert requests.put(f"{BASE}/api/tasks/{tid}", json={"done": True}, timeout=5).json()["done"] is True
    assert requests.delete(f"{BASE}/api/tasks/{tid}", timeout=5).status_code == 204


def test_metrics_endpoint():
    assert "http_requests_total" in requests.get(f"{BASE}/metrics", timeout=5).text
