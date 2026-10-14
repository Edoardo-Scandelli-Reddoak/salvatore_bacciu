"""
Impostazioni del backend prenotazioni — Cala Brandinchi Escursioni.

Tutto ciò che cambia tra locale e Railway arriva da variabili d'ambiente
(vedi README.md). In locale basta DJANGO_DEBUG=1: database SQLite e chiave di sviluppo.
"""

import os
from pathlib import Path

import dj_database_url
from django.templatetags.static import static
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(nome, default=False):
    return os.environ.get(nome, str(default)).lower() in ("1", "true", "yes", "on")


def env_list(nome):
    return [v.strip() for v in os.environ.get(nome, "").split(",") if v.strip()]


DEBUG = env_bool("DJANGO_DEBUG")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("DJANGO_SECRET_KEY è obbligatoria quando DJANGO_DEBUG non è attivo")
    SECRET_KEY = "solo-sviluppo-locale-non-usare-in-produzione"

# Railway espone il dominio pubblico del servizio in RAILWAY_PUBLIC_DOMAIN
RAILWAY_DOMAIN = os.environ.get("RAILWAY_PUBLIC_DOMAIN")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")
if RAILWAY_DOMAIN:
    ALLOWED_HOSTS.append(RAILWAY_DOMAIN)
    CSRF_TRUSTED_ORIGINS.append(f"https://{RAILWAY_DOMAIN}")
if os.environ.get("RAILWAY_ENVIRONMENT"):
    # L'healthcheck di Railway chiama con questo host
    ALLOWED_HOSTS.append("healthcheck.railway.app")
if DEBUG:
    ALLOWED_HOSTS += ["localhost", "127.0.0.1"]


INSTALLED_APPS = [
    "unfold",
    "unfold.contrib.filters",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "prenotazioni",
    "sito",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
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

WSGI_APPLICATION = "config.wsgi.application"

# Railway inietta DATABASE_URL quando si collega un Postgres al servizio
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        conn_health_checks=True,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "it"
TIME_ZONE = "Europe/Rome"
USE_I18N = True
# Unfold non include l'italiano: le sue stringhe sono tradotte in locale/it
LOCALE_PATHS = [BASE_DIR / "locale"]
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        if not DEBUG
        else "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Dopo il login si entra nel pannello (senza, Django manda a /accounts/profile/)
LOGIN_URL = "admin:login"
LOGIN_REDIRECT_URL = "admin:index"

# Dietro il proxy HTTPS di Railway
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SSL_REDIRECT", True)
    # /salute/ resta raggiungibile in HTTP per l'healthcheck interno di Railway
    SECURE_REDIRECT_EXEMPT = [r"^salute/$"]
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_CONTENT_TYPE_NOSNIFF = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO")},
}


# --------------------------------------------------------------------------
# Regole di prenotazione
# --------------------------------------------------------------------------

# Stagione in cui il sito accetta prenotazioni: (mese, giorno) di inizio e fine.
# Dal pannello si possono comunque inserire prenotazioni fuori stagione.
STAGIONE_INIZIO = (5, 1)
STAGIONE_FINE = (9, 30)


# --------------------------------------------------------------------------
# Pagamenti (Stripe)
# --------------------------------------------------------------------------

# Chiavi dalla dashboard Stripe (Sviluppatori → Chiavi API). In test iniziano con sk_test_/pk_test_.
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
# Segreto dell'endpoint webhook (whsec_…): Workbench → Webhooks, oppure `stripe listen` in locale
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

# Minuti in cui i posti restano bloccati mentre il cliente paga. 30 è il minimo che Stripe
# accetta per la scadenza di una sessione di Checkout.
PAGAMENTO_BLOCCO_MINUTI = 30

# Senza chiavi Stripe, in sviluppo il pagamento è simulato (mai in produzione)
PAGAMENTI_SIMULATI = DEBUG and not STRIPE_SECRET_KEY
if not DEBUG and not STRIPE_SECRET_KEY:
    import warnings

    warnings.warn("STRIPE_SECRET_KEY non impostata: dal sito non si potrà pagare l'acconto.", stacklevel=1)


# --------------------------------------------------------------------------
# Unfold
# --------------------------------------------------------------------------


