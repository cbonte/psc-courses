"""Réglages du projet psc-courses.

Toute valeur sensible ou dépendante de l'environnement se lit dans les variables
d'environnement, éventuellement alimentées par un fichier `.env` à la racine du
dépôt (voir `.env.example`). Aucun secret n'est écrit ici.
"""

import os
import urllib.parse
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


# Vercel expose VERCEL=1 sur ses instances, en construction comme à l'exécution.
ON_VERCEL = bool(os.environ.get("VERCEL"))

DEBUG = env_bool("PSC_DEBUG", False)

# En développement, une clé fixe évite de déconnecter tout le monde à chaque
# redémarrage. Elle n'est jamais utilisée hors DEBUG.
_DEV_SECRET_KEY = "dev-only-not-a-secret-do-not-use-in-production"
SECRET_KEY = env("PSC_SECRET_KEY", _DEV_SECRET_KEY if DEBUG else None, required=not DEBUG)

ALLOWED_HOSTS = env_list("PSC_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]" if DEBUG else "")
CSRF_TRUSTED_ORIGINS = env_list("PSC_CSRF_TRUSTED_ORIGINS")

# Les adresses fournies par la plateforme, ajoutées d'office. Celle d'un
# déploiement de prévisualisation est tirée au sort à chaque fois : sans cela,
# elle serait rejetée avant même d'atteindre une vue.
for _variable in ("VERCEL_PROJECT_PRODUCTION_URL", "VERCEL_URL", "VERCEL_BRANCH_URL"):
    _host = os.environ.get(_variable, "").strip()
    if _host and _host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_host)
        CSRF_TRUSTED_ORIGINS.append(f"https://{_host}")


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

# ASGI_APPLICATION n'est lu que par Channels, absent du projet, et sa présence
# ferait choisir l'entrée ASGI à Vercel. Toutes les vues sont synchrones : on
# reste en WSGI, sans passer par un pont de threads.
WSGI_APPLICATION = "psc.wsgi.application"


# Base de données
#
# SQLite : le volume est de quelques dizaines de courses par an et la sauvegarde
# se réduit à une copie de fichier.

def _database_from_url(url):
    """Traduit une DATABASE_URL PostgreSQL en réglage Django.

    Analysée à la main plutôt qu'avec dj-database-url : une douzaine de lignes
    contre une dépendance de plus, pour un besoin qui ne bougera pas.
    """
    parts = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parts.query)
    options = {}
    # Neon n'accepte que le TLS, et refuse une connexion en clair.
    options["sslmode"] = query.get("sslmode", ["require"])[0]
    if "channel_binding" in query:
        options["channel_binding"] = query["channel_binding"][0]
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": urllib.parse.unquote(parts.path.lstrip("/")),
        "USER": urllib.parse.unquote(parts.username or ""),
        "PASSWORD": urllib.parse.unquote(parts.password or ""),
        "HOST": parts.hostname or "",
        "PORT": str(parts.port or ""),
        "OPTIONS": options,
        # Une instance sans serveur sert plusieurs requêtes : garder la
        # connexion évite de la rouvrir à chaque fois, sans la garder trop
        # longtemps pour ne pas épuiser le quota de Neon.
        "CONN_MAX_AGE": int(env("PSC_CONN_MAX_AGE", "60")),
        "CONN_HEALTH_CHECKS": True,
    }


_DATABASE_URL = env("DATABASE_URL", "")

DATABASES = {
    "default": _database_from_url(_DATABASE_URL)
    if _DATABASE_URL
    else {
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
    # Vercel termine le TLS : sans cet en-tête, Django croit la requête en
    # clair et la redirection ci-dessus boucle indéfiniment.
    if env_bool("PSC_BEHIND_PROXY", ON_VERCEL):
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("PSC_LOG_LEVEL", "INFO")},
}
