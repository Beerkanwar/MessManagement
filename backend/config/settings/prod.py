"""
Production settings for Hostel Mess Management System.
"""
from django.core.exceptions import ImproperlyConfigured
from .base import *  # noqa: F403
from .base import env, SIMPLE_JWT

# DEBUG forced off in prod settings [ImplementationGuide Phase 1]
DEBUG = False

# Strict production secrets enforcement (ISSUE-02)
INSECURE_DEV_SECRETS = {
    "django-insecure-mess-management-phase1-dev-key-change-in-prod",
    "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "dev-jwt-signing-secret-key-at-least-32-chars-long!",
}

SECRET_KEY = env("DJANGO_SECRET_KEY")
if not SECRET_KEY or SECRET_KEY in INSECURE_DEV_SECRETS:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be securely configured in production.")

qr_enc_key = env("QR_SECRET_ENCRYPTION_KEY")
if not qr_enc_key or qr_enc_key in INSECURE_DEV_SECRETS:
    raise ImproperlyConfigured("QR_SECRET_ENCRYPTION_KEY must be securely configured in production.")
SECRET_ENCRYPTION_KEYS = {1: qr_enc_key}

jwt_key = env("JWT_SIGNING_KEY")
if not jwt_key or jwt_key in INSECURE_DEV_SECRETS:
    raise ImproperlyConfigured("JWT_SIGNING_KEY must be securely configured in production.")
SIMPLE_JWT["SIGNING_KEY"] = jwt_key

# Strict allowed hosts
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")

# HTTPS and Proxy Security
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Email backend in production
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
