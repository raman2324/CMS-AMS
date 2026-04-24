from pathlib import Path
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config("SECRET_KEY", default="django-insecure-dev-key-change-in-production")
DEBUG = config("DEBUG", default=True, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1,0.0.0.0", cast=Csv())

ANTHROPIC_API_KEY = config("ANTHROPIC_API_KEY", default="")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.sites",           # required by allauth
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    # Third-party: host
    "axes",
    # Third-party: AMS
    "allauth",
    "allauth.account",
    "crispy_forms",
    "crispy_bootstrap5",
    "django_htmx",
    # Host apps
    "accounts",
    "documents",
    "uploads",
    # AMS apps
    "ams.approvals",
    "ams.subscriptions",
    "ams.expenses",
    "ams.audit",
    "ams.notifications",
    "ams.management",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "accounts.middleware.RoleBasedAccessMiddleware",
    "axes.middleware.AxesMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
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

# ---------------------------------------------------------------------------
# Database — SQLite by default.
# Switch to PostgreSQL by setting DB_ENGINE + DB_NAME + DB_USER + DB_PASSWORD
# + DB_HOST + DB_PORT (see .env.example). Nothing else in the app needs to
# change — Django's ORM abstracts the rest.
# ---------------------------------------------------------------------------
_db_engine = config("DB_ENGINE", default="django.db.backends.sqlite3")
_db_name = config("DB_NAME", default=str(BASE_DIR / "db.sqlite3"))

DATABASES = {
    "default": {
        "ENGINE": _db_engine,
        "NAME": _db_name,
        "USER": config("DB_USER", default=""),
        "PASSWORD": config("DB_PASSWORD", default=""),
        "HOST": config("DB_HOST", default=""),
        "PORT": config("DB_PORT", default=""),
    }
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-in"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# ---------------------------------------------------------------------------
# Media / File Storage
# Local filesystem in DEBUG mode; swap to S3 by setting DEBUG=False and the
# AWS_* variables below — zero application code changes required.
# ---------------------------------------------------------------------------
if DEBUG:
    DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"
    MEDIA_ROOT = BASE_DIR / "local_pdfs"
    MEDIA_URL = "/media/"
else:
    DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
    AWS_STORAGE_BUCKET_NAME = config("AWS_STORAGE_BUCKET_NAME", default="")
    AWS_S3_REGION_NAME = config("AWS_S3_REGION_NAME", default="ap-south-1")
    AWS_ACCESS_KEY_ID = config("AWS_ACCESS_KEY_ID", default="")
    AWS_SECRET_ACCESS_KEY = config("AWS_SECRET_ACCESS_KEY", default="")
    # Remove AWS_S3_ENDPOINT_URL when switching from MinIO to real AWS S3
    _endpoint = config("AWS_S3_ENDPOINT_URL", default="")
    if _endpoint:
        AWS_S3_ENDPOINT_URL = _endpoint
    AWS_DEFAULT_ACL = "private"
    AWS_S3_FILE_OVERWRITE = False

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/documents/"
LOGOUT_REDIRECT_URL = "/login/"

# ---------------------------------------------------------------------------
# django-allauth — AMS uses email-based auth; login UI stays at /login/
# ---------------------------------------------------------------------------
SITE_ID = 1
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_LOGIN_URL = "/login/"          # allauth redirects to host login page

# ---------------------------------------------------------------------------
# crispy-forms (AMS templates use Bootstrap 5)
# ---------------------------------------------------------------------------
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

# ---------------------------------------------------------------------------
# Email (required by allauth; console backend in dev)
# ---------------------------------------------------------------------------
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="noreply@example.com")
EMAIL_BACKEND = config("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")

# ---------------------------------------------------------------------------
# CSRF trusted origins (needed for AMS production deployments)
# ---------------------------------------------------------------------------
_csrf_origins = config("CSRF_TRUSTED_ORIGINS", default="")
if _csrf_origins:
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_origins.split(",")]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Session security
# Session expires on browser close and after 8 hours max.
# Cookies are HTTPS-only and inaccessible to JavaScript.
# ---------------------------------------------------------------------------
SESSION_COOKIE_AGE = 8 * 60 * 60          # 8 hours — auto-logout overnight
SESSION_EXPIRE_AT_BROWSER_CLOSE = True     # logout when browser is closed
SESSION_COOKIE_HTTPONLY = True             # block JS access to session cookie
SESSION_COOKIE_SAMESITE = "Lax"           # CSRF defence

# In production (DEBUG=False) enforce HTTPS for the session cookie
if not DEBUG:
    SESSION_COOKIE_SECURE = True

# ---------------------------------------------------------------------------
# HTTPS / security headers (production only)
# ---------------------------------------------------------------------------
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000          # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True

X_FRAME_OPTIONS = "DENY"

# ---------------------------------------------------------------------------
# django-axes: login attempt throttling
# Lock accounts after 5 failed attempts within 10 minutes.
# Finance Head or Admin can unlock via Django admin.
# ---------------------------------------------------------------------------
AXES_FAILURE_LIMIT = 5          # lock after 5 wrong passwords
AXES_COOLOFF_TIME = 0.5         # 30-minute lockout (hours as float)
AXES_LOCKOUT_PARAMETERS = ["username"]   # lock by username (not IP, to avoid shared-IP false positives)
AXES_RESET_ON_SUCCESS = True    # reset failure count on successful login
AXES_VERBOSE = False

# ---------------------------------------------------------------------------
# PDF encryption key (optional — leave blank in dev, required in production)
# Generate with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# ---------------------------------------------------------------------------
# DOCUMENT_ENCRYPTION_KEY is read directly from env by storage_service.py
