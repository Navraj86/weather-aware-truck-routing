import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIST = Path(os.environ.get("FRONTEND_DIST", BASE_DIR.parent / "frontend" / "dist"))


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).lower() in {"1", "true", "yes", "on"}


DEBUG = env_bool("DJANGO_DEBUG", False)
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key" if DEBUG else "")
if not SECRET_KEY:
    raise RuntimeError("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is off")

ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
if os.environ.get("RENDER_EXTERNAL_HOSTNAME"):
    ALLOWED_HOSTS.append(os.environ["RENDER_EXTERNAL_HOSTNAME"])
CSRF_TRUSTED_ORIGINS = [
    f"https://*{h}" if h.startswith(".") else f"https://{h}" for h in ALLOWED_HOSTS if h not in {"localhost", "127.0.0.1"}
]

INSTALLED_APPS = [
    "corsheaders",
    "rest_framework",
    "planner",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.gzip.GZipMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
DATABASES: dict = {}  # stateless API, no persistence needed

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "OPTIONS": {"MAX_ENTRIES": 20000},
    }
}

USE_TZ = True
TIME_ZONE = "UTC"

STATIC_URL = "static/"
# Serve the built React app (index.html, /assets/*) from the site root.
WHITENOISE_ROOT = FRONTEND_DIST if FRONTEND_DIST.exists() else None
WHITENOISE_MAX_AGE = 3600


def _hashed_asset(path: str, url: str) -> bool:
    return url.startswith("/assets/")  # Vite fingerprints these, so they can be cached forever


WHITENOISE_IMMUTABLE_FILE_TEST = _hashed_asset

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "geocode": os.environ.get("GEOCODE_RATE_LIMIT", "120/min"),
        "plan": os.environ.get("PLAN_RATE_LIMIT", "20/min"),
    },
}

CORS_ALLOWED_ORIGINS = [o for o in os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",") if o]

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Third-party services (all free, keyless by default).
VALHALLA_URL = os.environ.get("VALHALLA_URL", "https://valhalla1.openstreetmap.de")
OSRM_URL = os.environ.get("OSRM_URL", "https://router.project-osrm.org")
OPEN_METEO_URL = os.environ.get("OPEN_METEO_URL", "https://api.open-meteo.com")
OPEN_METEO_API_KEY = os.environ.get("OPEN_METEO_API_KEY", "")
PHOTON_URL = os.environ.get("PHOTON_URL", "https://photon.komoot.io")
HTTP_USER_AGENT = os.environ.get("HTTP_USER_AGENT", "weather-aware-truck-routing/1.0")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
}
