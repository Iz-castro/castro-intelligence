# -*- coding: utf-8 -*-

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - uvicorn[standard] instala python-dotenv
    load_dotenv = None

if load_dotenv:
    load_dotenv(BASE_DIR / ".env", override=False)

IS_CLOUD_RUN = bool(os.getenv("K_SERVICE"))


def _as_bool(value, default=False):
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _split_csv(value):
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _as_int(value, default):
    if value is None or str(value).strip() == "":
        return default
    return int(value)


SUPPORTED_DATA_BACKENDS = {"sql", "firestore"}
DATA_BACKEND = os.getenv("DATA_BACKEND", "sql").strip().lower()
if DATA_BACKEND not in SUPPORTED_DATA_BACKENDS:
    raise RuntimeError(f"DATA_BACKEND invalido: {DATA_BACKEND}")

IS_FIRESTORE_BACKEND = DATA_BACKEND == "firestore"

SUPPORTED_AUTH_MODES = {"legacy", "firebase"}
AUTH_MODE = os.getenv(
    "AUTH_MODE",
    "firebase" if IS_FIRESTORE_BACKEND else "legacy",
).strip().lower()
if AUTH_MODE not in SUPPORTED_AUTH_MODES:
    raise RuntimeError(f"AUTH_MODE invalido: {AUTH_MODE}")
USE_FIREBASE_AUTH = AUTH_MODE == "firebase"

FIRESTORE_PROJECT_ID = os.getenv("FIRESTORE_PROJECT_ID", "").strip()
FIRESTORE_COLLECTION_PREFIX = os.getenv("FIRESTORE_COLLECTION_PREFIX", "castro_crm").strip().strip("_")
FIRESTORE_MEDIA_COMPRESS_THRESHOLD_KB = _as_int(os.getenv("FIRESTORE_MEDIA_COMPRESS_THRESHOLD_KB"), 256)
FIRESTORE_MEDIA_MAX_MB = _as_int(os.getenv("FIRESTORE_MEDIA_MAX_MB"), 8)
FIRESTORE_MEDIA_CHUNK_KB = _as_int(os.getenv("FIRESTORE_MEDIA_CHUNK_KB"), 768)
ALLOWED_FIREBASE_EMAIL_DOMAIN = os.getenv("ALLOWED_FIREBASE_EMAIL_DOMAIN", "").strip().lower()
AUTO_PROVISION_FIREBASE_USERS = _as_bool(os.getenv("AUTO_PROVISION_FIREBASE_USERS"), default=True)
FIREBASE_STORAGE_BUCKET = os.getenv("FIREBASE_STORAGE_BUCKET", "").strip()

SUPPORTED_CHAT_DELIVERY_MODES = {"snapshot", "polling"}
CHAT_DELIVERY_MODE = os.getenv(
    "CHAT_DELIVERY_MODE",
    "snapshot" if IS_FIRESTORE_BACKEND else "polling",
).strip().lower()
if CHAT_DELIVERY_MODE not in SUPPORTED_CHAT_DELIVERY_MODES:
    raise RuntimeError(f"CHAT_DELIVERY_MODE invalido: {CHAT_DELIVERY_MODE}")
POLLING_INTERVAL_MS = _as_int(os.getenv("POLLING_INTERVAL_MS"), 5000)


def _default_database_path():
    raw_path = os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "castro_crm.db")).strip()
    path = Path(raw_path)
    if not path.is_absolute():
        path = (BASE_DIR / path).resolve()
    return path


def _get_database_url():
    value = os.getenv("DATABASE_URL", "").strip()
    if value:
        if value.startswith(("sqlite", "postgresql")):
            return value
        raise RuntimeError("DATABASE_URL deve apontar para SQLite ou PostgreSQL.")
    return f"sqlite:///{DATABASE_PATH.as_posix()}"


def _database_kind(database_url):
    if database_url.startswith("sqlite"):
        return "sqlite"
    if database_url.startswith("postgresql"):
        return "postgresql"
    return "unknown"


