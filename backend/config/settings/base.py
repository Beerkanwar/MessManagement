"""
Base Django settings for Hostel Mess Management System.
Governed by ImplementationGuide.md Phase 1 and reference specifications.
"""
from datetime import timedelta
from pathlib import Path
import environ

# Paths: BASE_DIR is backend/
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Initialize django-environ
env = environ.Env()
if (BASE_DIR / ".env").exists():
    env.read_env(BASE_DIR / ".env")
elif (BASE_DIR.parent / ".env").exists():
    env.read_env(BASE_DIR.parent / ".env")

# Security & Core
SECRET_KEY = env("DJANGO_SECRET_KEY", default="django-insecure-mess-management-phase1-dev-key-change-in-prod")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# Time & Localization (DEC-01)
# Server TIME_ZONE = Asia/Kolkata (no DST); timestamps stored UTC in timestamptz
TIME_ZONE = "Asia/Kolkata"
USE_TZ = True
USE_I18N = True

# Primary Key & User Model
# DEFAULT_AUTO_FIELD = AutoField so master and transaction keys are PostgreSQL integer identity columns [SPEC DBDD §1]
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
# Custom user model before the first migration [SPEC DBDD §3, ImplementationGuide Phase 1]
AUTH_USER_MODEL = "identity.User"

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party packages
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    # Core utilities (no tables)
    "apps.core",
    # 11 table-owning DBDD apps + 2 table-less apps (CONFLICT-02)
    "apps.identity",
    "apps.config",
    "apps.hostel",
    "apps.mess",
    "apps.attendance",
    "apps.pause",
    "apps.billing",
    "apps.menu",
    "apps.feedback",
    "apps.sync",
    "apps.audit",
    "apps.qr",
    "apps.reports",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "apps.core.middleware.RequestIdMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "apps.core.middleware.RequestLoggingMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database Configuration (PostgreSQL 16 via psycopg 3)
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://mess_dev:change-me-dev-only@127.0.0.1:5432/MessManagementDb",
    )
}
# ATOMIC_REQUESTS off, because services open explicit transactions [REC]
DATABASES["default"]["ATOMIC_REQUESTS"] = False

# Shared Database Cache for DRF Throttling across gunicorn workers [REC]
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "api_cache_table",
    }
}

# Password Hashers & Validators
# argon2-cffi (Argon2id first in PASSWORD_HASHERS [REC])
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

# Institutional Password Policy [DEC-11]
# Password: 10+ characters plus Django's common/numeric/similarity validators
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Password Hashers - Argon2id primary per ImplementationGuide Phase 3 & DEC-11
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]

# REST Framework Configuration
REST_FRAMEWORK = {
    # JSON-only renderers and parsers (multipart enabled only on import endpoint) [REC]
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    # Default permission is authenticated [SPEC SDD §64]
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.identity.authentication.DeviceBindingJWTAuthentication",
    ],
    # Pagination: default 50, max 200 [ImplementationGuide Phase 1]
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPageNumberPagination",
    "PAGE_SIZE": 50,
    # DRF exception handler returning {code, message, traceId} [SPEC SDD §88, §89]
    "EXCEPTION_HANDLER": "apps.core.exceptions.custom_exception_handler",
    # Throttling limits shared across workers using DB cache [REC]
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/minute",
        "user": "1000/minute",
    },
    # drf-spectacular schema generator
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# Upload Size Caps (10 MB cap) [REC]
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# Security behind reverse proxy
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# CORS Settings (Web origin only; mobile needs no CORS) [ImplementationGuide Phase 1]
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=["http://localhost:5173"],
)
CORS_ALLOW_CREDENTIALS = True

# SimpleJWT Configuration [SPEC SDD §11.1, §100, DEC-10]
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ALGORITHM": "HS256",
    "SIGNING_KEY": env("JWT_SIGNING_KEY", default="dev-jwt-signing-secret-key-at-least-32-chars-long!"),
    "AUDIENCE": env("JWT_AUDIENCE", default="mess-management-api"),
    "ISSUER": env("JWT_ISSUER", default="mess-management-auth"),
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# drf-spectacular OpenAPI Settings [SPEC SDD §64]
SPECTACULAR_SETTINGS = {
    "TITLE": "Hostel Mess Management System API",
    "DESCRIPTION": "Central API contract for Hostel Mess Management System",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    "COMPONENT_SPLIT_REQUEST": True,
    "OPERATION_ID_GENERATOR": "apps.core.schema.custom_operation_id_generator",
}

# Static & Media
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Structured Logging with Structlog & Redaction [SPEC SDD §63, §103]
LOG_LEVEL = env("LOG_LEVEL", default="INFO").upper()

import structlog
from apps.core.logging import redact_sensitive_data

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        redact_sensitive_data,
        structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": structlog.stdlib.ProcessorFormatter,
            "processor": structlog.processors.JSONRenderer(),
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}
