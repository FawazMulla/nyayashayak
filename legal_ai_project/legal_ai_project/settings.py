import os
import dj_database_url
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-kakifjr5@cd^t9tla1#ga)v_l-#8b&axpv&7eqiwam&b7tdm$3")
DEBUG      = os.environ.get("DEBUG", "true").lower() == "true"

_raw_hosts = os.environ.get("ALLOWED_HOSTS", "*")
ALLOWED_HOSTS = [h.strip() for h in _raw_hosts.split(",") if h.strip()]

_raw_origins = os.environ.get("CSRF_TRUSTED_ORIGINS", "http://localhost:8000")
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

# ML — enabled by default (OCI VM has enough RAM), set ML_ENABLED=false on low-memory hosts
ML_ENABLED = os.environ.get("ML_ENABLED", "true").lower() == "true"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "app",
]

AUTH_USER_MODEL = "app.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",          # Render static files
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "legal_ai_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
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

WSGI_APPLICATION = "legal_ai_project.wsgi.application"

# ── Database — dj-database-url handles both local and Render ─────────────────
# Render sets DATABASE_URL automatically. Locally we build it from .env vars.
_local_db = (
    f"postgresql://{os.environ.get('DB_USER','postgres')}:"
    f"{os.environ.get('DB_PASSWORD','')}@"
    f"{os.environ.get('DB_HOST','localhost')}:"
    f"{os.environ.get('DB_PORT','5432')}/"
    f"{os.environ.get('DB_NAME','nuc_legal_ai')}"
)
DATABASES = {
    "default": dj_database_url.config(
        default=os.environ.get("DATABASE_URL", _local_db),
        conn_max_age=600,
        ssl_require=os.environ.get("DATABASE_URL", "").startswith("postgres"),
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE     = "UTC"
USE_I18N      = True
USE_TZ        = True

# ── Static files ──────────────────────────────────────────────────────────────
STATIC_URL   = "static/"
STATIC_ROOT  = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# ── Media files ───────────────────────────────────────────────────────────────
MEDIA_URL  = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DATA_DIR = BASE_DIR / "data"

# ── AI / API keys ─────────────────────────────────────────────────────────────
COHERE_API_KEY        = os.environ.get("COHERE_API_KEY", "")
AI_CORRECTION_ENABLED = os.environ.get("AI_CORRECTION_ENABLED", "true").lower() == "true"

CHATBOT_ENABLED      = os.environ.get("CHATBOT_ENABLED", "true").lower() == "true"
OCI_USER_OCID        = os.environ.get("OCI_USER_OCID", "")
OCI_TENANCY_OCID     = os.environ.get("OCI_TENANCY_OCID", "")
OCI_FINGERPRINT      = os.environ.get("OCI_FINGERPRINT", "")
OCI_PRIVATE_KEY_PATH = os.environ.get("OCI_PRIVATE_KEY_PATH", "")
OCI_REGION           = os.environ.get("OCI_REGION", "us-chicago-1")
OCI_COMPARTMENT_ID   = os.environ.get("OCI_COMPARTMENT_ID", "")
OCI_CHAT_MODEL_ID    = os.environ.get("OCI_CHAT_MODEL_ID", "cohere.command-a-03-2025")

# ── Auth ──────────────────────────────────────────────────────────────────────
LOGIN_URL           = "/auth/login/"
LOGIN_REDIRECT_URL  = "/dashboard/"
LOGOUT_REDIRECT_URL = "/"

# ── Email ─────────────────────────────────────────────────────────────────────
EMAIL_BACKEND       = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST          = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT          = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USE_TLS       = os.environ.get("EMAIL_USE_TLS", "true").lower() == "true"
EMAIL_HOST_USER     = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL  = os.environ.get("DEFAULT_FROM_EMAIL", "NUC Legal AI <noreply@nuc-legal.ai>")
SITE_URL            = os.environ.get("SITE_URL", "http://localhost:8000")

# ── Sessions ──────────────────────────────────────────────────────────────────
SESSION_ENGINE     = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 3600