if DATA_BACKEND == "sql":
    DATABASE_PATH = _default_database_path()
    DATABASE_URL = _get_database_url()
    DATABASE_KIND = _database_kind(DATABASE_URL)
    IS_SQLITE = DATABASE_KIND == "sqlite"
    IS_POSTGRES = DATABASE_KIND == "postgresql"

    if DATABASE_KIND == "unknown":
        raise RuntimeError("DATABASE_URL deve apontar para SQLite ou PostgreSQL.")

    if IS_CLOUD_RUN and IS_SQLITE:
        raise RuntimeError("Cloud Run nao deve usar SQLite. Use PostgreSQL/Cloud SQL.")
else:
    DATABASE_PATH = None
    DATABASE_URL = ""
    DATABASE_KIND = "firestore"
    IS_SQLITE = False
    IS_POSTGRES = False


# -- Banco de dados --
# variaveis ja definidas acima: DATABASE_PATH, DATABASE_URL, DATABASE_KIND

# -- Seguranca --
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_MINUTES = int(os.getenv("JWT_EXPIRATION_MINUTES", "480"))

MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 300
MAX_MESSAGE_LENGTH = 4000

# -- Servidor --
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))

# -- WhatsApp Business API (Meta Cloud API) --
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_WABA_ID = os.getenv("WHATSAPP_WABA_ID", "")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")
REQUIRE_WEBHOOK_SIGNATURE = _as_bool(
    os.getenv("REQUIRE_WEBHOOK_SIGNATURE"),
    default=IS_CLOUD_RUN,
)

GRAPH_API_VERSION = "v22.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# -- Media --
DEFAULT_MEDIA_DIR = Path("/tmp/castro_crm_media") if IS_CLOUD_RUN else BASE_DIR / "media"
MEDIA_DIR = os.getenv("MEDIA_DIR", str(DEFAULT_MEDIA_DIR))
GCS_MEDIA_BUCKET = os.getenv("GCS_MEDIA_BUCKET", FIREBASE_STORAGE_BUCKET).strip()
GCS_MEDIA_PREFIX = os.getenv("GCS_MEDIA_PREFIX", "media").strip().strip("/")
MEDIA_STORAGE_BACKEND = os.getenv(
    "MEDIA_STORAGE_BACKEND",
    "gcs" if GCS_MEDIA_BUCKET else ("local" if not IS_FIRESTORE_BACKEND else "firestore"),
).strip().lower()
MAX_MEDIA_SIZE_MB = 16

# -- Avatar / Foto de perfil --
AVATAR_DIR = os.path.join(MEDIA_DIR, "avatars")
AVATAR_MAX_SIZE_KB = 512
AVATAR_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}

# -- Audio gravado --
AUDIO_MAX_DURATION_SEC = 120
AUDIO_ALLOWED_MIME = {"audio/ogg", "audio/webm", "audio/mp4", "audio/mpeg"}

# -- Qualificacao de contatos --
QUALIFICATION_OPTIONS = [
    "novo",
    "em_atendimento",
    "qualificado",
    "nao_qualificado",
    "convertido",
]

# -- Cargos / funcoes --
ROLE_OPTIONS = [
    "admin",
    "supervisor",
    "operador",
]

# -- Bootstrap inicial --
BOOTSTRAP_ADMIN_USERNAME = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "").strip().lower()
BOOTSTRAP_ADMIN_EMAIL = os.getenv("BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
BOOTSTRAP_ADMIN_PASSWORD = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
BOOTSTRAP_ADMIN_DISPLAY_NAME = os.getenv("BOOTSTRAP_ADMIN_DISPLAY_NAME", "Administrador")
BOOTSTRAP_ADMIN_DEPARTMENT = os.getenv("BOOTSTRAP_ADMIN_DEPARTMENT", "Geral")

# -- Logging --
DEFAULT_LOG_FILE = Path("/tmp/logs/castro_crm.log") if IS_CLOUD_RUN else BASE_DIR / "logs" / "castro_crm.log"
LOG_FILE = os.getenv("LOG_FILE", str(DEFAULT_LOG_FILE))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_TO_FILE = _as_bool(os.getenv("LOG_TO_FILE"), default=not IS_CLOUD_RUN)

# -- CORS --
DEFAULT_CORS_ORIGINS = "http://localhost:8080,http://127.0.0.1:8080"
CORS_ORIGINS = _split_csv(os.getenv("CORS_ORIGINS", DEFAULT_CORS_ORIGINS))
