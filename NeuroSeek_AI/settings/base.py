"""
Base settings for NeuroSeek AI.

All values that don't differ between dev and prod live here.
Environment-specific overrides go in dev.py / prod.py.
"""
from datetime import timedelta
from pathlib import Path

import environ

# ---------------------------------------------------------------------------
# Paths & environment
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CORS_ALLOWED_ORIGINS=(list, []),
    JWT_ACCESS_TOKEN_LIFETIME_MINUTES=(int, 60),
    JWT_REFRESH_TOKEN_LIFETIME_DAYS=(int, 7),
    EMBEDDING_DIM=(int, 384),
)

# Load .env if present (Docker also injects via env_file; both work)
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = env("DJANGO_SECRET_KEY", default="unsafe-default-replace-me")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")

# ---------------------------------------------------------------------------
# Apps
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "daphne",  # must come before django.contrib.staticfiles for ASGI dev server
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "channels",
    "django_celery_results",
]

LOCAL_APPS = [
    "apps.accounts",
    "apps.vector",
    "apps.realtime",
    "apps.search",
    "apps.queries",
    "apps.ai",
    "apps.research",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "NeuroSeek_AI.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "frontend" / "templates"],
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

WSGI_APPLICATION = "NeuroSeek_AI.wsgi.application"
ASGI_APPLICATION = "NeuroSeek_AI.asgi.application"

# ---------------------------------------------------------------------------
# Database (Postgres + pgvector)
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST"),
        "PORT": env("POSTGRES_PORT"),
        "CONN_MAX_AGE": 60,
    }
}

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# DRF + JWT
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    # JWT only — sessions are only used for /admin/ (Django handles those
    # natively, outside DRF). Including SessionAuthentication here triggers
    # CSRF enforcement for any API POST whenever a Django sessionid cookie is
    # present in the browser (e.g. after logging into /admin/), which breaks
    # JWT login/register flows from the SPA. Don't add it back.
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "30/min",
        "user": "120/min",
    },
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.URLPathVersioning",
    "DEFAULT_VERSION": "v1",
    "ALLOWED_VERSIONS": ["v1"],
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env("JWT_ACCESS_TOKEN_LIFETIME_MINUTES")),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env("JWT_REFRESH_TOKEN_LIFETIME_DAYS")),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [env("CHANNELS_REDIS_URL")]},
    },
}

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = env("TIME_ZONE", default="UTC")
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 60 * 30  # 30 min hard cap (research jobs)
CELERY_TASK_SOFT_TIME_LIMIT = 60 * 25
CELERY_WORKER_MAX_TASKS_PER_CHILD = 50  # recycle workers to release memory
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # one task at a time on a small VPS

# ---------------------------------------------------------------------------
# Redis (shared by cache + realtime publisher)
# ---------------------------------------------------------------------------
REDIS_URL = env("REDIS_URL")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "TIMEOUT": 300,
    }
}

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True

# ---------------------------------------------------------------------------
# i18n / tz
# ---------------------------------------------------------------------------
LANGUAGE_CODE = env("LANGUAGE_CODE", default="en-us")
TIME_ZONE = env("TIME_ZONE", default="UTC")
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static & media
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "frontend" / "static"] if (BASE_DIR / "frontend" / "static").exists() else []

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# AI / Embeddings (read here so all apps share one source of truth)
# ---------------------------------------------------------------------------
EMBEDDING_MODEL_NAME = env("EMBEDDING_MODEL_NAME", default="sentence-transformers/all-MiniLM-L6-v2")
EMBEDDING_DIM = env("EMBEDDING_DIM")

# ---------------------------------------------------------------------------
# SearXNG (web search backend)
# ---------------------------------------------------------------------------
SEARXNG_BASE_URL = env("SEARXNG_BASE_URL", default="http://searxng:8080")

# ---------------------------------------------------------------------------
# Web scraping — Jina Reader fallback for hostile sites (Medium, JS SPAs, etc.)
# ---------------------------------------------------------------------------
USE_JINA_FALLBACK = env.bool("USE_JINA_FALLBACK", default=True)
JINA_API_KEY = env("JINA_API_KEY", default="")

# ---------------------------------------------------------------------------
# LLM (pluggable provider — currently only Ollama implemented)
# ---------------------------------------------------------------------------
LLM_PROVIDER = env("LLM_PROVIDER", default="ollama")
OLLAMA_BASE_URL = env("OLLAMA_BASE_URL", default="http://ollama:11434")
OLLAMA_MODEL = env("OLLAMA_MODEL", default="qwen2.5:1.5b")
LLM_TIMEOUT_SECONDS = env.int("LLM_TIMEOUT_SECONDS", default=60)
LLM_MAX_TOKENS = env.int("LLM_MAX_TOKENS", default=900)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "apps": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
    },
}
