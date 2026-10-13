"""
Test settings for Hostel Mess Management System.
Configured for pytest against real PostgreSQL 16.
"""
from .base import *  # noqa: F403

DEBUG = False

# Fast password hasher for test execution speed [ImplementationGuide Phase 1]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Fast in-memory sinks for tests
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test-cache",
    }
}
