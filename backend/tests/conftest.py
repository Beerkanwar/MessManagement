"""
Pytest configuration and shared fixtures for backend test harness.
Configured for execution against real PostgreSQL 16.
"""
import pytest
from rest_framework.test import APIClient
from apps.core.clock import clock


@pytest.fixture
def api_client():
    """Provides a fresh Django REST Framework APIClient instance."""
    return APIClient()


@pytest.fixture(autouse=True)
def reset_clock_service():
    """Ensures clock service is always reset after each test execution."""
    yield
    clock.reset()
