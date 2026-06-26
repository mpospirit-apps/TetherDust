"""Django settings for the TetherDust backend."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


# ===========================================================================
# SECURITY
# ===========================================================================
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-change-me-in-production")
DEBUG = os.getenv("DJANGO_DEBUG", "False").lower() in ("true", "1", "yes")

if not DEBUG and SECRET_KEY == "django-insecure-change-me-in-production":
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set in production (DEBUG=False).")

ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

# CSRF trusted origins — required when serving over HTTPS behind a proxy.
# Comma-separated, scheme included, e.g. "https://tetherdust.example.com".
_csrf_trusted = os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "")
if _csrf_trusted:
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_trusted.split(",") if o.strip()]

# Production security hardening. Enabled automatically whenever DEBUG is off, so
# a production deploy is never wide-open by default. Assumes TLS is terminated by
# a reverse proxy / load balancer in front of the app.
if not DEBUG:
    # Trust the proxy's X-Forwarded-Proto so Django recognizes HTTPS requests.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    # Redirect HTTP → HTTPS (override to False if the proxy already does this).
    SECURE_SSL_REDIRECT = os.getenv("DJANGO_SECURE_SSL_REDIRECT", "True").lower() in (
        "true",
        "1",
        "yes",
    )
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    # HSTS — default one year. Set DJANGO_SECURE_HSTS_SECONDS=0 to disable while
    # validating a TLS rollout.
    SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
    SECURE_HSTS_PRELOAD = SECURE_HSTS_SECONDS > 0


# ===========================================================================
# LOGGING
# ===========================================================================
# Kept after SECURITY (rather than the conventional second slot) because
# LOG_LEVEL derives from DEBUG, which the SECURITY section defines.
LOG_LEVEL = os.getenv("DJANGO_LOG_LEVEL", "INFO" if not DEBUG else "DEBUG")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {message}",
            "style": "{",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "simple": {
            "format": "{levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "management": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["management"],
        "level": "WARNING",
    },
    "loggers": {
        "django": {
            "handlers": ["management"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["management"],
            "level": "ERROR",
            "propagate": False,
        },
        "engine": {
            "handlers": ["management"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "workspace": {
            "handlers": ["management"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "management": {
            "handlers": ["management"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "workspace.consumers": {
            "handlers": ["management"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "engine.consumers": {
            "handlers": ["management"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "engine.agents": {
            "handlers": ["management"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
    },
}


# ===========================================================================
# APPLICATION DEFINITION
# ===========================================================================
INSTALLED_APPS = [
    # Daphne — must precede django.contrib.staticfiles so its ASGI runserver wins
    "daphne",
    # Django core
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Third-party
    "channels",
    "rest_framework",
    # Project apps
    "engine.apps.EngineConfig",
    "workspace.apps.WorkspaceConfig",
    "management.apps.ManagementConfig",
    "api.apps.ApiConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Serves collected static files directly (from STATIC_ROOT) so the app works
    # with DEBUG=False, where Django's dev-server static handler is disabled.
    # Must sit immediately after SecurityMiddleware (WhiteNoise convention).
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# ===========================================================================
# URLS AND WSGI
# ===========================================================================
ROOT_URLCONF = "project.urls"
WSGI_APPLICATION = "project.wsgi.application"
ASGI_APPLICATION = "project.asgi.application"


# ===========================================================================
# TEMPLATES
# ===========================================================================
# The template engine is retained only for DRF's browsable API; there are no app
# templates (the SPA is the entire UI). The legacy per-view UI context processors
# were removed with the server-rendered pages — /api/v1/auth/me/ now carries the
# permission flags the templates used to inject.
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


# ===========================================================================
# AUTH
# ===========================================================================
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"


# ===========================================================================
# DATABASE
# ===========================================================================
if os.getenv("DB_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "HOST": os.getenv("DB_HOST"),
            "PORT": os.getenv("DB_PORT", "5432"),
            "NAME": os.getenv("DB_NAME", "tetherdust"),
            "USER": os.getenv("DB_USER", "tetherdust"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(BASE_DIR / "db.sqlite3"),
        }
    }


# ===========================================================================
# INTERNATIONALIZATION
# ===========================================================================
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# ===========================================================================
# STATIC FILES
# ===========================================================================
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
# Where `collectstatic` gathers files for WhiteNoise to serve in production.
# Placed outside the app source tree (which the dev compose bind-mounts) so the
# image-baked collected files aren't shadowed by the mount. WhiteNoise serves
# files at their original names (no manifest hashing), so templates that
# reference /static/... paths keep working without changes.
STATIC_ROOT = BASE_DIR.parent / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ===========================================================================
# CELERY
# ===========================================================================
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
CELERY_TASK_IGNORE_RESULT = True
CELERY_BEAT_SCHEDULE = {
    "check-due-reports": {
        "task": "engine.tasks.check_due_reports",
        "schedule": 60.0,
    },
    "refresh-dashboard-charts": {
        "task": "engine.tasks.check_due_dashboard_refreshes",
        "schedule": 60.0,
    },
    "sync-codex-auth-token": {
        "task": "engine.tasks.sync_codex_auth_token",
        "schedule": 3600.0,
    },
    "check-for-updates": {
        "task": "engine.tasks.check_for_updates",
        "schedule": 21600.0,  # every 6 hours
    },
}


# ===========================================================================
# CHANNELS
# ===========================================================================
_REDIS_URL = os.getenv("REDIS_URL")
if _REDIS_URL:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [_REDIS_URL]},
        },
    }
else:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        },
    }


# ===========================================================================
# REST FRAMEWORK
# ===========================================================================
# Session-cookie auth (CSRF enforced on unsafe methods).
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "EXCEPTION_HANDLER": "api.exceptions.custom_exception_handler",
}


# ===========================================================================
# TETHERDUST
# ===========================================================================
# Encryption key for database credentials (generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") # noqa: E501
TETHERDUST_ENCRYPTION_KEY = os.getenv("TETHERDUST_ENCRYPTION_KEY", "")

# Shared secret authenticating the internal service API (tdmcp → backend). The
# MCP server's mutating tools send it as the X-Service-Token header. Fails closed:
# when unset, every /api/internal/ call is rejected (it is a write API).
INTERNAL_API_SERVICE_TOKEN = os.getenv("INTERNAL_API_SERVICE_TOKEN", "")

# Report results filesystem storage.
TETHERDUST_REPORT_RESULTS_DIR = os.getenv(
    "TETHERDUST_REPORT_RESULTS_DIR",
    str(BASE_DIR / "report_results"),
)

# Documentation sources folder — admins place doc folders here.
TETHERDUST_DOCUMENTATIONS_DIR = os.getenv(
    "TETHERDUST_DOCUMENTATIONS_DIR",
    str(BASE_DIR.parent / "documentations"),
)