def pagina_admin(*nomi):
    """Voce del menu attiva solo su queste pagine. Senza, Unfold accende ogni voce il cui
    link è un prefisso dell'indirizzo (il calendario sta sotto /prenotazione/ e accendeva anche l'elenco)."""

    def attiva(request):
        match = getattr(request, "resolver_match", None)
        return bool(match) and match.url_name in nomi

    return attiva


UNFOLD = {
    "SITE_TITLE": "Cala Brandinchi Escursioni",
    "SITE_HEADER": "Cala Brandinchi",
    "SITE_SUBHEADER": "Prenotazioni escursioni",
    "SITE_URL": "/",  # «Vedi il sito» porta alla homepage
    "SITE_LOGO": {
        "light": lambda request: static("admin_extra/logo-blu.png"),
        "dark": lambda request: static("admin_extra/logo-bianco.png"),
    },
    "SITE_FAVICONS": [
        {"rel": "icon", "type": "image/svg+xml", "href": lambda request: static("admin_extra/favicon.svg")},
    ],
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "DASHBOARD_CALLBACK": "prenotazioni.admin_views.dashboard_callback",
    "STYLES": [lambda request: static("admin_extra/pannello.css")],
    # Blu del sito (#17608F al 600)
    "COLORS": {
        "primary": {
            "50": "#eef6fb",
            "100": "#d6e9f4",
            "200": "#b0d4ea",
            "300": "#7db7da",
            "400": "#4b95c4",
            "500": "#2a78aa",
            "600": "#17608f",
            "700": "#144f76",
            "800": "#134262",
            "900": "#0b2b45",
            "950": "#071c2e",
        },
    },
    "SIDEBAR": {
        "show_search": False,
        "show_all_applications": False,
        "navigation": [
            {
                "title": _("Prenotazioni"),
                "items": [
                    {
                        "title": _("Oggi e prossimi giorni"),
                        "icon": "dashboard",
                        "link": reverse_lazy("admin:index"),
                        "active": pagina_admin("index"),
                    },
                    {
                        "title": _("Calendario disponibilità"),
                        "icon": "calendar_month",
                        "link": reverse_lazy("admin:prenotazioni_disponibilita"),
                        "active": pagina_admin("prenotazioni_disponibilita", "prenotazioni_uscita"),
                    },
                    {
                        "title": _("Tutte le prenotazioni"),
                        "icon": "list_alt",
                        "link": reverse_lazy("admin:prenotazioni_prenotazione_changelist"),
                        "active": pagina_admin(
                            "prenotazioni_prenotazione_changelist",
                            "prenotazioni_prenotazione_change",
                            "prenotazioni_prenotazione_delete",
                            "prenotazioni_prenotazione_history",
                        ),
                    },
                    {
                        "title": _("Pagamenti"),
                        "icon": "payments",
                        "link": reverse_lazy("admin:prenotazioni_pagamento_changelist"),
                        "active": pagina_admin(
                            "prenotazioni_pagamento_changelist",
                            "prenotazioni_pagamento_change",
                            "prenotazioni_pagamento_delete",
                        ),
                    },
                    {
                        "title": _("Nuova prenotazione"),
                        "icon": "add_circle",
                        "link": reverse_lazy("admin:prenotazioni_prenotazione_add"),
                        "active": pagina_admin("prenotazioni_prenotazione_add"),
                    },
                ],
            },
            {
                "title": _("Configurazione"),
                "collapsible": True,
                "items": [
                    {
                        "title": _("Chiusure"),
                        "icon": "block",
                        "link": reverse_lazy("admin:prenotazioni_chiusura_changelist"),
                    },
                    {
                        "title": _("Gommoni"),
                        "icon": "sailing",
                        "link": reverse_lazy("admin:prenotazioni_gommone_changelist"),
                    },
                    {
                        "title": _("Uscite (mattino/pomeriggio)"),
                        "icon": "schedule",
                        "link": reverse_lazy("admin:prenotazioni_fascia_changelist"),
                    },
                    {
                        "title": _("Utenti"),
                        "icon": "person",
                        "link": reverse_lazy("admin:auth_user_changelist"),
                        "permission": lambda request: request.user.is_superuser,
                    },
                ],
            },
        ],
    },
}
