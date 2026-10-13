"""
Tests for health endpoints outside versioned prefix [SPEC SDD §105].
Checkpoints:
- GET /health/live and /health/ready return 200 OK.
- /health/ready turns 503 when DB is stopped/unreachable or migrations are pending.
"""
from unittest.mock import patch
import pytest
from django.db import OperationalError


@pytest.mark.django_db
def test_health_live_success(api_client):
    """GET /health/live returns 200 and confirms process is up."""
    response = api_client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "live": True}


@pytest.mark.django_db
def test_health_ready_success(api_client):
    """GET /health/ready returns 200 when database is reachable and migrations are applied."""
    response = api_client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["ready"] is True
    assert data["database"] == "connected"
    assert data["migrations"] == "applied"


@pytest.mark.django_db
def test_health_ready_database_failure(api_client):
    """GET /health/ready turns 503 when the database is unreachable."""
    with patch("django.db.connection.cursor", side_effect=OperationalError("Connection refused")):
        response = api_client.get("/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unavailable"
        assert data["ready"] is False
        assert data["error"] == "Database unreachable"


@pytest.mark.django_db
def test_health_ready_unapplied_migrations(api_client):
    """GET /health/ready turns 503 when unapplied migrations are pending."""
    fake_plan = [("identity", "0002_migration")]
    with patch("django.db.migrations.executor.MigrationExecutor.migration_plan", return_value=fake_plan):
        response = api_client.get("/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unavailable"
        assert data["ready"] is False
        assert data["error"] == "Unapplied migrations pending"
        assert data["pending_migrations_count"] == 1
