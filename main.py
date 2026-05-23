# -*- coding: utf-8 -*-

import logging
import os
from datetime import datetime, timedelta, timezone
from time import monotonic as _monotonic

import httpx

# Caches in-memory por instancia Cloud Run. Reduzem hits Meta Graph API
# que estouram rate limit per-WABA (#80008) quando frontend faz polling
# agressivo de billing-status / templates. Cache miss em outra instancia
# Cloud Run resulta em apenas 1 hit extra na Meta — bem dentro do limite.
_templates_cache: "dict[int, tuple[float, dict]]" = {}
_billing_cache: "dict[int, tuple[float, dict]]" = {}
_TEMPLATES_TTL_S = 60.0
_BILLING_TTL_S_OK = 300.0   # billing OK: cache 5min
_BILLING_TTL_S_ERR = 30.0   # billing erro/rate-limited: cache 30s (evita re-bater)
from fastapi import (
    FastAPI, Request,
    HTTPException, Depends, Query, UploadFile, File, Form,
)
from fastapi.responses import JSONResponse, HTMLResponse, PlainTextResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

from bootstrap_data import ensure_default_departments
from config import (
    HOST, PORT, MAX_MESSAGE_LENGTH, BASE_DIR, LOG_FILE, LOG_LEVEL, LOG_TO_FILE,
    FEATURE_AUDIO_TRANSCRIPTION, FEATURE_MESSAGE_STATUS, FEATURE_GOOGLE_CHAT,
    WHATSAPP_VERIFY_TOKEN, WHATSAPP_TOKEN,
    WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_WABA_ID, GRAPH_API_BASE, GRAPH_API_VERSION,
    AVATAR_MAX_SIZE_KB, AVATAR_ALLOWED_MIME,
    QUALIFICATION_OPTIONS, ROLE_OPTIONS,
    BOOTSTRAP_ADMIN_EMAIL, BOOTSTRAP_ADMIN_DISPLAY_NAME, BOOTSTRAP_ADMIN_DEPARTMENT,
    CORS_ORIGINS, GCS_MEDIA_BUCKET, IS_CLOUD_RUN,
    MEDIA_STORAGE_BACKEND, REQUIRE_WEBHOOK_SIGNATURE, WHATSAPP_APP_SECRET,
    CHAT_DELIVERY_MODE, POLLING_INTERVAL_MS, AUTH_MODE,
    FIRESTORE_PROJECT_ID, FIREBASE_STORAGE_BUCKET,
    FIREBASE_WEB_API_KEY, FIREBASE_WEB_AUTH_DOMAIN, FIREBASE_WEB_APP_ID,
    FIREBASE_WEB_MESSAGING_SENDER_ID, FIREBASE_WEB_MEASUREMENT_ID,
    ALLOWED_FIREBASE_EMAIL_DOMAIN,
    STT_LANGUAGE_CODE, STT_TIMEOUT_SECONDS,
    META_APP_ID, META_APP_SECRET, EMBEDDED_SIGNUP_CONFIG_ID,
)
from database import (
    init_database, get_user_by_id, get_all_users,
    get_all_wa_contacts, get_wa_conversation,
    mark_wa_conversation_read, mark_wa_conversation_read_by_id,
    save_wa_message, get_wa_contact,
    log_audit, normalize_br_phone,
    get_all_departments, create_department,
    get_department_by_id, update_department, deactivate_department,
    assign_wa_contact, assign_wa_conversation, get_transfer_history,
    return_contact_to_bot, get_contacts_by_assigned_user,
    get_wa_contacts_scoped_for_user,
    update_user_avatar, get_user_avatar,
    update_user, deactivate_user, set_coex_authorization,
    upsert_firebase_user, get_user_by_email,
    update_wa_contact_qualification, archive_wa_contact, restore_wa_contact,
    update_contact_avatar, insert_transfer_system_message, set_attendance_protocol,
    get_wa_message_by_id, update_wa_message_transcription,
    create_manual_wa_contact, update_wa_contact_declared_name,
    mark_message_corrected,
    get_wa_conversation_by_id, upsert_wa_conversation,
    set_conversation_takeover_active, clear_conversation_takeover,
    get_system_settings, save_system_settings,
    get_user_settings, save_user_settings,
    get_all_gc_conversations, get_gc_messages, save_gc_message,
    mark_gc_conversation_read, upsert_gc_conversation,
    get_audit_metrics, get_all_ratings,
    get_monthly_usage, get_usage_history,
    get_assume_counter, decrement_assume_counter, increment_assume_counter,
    mark_contact_pending_response, clear_contact_pending_response,
    reset_assume_counter,
)
from channel_service import (
    get_all_active_channels, get_channels_for_user,
    create_channel, update_channel, deactivate_channel,
    get_channel_by_id_from_db,
    CHANNEL_TYPE_STANDARD, CHANNEL_TYPE_COEXISTENCE,
)
from auth import authenticate_firebase_token
from firestore_common import (
    collection_name, document as fs_document, utcnow as fs_utcnow,
    set_tenant_context, tenant_context, get_tenant_context,
)
from pii_redaction import redact_phone, redact_name
from tenant_service import (
    create_tenant, get_tenant, tenant_exists, lookup_phone_routing,
)
from webhook import process_webhook_payload, validate_signature
from webhook_google_chat import validate_google_chat_token, process_google_chat_event
from media import (
    ensure_media_dir, upload_media_to_whatsapp, send_media_message,
    save_upload_media, convert_audio_to_ogg_opus,
    save_avatar_media, delete_media, get_media_asset,
    _write_media_bytes,
)

# -- Logging --

log_handlers = [logging.StreamHandler()]
if LOG_TO_FILE and LOG_FILE:
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    log_handlers.insert(0, logging.FileHandler(LOG_FILE, encoding="utf-8"))

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=log_handlers,
)
logger = logging.getLogger("castro_crm.main")

# -- App --

FRONTEND_DIST_DIR = os.path.join(BASE_DIR, "frontend_dist")
FRONTEND_ASSETS_DIR = os.path.join(FRONTEND_DIST_DIR, "assets")
FRONTEND_INDEX_FILE = os.path.join(FRONTEND_DIST_DIR, "index.html")

app = FastAPI(
    title="Castro Intelligence CRM",
    version="0.4.0",
    docs_url=None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    # O Embedded Signup (FB.login) e o Firebase Auth abrem um popup e
    # precisam checar window.closed / window.opener pra concluir o fluxo.
    # A policy padrao do Chrome (same-origin) bloqueia essa chamada e gera
    # "Cross-Origin-Opener-Policy policy would block the window.closed call".
    # same-origin-allow-popups libera a comunicacao com o popup sem abrir mao
    # do isolamento entre origens distintas. NAO setamos COEP (require-corp)
    # de proposito: quebraria o carregamento de assets/sdk de terceiros.
    response = await call_next(request)
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin-allow-popups")
    return response


# Middleware HTTP que extrai tenant_id do JWT ANTES do endpoint e seta o
# contextvar no asyncio task correto. Necessario porque get_current_user
# eh sync (def) e roda em threadpool — set_tenant_context dentro dele nao
# persiste pro endpoint async no main thread.
@app.middleware("http")
async def tenant_context_middleware(request: Request, call_next):
    from firestore_common import set_tenant_context, reset_tenant_context
    from firebase_admin_client import verify_firebase_id_token

    auth_header = request.headers.get("authorization", "") or request.headers.get("Authorization", "")
    tid = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        try:
            decoded = verify_firebase_id_token(token)
            tid = decoded.get("tenant_id")
            # Cache decoded no request.state pro get_current_user reutilizar
            request.state.firebase_decoded = decoded
        except Exception:
            # Auth real acontece em get_current_user; aqui so detecta
            # tenant pra setar context cedo.
            pass
    # Fallback: usuarios pre-Fase 2 sem custom_claim ainda — assume tenant default.
    if not tid and auth_header:
        tid = "hubloc"

    if tid:
        ctx_token = set_tenant_context(tid)
        try:
            return await call_next(request)
        finally:
            reset_tenant_context(ctx_token)
    return await call_next(request)


if os.path.isdir(FRONTEND_ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=FRONTEND_ASSETS_DIR), name="frontend-assets")

class WaSendRequest(BaseModel):
    # Fase 2C: conversation_id e o canonico (identifica thread channel+wa_id).
    # contact_id continua aceito enquanto o frontend nao migrou todas as views
    # — backend resolve para (conversation, contact) via _resolve_send_target.
    conversation_id: str | None = None
    contact_id: int | None = None
    content: str
    reply_to_message_id: int | None = None
    reply_to_preview: str = ""
    reply_to_sender_name: str = ""

    @field_validator("content")
    @classmethod
    def validate_content(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Mensagem vazia")
        if len(v) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"Excede {MAX_MESSAGE_LENGTH} caracteres")
        return v

    @field_validator("reply_to_preview", "reply_to_sender_name")
    @classmethod
    def trim_reply_fields(cls, v):
        return v.strip()


class WaSendLocationRequest(BaseModel):
    conversation_id: str | None = None
    contact_id: int | None = None
    latitude: float
    longitude: float
    name: str = ""
    address: str = ""
    reply_to_message_id: int | None = None
    reply_to_preview: str = ""
    reply_to_sender_name: str = ""

    @field_validator("reply_to_preview", "reply_to_sender_name")
    @classmethod
    def trim_reply_fields(cls, v):
        return v.strip()


# -- Dependencias --

def get_current_user(request: Request):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token ausente")
    token = auth_header.split(" ", 1)[1]
    ip = request.client.host if request.client else "unknown"
    result = authenticate_firebase_token(token, ip)
    if not result["success"]:
        raise HTTPException(status_code=result.get("status_code", 401), detail=result["error"])
    return result["user"]


# -- Validacao de imagem --

AVATAR_MAGIC_BYTES = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG": "image/png",
    b"RIFF": "image/webp",
}


def _wa_target(wa_id):
    # Para respostas, use exatamente o identificador telefonico recebido/salvo no contato.
    # Inserir digitos extras aqui faz a Meta rejeitar o envio com HTTP 400.
    return "".join(ch for ch in str(wa_id or "").strip() if ch.isdigit())


def _fallback_reply_preview(message: dict) -> str:
    content = str(message.get("content") or "").strip()
    if content:
        return content

    transcription = str(message.get("transcription") or "").strip()
    if transcription:
        return transcription

    filename = str(message.get("filename") or "").strip()
    msg_type = str(message.get("msg_type") or "").strip().lower()
    labels = {
        "audio": "Audio",
        "document": "Documento",
        "gif": "Video",
        "image": "Imagem",
        "location": "Localizacao",
        "sticker": "Figurinha",
        "template": "Template",
        "video": "Video",
    }
    if filename and msg_type in labels:
        return f"{labels[msg_type]}: {filename}"
    return labels.get(msg_type, "Mensagem")


def _fallback_reply_sender(message: dict) -> str:
    direction = str(message.get("direction") or "").strip().lower()
    if direction == "inbound":
        return "Cliente"
    if direction == "system":
        return "Sistema"
    operator_id = message.get("operator_id")
    operator = get_user_by_id(operator_id) if operator_id else None
    return str((operator or {}).get("display_name") or "Equipe")


def _build_reply_fields(contact_id: int, reply_to_message_id: int | None, reply_to_preview: str = "", reply_to_sender_name: str = "") -> dict:
    if reply_to_message_id is None:
        return {}

    reply_message = get_wa_message_by_id(reply_to_message_id)
    if not reply_message or int(reply_message.get("contact_id") or 0) != int(contact_id):
        raise HTTPException(status_code=400, detail="Mensagem de resposta invalida para este contato")

    preview = (reply_to_preview or _fallback_reply_preview(reply_message)).strip()
    sender_name = (reply_to_sender_name or _fallback_reply_sender(reply_message)).strip()
    return {
        "reply_to_message_id": int(reply_message.get("id") or reply_to_message_id),
        "reply_to_preview": preview[:280],
        "reply_to_sender_name": sender_name[:80],
    }


def _build_reply_context(contact_id: int, reply_to_message_id: int | None) -> dict:
    if reply_to_message_id is None:
        return {}
    reply_message = get_wa_message_by_id(reply_to_message_id)
    if not reply_message or int(reply_message.get("contact_id") or 0) != int(contact_id):
        raise HTTPException(status_code=400, detail="Mensagem de resposta invalida para este contato")
    wa_message_id = str(reply_message.get("wa_message_id") or "").strip()
    if not wa_message_id:
        return {}
    return {"context": {"message_id": wa_message_id}}


def _validate_image_bytes(content):
    for magic, mime in AVATAR_MAGIC_BYTES.items():
        if content[:len(magic)] == magic:
            return mime
    return None


def _save_avatar(content, prefix, entity_id):
    real_mime = _validate_image_bytes(content)
    if not real_mime or real_mime not in AVATAR_ALLOWED_MIME:
        return None
    return save_avatar_media(content, prefix, entity_id, real_mime)


def _remove_old_avatar(old_path):
    delete_media(old_path)


def _frontend_build_available():
    return os.path.isfile(FRONTEND_INDEX_FILE)


def _serve_frontend_app():
    if not os.path.isfile(FRONTEND_INDEX_FILE):
        return HTMLResponse(
            content="<h1>Frontend React nao compilado. Execute: cd frontend && npm run build</h1>",
            status_code=503,
        )
    return FileResponse(FRONTEND_INDEX_FILE)


def bootstrap_admin_user():
    if not BOOTSTRAP_ADMIN_EMAIL:
        logger.info("Bootstrap admin Firebase nao configurado")
        return

    department_id = create_department(
        BOOTSTRAP_ADMIN_DEPARTMENT,
        "Setor criado automaticamente no primeiro deploy",
    )
    user = upsert_firebase_user(
        firebase_uid="",
        email=BOOTSTRAP_ADMIN_EMAIL,
        display_name=BOOTSTRAP_ADMIN_DISPLAY_NAME,
        role="admin",
        department_id=department_id,
    )
    if user:
        # Sincroniza custom_claim tenant_id no usuario Firebase para a
        # proxima sessao. O usuario precisa renovar o ID token (logout/login
        # ou getIdToken(true)) para o claim aparecer.
        firebase_uid = user.get("firebase_uid", "")
        tenant_id = get_tenant_context() or "hubloc"
        if firebase_uid:
            try:
                from firebase_admin_client import set_tenant_claims
                set_tenant_claims(firebase_uid, tenant_id, role="admin")
            except Exception as exc:
                logger.warning("Falha ao setar custom_claim tenant_id no admin: %s", exc)
        logger.info(
            "Bootstrap admin Firebase sincronizado | email=%s tenant_id=%s",
            redact_name(BOOTSTRAP_ADMIN_EMAIL), tenant_id,
        )
    else:
        logger.warning(
            "Falha ao sincronizar bootstrap admin Firebase | email=%s",
            redact_name(BOOTSTRAP_ADMIN_EMAIL),
        )


def bootstrap_departments():
    dept_map = ensure_default_departments(create_department)
    logger.info("Departamentos padrao sincronizados | total=%d", len(dept_map))


def bootstrap_default_tenant():
    """Cria o tenant 'hubloc' (default single-tenant) se ainda nao existir.

    Esse tenant e usado durante a transicao multi-tenant: todos os
    usuarios e dados que nao tem tenant_id explicito sao roteados para
    ele. Quando UI super-admin de criacao de tenants estiver pronta
    (Roadmap pos-Fase 2), tenants adicionais sao criados via interface.
    """
    if tenant_exists("hubloc"):
        logger.info("Tenant default 'hubloc' ja existe")
        return
    create_tenant(
        tenant_id="hubloc",
        name="Hubloc Imobiliaria",
        plan="professional",
        cnpj="",
    )
    logger.info("Tenant default 'hubloc' criado")


def validate_runtime_config():
    if not IS_CLOUD_RUN:
        return

    if MEDIA_STORAGE_BACKEND == "gcs":
        if not GCS_MEDIA_BUCKET:
            raise RuntimeError("Cloud Run com GCS requer GCS_MEDIA_BUCKET configurado")
    elif MEDIA_STORAGE_BACKEND != "firestore":
        raise RuntimeError("Cloud Run requer MEDIA_STORAGE_BACKEND=gcs ou firestore")

    if REQUIRE_WEBHOOK_SIGNATURE and not WHATSAPP_APP_SECRET:
        raise RuntimeError("Cloud Run requer WHATSAPP_APP_SECRET quando REQUIRE_WEBHOOK_SIGNATURE=true")

    if not WHATSAPP_VERIFY_TOKEN:
        raise RuntimeError("Cloud Run requer WHATSAPP_VERIFY_TOKEN configurado")


# -- Startup --

