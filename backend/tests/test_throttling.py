"""
Throttle gates for the unauthenticated authentication endpoints
[ImplementationGuide Phase 13].

``auth/login``, ``auth/refresh``, ``auth/forgot-password``, ``auth/verify-otp``
and ``auth/reset-password`` are reachable without a token, so they must remain
behind DRF's anonymous throttle. These tests lower the anonymous rate and prove
the third request in a window is rejected with 429.
"""
from __future__ import annotations

import pytest
from django.core.cache import cache
from rest_framework import status
from rest_framework.throttling import AnonRateThrottle

PUBLIC_AUTH_REQUESTS = [
    (
        "/api/v1/auth/login",
        {
            "email": "throttle-nobody@college.edu",
            "password": "WrongP@ssw0rd123!",
            "device_id": "throttle-device",
            "platform": "ANDROID",
        },
    ),
    ("/api/v1/auth/refresh", {"refresh": "not-a-real-refresh-token"}),
    ("/api/v1/auth/forgot-password", {"email": "throttle-nobody@college.edu"}),
    (
        "/api/v1/auth/verify-otp",
        {"email": "throttle-nobody@college.edu", "otp": "000000"},
    ),
    (
        "/api/v1/auth/reset-password",
        {
            "email": "throttle-nobody@college.edu",
            "otp": "000000",
            "new_password": "AnotherP@ssw0rd123!",
        },
    ),
]


@pytest.fixture(autouse=True)
def clear_throttle_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
def test_public_auth_endpoints_reject_third_request_when_anon_rate_is_low(
    api_client, monkeypatch
):
    monkeypatch.setattr(
        AnonRateThrottle,
        "THROTTLE_RATES",
        {**AnonRateThrottle.THROTTLE_RATES, "anon": "2/minute"},
    )

    for path, payload in PUBLIC_AUTH_REQUESTS:
        cache.clear()

        first = api_client.post(path, payload, format="json")
        second = api_client.post(path, payload, format="json")
        third = api_client.post(path, payload, format="json")

        assert first.status_code != status.HTTP_429_TOO_MANY_REQUESTS, (
            f"{path} was throttled on the first request"
        )
        assert second.status_code != status.HTTP_429_TOO_MANY_REQUESTS, (
            f"{path} was throttled on the second request"
        )
        assert third.status_code == status.HTTP_429_TOO_MANY_REQUESTS, (
            f"{path} did not throttle the third request "
            f"(got {third.status_code})"
        )
        assert "throttl" in str(third.data).lower()
