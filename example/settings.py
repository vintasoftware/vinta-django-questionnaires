"""Settings for the example project.

Local development only: the secret key is in the file and the database is a
sqlite file next to it.
"""

from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

SECRET_KEY = "vinta-django-questionnaires-example-only"
DEBUG = True
ALLOWED_HOSTS = ["*"]
USE_TZ = True
TIME_ZONE = "UTC"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.messages",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "vinta_django_questionnaires",
    "example",
]

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "example.urls"

# The React demo runs on its own port and reaches Django through Vite's proxy,
# so the browser's Origin is the Vite one while the Host is Django's.
CSRF_TRUSTED_ORIGINS = ["http://localhost:5273", "http://127.0.0.1:5273"]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

STATIC_URL = "/static/"

# The admin's structure editor puts a whole questionnaire on one form, so it
# posts one input per field of every page, section, question, choice and
# validator. Django's default cap is 1000, which a questionnaire of a dozen
# questions goes past; the editor says so rather than failing with a 500, but
# a project that wants to use it has to raise this.
DATA_UPLOAD_MAX_NUMBER_FIELDS = 5000
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
