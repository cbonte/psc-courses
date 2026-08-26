"""Réglages du projet psc-courses.

Toute valeur sensible ou dépendante de l'environnement se lit dans les variables
d'environnement, éventuellement alimentées par un fichier `.env` à la racine du
dépôt (voir `.env.example`). Aucun secret n'est écrit ici.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

# BASE_DIR      : le paquet Django, contient manage.py       -> <dépôt>/psc
# PROJECT_ROOT  : la racine du dépôt                          -> <dépôt>
BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent


def _load_dotenv(path):
    """Alimente os.environ depuis un fichier .env, sans écraser l'existant.

    Volontairement minimal : cela évite une dépendance supplémentaire pour un
    besoin qui tient en quinze lignes.
    """
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip("\"'")
        # Une valeur vide veut dire « non configuré », pas « chaîne vide » :
        # sans cela un gabarit de .env masquerait la vraie valeur.
        if value:
            os.environ.setdefault(key.strip(), value)


_load_dotenv(PROJECT_ROOT / ".env")


def env(name, default=None, required=False):
    value = os.environ.get(name, default)
    if required and not value:
        raise ImproperlyConfigured(
            f"La variable d'environnement {name} est obligatoire. "
            f"Copiez .env.example vers .env et renseignez-la."
        )
    return value


def env_bool(name, default=False):
    return str(os.environ.get(name, default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


DEBUG = env_bool("PSC_DEBUG", False)

# En développement, une clé fixe évite de déconnecter tout le monde à chaque
# redémarrage. Elle n'est jamais utilisée hors DEBUG.
_DEV_SECRET_KEY = "dev-only-not-a-secret-do-not-use-in-production"
SECRET_KEY = env("PSC_SECRET_KEY", _DEV_SECRET_KEY if DEBUG else None, required=not DEBUG)

ALLOWED_HOSTS = env_list("PSC_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]" if DEBUG else "")
CSRF_TRUSTED_ORIGINS = env_list("PSC_CSRF_TRUSTED_ORIGINS")


# Applications

# Ni admin, ni auth : l'application ne connaît pas de rôle. L'accès est un
# mot de passe unique, l'identité une déclaration, et tout se gère dans les
# écrans du club.
INSTALLED_APPS = [
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "events",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Porte d'entrée du site : mot de passe unique partagé.
    "core.middleware.SharedAccessMiddleware",
    # Résout le membre déclaré en session et l'expose sur la requête.
    "core.middleware.CurrentMemberMiddleware",
]

ROOT_URLCONF = "psc.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.site",
            ],
        },
    },
]

WSGI_APPLICATION = "psc.wsgi.application"
ASGI_APPLICATION = "psc.asgi.application"


# Base de données
#
# SQLite : le volume est de quelques dizaines de courses par an et la sauvegarde
# se réduit à une copie de fichier.

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": env("PSC_DB_PATH", str(PROJECT_ROOT / "data" / "psc.sqlite3")),
        "OPTIONS": {
            "transaction_mode": "IMMEDIATE",
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
        },
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Cache
#
# En base, et non en mémoire du processus. Le compteur de tentatives de la page
# d'accès est la seule chose qui y vit aujourd'hui : en mémoire, il repartait de
# zéro à chaque processus, donc à chaque instance sur un hébergement sans
# serveur, et le plafond ne se déclenchait jamais.

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "psc_cache",
    }
}


# Accès partagé
#
# Le site entier est protégé par un mot de passe unique, stocké haché. Générer
# la valeur avec : python psc/manage.py hash_access_password

PSC_ACCESS_PASSWORD_HASH = env("PSC_ACCESS_PASSWORD_HASH", "")
PSC_ACCESS_MAX_ATTEMPTS = int(env("PSC_ACCESS_MAX_ATTEMPTS", "10"))
PSC_ACCESS_LOCKOUT_SECONDS = int(env("PSC_ACCESS_LOCKOUT_SECONDS", "900"))

# Session longue : on ne redemande pas le mot de passe du club à chaque visite.
SESSION_COOKIE_AGE = 60 * 60 * 24 * 365
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_SAMESITE = "Lax"


# Internationalisation

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Europe/Paris"
USE_I18N = True
USE_TZ = True


# Fichiers statiques

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = PROJECT_ROOT / "staticfiles"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"
        )
    },
}


# Sécurité en production

if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("PSC_SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(env("PSC_HSTS_SECONDS", str(60 * 60 * 24 * 365)))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"
    if env_bool("PSC_BEHIND_PROXY", False):
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("PSC_LOG_LEVEL", "INFO")},
}
