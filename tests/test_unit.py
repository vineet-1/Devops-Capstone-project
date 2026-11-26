"""Unit tests: API behaviour against an isolated in-memory SQLite database."""
import pytest

from app.main import create_app


@pytest.fixture
def client():
    return create_app("sqlite:///:memory:").test_client()


def test_health(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json["status"] == "alive"


def test_ready(client):
    assert client.get("/readyz").json["database"] == "ok"


def test_create_and_get_task(client):
    r = client.post("/api/tasks", json={"title": "Write report", "priority": "high"})
    assert r.status_code == 201
    tid = r.json["id"]
    assert client.get(f"/api/tasks/{tid}").json["title"] == "Write report"


def test_default_priority(client):
    assert client.post("/api/tasks", json={"title": "x"}).json["priority"] == "medium"


@pytest.mark.parametrize("payload", [{}, {"title": ""}, {"title": "a" * 201}, {"title": "ok", "priority": "urgent"}])
def test_validation(client, payload):
    assert client.post("/api/tasks", json=payload).status_code == 400


def test_update_and_delete(client):
    tid = client.post("/api/tasks", json={"title": "t"}).json["id"]
    assert client.put(f"/api/tasks/{tid}", json={"done": True}).json["done"] in (True, 1)
    assert client.put(f"/api/tasks/{tid}", json={"done": "yes"}).status_code == 400
    assert client.delete(f"/api/tasks/{tid}").status_code == 204
    assert client.get(f"/api/tasks/{tid}").status_code == 404


def test_not_found(client):
    assert client.delete("/api/tasks/999").status_code == 404
    assert client.put("/api/tasks/999", json={"done": True}).status_code == 404


def test_metrics_exposed(client):
    client.get("/api/tasks")
    body = client.get("/metrics").data.decode()
    assert "http_requests_total" in body and "app_info" in body


def test_filter_by_priority(client):
    client.post("/api/tasks", json={"title": "a", "priority": "high"})
    client.post("/api/tasks", json={"title": "b", "priority": "low"})
    assert [t["title"] for t in client.get("/api/tasks?priority=high").json] == ["a"]
    assert client.get("/api/tasks?priority=urgent").status_code == 400
