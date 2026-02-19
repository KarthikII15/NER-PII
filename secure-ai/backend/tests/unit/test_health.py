"""
test_health.py — Phase 1 smoke tests for the /health endpoints.
These must always pass. They are the CI gate for every build.
"""


def test_liveness_returns_200(client):
    """GET /health/live must return HTTP 200."""
    response = client.get("/health/live")
    assert response.status_code == 200


def test_liveness_returns_ok_status(client):
    """GET /health/live must return {'status': 'ok'}."""
    response = client.get("/health/live")
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data


def test_readiness_returns_200(client):
    """GET /health/ready must return HTTP 200."""
    response = client.get("/health/ready")
    assert response.status_code == 200


def test_readiness_has_checks(client):
    """GET /health/ready must include a 'checks' field (Phase 1: baseline only)."""
    response = client.get("/health/ready")
    data = response.json()
    assert data["status"] == "ready"
    assert "checks" in data
    assert "model" in data["checks"]
    assert "database" in data["checks"]


def test_root_redirect(client):
    """GET / must return 200 and a welcome message."""
    response = client.get("/")
    assert response.status_code == 200
    assert "message" in response.json()