@app.on_event("startup")
async def startup():
    validate_runtime_config()
    init_database()
    # Cria o tenant default antes de qualquer bootstrap escopado.
    bootstrap_default_tenant()
    # Departamentos e admin do tenant default rodam DENTRO do contexto
    # do tenant — assim ficam em tenants/hubloc/{departments,users,...}.
    with tenant_context("hubloc"):
        bootstrap_departments()
        bootstrap_admin_user()
    ensure_media_dir()
    # Channel ainda fica em colecao flat (compartilhado por enquanto).
    # Migrar para tenants/{tid}/channels e parte da Fase 2 (sub-fase
    # futura). Por enquanto, todos os tenants compartilham os canais
    # ativos no Cloud Run — o webhook resolve o tenant via tenant_id
    # do channel ou via phone_routing global.
    from channel_service import bootstrap_default_channel
    bootstrap_default_channel()
    if FEATURE_AUDIO_TRANSCRIPTION:
        from transcription_service import init_speech_client
        if init_speech_client():
            logger.info("Transcricao de audio habilitada (Faster Whisper)")
        else:
            logger.warning("Transcricao de audio desabilitada (Faster Whisper falhou)")
    logger.info("CRM iniciado | host=%s port=%d", HOST, PORT)
    if WHATSAPP_TOKEN:
        if WHATSAPP_WABA_ID:
            logger.info(
                "WABA configurado | waba_id=%s phone_id=%s",
                WHATSAPP_WABA_ID,
                WHATSAPP_PHONE_NUMBER_ID,
            )
        else:
            logger.info("WABA configurado | phone_id=%s", WHATSAPP_PHONE_NUMBER_ID)
    else:
        logger.warning("WHATSAPP_TOKEN nao definido - webhook ativo mas envio desabilitado")


# -- Paginas HTML --

@app.get("/", response_class=HTMLResponse)
async def index():
    return _serve_frontend_app()


@app.get("/chat", response_class=HTMLResponse)
async def chat_page():
    return _serve_frontend_app()


@app.get("/app", response_class=HTMLResponse)
async def app_shell():
    if not _frontend_build_available():
        raise HTTPException(status_code=503, detail="Frontend React nao buildado")
    return FileResponse(FRONTEND_INDEX_FILE)


# -- Servir midia --

@app.get("/media/{subdir}/{filename}")
async def serve_media(subdir: str, filename: str):
    safe_subdir = os.path.basename(subdir)
    safe_filename = os.path.basename(filename)
    asset = get_media_asset(f"/media/{safe_subdir}/{safe_filename}")
    if not asset:
        raise HTTPException(status_code=404, detail="Arquivo nao encontrado")
    if asset.get("file_path"):
        return FileResponse(asset["file_path"], media_type=asset.get("mime_type"))
    return Response(content=asset["content"], media_type=asset.get("mime_type"))


# -- Webhook WABA --

@app.get("/webhook")
async def webhook_verify(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
):
    if hub_mode == "subscribe" and hub_verify_token == WHATSAPP_VERIFY_TOKEN:
        logger.info("Webhook verificado com sucesso")
        return PlainTextResponse(hub_challenge)
    # NAO logar o token recebido (LGPD/secret leakage). Indica apenas o
    # comprimento pra diferenciar "token vazio" de "token errado".
    logger.warning(
        "Falha na verificacao do webhook | mode=%s token_len=%s",
        hub_mode, len(hub_verify_token or ""),
    )
    return PlainTextResponse("Forbidden", status_code=403)


