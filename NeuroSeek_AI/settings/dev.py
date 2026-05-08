"""Development settings — loaded by default via DJANGO_SETTINGS_MODULE."""
from .base import *  # noqa: F401,F403

DEBUG = True

# Generous CORS for local frontend tinkering
CORS_ALLOW_ALL_ORIGINS = True

# Console email in dev
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Loosen DRF throttles in dev
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {  # noqa: F405
    "anon": "1000/min",
    "user": "5000/min",
}

# WhiteNoise: serve static files directly from STATICFILES_DIRS in dev
# (no need to run `collectstatic` while iterating on frontend code)
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True

# Hot-reloading-ish: the bind mount + this autorefresh means saving CSS/JS
# is picked up on the next page reload.
