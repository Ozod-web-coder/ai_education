from datetime import timedelta
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(DEBUG=(bool, False))
environ.Env.read_env(BASE_DIR / ".env")

# Vercel сам задаёт VERCEL=1 в окружении сборки и функций.
VERCEL = env.bool("VERCEL", default=False)

try:
    SECRET_KEY = env("SECRET_KEY")
except ImproperlyConfigured:
    raise ImproperlyConfigured(
        "Не задана переменная SECRET_KEY. Локально добавьте её в файл .env, "
        "на Vercel: Project → Settings → Environment Variables (для всех окружений, она нужна и при сборке). "
        "Ключ: python -c \"from django.core.management.utils import get_random_secret_key as g; print(g())\""
    ) from None
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
# Для своего домена с HTTPS (с https://), например https://api.example.com.
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

if VERCEL:
    ALLOWED_HOSTS.append(".vercel.app")
    # Vercel терминирует HTTPS сам; без этого Django считает запрос http и вход в админку
    # падает с «CSRF verification failed».
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "drf_spectacular",
    "apps.core",
    "apps.catalog",
    "apps.leads",
    "apps.booking",
    "apps.assessment",
    "apps.assistant",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

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

WSGI_APPLICATION = "config.wsgi.application"

if VERCEL and not env("DATABASE_URL", default=""):
    # Файловая система функций Vercel временная: SQLite там теряет данные.
    raise ImproperlyConfigured(
        "На Vercel нужна внешняя база. Задайте DATABASE_URL (Supabase: Connect → Session pooler), см. README."
    )

DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
}

AUTH_USER_MODEL = "core.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ru"
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "AI Education API",
    "VERSION": "0.1.0",
}

# Сколько секунд initData из Telegram Mini App считается свежим.
TELEGRAM_INIT_DATA_MAX_AGE = env.int("TELEGRAM_INIT_DATA_MAX_AGE", default=86400)
# Сколько минут держится бронь места до подтверждения.
BOOKING_HOLD_MINUTES = env.int("BOOKING_HOLD_MINUTES", default=15)
# HTTPS-адрес фронта Mini App. Пока пусто — бот не показывает кнопку приложения.
MINI_APP_URL = env("MINI_APP_URL", default="")

# Адреса, с которых Mini App ходит в API (через запятую), например https://app.example.com.
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])

# ИИ-консультант: любой OpenAI-совместимый API (см. apps/assistant/llm.py).
LLM_BASE_URL = env("LLM_BASE_URL", default="")
LLM_API_KEY = env("LLM_API_KEY", default="")
LLM_MODEL = env("LLM_MODEL", default="")
# Резервные модели через запятую: используются, когда основная перегружена или исчерпала лимит.
LLM_FALLBACK_MODELS = env.list("LLM_FALLBACK_MODELS", default=[])
# Отдельная (более точная) модель для оценки письма. Пусто — та же, что для диалога.
LLM_WRITING_MODEL = env("LLM_WRITING_MODEL", default="")
LLM_TIMEOUT = env.float("LLM_TIMEOUT", default=30.0)
LLM_TEMPERATURE = env.float("LLM_TEMPERATURE", default=0.3)