@app.post("/webhook")
async def webhook_receive(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not validate_signature(body, signature):
        logger.warning("Assinatura invalida no webhook")
        return JSONResponse(status_code=403, content={"error": "Assinatura invalida"})
    payload = await request.json()
    await process_webhook_payload(payload, ws_notify_callback=broadcast_to_operators)
    return {"status": "ok"}


# -- API: Autenticacao --

@app.post("/api/login")
async def login_removed():
    raise HTTPException(
        status_code=410,
        detail="Login legado removido. Use Firebase Auth no frontend e envie o ID token nas chamadas da API.",
    )


@app.get("/api/session")
async def session_info(current_user: dict = Depends(get_current_user)):
    """Retorna dados da sessao do usuario autenticado.

    Inclui paths das colecoes Firestore SCOPADAS ao tenant atual — o
    frontend sobrescreve config.firestore.collections com esses paths
    para que snapshots em modo realtime leiam diretamente da subcolecao
    do tenant (tenants/{tenant_id}/<colecao>).
    """
    tenant_id = current_user.get("tenant_id") or "hubloc"
    tenants_root = collection_name("tenants")
    tenant_collections = {
        "departments": f"{tenants_root}/{tenant_id}/departments",
        "operator_profiles": f"{tenants_root}/{tenant_id}/operator_profiles",
        "wa_contacts": f"{tenants_root}/{tenant_id}/wa_contacts",
        "wa_messages": f"{tenants_root}/{tenant_id}/wa_messages",
        "wa_conversations": f"{tenants_root}/{tenant_id}/wa_conversations",
        "wa_transfer_log": f"{tenants_root}/{tenant_id}/wa_transfer_log",
        "gc_conversations": f"{tenants_root}/{tenant_id}/gc_conversations",
        "gc_messages": f"{tenants_root}/{tenant_id}/gc_messages",
    }
    return {
        "user": current_user,
        "auth_mode": AUTH_MODE,
        "tenant_id": tenant_id,
        "firestore_collections": tenant_collections,
    }


@app.get("/api/client-config")
async def client_config():
    return {
        "auth_mode": AUTH_MODE,
        "chat_delivery_mode": CHAT_DELIVERY_MODE,
        "polling_interval_ms": POLLING_INTERVAL_MS,
        "data_backend": "firestore",
        "media_storage_backend": MEDIA_STORAGE_BACKEND,
        "allowed_email_domain": ALLOWED_FIREBASE_EMAIL_DOMAIN,
        "firebase_web_config": {
            "apiKey": FIREBASE_WEB_API_KEY,
            "authDomain": FIREBASE_WEB_AUTH_DOMAIN,
            "projectId": FIRESTORE_PROJECT_ID,
            "storageBucket": FIREBASE_STORAGE_BUCKET,
            "appId": FIREBASE_WEB_APP_ID,
            "messagingSenderId": FIREBASE_WEB_MESSAGING_SENDER_ID,
            "measurementId": FIREBASE_WEB_MEASUREMENT_ID,
        },
        "feature_message_status": FEATURE_MESSAGE_STATUS,
        "feature_google_chat": FEATURE_GOOGLE_CHAT,
        "firestore": {
            "collections": {
                "departments": collection_name("departments"),
                "operator_profiles": collection_name("operator_profiles"),
                "wa_contacts": collection_name("wa_contacts"),
                "wa_messages": collection_name("wa_messages"),
                "wa_transfer_log": collection_name("wa_transfer_log"),
                "gc_conversations": collection_name("gc_conversations"),
                "gc_messages": collection_name("gc_messages"),
            },
            "snapshot_enabled": True,
        },
    }


# -- API: Avatar do operador --

@app.post("/api/profile/avatar")
async def upload_avatar(request: Request, file: UploadFile = File(...)):
    current_user = get_current_user(request)
    user_id = current_user["id"]
    declared_mime = (file.content_type or "").lower()
    if declared_mime not in AVATAR_ALLOWED_MIME:
        raise HTTPException(status_code=400, detail="Formato nao permitido. Use JPEG, PNG ou WebP.")
    content = await file.read()
    if len(content) > AVATAR_MAX_SIZE_KB * 1024:
        raise HTTPException(status_code=413, detail=f"Imagem excede {AVATAR_MAX_SIZE_KB}KB.")
    _remove_old_avatar(get_user_avatar(user_id))
    path = _save_avatar(content, "avatar", user_id)
    if not path:
        raise HTTPException(status_code=400, detail="Conteudo do arquivo nao corresponde a uma imagem valida.")
    update_user_avatar(user_id, path)
    log_audit(user_id, "AVATAR_UPLOAD", f"Arquivo: {os.path.basename(path)}")
    return {"status": "ok", "avatar_path": path}


@app.delete("/api/profile/avatar")
async def remove_avatar(current_user: dict = Depends(get_current_user)):
    _remove_old_avatar(get_user_avatar(current_user["id"]))
    update_user_avatar(current_user["id"], "")
    log_audit(current_user["id"], "AVATAR_REMOVE", "")
    return {"status": "ok"}


# -- API: Avatar do contato WhatsApp --

@app.post("/api/wa/contact/{contact_id}/avatar")
async def upload_contact_avatar(contact_id: int, request: Request, file: UploadFile = File(...)):
    current_user = get_current_user(request)
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    declared_mime = (file.content_type or "").lower()
    if declared_mime not in AVATAR_ALLOWED_MIME:
        raise HTTPException(status_code=400, detail="Formato nao permitido.")
    content = await file.read()
    if len(content) > AVATAR_MAX_SIZE_KB * 1024:
        raise HTTPException(status_code=413, detail=f"Imagem excede {AVATAR_MAX_SIZE_KB}KB.")
    _remove_old_avatar(contact.get("contact_avatar_path", ""))
    path = _save_avatar(content, "contact", contact_id)
    if not path:
        raise HTTPException(status_code=400, detail="Arquivo invalido.")
    update_contact_avatar(contact_id, path)
    log_audit(current_user["id"], "CONTACT_AVATAR", f"Contato {contact_id}: {os.path.basename(path)}")
    return {"status": "ok", "avatar_path": path}


# -- API: Admin - Gerenciar usuarios --

@app.post("/api/admin/users")
async def admin_create_user(request: Request, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Permissao negada")
    body = await request.json()
    email = (body.get("email", "")).strip().lower()
    display_name = (body.get("display_name", "")).strip()
    department_id = body.get("department_id")
    role = body.get("role", "operador")
    if not email or not display_name:
        raise HTTPException(status_code=400, detail="Campos obrigatorios: email, display_name")
    if "@" not in email:
        raise HTTPException(status_code=400, detail="Email invalido")
    if len(display_name) > 100:
        raise HTTPException(status_code=400, detail="Display name excede limite de caracteres")
    if role not in ROLE_OPTIONS:
        raise HTTPException(status_code=400, detail=f"Cargo invalido. Opcoes: {', '.join(ROLE_OPTIONS)}")
    existing = get_user_by_email(email)
    if existing:
        raise HTTPException(status_code=409, detail="Usuario ja existe")
    user = upsert_firebase_user(
        firebase_uid="",
        email=email,
        display_name=display_name,
        role=role,
        department_id=department_id,
    )
    if not user:
        raise HTTPException(status_code=500, detail="Falha ao provisionar usuario Firebase")
    log_audit(current_user["id"], "USER_CREATE", f"{email} ({role})")
    return {"status": "ok", "user_id": user["id"]}


@app.put("/api/admin/users/{user_id}")
async def admin_update_user(user_id: int, request: Request, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Permissao negada")
    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    body = await request.json()
    display_name = body.get("display_name")
    department_id = body.get("department_id")
    role = body.get("role")
    if role and role not in ROLE_OPTIONS:
        raise HTTPException(status_code=400, detail=f"Cargo invalido. Opcoes: {', '.join(ROLE_OPTIONS)}")
    update_user(user_id, display_name=display_name, department_id=department_id, role=role)
    log_audit(current_user["id"], "USER_UPDATE", f"id={user_id}")
    return {"status": "ok"}


@app.delete("/api/admin/users/{user_id}")
async def admin_deactivate_user(user_id: int, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ("admin",):
        raise HTTPException(status_code=403, detail="Apenas admin pode desativar usuarios")
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Nao pode desativar a si mesmo")
    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    deactivate_user(user_id)
    log_audit(current_user["id"], "USER_DEACTIVATE", f"id={user_id} ({target['display_name']})")
    return {"status": "ok"}


@app.post("/api/admin/users/{user_id}/coex")
async def admin_authorize_coex(user_id: int, request: Request, current_user: dict = Depends(get_current_user)):
    """Autoriza um usuario (tipicamente operador) a fazer o proprio Embedded
    Signup coexistence. O admin/supervisor pre-cadastra o numero corporativo
    que sera conectado: isso libera a tela 'WhatsApp Coexistence' pra esse
    operador e o /exchange exige que o numero conectado bata com o autorizado.
    """
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Permissao negada")
    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    body = await request.json()
    phone_digits = "".join(ch for ch in str(body.get("phone", "")) if ch.isdigit())
    if len(phone_digits) < 10:
        raise HTTPException(status_code=400, detail="Numero invalido. Informe DDI+DDD+numero (ex: 5531999990000).")
    set_coex_authorization(user_id, phone_digits, authorized=True)
    # LGPD: nao logar o numero completo — so os 4 ultimos digitos.
    log_audit(current_user["id"], "COEX_AUTHORIZE", f"user={user_id} phone=...{phone_digits[-4:]}")
    return {"status": "ok", "user_id": user_id, "coex_phone": phone_digits}


@app.delete("/api/admin/users/{user_id}/coex")
async def admin_revoke_coex(user_id: int, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Permissao negada")
    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    set_coex_authorization(user_id, "", authorized=False)
    log_audit(current_user["id"], "COEX_REVOKE", f"user={user_id}")
    return {"status": "ok", "user_id": user_id}


@app.get("/api/admin/roles")
async def list_roles(current_user: dict = Depends(get_current_user)):
    return {"roles": ROLE_OPTIONS}


# -- API: Configuracoes do sistema --

@app.get("/api/settings/system")
async def get_settings_system(current_user: dict = Depends(get_current_user)):
    return get_system_settings()


@app.put("/api/settings/system")
async def update_settings_system(request: Request, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Apenas admin pode alterar configuracoes do sistema")
    body = await request.json()
    result = save_system_settings(body)
    log_audit(current_user["id"], "SYSTEM_SETTINGS_UPDATE", str(body))
    return result


@app.get("/api/settings/user")
async def get_settings_user(current_user: dict = Depends(get_current_user)):
    return get_user_settings(current_user["id"])


@app.put("/api/settings/user")
async def update_settings_user(request: Request, current_user: dict = Depends(get_current_user)):
    body = await request.json()
    result = save_user_settings(current_user["id"], body)
    log_audit(current_user["id"], "USER_SETTINGS_UPDATE", str(body))
    return result


ALARM_ALLOWED_MIME = {"audio/mpeg", "audio/wav", "audio/ogg", "audio/webm", "audio/mp3"}
ALARM_MAX_SIZE_KB = 500


@app.post("/api/admin/upload-alarm-sound")
async def upload_alarm_sound(
    request: Request,
    file: UploadFile = File(...),
    kind: str = Form("alarm"),
    current_user: dict = Depends(get_current_user),
):
    """Upload de som personalizado para notificacao ou alarme. Apenas admin."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Apenas admin")
    content = await file.read()
    if len(content) > ALARM_MAX_SIZE_KB * 1024:
        raise HTTPException(status_code=413, detail=f"Arquivo excede {ALARM_MAX_SIZE_KB}KB")
    mime = file.content_type or "audio/mpeg"
    if mime not in ALARM_ALLOWED_MIME:
        raise HTTPException(status_code=400, detail=f"Tipo nao permitido: {mime}. Use MP3, WAV ou OGG.")
    filename = file.filename or "alarm.mp3"
    ext = os.path.splitext(filename)[1] or ".mp3"
    safe_kind = "alarm" if kind == "alarm" else "notification"
    dest_name = f"{safe_kind}_custom{ext}"
    path = _write_media_bytes(content, "sounds", dest_name, mime)
    settings = get_system_settings()
    field = "alarm_sound_path" if safe_kind == "alarm" else "notification_sound_path"
    settings[field] = path
    save_system_settings(settings)
    log_audit(current_user["id"], "UPLOAD_ALARM_SOUND", f"{safe_kind}: {filename}")
    return {"status": "ok", "path": path, "kind": safe_kind}


# -- API: WhatsApp --

@app.get("/api/wa/contacts")
async def wa_contacts(current_user: dict = Depends(get_current_user)):
    contacts = get_all_wa_contacts()
    for c in contacts:
        c["unread"] = int(c.get("unread_count", 0))
    return {"contacts": contacts}


@app.get("/api/wa/contacts/all")
async def wa_contacts_all(
    q: str | None = Query(default=None, description="Busca por nome ou telefone"),
    limit: int = Query(default=5000, ge=1, le=10000),
    current_user: dict = Depends(get_current_user),
):
    """Lista TODOS os contatos do tenant — usado pelo modal de selecao
    (botao + da sidebar) que mostra tambem contatos da agenda telefonica
    sincronizada via smb_app_state_sync, nao so quem tem conversa ativa.

    Diferente de /api/wa/contacts (que usa orderBy('last_message_at')
    e exclui contatos sem mensagem), aqui retornamos ordenados com
    contatos COM nome real antes de contatos sem nome (telefones).
    Aceita filtro 'q' pra busca parcial em display_name,
    declared_name, whatsapp_profile_name e wa_id.
    """
    from firestore_common import collection as fs_coll
    privileged = current_user.get("role") in ("admin", "supervisor")
    rows = []
    if privileged:
        # Admin/supervisor enxerga toda a agenda do tenant (paridade #1).
        for snap in fs_coll("wa_contacts").stream():
            d = snap.to_dict() or {}
            if int(d.get("is_archived", 0) or 0) != 0:
                continue
            rows.append(d)
    else:
        # Operador comum: SO a propria agenda. Isolamento LGPD (nao expoe
        # contatos de outro operador/cliente) + corte de leitura (nao
        # varre os ~milhares de docs do tenant a cada sessao).
        for d in get_wa_contacts_scoped_for_user(
            current_user.get("id"), current_user.get("department_id"),
        ):
            if int(d.get("is_archived", 0) or 0) != 0:
                continue
            rows.append(d)

    if q:
        needle = q.strip().lower()
        if needle:
            def _match(c):
                return any(
                    needle in str(c.get(field, "") or "").lower()
                    for field in ("display_name", "declared_name", "whatsapp_profile_name", "wa_id", "phone_formatted")
                )
            rows = [c for c in rows if _match(c)]

    def _sort_key(c):
        # Prioriza nome real (declared > whatsapp_profile_name > display_name
        # com letra) sobre fallback de telefone. Dentro de cada grupo,
        # alfabético ASC.
        declared = str(c.get("declared_name") or "").strip()
        wpn = str(c.get("whatsapp_profile_name") or "").strip()
        display = str(c.get("display_name") or "").strip()
        # nome efetivo pra ordenacao
        effective = declared or wpn or display
        # 0 = nome real (comeca com letra). 1 = sem nome (telefone/simbolo).
        has_real_name = bool(effective) and effective[0].isalpha()
        return (0 if has_real_name else 1, effective.lower())

    rows.sort(key=_sort_key)
    total = len(rows)
    rows = rows[:limit]
    return {"contacts": rows, "total": total, "returned": len(rows)}


@app.post("/api/wa/conversation/open")
async def wa_conversation_open(request: Request, current_user: dict = Depends(get_current_user)):
    """Abre (ou cria) a conversation pra um contato + canal especifico.

    Usado quando o operador clica num contato da agenda telefonica que
    ainda nao tem thread no CRM — precisamos materializar a conversation
    pra ela aparecer na sidebar e o operador conseguir mandar template
    ou esperar mensagem do cliente.

    Body: { contact_id: int, channel_id?: int }
    Retorna o conversation_id determinístico.
    """
    body = await request.json()
    contact_id = body.get("contact_id")
    if contact_id is None:
        raise HTTPException(status_code=400, detail="contact_id obrigatorio")
    contact = get_wa_contact(int(contact_id))
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    channel_id = body.get("channel_id") or contact.get("channel_id")
    if channel_id is None:
        raise HTTPException(
            status_code=400,
            detail="channel_id obrigatorio (contato sem canal associado)",
        )
    from database import upsert_wa_conversation
    wa_id = str(contact.get("wa_id") or "")
    if not wa_id:
        raise HTTPException(status_code=400, detail="Contato sem wa_id")
    conversation_id = upsert_wa_conversation(
        contact_id=int(contact_id),
        wa_id=wa_id,
        channel_id=int(channel_id),
        source_channel_type=str(contact.get("source_channel_type", "") or ""),
        phone_number_id=str(contact.get("phone_number_id", "") or ""),
        auto_assign_user_id=current_user["id"],
        direction_for_unread=None,
    )
    log_audit(
        current_user["id"],
        "WA_CONVERSATION_OPEN",
        f"contact_id={contact_id} channel_id={channel_id} conv_id={conversation_id}",
    )
    return {"conversation_id": conversation_id, "contact_id": int(contact_id), "channel_id": int(channel_id)}


@app.get("/api/wa/conversations")
async def wa_conversations(current_user: dict = Depends(get_current_user)):
    """Retorna lista de conversations enriquecidas (Fase 3 multi-canal).

    Cada conversation representa uma thread (channel_id + wa_id).
    O mesmo wa_id em mais de um canal aparece como entradas distintas,
    cada uma com seu proprio assigned_to/unread/last_message_at.
    Dados do cliente (nome, telefone formatado, notas, qualificacao,
    rating) sao mesclados via join in-memory com wa_contacts.
    """
    from firestore_common import collection as fs_coll
    from channel_service import get_channel
    convs_raw = []
    for snap in fs_coll("wa_conversations").stream():
        data = snap.to_dict() or {}
        if "id" not in data:
            data["id"] = snap.id
        convs_raw.append(data)

    # Cache de contatos por id (evita N queries)
    contacts_by_id = {}
    for c in get_all_wa_contacts():
        contacts_by_id[c["id"]] = c

    enriched = []
    for conv in convs_raw:
        contact = contacts_by_id.get(conv.get("contact_id"))
        if not contact:
            continue
        channel = get_channel(conv.get("channel_id")) if conv.get("channel_id") else None
        item = {
            **conv,
            "wa_id": contact.get("wa_id"),
            "display_name": contact.get("display_name"),
            "declared_name": contact.get("declared_name"),
            "phone_formatted": contact.get("phone_formatted"),
            "qualification": contact.get("qualification"),
            "notes": contact.get("notes"),
            "rating": contact.get("rating"),
            "is_archived": contact.get("is_archived", 0),
            "contact_avatar_path": contact.get("contact_avatar_path"),
            "attendance_protocol": contact.get("attendance_protocol"),
            "attendance_started_at": contact.get("attendance_started_at"),
            "channel_label": channel.get("label", "") if channel else "",
            "channel_type": channel.get("channel_type", "") if channel else "",
            "channel_phone_number": channel.get("display_phone_number", "") if channel else "",
            "unread": int(conv.get("unread_count", 0)),
        }
        enriched.append(item)

    # Ordena por last_message_at desc (similar a get_all_wa_contacts)
    def _ts(c):
        v = c.get("last_message_at")
        if not v:
            return ""
        return v if isinstance(v, str) else v.isoformat()
    enriched.sort(key=_ts, reverse=True)

    return {"conversations": enriched}


@app.get("/api/wa/messages/{contact_id}")
async def wa_messages(
    contact_id: int,
    limit: int = Query(default=10, ge=1, le=200),
    conversation_id: str | None = Query(default=None, description="Filtra por thread especifica (canal+wa_id)"),
    current_user: dict = Depends(get_current_user),
):
    """Retorna mensagens de um contato.

    Comportamento Fase 2:
    - Se conversation_id e fornecido: filtra por aquela thread (canal+wa_id).
    - Se nao: retorna timeline cross-channel do contato (legado).
    """
    messages = get_wa_conversation(contact_id, limit=limit, conversation_id=conversation_id)
    return {"messages": messages}


@app.post("/api/wa/messages/{message_id}/transcribe")
async def wa_transcribe_message(message_id: int, current_user: dict = Depends(get_current_user)):
    from transcription_service import get_speech_client, transcribe_audio_bytes
    from media import get_media_asset

    speech_client = get_speech_client()
    if not speech_client:
        if FEATURE_AUDIO_TRANSCRIPTION:
            from transcription_service import init_speech_client
            speech_client = init_speech_client() and get_speech_client()
        if not speech_client:
            raise HTTPException(status_code=503, detail="Servico de transcricao nao disponivel. Verifique FEATURE_AUDIO_TRANSCRIPTION, dependencias e configuracao WHISPER_*.")

    msg = get_wa_message_by_id(message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Mensagem nao encontrada")
    if msg.get("msg_type") != "audio":
        raise HTTPException(status_code=400, detail="Mensagem nao e do tipo audio")

    media_path = msg.get("media_path", "")
    if not media_path:
        raise HTTPException(status_code=400, detail="Mensagem sem arquivo de audio")

    asset = get_media_asset(media_path)
    if not asset:
        raise HTTPException(status_code=404, detail="Arquivo de audio nao encontrado no storage")

    if "content" in asset:
        audio_bytes = asset["content"]
    elif "file_path" in asset:
        with open(asset["file_path"], "rb") as fh:
            audio_bytes = fh.read()
    else:
        raise HTTPException(status_code=500, detail="Nao foi possivel ler os bytes do audio")

    mime = asset.get("mime_type") or msg.get("media_mime") or "audio/ogg"
    transcript = transcribe_audio_bytes(
        audio_bytes,
        media_mime=mime,
        language_code=STT_LANGUAGE_CODE,
        timeout_s=STT_TIMEOUT_SECONDS,
    )

    if not transcript:
        raise HTTPException(status_code=422, detail="Nao foi possivel transcrever o audio. Verifique qualidade ou idioma.")

    update_wa_message_transcription(message_id, transcript)
    log_audit(current_user["id"], "WA_TRANSCRIBE", f"msg_id={message_id}")
    return {"transcription": transcript}


# -- Helper: janela de 24h do WhatsApp --

_24H = timedelta(hours=24)


def _check_send_permission(contact: dict, current_user: dict):
    """LEGADO. Substituido por _check_conv_send_permission (atua na conversation).
    Mantido apenas como fallback caso algum codigo legado interno chame.
    """
    assigned = contact.get("assigned_to")
    if assigned and assigned != current_user["id"]:
        raise HTTPException(status_code=403, detail="Atendimento atribuido a outro operador")
    if not assigned and current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Assuma o atendimento antes de enviar mensagem")


def _check_24h_window(contact: dict):
    """Raises 403 if last inbound message is older than 24h (Meta free-form window)."""
    last_inbound = contact.get("last_inbound_at")
    if not last_inbound:
        raise HTTPException(
            status_code=403,
            detail="Janela de 24h expirada. O cliente nunca enviou mensagem. Use um template.",
        )
    if isinstance(last_inbound, str):
        last_inbound = datetime.fromisoformat(last_inbound.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    if now - last_inbound > _24H:
        raise HTTPException(
            status_code=403,
            detail="Janela de 24h expirada. Use um template para reabrir a conversa.",
        )


def _maybe_refresh_coex_token(channel: dict | None) -> None:
    """Renova proativamente token coexistence se faltar <5min."""
    if not channel:
        return
    from channel_service import CHANNEL_TYPE_COEXISTENCE, refresh_coexistence_token

    if channel.get("channel_type") != CHANNEL_TYPE_COEXISTENCE:
        return
    expires_at_raw = channel.get("token_expires_at")
    if not expires_at_raw:
        return
    try:
        expires_at = datetime.fromisoformat(str(expires_at_raw).replace("Z", "+00:00"))
        if datetime.now(timezone.utc) >= expires_at - timedelta(minutes=5):
            refresh_coexistence_token(int(channel["id"]))
    except (ValueError, TypeError):
        logger.warning(
            "Canal coexistence %s com token_expires_at invalido: %s",
            channel.get("id"), expires_at_raw,
        )


def _resolve_channel_creds_by_id(channel_id: int | None) -> tuple[str, str, str]:
    """Resolve credenciais (token, phone_id, base) a partir de um channel_id.
    Refresh proativo do token coexistence quando aplicavel."""
    from channel_service import get_channel, get_send_credentials

    if channel_id is not None:
        _maybe_refresh_coex_token(get_channel(channel_id))

    try:
        return get_send_credentials(channel_id)
    except ValueError:
        # Fallback para env vars legadas
        if WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID:
            return WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID, GRAPH_API_BASE
        raise HTTPException(status_code=503, detail="Nenhum canal WhatsApp configurado")


def _resolve_send_target(
    conversation_id: str | None,
    contact_id: int | None,
) -> tuple[dict, dict, dict | None]:
    """Resolve (conversation, contact, channel) para um endpoint de envio.

    Estrategia Fase 2C:
      - Se conversation_id: thread e canonica. Carrega conversation, contato
        derivado dela, canal pelo conversation.channel_id.
      - Se so contact_id (legado): carrega contato, deriva
        conversation_id deterministico via (contact.channel_id, contact.wa_id),
        upserta conversation se nao existir.

    Levanta HTTPException 400/404 quando algo estiver inconsistente.
    Channel pode ser None quando canal foi removido (envio cai em fallback).
    """
    from channel_service import get_channel
    from database import (
        get_wa_conversation_by_id, get_wa_contact, upsert_wa_conversation,
    )

    if conversation_id:
        conv = get_wa_conversation_by_id(conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation nao encontrada")
        ctc = get_wa_contact(conv.get("contact_id"))
        if not ctc:
            raise HTTPException(status_code=404, detail="Contato da conversation nao encontrado")
        ch = get_channel(conv.get("channel_id")) if conv.get("channel_id") is not None else None
        return conv, ctc, ch

    if contact_id is None:
        raise HTTPException(status_code=400, detail="conversation_id ou contact_id obrigatorio")

    ctc = get_wa_contact(contact_id)
    if not ctc:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    ch_id = ctc.get("channel_id")
    ch = get_channel(ch_id) if ch_id is not None else None
    # Garante conversation: necessario pra audit + thread frontend
    derived_conv_id = upsert_wa_conversation(
        contact_id=ctc["id"],
        wa_id=ctc.get("wa_id", ""),
        channel_id=ch_id,
        source_channel_type=str(ctc.get("source_channel_type") or ""),
        phone_number_id=str(ctc.get("phone_number_id") or ""),
    )
    conv = get_wa_conversation_by_id(derived_conv_id) or {
        "id": derived_conv_id,
        "contact_id": ctc["id"],
        "wa_id": ctc.get("wa_id", ""),
        "channel_id": ch_id,
        "assigned_to": ctc.get("assigned_to"),
        "department_id": ctc.get("department_id"),
    }
    return conv, ctc, ch


def _check_conv_send_permission(conversation: dict, current_user: dict):
    """Permission check baseado na conversation (Fase 2C).

    Bloqueia envio se a thread esta atribuida a outro operador. Sem
    atribuicao, exige role admin/supervisor (mesma regra anterior, mas
    por thread em vez de por contato — admite que o mesmo cliente em
    canais diferentes seja atendido por gente diferente).
    """
    # Takeover temporario: durante 'pending' o operador precisa assumir antes
    # de responder (o frontend ja bloqueia o composer; isto fecha a brecha via API).
    if conversation.get("takeover_status") == "pending":
        raise HTTPException(status_code=403, detail="Assuma o atendimento temporario antes de responder")
    assigned = conversation.get("assigned_to")
    if assigned and assigned != current_user["id"]:
        raise HTTPException(status_code=403, detail="Atendimento atribuido a outro operador")
    if not assigned and current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Assuma o atendimento antes de enviar mensagem")


def _resolve_channel_creds(contact: dict) -> tuple[str, str, str]:
    """LEGADO. Resolve credenciais a partir do contato. Mantido para os
    poucos call-sites que ainda nao migraram para conversation_id (qualify
    rating template e similares onde a thread vem do contato direto).
    Novos endpoints devem usar _resolve_send_target + _resolve_channel_creds_by_id.
    """
    return _resolve_channel_creds_by_id(contact.get("channel_id"))


@app.post("/api/wa/send-location")
async def wa_send_location(body: WaSendLocationRequest, current_user: dict = Depends(get_current_user)):
    conv, contact, channel = _resolve_send_target(body.conversation_id, body.contact_id)
    token, phone_id, api_base = _resolve_channel_creds_by_id(
        channel["id"] if channel else conv.get("channel_id")
    )
    _check_conv_send_permission(conv, current_user)
    _check_24h_window(contact)
    reply_fields = _build_reply_fields(contact["id"], body.reply_to_message_id, body.reply_to_preview, body.reply_to_sender_name)
    reply_context = _build_reply_context(contact["id"], body.reply_to_message_id)

    wa_id = contact["wa_id"]
    url = f"{api_base}/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    location_obj: dict = {"latitude": body.latitude, "longitude": body.longitude}
    if body.name:
        location_obj["name"] = body.name
    if body.address:
        location_obj["address"] = body.address

    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "location",
        "location": location_obj,
        **reply_context,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        result = resp.json()

    if resp.status_code == 200:
        wa_msg_id = result.get("messages", [{}])[0].get("id", "")
        content = f"{body.name} {body.address}".strip()
        save_wa_message(
            wa_message_id=wa_msg_id,
            contact_id=contact["id"],
            direction="outbound",
            msg_type="location",
            content=content,
            latitude=body.latitude,
            longitude=body.longitude,
            status="sent",
            timestamp_wa=datetime.now(timezone.utc).isoformat(),
            operator_id=current_user["id"],
            channel_id=channel["id"] if channel else conv.get("channel_id"),
            conversation_id=conv["id"],
            sender_user_id=current_user["id"],
            channel_owner_user_id=(channel or {}).get("owner_user_id"),
            **reply_fields,
        )
        log_audit(current_user["id"], "WA_SEND_LOCATION", f"Para {wa_id}: {body.latitude},{body.longitude}")
        return {"status": "sent", "wa_message_id": wa_msg_id}

    error_msg = result.get("error", {}).get("message", "Erro desconhecido")
    raise HTTPException(status_code=502, detail=error_msg)


def _maybe_credit_assume_counter(contact: dict, operator_id: int):
    """Incrementa o contador do operador se esta e a primeira resposta apos assumir."""
    if contact.get("assume_pending_response") and contact.get("assigned_to") == operator_id:
        clear_contact_pending_response(contact["id"])
        increment_assume_counter(operator_id)


@app.post("/api/wa/send")
async def wa_send(body: WaSendRequest, current_user: dict = Depends(get_current_user)):
    conv, contact, channel = _resolve_send_target(body.conversation_id, body.contact_id)
    token, phone_id, api_base = _resolve_channel_creds_by_id(
        channel["id"] if channel else conv.get("channel_id")
    )
    _check_conv_send_permission(conv, current_user)
    _check_24h_window(contact)
    reply_fields = _build_reply_fields(contact["id"], body.reply_to_message_id, body.reply_to_preview, body.reply_to_sender_name)
    reply_context = _build_reply_context(contact["id"], body.reply_to_message_id)

    wa_id = _wa_target(contact["wa_id"])
    url = f"{api_base}/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": wa_id, "type": "text", "text": {"body": body.content}, **reply_context}

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        result = resp.json()

    if resp.status_code == 200:
        wa_msg_id = result.get("messages", [{}])[0].get("id", "")
        save_wa_message(
            wa_message_id=wa_msg_id, contact_id=contact["id"], direction="outbound",
            msg_type="text", content=body.content, status="sent",
            timestamp_wa=datetime.now(timezone.utc).isoformat(), operator_id=current_user["id"],
            channel_id=channel["id"] if channel else conv.get("channel_id"),
            conversation_id=conv["id"],
            sender_user_id=current_user["id"],
            channel_owner_user_id=(channel or {}).get("owner_user_id"),
            **reply_fields,
        )
        _maybe_credit_assume_counter(contact, current_user["id"])
        log_audit(current_user["id"], "WA_SEND", f"Para {wa_id}: {body.content[:80]}")
        return {"status": "sent", "wa_message_id": wa_msg_id}
    else:
        error_msg = result.get("error", {}).get("message", "Erro desconhecido")
        logger.warning("Falha ao enviar texto para %s | status=%s | erro=%s", redact_phone(wa_id), resp.status_code, error_msg)
        raise HTTPException(status_code=502, detail=error_msg)


@app.post("/api/wa/send-media")
async def wa_send_media(
    request: Request,
    conversation_id: str | None = Form(None),
    contact_id: int | None = Form(None),
    caption: str = Form(""), file: UploadFile = File(...),
    reply_to_message_id: int | None = Form(None),
    reply_to_preview: str = Form(""),
    reply_to_sender_name: str = Form(""),
):
    current_user = get_current_user(request)
    conv, contact, channel = _resolve_send_target(conversation_id, contact_id)
    token, phone_id, api_base = _resolve_channel_creds_by_id(
        channel["id"] if channel else conv.get("channel_id")
    )
    _check_conv_send_permission(conv, current_user)
    _check_24h_window(contact)
    reply_fields = _build_reply_fields(contact["id"], reply_to_message_id, reply_to_preview, reply_to_sender_name)
    reply_context = _build_reply_context(contact["id"], reply_to_message_id)

    file_content = await file.read()
    if len(file_content) > 16 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Arquivo excede 16MB")

    mime_type = file.content_type or "application/octet-stream"
    filename = file.filename or "upload"
    try:
        local_result = await save_upload_media(file_content, filename, mime_type)
    except RuntimeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    msg_type = local_result["msg_type"]

    media_id = await upload_media_to_whatsapp(file_content, mime_type, filename, token=token, phone_id=phone_id)
    if not media_id:
        raise HTTPException(status_code=502, detail="Falha no upload para a Meta")

    send_result = await send_media_message(contact["wa_id"], media_id, msg_type, caption, reply_context.get("context", {}).get("message_id", ""), token=token, phone_id=phone_id)
    if not send_result or "error" in send_result:
        error = send_result.get("error", "Erro desconhecido") if send_result else "Sem resposta"
        raise HTTPException(status_code=502, detail=str(error))

    wa_msg_id = send_result.get("wa_message_id", "")
    save_wa_message(
        wa_message_id=wa_msg_id, contact_id=contact["id"], direction="outbound",
        msg_type=msg_type, content=caption, media_path=local_result["path"],
        media_mime=mime_type, media_id=media_id, filename=filename,
        status="sent", timestamp_wa=datetime.now(timezone.utc).isoformat(),
        operator_id=current_user["id"],
        channel_id=channel["id"] if channel else conv.get("channel_id"),
        conversation_id=conv["id"],
        sender_user_id=current_user["id"],
        channel_owner_user_id=(channel or {}).get("owner_user_id"),
        media_size_bytes=len(file_content),
        **reply_fields,
    )
    _maybe_credit_assume_counter(contact, current_user["id"])
    log_audit(current_user["id"], "WA_SEND_MEDIA", f"{msg_type} para {contact['wa_id']}: {filename}")
    return {"status": "sent", "wa_message_id": wa_msg_id, "msg_type": msg_type, "media_path": local_result["path"]}


@app.post("/api/wa/send-audio")
async def wa_send_audio(
    request: Request,
    conversation_id: str | None = Form(None),
    contact_id: int | None = Form(None),
    file: UploadFile = File(...),
    reply_to_message_id: int | None = Form(None),
    reply_to_preview: str = Form(""),
    reply_to_sender_name: str = Form(""),
):
    """Envia audio gravado pelo microfone para contato WhatsApp.
    Converte WebM/Opus do navegador para OGG/Opus via FFmpeg."""
    current_user = get_current_user(request)

    conv, contact, channel = _resolve_send_target(conversation_id, contact_id)
    token, phone_id, api_base = _resolve_channel_creds_by_id(
        channel["id"] if channel else conv.get("channel_id")
    )
    _check_conv_send_permission(conv, current_user)
    _check_24h_window(contact)
    reply_fields = _build_reply_fields(contact["id"], reply_to_message_id, reply_to_preview, reply_to_sender_name)
    reply_context = _build_reply_context(contact["id"], reply_to_message_id)

    raw_content = await file.read()
    if len(raw_content) > 16 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio excede 16MB")

    original_mime = file.content_type or "audio/webm"

    # Converter WebM/Opus -> OGG/Opus (formato exigido pelo WhatsApp)
    converted = convert_audio_to_ogg_opus(raw_content, original_mime)
    if not converted:
        raise HTTPException(status_code=500, detail="Falha na conversao do audio. Verifique se o FFmpeg esta instalado.")

    # Salvar versao convertida localmente
    try:
        local_result = await save_upload_media(converted, "gravacao.ogg", "audio/ogg")
    except RuntimeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    # Upload do OGG convertido para a Meta
    media_id = await upload_media_to_whatsapp(converted, "audio/ogg", "audio.ogg", token=token, phone_id=phone_id)
    if not media_id:
        raise HTTPException(status_code=502, detail="Falha no upload de audio para a Meta")

    # Enviar mensagem de audio
    send_result = await send_media_message(contact["wa_id"], media_id, "audio", reply_wa_message_id=reply_context.get("context", {}).get("message_id", ""), token=token, phone_id=phone_id)
    if not send_result or "error" in send_result:
        error = send_result.get("error", "Erro desconhecido") if send_result else "Sem resposta"
        raise HTTPException(status_code=502, detail=str(error))

    wa_msg_id = send_result.get("wa_message_id", "")
    save_wa_message(
        wa_message_id=wa_msg_id, contact_id=contact["id"], direction="outbound",
        msg_type="audio", content="", media_path=local_result["path"],
        media_mime="audio/ogg", media_id=media_id, filename="gravacao.ogg",
        status="sent", timestamp_wa=datetime.now(timezone.utc).isoformat(),
        operator_id=current_user["id"],
        channel_id=channel["id"] if channel else conv.get("channel_id"),
        conversation_id=conv["id"],
        sender_user_id=current_user["id"],
        channel_owner_user_id=(channel or {}).get("owner_user_id"),
        media_size_bytes=len(converted),
        **reply_fields,
    )
    _maybe_credit_assume_counter(contact, current_user["id"])
    log_audit(current_user["id"], "WA_SEND_AUDIO", f"Para {contact['wa_id']}")
    return {"status": "sent", "wa_message_id": wa_msg_id, "msg_type": "audio", "media_path": local_result["path"]}


async def _load_approved_templates_for_channel(channel: dict) -> dict:
    # Compartilhado entre /api/wa/templates (UI) e /api/wa/send-template
    # (guard anti-WABA-mismatch #132001). Reusa _templates_cache (TTL 60s).
    # Levanta ValueError quando canal nao tem waba_id; HTTPException 502/503
    # quando a Meta/credenciais falham.
    from channel_service import get_send_credentials

    waba_id = str(channel.get("waba_id", "")).strip()
    if not waba_id:
        raise ValueError(f"Canal {channel.get('id')} sem waba_id")

    resolved_channel_id = int(channel.get("id") or 0)
    now = _monotonic()
    cached = _templates_cache.get(resolved_channel_id)
    if cached and (now - cached[0]) < _TEMPLATES_TTL_S:
        return cached[1]

    try:
        token, _phone_id, api_base = get_send_credentials(channel.get("id"))
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    url = f"{api_base}/{waba_id}/message_templates"
    params = {
        "fields": "name,language,category,status,components,id",
        "limit": 100,
    }
    headers = {"Authorization": f"Bearer {token}"}

    templates: list[dict] = []
    async with httpx.AsyncClient(timeout=15.0) as client:
        next_url: str | None = url
        next_params: dict | None = params
        while next_url:
            resp = await client.get(next_url, params=next_params, headers=headers)
            if resp.status_code >= 400:
                try:
                    err = resp.json().get("error", {}).get("message", resp.text[:300])
                except Exception:
                    err = resp.text[:300]
                raise HTTPException(status_code=502, detail=f"Meta retornou erro: {err}")
            data = resp.json()
            templates.extend(data.get("data", []) or [])
            paging = data.get("paging") or {}
            next_url = paging.get("next")
            next_params = None

    approved = [t for t in templates if str(t.get("status", "")).upper() == "APPROVED"]
    approved.sort(key=lambda t: (str(t.get("category", "")), str(t.get("name", ""))))
    result = {
        "channel_id": channel.get("id"),
        "waba_id": waba_id,
        "total": len(templates),
        "approved_count": len(approved),
        "templates": approved,
    }
    _templates_cache[resolved_channel_id] = (now, result)
    return result


class WaSendTemplateRequest(BaseModel):
    conversation_id: str | None = None
    contact_id: int | None = None
    template_name: str = "hello_world"
    language: str = "pt_BR"
    components: list[dict] | None = None  # [{type, sub_type?, index?, parameters: [{type:"text", text:"..."}]}]
    # Categoria Meta (marketing/utility/authentication). Best-effort
    # informada pelo frontend que ja conhece via /api/wa/templates.
    # Quando ausente, contabilizada em templates_sent.unknown.
    template_category: str | None = None


@app.post("/api/wa/send-template")
async def wa_send_template(
    body: WaSendTemplateRequest | None = None,
    contact_id: int | None = None,
    template_name: str = "hello_world",
    language: str = "pt_BR",
    current_user: dict = Depends(get_current_user),
):
    # Compat: aceita tanto body JSON quanto query params (legado).
    if body is not None:
        effective_conversation_id = body.conversation_id
        effective_contact_id = body.contact_id
        effective_template_name = body.template_name or template_name
        effective_language = body.language or language
        components = body.components or []
        effective_template_category = body.template_category
    else:
        if contact_id is None:
            raise HTTPException(status_code=400, detail="conversation_id ou contact_id obrigatorio")
        effective_conversation_id = None
        effective_contact_id = contact_id
        effective_template_name = template_name
        effective_language = language
        components = []
        effective_template_category = None

    conv, contact, channel = _resolve_send_target(effective_conversation_id, effective_contact_id)
    _check_conv_send_permission(conv, current_user)
    token, phone_id, api_base = _resolve_channel_creds_by_id(
        channel["id"] if channel else conv.get("channel_id")
    )

    # Guard anti-WABA-mismatch (Meta #132001): templates sao por-WABA e
    # tenants com >1 coexistence tem WABAs distintas. Se o frontend
    # listou templates de outra WABA (ex.: filtro pelo canal do contato
    # mas thread aberta pertence a outro canal apos transferencia), o
    # POST falha com 132001. Validamos antes server-side, reusando o
    # cache de listagem (TTL=60s) pra nao bater na Meta extra.
    # Falha do helper (Meta indisponivel) NAO bloqueia o envio — deixa
    # a Meta decidir; so 422 do mismatch sobe.
    if channel:
        try:
            approved = await _load_approved_templates_for_channel(channel)
            templates_list = approved.get("templates", []) or []
            matched = any(
                t.get("name") == effective_template_name
                and str(t.get("language", "")) == effective_language
                for t in templates_list
            )
            if not matched:
                waba_id = approved.get("waba_id", "?")
                display = channel.get("display_phone_number") or channel.get("phone_number_id") or "?"
                logger.warning(
                    "send-template WABA mismatch: template=%s lang=%s channel_id=%s waba=%s",
                    effective_template_name, effective_language, channel.get("id"), waba_id,
                )
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Template '{effective_template_name}' ({effective_language}) "
                        f"nao esta aprovado na WABA {waba_id} do canal "
                        f"{channel.get('id')} ({display}). Selecione um template "
                        f"aprovado nesta WABA ou submeta-o no Business Manager."
                    ),
                )
        except HTTPException as exc:
            if exc.status_code == 422:
                raise
            logger.warning(
                "send-template guard skip (helper indisponivel %s): %s",
                exc.status_code, exc.detail,
            )
        except ValueError as exc:
            logger.warning("send-template guard skip (canal sem waba_id): %s", exc)

    logger.info(
        "WA_SEND_TEMPLATE channel_id=%s waba=%s template=%s lang=%s",
        channel.get("id") if channel else None,
        str((channel or {}).get("waba_id", "")) or None,
        effective_template_name,
        effective_language,
    )

    url = f"{api_base}/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    template_payload: dict = {
        "name": effective_template_name,
        "language": {"code": effective_language},
    }
    if components:
        template_payload["components"] = components
    payload = {
        "messaging_product": "whatsapp",
        "to": _wa_target(contact["wa_id"]),
        "type": "template",
        "template": template_payload,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        result = resp.json()
    if resp.status_code == 200:
        wa_msg_id = result.get("messages", [{}])[0].get("id", "")
        # Renderiza preview do corpo para exibir no chat (substitui {{1}}..{{n}}).
        rendered_content = f"[template: {effective_template_name}]"
        try:
            body_params = []
            for comp in components:
                if comp.get("type") == "body":
                    body_params = [p.get("text", "") for p in comp.get("parameters", []) if p.get("type") == "text"]
                    break
            if body_params:
                rendered_content = f"[template: {effective_template_name}] " + " | ".join(body_params)
        except Exception:
            pass
        save_wa_message(
            wa_message_id=wa_msg_id, contact_id=contact["id"], direction="outbound",
            msg_type="template", content=rendered_content,
            status="sent", timestamp_wa=datetime.now(timezone.utc).isoformat(),
            operator_id=current_user["id"],
            channel_id=channel["id"] if channel else conv.get("channel_id"),
            conversation_id=conv["id"],
            sender_user_id=current_user["id"],
            channel_owner_user_id=(channel or {}).get("owner_user_id"),
            template_category=effective_template_category,
        )
        log_audit(current_user["id"], "WA_SEND_TEMPLATE", f"Para {contact['wa_id']} template={effective_template_name} lang={effective_language}")
        return {"status": "sent", "wa_message_id": wa_msg_id, "template_name": effective_template_name}
    else:
        # Fase 2.10: traduz erros Meta relacionados a billing para HTTP 402
        # com mensagem orientando o admin a configurar metodo de pagamento.
        err = (result or {}).get("error", {}) if isinstance(result, dict) else {}
        err_msg = str(err.get("message") or "Erro desconhecido")
        err_code = err.get("code")
        err_subcode = err.get("error_subcode")
        billing_signals = (
            err_code == 131009
            or err_subcode in (2494051, 2494052)
            or "not subscribed" in err_msg.lower()
            or "payment" in err_msg.lower()
        )
        if billing_signals:
            raise HTTPException(
                status_code=402,
                detail=(
                    "A WhatsApp Business Account ainda nao tem metodo de pagamento "
                    "configurado na Meta. Acesse business.facebook.com/wa/manage/billing/ "
                    "para adicionar e tente novamente em alguns minutos. "
                    f"(Meta: {err_msg} | code={err_code})"
                ),
            )
        raise HTTPException(status_code=502, detail=err_msg)


@app.get("/api/wa/templates")
async def wa_list_templates(
    channel_id: int | None = None,
    current_user: dict = Depends(get_current_user),
):
    """Lista templates aprovados da WABA do canal (ou canal default)."""
    from channel_service import get_channel, get_default_channel

    channel = get_channel(channel_id) if channel_id is not None else get_default_channel()
    if channel is None:
        raise HTTPException(status_code=503, detail="Nenhum canal WhatsApp configurado")

    try:
        return await _load_approved_templates_for_channel(channel)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


# -- API: Correcao de mensagem (Cenario C) --


class CorrectMessageRequest(BaseModel):
    message_id: int
    new_content: str

    @field_validator("new_content")
    @classmethod
    def validate_content(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Conteudo da correcao vazio")
        if len(v) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"Excede {MAX_MESSAGE_LENGTH} caracteres")
        return v


@app.post("/api/wa/correct-message")
async def correct_message(body: CorrectMessageRequest, current_user: dict = Depends(get_current_user)):
    """Envia uma nova mensagem corrigindo uma mensagem anterior.

    Marca a mensagem original como corrigida e envia a nova mensagem
    como reply da original, prefixada com indicador de correcao.
    """
    original = get_wa_message_by_id(body.message_id)
    if not original:
        raise HTTPException(status_code=404, detail="Mensagem original nao encontrada")
    if original.get("direction") != "outbound":
        raise HTTPException(status_code=400, detail="Apenas mensagens outbound podem ser corrigidas")
    if original.get("msg_type") != "text":
        raise HTTPException(status_code=400, detail="Apenas mensagens de texto podem ser corrigidas")
    if original.get("is_corrected"):
        raise HTTPException(status_code=400, detail="Mensagem ja foi corrigida")

    # Resolve thread original — preferimos conversation_id da mensagem
    # (denormalizado no save_wa_message) para nao confundir threads do
    # mesmo contato em canais distintos.
    conv, contact, channel = _resolve_send_target(
        original.get("conversation_id"),
        original.get("contact_id"),
    )
    token, phone_id, api_base = _resolve_channel_creds_by_id(
        channel["id"] if channel else conv.get("channel_id")
    )
    _check_24h_window(contact)

    # Enviar nova mensagem como reply da original
    wa_id = _wa_target(contact["wa_id"])
    url = f"{api_base}/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    reply_context = {}
    orig_wa_id = original.get("wa_message_id", "")
    if orig_wa_id and not orig_wa_id.startswith("local_"):
        reply_context = {"context": {"message_id": orig_wa_id}}
    payload = {
        "messaging_product": "whatsapp", "to": wa_id, "type": "text",
        "text": {"body": body.new_content},
        **reply_context,
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        result = resp.json()

    if resp.status_code != 200:
        error_msg = result.get("error", {}).get("message", "Erro desconhecido")
        raise HTTPException(status_code=502, detail=error_msg)

    wa_msg_id = result.get("messages", [{}])[0].get("id", "")
    original_preview = (original.get("content") or "")[:80]

    new_msg_id = save_wa_message(
        wa_message_id=wa_msg_id, contact_id=contact["id"], direction="outbound",
        msg_type="text", content=body.new_content, status="sent",
        timestamp_wa=datetime.now(timezone.utc).isoformat(),
        operator_id=current_user["id"],
        channel_id=channel["id"] if channel else conv.get("channel_id"),
        conversation_id=conv["id"],
        sender_user_id=current_user["id"],
        channel_owner_user_id=(channel or {}).get("owner_user_id"),
        reply_to_message_id=body.message_id,
        reply_to_preview=original_preview,
        reply_to_sender_name=current_user.get("display_name", "Operador"),
    )

    # Marcar original como corrigida
    mark_message_corrected(body.message_id, new_msg_id)

    log_audit(current_user["id"], "WA_MESSAGE_CORRECT", f"Msg {body.message_id} corrigida por {new_msg_id}")
    return {"status": "sent", "wa_message_id": wa_msg_id, "new_message_id": new_msg_id, "corrected_message_id": body.message_id}


# -- API: Contatos - Criacao manual e nome declarado --


class ManualContactRequest(BaseModel):
    declared_name: str
    phone: str
    channel_id: int | None = None

    @field_validator("declared_name")
    @classmethod
    def validate_name(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Nome e obrigatorio")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        v = "".join(ch for ch in v.strip() if ch.isdigit())
        if len(v) < 10:
            raise ValueError("Telefone invalido")
        return v


class DeclaredNameRequest(BaseModel):
    declared_name: str = ""

    @field_validator("declared_name")
    @classmethod
    def validate_name(cls, v):
        return v.strip()


@app.post("/api/wa/contact/manual")
async def create_contact_manual(body: ManualContactRequest, current_user: dict = Depends(get_current_user)):
    """Cria contato manualmente para iniciar conversa outbound via template."""
    wa_id = normalize_br_phone(body.phone)
    if not wa_id.startswith("55"):
        wa_id = f"55{wa_id}"

    # Resolver canal
    channel_id = body.channel_id
    if not channel_id:
        from channel_service import get_default_channel
        default_ch = get_default_channel()
        if not default_ch:
            raise HTTPException(status_code=400, detail="Nenhum canal WhatsApp disponivel")
        channel_id = default_ch["id"]

    allow_override = current_user.get("role") in ("admin", "supervisor")
    contact_id, error = create_manual_wa_contact(
        declared_name=body.declared_name,
        wa_id=wa_id,
        channel_id=channel_id,
        user_id=current_user["id"],
        allow_admin_override=allow_override,
    )
    if error:
        raise HTTPException(status_code=409, detail=error)

    contact = get_wa_contact(contact_id)
    # Conversation determinística criada por upsert_wa_conversation (Fase 3).
    conversation_id = f"{channel_id}__{wa_id}"
    log_audit(current_user["id"], "CONTACT_MANUAL_CREATE", f"Contato {contact_id}: {body.declared_name} ({wa_id})")
    return {"contact": contact, "conversation_id": conversation_id}


@app.put("/api/wa/contact/{contact_id}/declared-name")
async def update_declared_name(contact_id: int, body: DeclaredNameRequest, current_user: dict = Depends(get_current_user)):
    """Atualiza o nome declarado pelo operador."""
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    update_wa_contact_declared_name(contact_id, body.declared_name)
    log_audit(current_user["id"], "CONTACT_DECLARED_NAME", f"Contato {contact_id}: {body.declared_name}")
    updated = get_wa_contact(contact_id)
    return {"contact": updated}


# -- API: Contatos - Qualificacao e gerenciamento --

@app.put("/api/wa/contact/{contact_id}/qualify")
async def qualify_contact(contact_id: int, request: Request, current_user: dict = Depends(get_current_user)):
    body = await request.json()
    qualification = body.get("qualification", "")
    notes = body.get("notes")
    if qualification and qualification not in QUALIFICATION_OPTIONS:
        raise HTTPException(status_code=400, detail=f"Qualificacao invalida. Opcoes: {', '.join(QUALIFICATION_OPTIONS)}")
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    update_wa_contact_qualification(contact_id, qualification, notes)
    log_audit(current_user["id"], "CONTACT_QUALIFY", f"Contato {contact_id}: {qualification}")

    result = {"status": "ok"}

    # Ao marcar como convertido: gravar quem converteu e enviar template de avaliacao
    if qualification == "convertido":

        fs_document("wa_contacts", contact_id).set({
            "converted_by_user_id": current_user["id"],
            "rating_requested_at": fs_utcnow().isoformat(),
        }, merge=True)

        # Enviar template de avaliacao (mensagem visivel apenas para admin)
        try:
            token, phone_id, api_base = _resolve_channel_creds(contact)
            wa_id = _wa_target(contact["wa_id"])
            rating_url = f"{api_base}/{phone_id}/messages"
            rating_headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            rating_payload = {
                "messaging_product": "whatsapp",
                "to": wa_id,
                "type": "template",
                "template": {
                    "name": "rating_request",
                    "language": {"code": "pt_BR"},
                },
            }
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(rating_url, json=rating_payload, headers=rating_headers)
                resp_data = resp.json()

            if resp.status_code == 200:
                wa_msg_id = resp_data.get("messages", [{}])[0].get("id", "")
                from channel_service import get_channel as _get_ch
                _rating_channel = _get_ch(contact.get("channel_id")) if contact.get("channel_id") is not None else None
                save_wa_message(
                    wa_message_id=wa_msg_id, contact_id=contact_id, direction="outbound",
                    msg_type="template", content="[avaliacao: responda de 1 a 10]",
                    status="sent", timestamp_wa=datetime.now(timezone.utc).isoformat(),
                    operator_id=current_user["id"],
                    sender_user_id=current_user["id"],
                    channel_id=contact.get("channel_id"),
                    channel_owner_user_id=(_rating_channel or {}).get("owner_user_id"),
                    is_rating_message=True, visibility="admin_only",
                )
                result["rating_sent"] = True
                logger.info("Rating template enviado para contato %d", contact_id)
            else:
                # Template pode nao existir ainda — nao bloqueia a conversao
                error_msg = resp_data.get("error", {}).get("message", "")
                logger.warning("Falha ao enviar rating template: %s", error_msg)
                result["rating_sent"] = False
                result["rating_error"] = error_msg
        except Exception as exc:
            logger.warning("Erro ao enviar rating template: %s", exc)
            result["rating_sent"] = False

    return result


@app.post("/api/wa/contact/{contact_id}/read")
async def mark_contact_read(contact_id: int, current_user: dict = Depends(get_current_user)):
    """LEGADO: marca todas as mensagens inbound do contato como lidas
    (cross-channel). Frontend novo deve usar
    POST /api/wa/conversation/{conversation_id}/read pra zerar unread
    apenas da thread aberta."""
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    if int(contact.get("unread_count", 0) or 0) <= 0:
        return {"status": "ok", "updated_count": 0}
    updated_count = mark_wa_conversation_read(contact_id)
    return {"status": "ok", "updated_count": updated_count}


@app.post("/api/wa/conversation/{conversation_id}/read")
async def mark_conversation_read(conversation_id: str, current_user: dict = Depends(get_current_user)):
    """Zera unread_count da conversation e marca mensagens inbound da
    thread como lidas. Diferente do endpoint legado por contato, nao
    afeta unread de outras threads do mesmo cliente em canais distintos.
    """
    conv = get_wa_conversation_by_id(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation nao encontrada")
    if int(conv.get("unread_count", 0) or 0) <= 0:
        return {"status": "ok", "updated_count": 0}
    updated_count = mark_wa_conversation_read_by_id(conversation_id)
    return {"status": "ok", "updated_count": updated_count}


@app.post("/api/wa/conversation/{conversation_id}/takeover")
async def conversation_takeover(conversation_id: str, current_user: dict = Depends(get_current_user)):
    """Operador dono do numero assume um atendimento temporario: um cliente que
    e lead de outro operador mandou mensagem pro numero dele. NAO transfere a
    posse do lead — so libera este operador a responder nesta thread."""
    conv = get_wa_conversation_by_id(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation nao encontrada")
    handler = conv.get("takeover_handler_user_id")
    privileged = current_user.get("role") in ("admin", "supervisor")
    if handler and int(handler) != current_user["id"] and not privileged:
        raise HTTPException(status_code=403, detail="Apenas o dono do numero pode assumir este atendimento")
    set_conversation_takeover_active(conversation_id, current_user["id"])
    log_audit(current_user["id"], "TAKEOVER_START", f"conv={conversation_id} lead_owner={conv.get('lead_owner_user_id')}")
    return {"status": "ok", "conversation_id": conversation_id}


@app.post("/api/wa/conversation/{conversation_id}/return")
async def conversation_return(conversation_id: str, current_user: dict = Depends(get_current_user)):
    """Encerra o atendimento temporario e devolve o lead ao dono original.
    O historico fica no contato; novas mensagens nesse canal reabrem 'pending'."""
    conv = get_wa_conversation_by_id(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation nao encontrada")
    lead_owner = conv.get("lead_owner_user_id")
    clear_conversation_takeover(conversation_id)
    contact_id = conv.get("contact_id")
    if contact_id is not None:
        lead_name = (get_user_by_id(lead_owner) or {}).get("display_name", "operador de origem") if lead_owner else "operador de origem"
        insert_transfer_system_message(
            contact_id,
            f"Atendimento temporario encerrado por {current_user.get('display_name', 'operador')} e devolvido para {lead_name}.",
            current_user["id"],
        )
    log_audit(current_user["id"], "TAKEOVER_RETURN", f"conv={conversation_id} lead_owner={lead_owner}")
    return {"status": "ok", "conversation_id": conversation_id}


@app.delete("/api/wa/contact/{contact_id}")
async def delete_contact(contact_id: int, current_user: dict = Depends(get_current_user)):
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    archive_wa_contact(contact_id)
    log_audit(current_user["id"], "CONTACT_ARCHIVE", f"Contato {contact_id}")
    return {"status": "ok"}


@app.post("/api/wa/contact/{contact_id}/restore")
async def restore_contact(contact_id: int, current_user: dict = Depends(get_current_user)):
    restore_wa_contact(contact_id)
    log_audit(current_user["id"], "CONTACT_RESTORE", f"Contato {contact_id}")
    return {"status": "ok"}


@app.get("/api/wa/qualifications")
async def list_qualifications(current_user: dict = Depends(get_current_user)):
    return {"qualifications": QUALIFICATION_OPTIONS}


# -- API: Departamentos e Transferencia --

@app.get("/api/departments")
async def list_departments(current_user: dict = Depends(get_current_user)):
    return {"departments": get_all_departments()}


@app.post("/api/admin/departments")
async def create_department_endpoint(request: Request, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor")
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nome obrigatorio")
    department_id = create_department(name, body.get("description", ""), bot_key=body.get("bot_key"))
    from bot_service import invalidate_dept_cache
    invalidate_dept_cache()
    log_audit(current_user["id"], "DEPARTMENT_CREATE", f"name={name} id={department_id}")
    return {"id": department_id, "name": name}


@app.put("/api/admin/departments/{department_id}")
async def update_department_endpoint(department_id: int, request: Request, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor")
    existing = get_department_by_id(department_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Departamento nao encontrado")
    body = await request.json()
    update_kwargs = dict(
        name=body.get("name"),
        description=body.get("description"),
        is_active=body.get("is_active"),
        sort_order=body.get("sort_order"),
    )
    if "bot_key" in body:
        update_kwargs["bot_key"] = body.get("bot_key")
    ok, error = update_department(department_id, **update_kwargs)
    if not ok:
        raise HTTPException(status_code=400, detail=error)
    from bot_service import invalidate_dept_cache
    invalidate_dept_cache()
    log_audit(current_user["id"], "DEPARTMENT_UPDATE", f"id={department_id} fields={list(body.keys())}")
    return {"ok": True}


@app.delete("/api/admin/departments/{department_id}")
async def delete_department_endpoint(department_id: int, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Apenas admin")
    existing = get_department_by_id(department_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Departamento nao encontrado")
    deactivate_department(department_id)
    from bot_service import invalidate_dept_cache
    invalidate_dept_cache()
    log_audit(current_user["id"], "DEPARTMENT_DELETE", f"id={department_id} name={existing.get('name')}")
    return {"ok": True}


# -- API: Canais WhatsApp --

@app.get("/api/admin/channels")
async def list_channels(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") in ("admin", "supervisor"):
        channels = get_all_active_channels()
    else:
        channels = get_channels_for_user(current_user["id"])
    # Nao expor access_token na resposta
    safe = []
    for ch in channels:
        c = dict(ch)
        c.pop("access_token", None)
        safe.append(c)
    return {"channels": safe}


@app.post("/api/admin/channels")
async def create_channel_endpoint(request: Request, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor")
    body = await request.json()
    channel_type = body.get("channel_type", CHANNEL_TYPE_COEXISTENCE)
    label = (body.get("label") or "").strip()
    if not label:
        raise HTTPException(status_code=400, detail="Label obrigatorio")
    phone_number_id = (body.get("phone_number_id") or "").strip()
    if not phone_number_id:
        raise HTTPException(status_code=400, detail="phone_number_id obrigatorio")
    channel_id = create_channel(
        channel_type=channel_type,
        label=label,
        waba_id=body.get("waba_id", ""),
        phone_number_id=phone_number_id,
        display_phone_number=body.get("display_phone_number", ""),
        access_token=body.get("access_token", ""),
        owner_user_id=body.get("owner_user_id"),
        owner_firebase_uid=body.get("owner_firebase_uid", ""),
        default_department_id=body.get("default_department_id"),
        is_bot_enabled=body.get("is_bot_enabled", False),
    )
    log_audit(current_user["id"], "CHANNEL_CREATE", f"id={channel_id} type={channel_type} label={label}")
    return {"id": channel_id, "channel_type": channel_type, "label": label}


@app.put("/api/admin/channels/{channel_id}")
async def update_channel_endpoint(channel_id: int, request: Request, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor")
    existing = get_channel_by_id_from_db(channel_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Canal nao encontrado")
    body = await request.json()
    ok = update_channel(channel_id, **body)
    if not ok:
        raise HTTPException(status_code=400, detail="Nenhum campo valido para atualizar")
    log_audit(current_user["id"], "CHANNEL_UPDATE", f"id={channel_id} fields={list(body.keys())}")
    return {"ok": True}


@app.delete("/api/admin/channels/{channel_id}")
async def delete_channel_endpoint(channel_id: int, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Apenas admin")
    existing = get_channel_by_id_from_db(channel_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Canal nao encontrado")
    deactivate_channel(channel_id)
    log_audit(current_user["id"], "CHANNEL_DELETE", f"id={channel_id} label={existing.get('label')}")
    return {"ok": True}


@app.post("/api/admin/channels/{channel_id}/trigger-coex-sync")
async def trigger_coex_sync(
    channel_id: int,
    sync_type: str = Query(default="both", description="smb_app_state_sync|history|both"),
    current_user: dict = Depends(get_current_user),
):
    """Dispara sync de contatos e/ou history para canal coexistence.

    Doc Meta: POST /{phone_id}/smb_app_data com sync_type. Cada sync
    so pode ser disparado UMA VEZ por signup. Se ja foi disparado
    antes, Meta retorna erro. Janela de 24h apos signup — passou disso
    precisa desligar canal e refazer signup.
    """
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor")
    if sync_type not in ("smb_app_state_sync", "history", "both"):
        raise HTTPException(status_code=400, detail="sync_type deve ser smb_app_state_sync, history, ou both")
    channel = get_channel_by_id_from_db(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Canal nao encontrado")
    if str(channel.get("channel_type", "")) != CHANNEL_TYPE_COEXISTENCE:
        raise HTTPException(status_code=400, detail="Apenas canais coexistence")
    phone_id = str(channel.get("phone_number_id", "")).strip()
    token = str(channel.get("access_token", "")).strip()
    if not phone_id or not token:
        raise HTTPException(status_code=400, detail="Canal sem phone_number_id ou access_token")

    types_to_sync = ["smb_app_state_sync", "history"] if sync_type == "both" else [sync_type]
    results: dict[str, dict] = {}
    smb_data_url = f"{GRAPH_API_BASE}/{phone_id}/smb_app_data"

    async with httpx.AsyncClient(timeout=30.0) as client:
        for stype in types_to_sync:
            try:
                resp = await client.post(
                    smb_data_url,
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    json={"messaging_product": "whatsapp", "sync_type": stype},
                )
                if resp.status_code >= 400:
                    detail = _meta_error_detail(resp)
                    results[stype] = {"ok": False, "error": detail}
                    logger.error("trigger-coex-sync %s falhou: %s", stype, detail)
                else:
                    body = resp.json()
                    results[stype] = {"ok": True, "request_id": body.get("request_id", "")}
                    logger.info("trigger-coex-sync %s OK | request_id=%s", stype, body.get("request_id", ""))
            except httpx.RequestError as exc:
                results[stype] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
                logger.warning("trigger-coex-sync %s erro de rede: %s", stype, exc)

    log_audit(
        current_user["id"],
        "TRIGGER_COEX_SYNC",
        f"channel_id={channel_id} types={types_to_sync} results={results}",
    )
    return {"channel_id": channel_id, "results": results}


# -- API: Pending webhook events (eventos da Meta sem canal resolvido) --

@app.get("/api/admin/pending-webhook-events")
async def list_pending_webhook_events(
    status: str | None = Query(default=None, description="pending|resolved|failed"),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
):
    """Lista eventos da Meta que nao puderam ser processados imediatamente
    (canal nao indexado ainda durante onboarding, phone_id sem canal,
    excecao no processamento). Garantia de zero perda — operador retenta
    apos o canal estar disponivel."""
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor")
    from pending_events import list_pending_events
    events = list_pending_events(status=status, limit=limit)
    return {"events": events, "count": len(events)}


@app.post("/api/admin/pending-webhook-events/{event_id}/retry")
async def retry_pending_webhook_event(event_id: int, current_user: dict = Depends(get_current_user)):
    """Re-roda process_webhook_payload com o payload original. Idempotente
    via wa_message_id (save_wa_message detecta duplicata)."""
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor")
    from pending_events import get_pending_event, mark_event_attempt
    event = get_pending_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Evento nao encontrado")
    if event.get("status") == "resolved":
        return {"status": "already_resolved", "id": event_id}
    payload = event.get("payload") or {}
    if not payload:
        raise HTTPException(status_code=400, detail="Evento sem payload")
    try:
        await process_webhook_payload(payload, ws_notify_callback=broadcast_to_operators)
        mark_event_attempt(event_id, success=True)
        log_audit(current_user["id"], "PENDING_EVENT_RETRY", f"id={event_id} ok")
        return {"status": "ok", "id": event_id}
    except Exception as exc:
        mark_event_attempt(event_id, success=False, error=f"{type(exc).__name__}: {exc}")
        log_audit(current_user["id"], "PENDING_EVENT_RETRY", f"id={event_id} err={type(exc).__name__}")
        raise HTTPException(status_code=502, detail=f"Falha ao reprocessar: {exc}")


@app.post("/api/admin/pending-webhook-events/{event_id}/dismiss")
async def dismiss_pending_webhook_event(event_id: int, current_user: dict = Depends(get_current_user)):
    """Marca evento como definitivamente falho (nao retentar). Usar quando
    intervencao confirma que o evento nao tem como ser recuperado."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Apenas admin")
    from pending_events import mark_event_failed, get_pending_event
    if not get_pending_event(event_id):
        raise HTTPException(status_code=404, detail="Evento nao encontrado")
    mark_event_failed(event_id, error="dismissed_by_admin")
    log_audit(current_user["id"], "PENDING_EVENT_DISMISS", f"id={event_id}")
    return {"status": "dismissed", "id": event_id}


@app.delete("/api/admin/pending-webhook-events/{event_id}")
async def delete_pending_webhook_event_endpoint(event_id: int, current_user: dict = Depends(get_current_user)):
    """Remove evento da fila. Use apos retry confirmado ou eventos sem
    valor de retencao."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Apenas admin")
    from pending_events import delete_pending_event
    if not delete_pending_event(event_id):
        raise HTTPException(status_code=404, detail="Evento nao encontrado")
    log_audit(current_user["id"], "PENDING_EVENT_DELETE", f"id={event_id}")
    return {"status": "deleted", "id": event_id}


async def _fetch_channel_billing_status(channel_id: int) -> dict:
    """Helper reusavel: consulta Meta Graph API e retorna estado de billing
    de um canal. Usado pelo endpoint admin (channel_billing_status) e pelo
    cron de health-check (Fase 2.10.3).

    Em vez de raise, retorna dict com `ok=False` e `error` na falha.
    """
    from channel_service import get_channel, get_send_credentials

    channel = get_channel(channel_id)
    if not channel:
        return {
            "channel_id": channel_id,
            "ok": False,
            "error": "channel_not_found",
            "has_payment_method": False,
        }

    waba_id = str(channel.get("waba_id") or "").strip()
    if not waba_id:
        return {
            "channel_id": channel_id,
            "ok": False,
            "error": "missing_waba_id",
            "has_payment_method": False,
        }

    try:
        token, _phone_id, api_base = get_send_credentials(channel_id)
    except ValueError as exc:
        return {
            "channel_id": channel_id,
            "waba_id": waba_id,
            "ok": False,
            "error": str(exc),
            "has_payment_method": False,
        }

    url = f"{api_base}/{waba_id}"
    params = {"fields": "primary_funding_id,account_review_status,health_status,owner_business_info"}
    headers = {"Authorization": f"Bearer {token}"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params, headers=headers)
        if resp.status_code >= 400:
            return {
                "channel_id": channel_id,
                "waba_id": waba_id,
                "ok": False,
                "error": _meta_error_detail(resp),
                "has_payment_method": False,
            }
        data = resp.json()
    except Exception as exc:
        return {
            "channel_id": channel_id,
            "waba_id": waba_id,
            "ok": False,
            "error": str(exc),
            "has_payment_method": False,
        }

    primary_funding_id = data.get("primary_funding_id") or ""
    return {
        "channel_id": channel_id,
        "waba_id": waba_id,
        "ok": True,
        "has_payment_method": bool(primary_funding_id),
        "primary_funding_id": primary_funding_id,
        "account_review_status": data.get("account_review_status"),
        "health_status": data.get("health_status"),
        "owner_business_info": data.get("owner_business_info"),
        "checked_at": fs_utcnow().isoformat(),
    }


@app.get("/api/wa/channel/{channel_id}/billing-status")
async def channel_billing_status(channel_id: int, current_user: dict = Depends(get_current_user)):
    """Health-check do canal na Meta (Fase 2.10).

    Consulta GET /<WABA_ID>?fields=primary_funding_id,account_review_status
    para descobrir se o cliente ja configurou metodo de pagamento. Sem
    isso, templates de marketing/utility falham com erro #131009 ao
    tentar enviar.
    """
    from channel_service import get_channel

    channel = get_channel(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Canal nao encontrado")
    waba_id = str(channel.get("waba_id") or "").strip()
    if not waba_id:
        raise HTTPException(status_code=400, detail="Canal sem WABA_ID associado")

    now = _monotonic()
    cached = _billing_cache.get(channel_id)
    if cached and (now - cached[0]) < (_BILLING_TTL_S_OK if cached[1].get("ok") else _BILLING_TTL_S_ERR):
        return cached[1]

    res = await _fetch_channel_billing_status(channel_id)
    if not res.get("ok") and res.get("error") in ("channel_not_found", "missing_waba_id"):
        # Caminho rejeitado antes do helper — manter HTTPException pro endpoint admin
        raise HTTPException(
            status_code=404 if res["error"] == "channel_not_found" else 400,
            detail=res["error"],
        )
    _billing_cache[channel_id] = (now, res)
    return res


# ---------------------------------------------------------------------------
# Cron health-check (Fase 2.10.3) — Cloud Scheduler chama diariamente.
# Computa estado consolidado por tenant em tenants/{tid}/health_status/current
# e atualiza payment_method_status no doc flat de cada canal.
# ---------------------------------------------------------------------------

def _classify_payment_status(billing: dict, channel: dict) -> tuple[str, bool, bool]:
    """Decide payment_method_status (ok|pending|error|expired) e flags
    de token_expired/token_expiring_soon (so coexistence)."""
    if not billing.get("ok"):
        status = "error"
    elif billing.get("has_payment_method"):
        status = "ok"
    else:
        status = "pending"

    token_expired = False
    token_expiring = False
    if channel.get("channel_type") == "coexistence":
        expires_at_raw = channel.get("token_expires_at")
        if expires_at_raw:
            try:
                expires_at = datetime.fromisoformat(
                    str(expires_at_raw).replace("Z", "+00:00")
                )
                now = datetime.now(timezone.utc)
                if expires_at <= now:
                    token_expired = True
                    status = "expired"
                elif expires_at - now <= timedelta(days=7):
                    token_expiring = True
            except (ValueError, TypeError):
                pass
    return status, token_expired, token_expiring


async def _compute_tenant_health() -> dict:
    """Executa dentro de tenant_context. Para cada canal ativo: chama
    _fetch_channel_billing_status, classifica, persiste payment_method_status
    no doc flat do canal. Retorna dict pronto pra gravar em
    tenants/{tid}/health_status/current.
    """
    import asyncio
    from channel_service import get_all_active_channels
    from firestore_common import global_document

    channels = get_all_active_channels()
    if not channels:
        return {
            "checked_at": fs_utcnow().isoformat(),
            "channels_total": 0,
            "channels_pending_payment": 0,
            "tokens_expiring_soon": 0,
            "templates_recent_failures": 0,
            "per_channel": [],
        }

    billing_results = await asyncio.gather(
        *[_fetch_channel_billing_status(ch["id"]) for ch in channels],
        return_exceptions=True,
    )

    channels_pending_payment = 0
    tokens_expiring_soon = 0
    per_channel: list[dict] = []
    for ch, billing in zip(channels, billing_results):
        if isinstance(billing, Exception):
            billing = {
                "channel_id": ch["id"],
                "ok": False,
                "error": str(billing),
                "has_payment_method": False,
            }
        status, token_expired, token_expiring = _classify_payment_status(billing, ch)
        if status == "pending":
            channels_pending_payment += 1
        if token_expiring:
            tokens_expiring_soon += 1

        try:
            global_document("channels", ch["id"]).set({
                "payment_method_status": status,
                "payment_method_checked_at": fs_utcnow(),
            }, merge=True)
        except Exception as exc:
            logger.warning(
                "cron health: falha ao atualizar payment_method_status canal %s: %s",
                ch["id"], exc,
            )

        per_channel.append({
            "channel_id": ch["id"],
            "label": ch.get("label", ""),
            "channel_type": ch.get("channel_type"),
            "payment_method_status": status,
            "has_payment_method": billing.get("has_payment_method", False),
            "account_review_status": billing.get("account_review_status"),
            "token_expiring_soon": token_expiring,
            "token_expired": token_expired,
            "error": billing.get("error") if not billing.get("ok") else None,
        })

    return {
        "checked_at": fs_utcnow().isoformat(),
        "channels_total": len(channels),
        "channels_pending_payment": channels_pending_payment,
        "tokens_expiring_soon": tokens_expiring_soon,
        "templates_recent_failures": 0,  # placeholder pra futura agregacao
        "per_channel": per_channel,
    }


def _verify_oidc_token(token: str) -> None:
    """Valida OIDC token Bearer (Cloud Scheduler nativo).

    Cloud Scheduler com `--oidc-service-account-email=<sa>` e
    `--oidc-token-audience=<url>` envia Authorization: Bearer <jwt>
    onde o JWT eh assinado pelo Google e tem:
      - iss = https://accounts.google.com
      - aud = audience configurado no job
      - email = SA do scheduler

    Env vars (configuradas no Cloud Run):
      CRON_OIDC_AUDIENCE          (obrigatorio, ex: a propria URL do endpoint)
      CRON_OIDC_SERVICE_ACCOUNT   (opcional, email do SA esperado — strict)
    """
    audience = os.environ.get("CRON_OIDC_AUDIENCE", "").strip()
    if not audience:
        raise HTTPException(
            status_code=503,
            detail="CRON_OIDC_AUDIENCE nao configurado",
        )
    expected_sa = os.environ.get("CRON_OIDC_SERVICE_ACCOUNT", "").strip()

    from google.oauth2 import id_token as _id_token
    from google.auth.transport import requests as _ga_requests

    try:
        payload = _id_token.verify_oauth2_token(
            token, _ga_requests.Request(), audience=audience
        )
    except ValueError as exc:
        # Token invalido / mal-assinado / aud errada / iss errada / expirado
        raise HTTPException(
            status_code=401,
            detail=f"OIDC token invalido: {exc}",
        )

    if expected_sa and payload.get("email") != expected_sa:
        # Strict mode: rejeita se SA nao bate com o esperado
        raise HTTPException(
            status_code=401,
            detail="OIDC SA mismatch",
        )


def _verify_cron_auth(request: Request) -> None:
    """Aceita OIDC Bearer (Cloud Scheduler) OU header X-Cron-Secret.

    Tenta primeiro o que estiver presente:
      1. Authorization: Bearer ...  -> OIDC verify
      2. X-Cron-Secret: ...         -> shared secret hmac compare
      3. Nenhum                     -> 401

    Cada metodo eh independente — falha de um nao cai no outro.
    Em prod, mover pra OIDC e remover INTERNAL_CRON_SECRET (CRON_OIDC_*
    sao suficientes); em staging/dev/CI, X-Cron-Secret continua util.
    """
    import hmac as _hmac

    auth_header = request.headers.get("authorization", "") or request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        _verify_oidc_token(auth_header[7:].strip())
        return

    secret_header = request.headers.get("X-Cron-Secret", "")
    if secret_header:
        expected = os.environ.get("INTERNAL_CRON_SECRET", "").strip()
        if not expected:
            raise HTTPException(
                status_code=503,
                detail="INTERNAL_CRON_SECRET nao configurado",
            )
        if not _hmac.compare_digest(secret_header.encode("utf-8"), expected.encode("utf-8")):
            raise HTTPException(status_code=401, detail="X-Cron-Secret invalido")
        return

    raise HTTPException(
        status_code=401,
        detail="auth ausente: envie Authorization: Bearer <oidc> ou X-Cron-Secret",
    )


@app.post("/api/internal/cron/health-check")
async def cron_health_check(request: Request):
    """Cloud Scheduler chama diariamente. Itera tenants ativos, computa
    estado consolidado e grava em tenants/{tid}/health_status/current.

    Auth (qualquer um valida):
      - Authorization: Bearer <OIDC token>  (Cloud Scheduler com
        --oidc-service-account-email + --oidc-token-audience)
      - X-Cron-Secret: <secret>             (header customizado, fallback
        pra dev/staging onde OIDC nao tem SA configurado)
    """
    _verify_cron_auth(request)

    from tenant_service import list_tenants
    from firestore_common import set_tenant_context, reset_tenant_context, document as fs_doc

    summary: list[dict] = []
    for tenant in list_tenants(active_only=True):
        tid = str(tenant.get("id") or "")
        if not tid:
            continue
        token = set_tenant_context(tid)
        try:
            health = await _compute_tenant_health()
            fs_doc("health_status", "current").set(health, merge=False)
            summary.append({
                "tenant_id": tid,
                "channels_total": health["channels_total"],
                "channels_pending_payment": health["channels_pending_payment"],
                "tokens_expiring_soon": health["tokens_expiring_soon"],
            })
        except Exception as exc:
            logger.warning("cron_health_check: tenant %s falhou: %s", tid, exc)
            summary.append({"tenant_id": tid, "error": str(exc)})
        finally:
            reset_tenant_context(token)

    return {
        "checked_at": fs_utcnow().isoformat(),
        "tenants_processed": len(summary),
        "summary": summary,
    }


@app.get("/api/wa/contact/{contact_id}")
async def wa_contact_detail(contact_id: int, current_user: dict = Depends(get_current_user)):
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    return {"contact": contact}


@app.post("/api/wa/transfer")
async def wa_transfer(request: Request, current_user: dict = Depends(get_current_user)):
    body = await request.json()
    conversation_id = body.get("conversation_id")
    contact_id = body.get("contact_id")
    to_user_id = body.get("to_user_id")
    to_department_id = body.get("to_department_id")
    reason = body.get("reason", "")
    summary = body.get("summary", "")
    if not conversation_id and not contact_id:
        raise HTTPException(status_code=400, detail="conversation_id ou contact_id obrigatorio")
    if not to_user_id:
        raise HTTPException(status_code=400, detail="Selecione o operador destino")
    if not summary:
        raise HTTPException(status_code=400, detail="Resumo do atendimento e obrigatorio")

    conv, contact, channel = _resolve_send_target(conversation_id, contact_id)

    # Fase 2C: transferencia atua na conversation. Quando vier so contact_id
    # (legado), assign_wa_contact espelha em todas as conversations do contato
    # — mas no fluxo novo so transferimos a thread aberta, deixando outras
    # threads coexistence intactas.
    if conversation_id:
        result = assign_wa_conversation(conv["id"], to_user_id, to_department_id, current_user["id"], reason, summary)
    else:
        result = assign_wa_contact(contact["id"], to_user_id, to_department_id, current_user["id"], reason, summary)
    if result is None:
        raise HTTPException(status_code=404, detail="Conversation nao encontrada")

    to_user = get_user_by_id(to_user_id) if to_user_id else None
    to_name = to_user["display_name"] if to_user else "Nenhum"

    sys_content = (
        f"Transferido de {current_user['display_name']} para {to_name}"
        + (f" | Motivo: {reason}" if reason else "")
        + (f" | Resumo: {summary}" if summary else "")
    )
    insert_transfer_system_message(
        contact["id"], sys_content, current_user["id"],
        conversation_id=conv["id"],
        channel_id=channel["id"] if channel else conv.get("channel_id"),
    )
    log_audit(current_user["id"], "WA_TRANSFER", f"Conv {conv['id']} -> {to_name} (dept={to_department_id}): {reason}")

    await broadcast_to_operators({
        "event": "wa_contact_reassigned",
        "data": {
            "conversation_id": conv["id"],
            "contact_id": contact["id"],
            "assigned_to": to_user_id,
            "assigned_name": to_name,
        },
    })
    return {"status": "transferred", "to_user": to_name}


@app.post("/api/wa/assume/{contact_id}")
async def wa_assume_contact(contact_id: int, current_user: dict = Depends(get_current_user)):
    """Operador assume o atendimento de um contato nao atribuido."""
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    try:
        existing_id = int(contact.get("assigned_to") or 0) or None
        current_id = int(current_user["id"])
    except (TypeError, ValueError):
        existing_id = None
        current_id = None
    if existing_id is not None and existing_id != current_id:
        raise HTTPException(status_code=409, detail="Atendimento ja assumido por outro operador")
    # -- Regra do contador de assumidas sem resposta --
    assume_counter = get_assume_counter(current_user["id"])
    if assume_counter <= -2:
        raise HTTPException(
            status_code=403,
            detail="Voce atingiu o limite de atendimentos assumidos sem resposta. Responda as conversas pendentes antes de assumir novas.",
        )
    result = assign_wa_contact(contact_id, current_user["id"], contact.get("department_id"), current_user["id"], reason="Assumido pelo operador", summary="Assumido pelo operador")
    if result is None:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    # Decrementar contador e marcar contato como pendente de resposta
    decrement_assume_counter(current_user["id"])
    mark_contact_pending_response(contact_id)
    # Gravar original_operator_id se ainda nao definido (para roteamento de lead retornante)
    if not contact.get("original_operator_id"):

        fs_document("wa_contacts", contact_id).set({"original_operator_id": current_user["id"]}, merge=True)
    now = datetime.now(timezone.utc)
    protocol = f"ATD-{now.strftime('%Y%m%d%H%M%S')}-{contact_id:05d}"
    set_attendance_protocol(contact_id, protocol, now.isoformat())
    sys_content = f"Atendimento assumido por {current_user['display_name']} | Protocolo: {protocol}"
    insert_transfer_system_message(contact_id, sys_content, current_user["id"])
    log_audit(current_user["id"], "WA_ASSUME", f"Contato {contact_id} | Protocolo {protocol}")
    await broadcast_to_operators({
        "event": "wa_contact_reassigned",
        "data": {"contact_id": contact_id, "assigned_to": current_user["id"], "assigned_name": current_user["display_name"]},
    })
    return {"status": "assumed", "assigned_to": current_user["id"], "assigned_name": current_user["display_name"], "protocol": protocol}


@app.post("/api/admin/operator/{user_id}/reset-assume-counter")
async def admin_reset_assume_counter(user_id: int, current_user: dict = Depends(get_current_user)):
    """Reseta o contador de assumidas sem resposta de um operador. Apenas admin/supervisor."""
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor")
    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Operador nao encontrado")
    reset_assume_counter(user_id)
    log_audit(current_user["id"], "RESET_ASSUME_COUNTER", f"Operador {target.get('display_name', user_id)} (id={user_id})")
    return {"status": "reset", "user_id": user_id, "counter": 0}


@app.get("/api/wa/transfer-history/{contact_id}")
async def wa_transfer_hist(contact_id: int, current_user: dict = Depends(get_current_user)):
    return {"history": get_transfer_history(contact_id)}


@app.post("/api/wa/contact/{contact_id}/return-to-bot")
async def wa_return_to_bot(contact_id: int, current_user: dict = Depends(get_current_user)):
    """Devolve o contato para a fila do bot. Apenas admin/supervisor."""
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor")
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    result = return_contact_to_bot(contact_id, current_user["id"])
    if not result:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    sys_content = f"Devolvido ao bot por {current_user['display_name']}"
    insert_transfer_system_message(contact_id, sys_content, current_user["id"])
    log_audit(current_user["id"], "WA_RETURN_TO_BOT", f"Contato {contact_id}")
    return {"status": "returned_to_bot"}


@app.post("/api/admin/bulk-reassign")
async def admin_bulk_reassign(request: Request, current_user: dict = Depends(get_current_user)):
    """Reatribuicao em lote de contatos de um operador.

    Body: { from_user_id, action: "return_to_bot" | "transfer", to_user_id? }

    Exclui automaticamente contatos cujo canal e coexistence proprio do
    operador X (i.e. `channel.owner_user_id == from_user_id`). Esses
    contatos pertencem ao WhatsApp pessoal dele e nao podem ser
    transferidos sem perder acesso ao numero — o operador continua dono.
    """
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor")
    body = await request.json()
    from_user_id = body.get("from_user_id")
    action = body.get("action", "return_to_bot")
    to_user_id = body.get("to_user_id")

    if not from_user_id:
        raise HTTPException(status_code=400, detail="from_user_id obrigatorio")

    contacts = get_contacts_by_assigned_user(from_user_id)
    if not contacts:
        return {"status": "ok", "count": 0}

    from channel_service import CHANNEL_TYPE_COEXISTENCE, get_channel

    count = 0
    skipped_coex = 0
    for contact in contacts:
        cid = contact["id"]
        # Filtro coexistence: se canal e coexistence cujo dono e exatamente
        # o operador que estamos esvaziando, manter o vinculo.
        ch_id = contact.get("channel_id")
        if ch_id is not None:
            ch = get_channel(ch_id)
            if (
                ch
                and ch.get("channel_type") == CHANNEL_TYPE_COEXISTENCE
                and int(ch.get("owner_user_id") or 0) == int(from_user_id)
            ):
                skipped_coex += 1
                continue
        if action == "return_to_bot":
            return_contact_to_bot(cid, current_user["id"])
            insert_transfer_system_message(cid, f"Devolvido ao bot (reatribuicao em lote) por {current_user['display_name']}", current_user["id"])
        elif action == "transfer" and to_user_id:
            to_user = get_user_by_id(to_user_id)
            assign_wa_contact(cid, to_user_id, (to_user or {}).get("department_id"), current_user["id"], reason="Reatribuicao em lote", summary=f"Reatribuido de operador {from_user_id}")
            insert_transfer_system_message(cid, f"Reatribuido para {(to_user or {}).get('display_name', '?')} por {current_user['display_name']} (lote)", current_user["id"])
        count += 1

    log_audit(current_user["id"], "BULK_REASSIGN", f"from={from_user_id} action={action} to={to_user_id} count={count} skipped_coex={skipped_coex}")
    return {"status": "ok", "count": count, "skipped_coex": skipped_coex}


@app.get("/api/operators")
async def list_operators(current_user: dict = Depends(get_current_user)):
    users = get_all_users()
    return [
        {
            "id": u["id"], "username": u.get("username", ""), "display_name": u["display_name"],
            "department_name": u.get("department_name", ""),
            "department_id": u.get("department_id"),
            "avatar_path": u.get("avatar_path", ""),
            "role": u.get("role", "operador"),
            "email": u.get("email", ""),
            "firebase_uid": u.get("firebase_uid", ""),
            "coex_authorized": u.get("coex_authorized", 0),
            "coex_phone": u.get("coex_phone", ""),
        }
        for u in users if u.get("is_active")
    ]


async def broadcast_to_operators(message: dict):
    # Mantido como no-op porque o fluxo legado de notificacao via WebSocket
    # foi removido. O webhook ainda pode chamar este callback sem efeito colateral.
    return None


# -- API: Google Chat (comunicacao interna) --


class GcSendRequest(BaseModel):
    conversation_id: int
    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Mensagem vazia")
        if len(v) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"Excede {MAX_MESSAGE_LENGTH} caracteres")
        return v


@app.get("/api/gc/conversations")
async def gc_list_conversations(current_user: dict = Depends(get_current_user)):
    """Lista todas as conversas do Google Chat."""
    if not FEATURE_GOOGLE_CHAT:
        raise HTTPException(status_code=404, detail="Google Chat desabilitado")
    conversations = get_all_gc_conversations()
    return {"conversations": conversations}


@app.get("/api/gc/messages/{conversation_id}")
async def gc_get_messages(
    conversation_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    """Retorna mensagens de uma conversa."""
    if not FEATURE_GOOGLE_CHAT:
        raise HTTPException(status_code=404, detail="Google Chat desabilitado")
    messages = get_gc_messages(conversation_id, limit=limit, offset=offset)
    return {"messages": messages}


@app.post("/api/gc/send")
async def gc_send_message(body: GcSendRequest, current_user: dict = Depends(get_current_user)):
    """Envia mensagem do CRM para o Google Chat."""
    if not FEATURE_GOOGLE_CHAT:
        raise HTTPException(status_code=404, detail="Google Chat desabilitado")

    from database import get_gc_conversation
    conversation = get_gc_conversation(body.conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversa nao encontrada")

    space_id = conversation.get("space_id")
    if not space_id:
        raise HTTPException(status_code=400, detail="Space ID nao configurado")

    # Enviar via Google Chat API
    from google_chat import send_text_message
    result = send_text_message(space_id, body.content)
    if not result:
        raise HTTPException(status_code=502, detail="Falha ao enviar para Google Chat")

    # Salvar no Firestore
    sender_email = current_user.get("email", "")
    sender_name = current_user.get("display_name", "")
    message_id = save_gc_message(
        conversation_id=body.conversation_id,
        gchat_message_id=result.get("gchat_message_id", ""),
        sender_email=sender_email,
        sender_name=sender_name,
        msg_type="text",
        content=body.content,
        source="crm",
        create_time=result.get("create_time", ""),
    )

    log_audit(current_user["id"], "gc_send_message", f"conv={body.conversation_id} msg_id={message_id}")
    return {"message_id": message_id, "gchat_message_id": result.get("gchat_message_id", "")}


@app.post("/api/gc/mark-read/{conversation_id}")
async def gc_mark_read(conversation_id: int, current_user: dict = Depends(get_current_user)):
    """Marca conversa como lida para o usuario atual."""
    if not FEATURE_GOOGLE_CHAT:
        raise HTTPException(status_code=404, detail="Google Chat desabilitado")
    user_identifier = current_user.get("email", str(current_user["id"]))
    mark_gc_conversation_read(conversation_id, user_identifier)
    return {"status": "ok"}


@app.get("/api/gc/spaces")
async def gc_list_spaces(current_user: dict = Depends(get_current_user)):
    """Lista spaces disponiveis no Google Chat."""
    if not FEATURE_GOOGLE_CHAT:
        raise HTTPException(status_code=404, detail="Google Chat desabilitado")
    from google_chat import list_spaces
    spaces = list_spaces()
    return {"spaces": spaces}


@app.post("/webhooks/google-chat")
async def webhook_google_chat(request: Request):
    """Recebe eventos do Google Chat (mensagens, bot adicionado/removido)."""
    if not FEATURE_GOOGLE_CHAT:
        return JSONResponse(status_code=404, content={"error": "Google Chat desabilitado"})

    auth_header = request.headers.get("Authorization", "")
    is_valid = await validate_google_chat_token(auth_header)
    if not is_valid:
        logger.warning("Webhook Google Chat: token invalido")
        return JSONResponse(status_code=403, content={"error": "Token invalido"})

    event = await request.json()
    response = await process_google_chat_event(event)
    return response or {}


# -- API: Dashboard de Auditoria --


@app.get("/api/admin/dashboard/summary")
async def dashboard_summary(
    date_from: str = Query(""),
    date_to: str = Query(""),
    current_user: dict = Depends(get_current_user),
):
    """Retorna metricas agregadas para o periodo."""
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor")
    if not date_from:
        date_from = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    if not date_to:
        date_to = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    metrics = get_audit_metrics(date_from, date_to)

    # Separar global vs per-operator
    global_metrics = [m for m in metrics if "_" not in str(m.get("doc_id", ""))[11:]]
    operator_metrics = [m for m in metrics if "_" in str(m.get("doc_id", ""))[11:]]

    # Agregar global
    total_inbound = sum(int(m.get("total_messages_inbound") or 0) for m in global_metrics)
    total_outbound = sum(int(m.get("total_messages_outbound") or 0) for m in global_metrics)
    total_leads = sum(int(m.get("total_leads_received") or 0) for m in global_metrics)
    total_assumed = sum(int(m.get("total_leads_assumed") or 0) for m in global_metrics)

    # Agregar por operador
    operators_agg: dict[str, dict] = {}
    for m in operator_metrics:
        doc_id = str(m.get("doc_id", ""))
        parts = doc_id.split("_", 1)
        if len(parts) < 2:
            continue
        uid = parts[1]
        if uid not in operators_agg:
            operators_agg[uid] = {"user_id": int(uid) if uid.isdigit() else uid, "inbound": 0, "outbound": 0, "leads_assumed": 0, "first_activity": None, "last_activity": None}
        agg = operators_agg[uid]
        agg["inbound"] += int(m.get("total_messages_inbound") or 0)
        agg["outbound"] += int(m.get("total_messages_outbound") or 0)
        agg["leads_assumed"] += int(m.get("total_leads_assumed") or 0)
        fa = m.get("first_activity_at")
        la = m.get("last_activity_at")
        if fa and (not agg["first_activity"] or fa < agg["first_activity"]):
            agg["first_activity"] = fa
        if la and (not agg["last_activity"] or la > agg["last_activity"]):
            agg["last_activity"] = la

    # Peak chart: agregar messages_by_half_hour
    peak: dict[str, int] = {}
    for m in global_metrics:
        half_hours = m.get("messages_by_half_hour") or {}
        if isinstance(half_hours, dict):
            for slot, count in half_hours.items():
                peak[slot] = peak.get(slot, 0) + int(count or 0)

    return {
        "date_from": date_from,
        "date_to": date_to,
        "total_messages_inbound": total_inbound,
        "total_messages_outbound": total_outbound,
        "total_messages": total_inbound + total_outbound,
        "total_leads_received": total_leads,
        "total_leads_assumed": total_assumed,
        "operators": list(operators_agg.values()),
        "peak_chart": peak,
    }


@app.get("/api/admin/dashboard/ratings")
async def dashboard_ratings(
    date_from: str = Query(""),
    date_to: str = Query(""),
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor")
    ratings = get_all_ratings(date_from or None, date_to or None)
    return {"ratings": ratings}


# -- API: Usage mensal per-tenant (Fase 2.10.4) --


@app.get("/api/wa/usage/current-month")
async def wa_usage_current_month(current_user: dict = Depends(get_current_user)):
    """Retorna usage do mes corrente pro tenant atual (informativo).

    Estrutura: { month, templates_sent: {marketing,utility,authentication,unknown},
    free_form_sent, inbound_received, media_uploaded_bytes }.
    Acessivel a admin/supervisor — visibilidade pra cruzar com fatura Meta.
    """
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor")
    return get_monthly_usage()


@app.get("/api/wa/usage/history")
async def wa_usage_history(
    months: int = Query(3, ge=1, le=24),
    current_user: dict = Depends(get_current_user),
):
    """Retorna ultimos N meses de usage do tenant atual (mes corrente primeiro)."""
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor")
    return {"months": get_usage_history(months)}


@app.get("/api/wa/usage/{year_month}")
async def wa_usage_specific_month(
    year_month: str,
    current_user: dict = Depends(get_current_user),
):
    """Retorna usage de um mes especifico (formato YYYY-MM)."""
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor")
    if len(year_month) != 7 or year_month[4] != "-":
        raise HTTPException(status_code=400, detail="Formato esperado: YYYY-MM")
    try:
        y, m = year_month.split("-")
        if not (1 <= int(m) <= 12) or not (2020 <= int(y) <= 2099):
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato esperado: YYYY-MM")
    return get_monthly_usage(year_month)


# -- API: Export --


@app.get("/api/admin/export")
async def export_data(
    date_from: str = Query(""),
    date_to: str = Query(""),
    format: str = Query("json"),
    current_user: dict = Depends(get_current_user),
):
    """Exporta conversas e contatos em JSON ou CSV."""
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor")

    contacts = get_all_wa_contacts(include_archived=True)
    # Filtrar por data se especificado
    if date_from:
        contacts = [c for c in contacts if str(c.get("first_seen_at", ""))[:10] >= date_from]
    if date_to:
        contacts = [c for c in contacts if str(c.get("first_seen_at", ""))[:10] <= date_to]

    if format == "csv":
        import csv
        import io
        output = io.StringIO()
        if contacts:
            fields = ["id", "wa_id", "display_name", "phone_formatted", "qualification",
                       "assigned_to", "assigned_name", "department_name", "channel_id",
                       "source_channel_type", "rating", "first_seen_at", "last_message_at",
                       "notes"]
            writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for c in contacts:
                writer.writerow(c)
        csv_content = output.getvalue()
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=export_{date_from}_{date_to}.csv"},
        )
    else:
        return {"contacts": contacts, "count": len(contacts), "date_from": date_from, "date_to": date_to}


# -- API: Embedded Signup (Coexistence) --


@app.get("/api/admin/embedded-signup/config")
async def embedded_signup_config(current_user: dict = Depends(get_current_user)):
    """Retorna configuracao necessaria para o frontend iniciar o Embedded Signup."""
    if current_user.get("role") not in ("admin", "supervisor") and not current_user.get("coex_authorized"):
        raise HTTPException(status_code=403, detail="Sem permissao para o signup. Peca a um admin para autorizar seu numero coexistence.")
    missing: list[str] = []
    if not META_APP_ID:
        missing.append("META_APP_ID")
    if not META_APP_SECRET:
        missing.append("META_APP_SECRET")
    if not EMBEDDED_SIGNUP_CONFIG_ID:
        missing.append("EMBEDDED_SIGNUP_CONFIG_ID")
    if missing:
        raise HTTPException(
            status_code=503,
            detail=f"Configuracao de Embedded Signup incompleta: {', '.join(missing)}",
        )
    return {
        "app_id": META_APP_ID,
        "config_id": EMBEDDED_SIGNUP_CONFIG_ID,
        "graph_api_version": GRAPH_API_VERSION,
    }


class EmbeddedSignupExchange(BaseModel):
    code: str
    channel_type: str = "coexistence"
    owner_user_id: int | None = None
    label: str = ""
    default_department_id: int | None = None


def _meta_error_detail(resp: httpx.Response) -> str:
    """Extrai mensagem de erro estruturada de uma resposta da Graph API."""
    try:
        data = resp.json()
    except Exception:
        return resp.text[:500] or f"HTTP {resp.status_code}"
    err = data.get("error") or {}
    msg = err.get("message") or err.get("error_user_msg") or ""
    code = err.get("code")
    subcode = err.get("error_subcode")
    trace = err.get("fbtrace_id")
    parts = []
    if msg:
        parts.append(msg)
    if code is not None:
        parts.append(f"code={code}")
    if subcode is not None:
        parts.append(f"subcode={subcode}")
    if trace:
        parts.append(f"trace={trace}")
    return " | ".join(parts) or resp.text[:500] or f"HTTP {resp.status_code}"


@app.post("/api/admin/embedded-signup/exchange")
async def embedded_signup_exchange(
    body: EmbeddedSignupExchange,
    current_user: dict = Depends(get_current_user),
):
    """Troca o code do Embedded Signup por token e descobre WABA/Phone IDs."""
    if current_user.get("role") not in ("admin", "supervisor") and not current_user.get("coex_authorized"):
        raise HTTPException(status_code=403, detail="Sem permissao para o signup. Peca a um admin para autorizar seu numero coexistence.")
    if not META_APP_ID or not META_APP_SECRET:
        raise HTTPException(status_code=503, detail="META_APP_ID e META_APP_SECRET sao obrigatorios")

    # 1. Trocar code por access token
    token_url = (
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/oauth/access_token"
        f"?client_id={META_APP_ID}"
        f"&client_secret={META_APP_SECRET}"
        f"&code={body.code}"
    )
    async with httpx.AsyncClient(timeout=20.0) as client:
        token_resp = await client.get(token_url)

    if token_resp.status_code >= 400:
        detail = _meta_error_detail(token_resp)
        logger.error("Embedded Signup token exchange falhou: %s", detail)
        raise HTTPException(status_code=502, detail=f"Erro na troca do code: {detail}")

    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        detail = _meta_error_detail(token_resp)
        logger.error("Embedded Signup token exchange sem access_token: %s", detail)
        raise HTTPException(status_code=502, detail=f"Erro na troca do code: {detail}")

    expires_in_raw = token_data.get("expires_in")
    token_expires_at_iso: str | None = None
    if isinstance(expires_in_raw, (int, float)) and expires_in_raw > 0:
        token_expires_at_iso = (
            datetime.now(timezone.utc) + timedelta(seconds=int(expires_in_raw))
        ).isoformat()
    logger.info(
        "Embedded Signup: token obtido (expires_in=%s)",
        expires_in_raw if expires_in_raw is not None else "n/a",
    )

    # 2. debug_token: descobre WABAs autorizados e valida escopo coexistence
    debug_url = (
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/debug_token"
        f"?input_token={access_token}&access_token={META_APP_ID}|{META_APP_SECRET}"
    )
    async with httpx.AsyncClient(timeout=20.0) as client:
        debug_resp = await client.get(debug_url)

    if debug_resp.status_code >= 400:
        detail = _meta_error_detail(debug_resp)
        logger.error("Embedded Signup debug_token falhou: %s", detail)
        raise HTTPException(status_code=502, detail=f"Erro ao validar token: {detail}")

    debug_data = debug_resp.json()
    granular_scopes = debug_data.get("data", {}).get("granular_scopes", [])

    waba_ids: list[str] = []
    coexistence_scope_present = False
    granted_scope_names: list[str] = []
    for scope in granular_scopes:
        scope_name = scope.get("scope") or ""
        granted_scope_names.append(scope_name)
        if scope_name == "whatsapp_business_management":
            for tid in scope.get("target_ids") or []:
                if tid and tid not in waba_ids:
                    waba_ids.append(str(tid))
        if scope_name == "whatsapp_business_app_onboarding":
            coexistence_scope_present = True

    if not waba_ids:
        logger.warning(
            "Embedded Signup: nenhum WABA nos scopes (granted=%s)",
            ",".join(granted_scope_names) or "<vazio>",
        )
        raise HTTPException(
            status_code=400,
            detail=(
                "Nenhuma conta WhatsApp Business retornada pelo signup. "
                "Confirme que o usuario concedeu acesso a uma WABA."
            ),
        )

    if body.channel_type == "coexistence" and not coexistence_scope_present:
        logger.warning(
            "Embedded Signup: pediu coexistence mas escopo whatsapp_business_app_onboarding ausente (granted=%s)",
            ",".join(granted_scope_names) or "<vazio>",
        )
        # Nao bloqueia (Meta as vezes nao retorna esse scope no debug),
        # mas registra para diagnostico futuro.

    waba_id = waba_ids[0]
    logger.info(
        "Embedded Signup: WABA ID = %s (total descobertos: %d)",
        waba_id, len(waba_ids),
    )

    # 3. Buscar todos os Phone Numbers do WABA, com paginacao
    phone_numbers: list[dict] = []
    next_url: str | None = f"{GRAPH_API_BASE}/{waba_id}/phone_numbers"
    next_params: dict | None = {"limit": 100}
    async with httpx.AsyncClient(timeout=20.0) as client:
        while next_url:
            phones_resp = await client.get(
                next_url,
                params=next_params,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if phones_resp.status_code >= 400:
                detail = _meta_error_detail(phones_resp)
                logger.error("Embedded Signup phone_numbers falhou: %s", detail)
                raise HTTPException(status_code=502, detail=f"Erro ao buscar numeros: {detail}")
            phones_data = phones_resp.json()
            phone_numbers.extend(phones_data.get("data", []) or [])
            paging = phones_data.get("paging") or {}
            next_url = paging.get("next")
            next_params = None  # paging.next ja inclui cursor

    if not phone_numbers:
        logger.warning("Embedded Signup: nenhum numero encontrado no WABA %s", waba_id)
        raise HTTPException(status_code=400, detail="Nenhum numero de telefone encontrado na conta")

    phone_info = phone_numbers[0]
    phone_number_id = phone_info.get("id", "")
    display_phone = phone_info.get("display_phone_number", "")
    verified_name = phone_info.get("verified_name", "")
    quality_rating = phone_info.get("quality_rating", "")
    platform_type = phone_info.get("platform_type", "")
    status = phone_info.get("status", "")
    code_verification_status = phone_info.get("code_verification_status", "")
    messaging_limit_tier = phone_info.get("messaging_limit_tier", "")
    is_official = phone_info.get("is_official_business_account")

    logger.info(
        "Embedded Signup concluido | waba=%s phone_id=%s display=%s status=%s platform=%s tier=%s",
        waba_id, phone_number_id, redact_phone(display_phone), status, platform_type, messaging_limit_tier,
    )

    # 4. Determinar tipo do canal antes de assinar webhook (campos diferem)
    is_coexistence = body.channel_type == "coexistence"
    channel_type = CHANNEL_TYPE_COEXISTENCE if is_coexistence else CHANNEL_TYPE_STANDARD
    is_privileged = current_user.get("role") in ("admin", "supervisor")
    # Operador autorizado so conecta canal COEX do PROPRIO numero: ignora
    # owner_user_id do body (so admin/supervisor atribui canal a outro user) e
    # nao pode criar canal standard.
    if not is_privileged and not is_coexistence:
        raise HTTPException(status_code=403, detail="Operador so pode conectar canal coexistence do proprio numero.")
    if is_coexistence:
        owner_id = body.owner_user_id if (is_privileged and body.owner_user_id) else current_user["id"]
    else:
        owner_id = None
    # Validacao do numero pre-autorizado: se o usuario tem numero coex autorizado
    # pelo admin, o numero conectado no signup TEM que bater (LGPD + politica de
    # numeros corporativos). normalize_br_phone trata o 9o digito BR.
    expected_phone = "".join(ch for ch in str(current_user.get("coex_phone") or "") if ch.isdigit())
    if is_coexistence and expected_phone:
        got_phone = "".join(ch for ch in str(display_phone or "") if ch.isdigit())
        if normalize_br_phone(expected_phone) != normalize_br_phone(got_phone):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Numero conectado (...{got_phone[-4:] or '????'}) difere do autorizado "
                    f"(...{expected_phone[-4:]}). Conecte o numero cadastrado pelo admin."
                ),
            )

    # 5. Registrar webhook do app no WABA com os fields apropriados
    if is_coexistence:
        subscribed_fields = [
            "messages",
            "message_template_status_update",
            "message_template_quality_update",
            "history",
            "smb_message_echoes",
            "smb_app_state_sync",
            "account_update",
        ]
    else:
        subscribed_fields = [
            "messages",
            "message_template_status_update",
            "message_template_quality_update",
            "account_update",
        ]

    subscribe_url = f"{GRAPH_API_BASE}/{waba_id}/subscribed_apps"
    sub_resp = None
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            sub_resp = await client.post(
                subscribe_url,
                headers={"Authorization": f"Bearer {access_token}"},
                json={"subscribed_fields": subscribed_fields},
            )
    except httpx.RequestError as exc:
        # ReadTimeout / ConnectError / etc na Meta sao transitorios e nao
        # devem aborter o signup — o canal eh criado e o admin reinscreve
        # o webhook depois (botao na UI ou rerun do signup).
        logger.warning(
            "Embedded Signup subscribed_apps falhou por erro de rede (%s: %s) "
            "— canal segue criado, admin reassina webhook depois",
            type(exc).__name__, exc,
        )

    webhook_subscribed = False
    if sub_resp is None:
        # Falha de rede — log ja emitido acima, continua com webhook=False
        pass
    elif sub_resp.status_code >= 400:
        sub_detail = _meta_error_detail(sub_resp)
        logger.error("Embedded Signup subscribed_apps falhou: %s", sub_detail)
        # Nao aborta: canal pode ser criado mesmo sem webhook (admin reassina depois)
    else:
        sub_data = sub_resp.json()
        webhook_subscribed = bool(sub_data.get("success", False))
        logger.info(
            "Embedded Signup: webhook subscription = %s | fields=%s",
            webhook_subscribed, ",".join(subscribed_fields),
        )

    # 6. Criar canal no registry
    owner_user = get_user_by_id(owner_id) if owner_id else None
    channel_label = body.label or (
        f"{(owner_user or {}).get('display_name', 'Operador')} - {display_phone}"
        if is_coexistence
        else f"Canal {display_phone}"
    )

    new_channel_id = create_channel(
        channel_type=channel_type,
        label=channel_label,
        waba_id=waba_id,
        phone_number_id=phone_number_id,
        display_phone_number=display_phone,
        access_token=access_token,
        token_expires_at=token_expires_at_iso,
        owner_user_id=owner_id,
        owner_firebase_uid=(owner_user or {}).get("firebase_uid", ""),
        default_department_id=body.default_department_id,
        is_bot_enabled=not is_coexistence,
        platform_type=platform_type,
        is_official_business_account=is_official,
        code_verification_status=code_verification_status,
        messaging_limit_tier=messaging_limit_tier,
        verified_name=verified_name,
        quality_rating=quality_rating,
        webhook_subscribed=webhook_subscribed,
    )

    # 7. Disparar sync de contatos + history (coexistence apenas).
    # Doc Meta: POST /{phone_id}/smb_app_data e necessario pra Meta
    # comecar a entregar webhooks 'smb_app_state_sync' (contatos) e
    # 'history' (mensagens dos ultimos 180 dias). Janela de 24h apos
    # signup, depois disso precisa desligar e refazer signup. Cada sync
    # so pode ser disparado UMA VEZ por signup.
    sync_results: dict[str, dict] = {}
    if is_coexistence:
        smb_data_url = f"{GRAPH_API_BASE}/{phone_number_id}/smb_app_data"
        for sync_type in ("smb_app_state_sync", "history"):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    sync_resp = await client.post(
                        smb_data_url,
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json",
                        },
                        json={"messaging_product": "whatsapp", "sync_type": sync_type},
                    )
                if sync_resp.status_code >= 400:
                    detail = _meta_error_detail(sync_resp)
                    logger.error(
                        "Embedded Signup smb_app_data %s falhou: %s",
                        sync_type, detail,
                    )
                    sync_results[sync_type] = {"ok": False, "error": detail}
                else:
                    body_json = sync_resp.json()
                    sync_results[sync_type] = {
                        "ok": True,
                        "request_id": body_json.get("request_id", ""),
                    }
                    logger.info(
                        "Embedded Signup smb_app_data %s OK | request_id=%s",
                        sync_type, body_json.get("request_id", ""),
                    )
            except httpx.RequestError as exc:
                # Erro de rede nao aborta signup. Admin pode redisparar
                # via POST /api/admin/channels/{id}/trigger-coex-sync
                # dentro da janela de 24h.
                logger.warning(
                    "Embedded Signup smb_app_data %s erro de rede (%s: %s) — "
                    "canal segue criado, admin redispara via endpoint",
                    sync_type, type(exc).__name__, exc,
                )
                sync_results[sync_type] = {"ok": False, "error": str(exc)}

    log_audit(
        current_user["id"],
        "EMBEDDED_SIGNUP",
        f"WABA={waba_id} Phone={phone_number_id} ({display_phone}) status={status} channel_id={new_channel_id} syncs={list(sync_results.keys())}",
    )

    return {
        "status": "ok",
        "channel_id": new_channel_id,
        "channel_type": channel_type,
        "access_token": access_token,
        "token_expires_at": token_expires_at_iso,
        "waba_id": waba_id,
        "all_wabas": waba_ids,
        "phone_number_id": phone_number_id,
        "display_phone_number": display_phone,
        "verified_name": verified_name,
        "quality_rating": quality_rating,
        "platform_type": platform_type,
        "phone_status": status,
        "code_verification_status": code_verification_status,
        "messaging_limit_tier": messaging_limit_tier,
        "is_official_business_account": is_official,
        "webhook_subscribed": webhook_subscribed,
        "subscribed_fields": subscribed_fields,
        "coex_syncs": sync_results,
        "all_phones": [
            {
                "id": p.get("id"),
                "display_phone_number": p.get("display_phone_number"),
                "verified_name": p.get("verified_name"),
                "status": p.get("status"),
                "platform_type": p.get("platform_type"),
            }
            for p in phone_numbers
        ],
    }


# -- Execucao --

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True, log_level="info")
