import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-key")

from .settings import *  # noqa: E402,F401,F403

ALLOWED_HOSTS = ["testserver", "localhost"]
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_CLASSES": []}  # noqa: F405
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "tests"}}
