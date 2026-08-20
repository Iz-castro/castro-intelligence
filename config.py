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


DATA_BACKEND = "firestore"
IS_FIRESTORE_BACKEND = True

# O CRM React depende de Firebase Auth e o runtime do backend nao expõe
# mais caminhos legados de autenticacao.
AUTH_MODE = "firebase"

FIRESTORE_PROJECT_ID = os.getenv("FIRESTORE_PROJECT_ID", "").strip()
FIRESTORE_COLLECTION_PREFIX = os.getenv("FIRESTORE_COLLECTION_PREFIX", "castro_crm").strip().strip("_")
FIRESTORE_MEDIA_COMPRESS_THRESHOLD_KB = _as_int(os.getenv("FIRESTORE_MEDIA_COMPRESS_THRESHOLD_KB"), 256)
FIRESTORE_MEDIA_MAX_MB = _as_int(os.getenv("FIRESTORE_MEDIA_MAX_MB"), 8)
FIRESTORE_MEDIA_CHUNK_KB = _as_int(os.getenv("FIRESTORE_MEDIA_CHUNK_KB"), 768)
ALLOWED_FIREBASE_EMAIL_DOMAIN = os.getenv("ALLOWED_FIREBASE_EMAIL_DOMAIN", "").strip().lower()
ALLOWED_FIREBASE_EMAILS = [item.lower() for item in _split_csv(os.getenv("ALLOWED_FIREBASE_EMAILS", ""))]
AUTO_PROVISION_FIREBASE_USERS = _as_bool(os.getenv("AUTO_PROVISION_FIREBASE_USERS"), default=True)
FIREBASE_STORAGE_BUCKET = os.getenv("FIREBASE_STORAGE_BUCKET", "").strip()
FIREBASE_WEB_API_KEY = os.getenv("FIREBASE_WEB_API_KEY", "").strip()
FIREBASE_WEB_AUTH_DOMAIN = os.getenv(
    "FIREBASE_WEB_AUTH_DOMAIN",
    f"{FIRESTORE_PROJECT_ID}.firebaseapp.com" if FIRESTORE_PROJECT_ID else "",
).strip()
FIREBASE_WEB_APP_ID = os.getenv("FIREBASE_WEB_APP_ID", "").strip()
FIREBASE_WEB_MESSAGING_SENDER_ID = os.getenv("FIREBASE_WEB_MESSAGING_SENDER_ID", "").strip()
FIREBASE_WEB_MEASUREMENT_ID = os.getenv("FIREBASE_WEB_MEASUREMENT_ID", "").strip()

CHAT_DELIVERY_MODE = os.getenv("CHAT_DELIVERY_MODE", "snapshot").strip().lower()
POLLING_INTERVAL_MS = _as_int(os.getenv("POLLING_INTERVAL_MS"), 15000)



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

GRAPH_API_VERSION = "v23.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# -- Embedded Signup (Coexistence) --
META_APP_ID = os.getenv("META_APP_ID", "").strip()
META_APP_SECRET = os.getenv("META_APP_SECRET", "").strip()
EMBEDDED_SIGNUP_CONFIG_ID = os.getenv("EMBEDDED_SIGNUP_CONFIG_ID", "").strip()
# Config de Embedded Signup STANDARD (Cloud API). Config separada na Meta —
# a de coexistence usa featureType=whatsapp_business_app_onboarding; a standard
# nao. Sem isso, o botao "Conectar numero (Cloud API)" retorna 503.
EMBEDDED_SIGNUP_CONFIG_ID_STANDARD = os.getenv("EMBEDDED_SIGNUP_CONFIG_ID_STANDARD", "").strip()
# System User token (long-lived) do portfolio Castro Operacoes. Acessa TODAS as
# WABAs onboardadas no app. Usado no Embedded Signup v4 (o token do popup volta
# so com public_profile e NAO consegue ler/gerenciar a WABA) e como credencial
# duravel dos canais coex — em vez do token por-signup que se perdia em wipe.
WHATSAPP_SYSTEM_USER_TOKEN = os.getenv("WHATSAPP_SYSTEM_USER_TOKEN", "").strip()

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

# -- Transcricao de audio (Faster Whisper) --
def _bool_env(key, default="false"):
    return os.getenv(key, default).strip().lower() in ("1", "true", "yes")

FEATURE_MESSAGE_STATUS = _bool_env("FEATURE_MESSAGE_STATUS", "true")
FEATURE_AUDIO_TRANSCRIPTION = _bool_env("FEATURE_AUDIO_TRANSCRIPTION", "false")
# Contador de "assumidas sem resposta" (bloqueia assume com 2+ pendentes).
# Desligado a pedido do cliente; religar via env sem mudar codigo.
FEATURE_ASSUME_COUNTER = _bool_env("FEATURE_ASSUME_COUNTER", "false")
STT_LANGUAGE_CODE = os.getenv("STT_LANGUAGE_CODE", "pt-BR").strip()
STT_TIMEOUT_SECONDS = float(os.getenv("STT_TIMEOUT_SECONDS", "30.0"))
STT_FALLBACK_TEXT = os.getenv("STT_FALLBACK_TEXT", "").strip()

