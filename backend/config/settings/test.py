"""
Test settings for Hostel Mess Management System.
Configured for pytest against real PostgreSQL 16.
"""
from .base import *  # noqa: F403

DEBUG = False
TESTING = True

# Fast password hasher strictly for test execution speed [ImplementationGuide Phase 1, ISSUE-21]
# SECURITY NOTE: MD5 is intentionally weak and strictly prohibited in dev and prod environments.
# Base and production settings enforce Argon2PasswordHasher with PBKDF2 fallbacks.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
    "django.contrib.auth.hashers.Argon2PasswordHasher",
]

# Fast in-memory sinks for tests
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test-cache",
    }
}