# -- Motor Dialogflow CX (tenants com settings.ai.bot_engine=dialogflow_cx) --
# Teto (s) que o bot espera UMA resposta do DetectIntent antes de desistir do
# turno (1o timeout -> "instabilidade momentanea"; 2o consecutivo -> handoff).
# Subiu de 15s pra 60s em 2026-08-18 a pedido do PO: o agente generativo da
# Varizemed leva 10-30s com frequencia (semana 11-18/08: ~7% dos turnos
# passaram de 15s e 7 leads receberam o fallback sem o CX estar fora).
# Timeout de LEITURA nao reenvia a mensagem (bot_engine_dialogflow) e os
# reenvios por frase de erro (bot_service) so usam o que SOBROU deste
# orcamento: e o teto por TURNO, nao por chamada. Como o webhook so responde
# a Meta depois do turno, a Meta REENTREGA o payload a cada ~23s sem ACK — o
# guard was_dup do webhook absorve as reentregas (nao suba isto sem manter
# aquele guard). Parse defensivo: env invalida NAO pode derrubar o startup de
# todos os tenants — cai no default e avisa no log.
def _float_env(key, default):
    raw = os.getenv(key)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = float(str(raw).strip())
    except ValueError:
        value = float("nan")
    if not (value > 0):  # NaN, zero e negativo caem aqui
        import logging
        logging.getLogger("castro_crm.config").warning(
            "%s=%r invalido — usando default %s", key, raw, default,
        )
        return default
    return value


CX_DETECT_TIMEOUT_SECONDS = _float_env("CX_DETECT_TIMEOUT_SECONDS", 60.0)

# Read-timeout da chamada PRINCIPAL do turno reenvia a mensagem 1x antes do
# fallback "instabilidade momentanea" (pedido do PO 2026-08-20: lead real
# aceitou a LGPD, o agente levou >109s e morreu em DEADLINE_EXCEEDED — o
# proprio Dialogflow loga "Resend the request with a higher deadline").
# Trade-off aceito pelo PO: pior caso o lead espera ~2x o teto (120s) e a
# Meta reentrega o webhook mais vezes (was_dup absorve). O reenvio pode
# duplicar o turno na sessao do agente se a 1a chamada tiver completado la
# depois do nosso timeout — beneficio (lead atendido) > risco. So vale pra
# chamada com orcamento inteiro; reenvios por frase de erro (que ja usam
# sobra de orcamento) NAO fazem read-retry. Kill-switch sem deploy: false.
CX_READ_TIMEOUT_RETRY = _bool_env("CX_READ_TIMEOUT_RETRY", "true")

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

# -- Takeover temporario (coexistence) --
# Horas de inatividade TOTAL (sem inbound nem outbound) antes de o sistema
# devolver automaticamente uma sessao de takeover 'active' ao dono do lead.
TAKEOVER_TIMEOUT_HOURS = int(os.environ.get("TAKEOVER_TIMEOUT_HOURS", "3"))

# -- Ciclo de vida do Atendimento (Fase 4) --
# Horas sem mensagem antes de FECHAR automaticamente um atendimento ATRIBUIDO
# por inatividade (attendance_status -> fechado_inatividade). Reabre sozinho na
# proxima mensagem.
ATTENDANCE_AUTOCLOSE_HOURS = int(os.environ.get("ATTENDANCE_AUTOCLOSE_HOURS", "24"))

# Modo Recepcao (ADR 0010): dias que uma thread da pool pode esperar o PRIMEIRO
# atendimento humano depois do handoff do bot. Enquanto espera, o auto-close
# NAO fecha — fechar devolveria o lead ao agente de IA (release_lead_to_bot),
# que zera bot_completed e some com a thread da aba Recepcao (lead de fim de
# semana ficava invisivel na segunda). Passado o teto, o lead e dado como morto
# e volta pro bot, senao ficaria preso em bot_completed=True pra sempre.
# O default 7 esta espelhado em close_stale_attendances (fallback de caller
# que nao passa o parametro, ex.: simuladores).
RECEPTION_UNATTENDED_RELEASE_DAYS = int(os.environ.get("RECEPTION_UNATTENDED_RELEASE_DAYS", "7"))

# -- Bootstrap inicial --
BOOTSTRAP_ADMIN_EMAIL = os.getenv("BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
BOOTSTRAP_ADMIN_DISPLAY_NAME = os.getenv("BOOTSTRAP_ADMIN_DISPLAY_NAME", "Administrador")
BOOTSTRAP_ADMIN_DEPARTMENT = os.getenv("BOOTSTRAP_ADMIN_DEPARTMENT", "Geral")

# -- Logging --
DEFAULT_LOG_FILE = Path("/tmp/logs/castro_crm.log") if IS_CLOUD_RUN else BASE_DIR / "logs" / "castro_crm.log"
LOG_FILE = os.getenv("LOG_FILE", str(DEFAULT_LOG_FILE))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_TO_FILE = _as_bool(os.getenv("LOG_TO_FILE"), default=not IS_CLOUD_RUN)

# -- Google Chat Integration --
FEATURE_GOOGLE_CHAT = _bool_env("FEATURE_GOOGLE_CHAT", "false")
GOOGLE_CHAT_PROJECT_NUMBER = os.getenv("GOOGLE_CHAT_PROJECT_NUMBER", "").strip()
GOOGLE_CHAT_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_CHAT_SERVICE_ACCOUNT_FILE", "").strip()

# -- CORS --
DEFAULT_CORS_ORIGINS = "http://localhost:8080,http://127.0.0.1:8080"
CORS_ORIGINS = _split_csv(os.getenv("CORS_ORIGINS", DEFAULT_CORS_ORIGINS))
