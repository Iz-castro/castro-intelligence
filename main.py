# -*- coding: utf-8 -*-

import asyncio
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

from config import (
    HOST, PORT, MAX_MESSAGE_LENGTH, BASE_DIR, LOG_FILE, LOG_LEVEL, LOG_TO_FILE,
    FEATURE_AUDIO_TRANSCRIPTION, FEATURE_MESSAGE_STATUS, FEATURE_GOOGLE_CHAT,
    FEATURE_ASSUME_COUNTER,
    WHATSAPP_VERIFY_TOKEN, WHATSAPP_TOKEN,
    WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_WABA_ID, GRAPH_API_BASE, GRAPH_API_VERSION,
    AVATAR_MAX_SIZE_KB, AVATAR_ALLOWED_MIME,
    QUALIFICATION_OPTIONS, ROLE_OPTIONS, TAKEOVER_TIMEOUT_HOURS, ATTENDANCE_AUTOCLOSE_HOURS,
    RATING_TEMPLATE_NAME, RATING_TEMPLATE_LANG, RATING_REASK_DAYS, CLOSE_TEMPLATE_NAME,
    RECEPTION_UNATTENDED_RELEASE_DAYS,
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
    EMBEDDED_SIGNUP_CONFIG_ID_STANDARD, WHATSAPP_SYSTEM_USER_TOKEN,
)
from database import (
    init_database, get_user_by_id, get_user_raw_by_id, get_all_users,
    get_all_wa_contacts, get_wa_conversation,
    mark_wa_conversation_read, mark_wa_conversation_read_by_id, recompute_wa_contact_unread,
    save_wa_message, get_wa_contact,
    log_audit, normalize_br_phone,
    get_all_departments, create_department,
    get_department_by_id, update_department, deactivate_department,
    assign_wa_contact, assign_wa_conversation, get_conversations_by_contact, get_transfer_history,
    assign_orphan_threads_to_lead_owner,
    return_contact_to_bot, return_contact_to_pool, get_contacts_by_assigned_user,
    get_wa_contacts_scoped_for_user, get_wa_contacts_visible_to,
    update_user_avatar, get_user_avatar,
    update_user, deactivate_user, set_coex_authorization,
    get_user_by_email,
    update_wa_contact_qualification, archive_wa_contact, restore_wa_contact,
    update_contact_avatar, insert_transfer_system_message, insert_internal_note, set_attendance_protocol,
    get_daily_attendance, close_daily_attendance, mark_protocol_informed,
    get_current_protocol_id, get_messages_by_protocol,
    get_wa_message_by_id, update_wa_message_transcription,
    create_manual_wa_contact, update_wa_contact_declared_name,
    mark_message_corrected,
    get_wa_conversation_by_id, upsert_wa_conversation,
    set_conversation_takeover_active, clear_conversation_takeover, expire_stale_takeovers,
    close_stale_attendances, set_attendance_status, set_sale_owner,
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
    get_channel_by_id_from_db, get_channel_by_phone_id_from_db, rebind_channel,
    CHANNEL_TYPE_STANDARD, CHANNEL_TYPE_COEXISTENCE,
)
from auth import authenticate_firebase_token, invalidate_auth_cache
from firestore_common import (
    collection_name, document as fs_document, utcnow as fs_utcnow,
)
from rbac import (
    PERMISSION_CATALOG, PERMISSION_KEYS, SEED_PERFIL_IDS,
    can_see_all_tenant, default_perfil_for_role, effective_toggles,
    ensure_permission, get_perfil, has_permission, toggles_beyond_user,
)
from pii_redaction import redact_phone, redact_name
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

# Convencao RBAC (M-B2): endpoints chamam ensure_permission(current_user,
# perm) no corpo — padrao unico em toda a base (dual-check PLANO_RBAC §3.8:
# toggle do perfil decide; perfil/chave ausente cai no seed da role).


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


# Bootstrap de tenant (tenant/setores/admin) vive em tenant_bootstrap.py
# (M-A2): mesma funcao serve o hubloc no startup e o onboarding de tenants
# novos pelo painel super-admin (Cloud Run B).


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
    # Garante o tenant default 'hubloc' (transicao multi-tenant): tenant +
    # setores + admin com claim atomico, tudo em tenants/hubloc/... —
    # idempotente, no-op em boot repetido (M-A2, tenant_bootstrap.py).
    from tenant_bootstrap import bootstrap_tenant
    bootstrap_tenant(
        "hubloc",
        name="Hubloc Imobiliaria",
        plan="professional",
        admin_email=BOOTSTRAP_ADMIN_EMAIL,
        admin_display_name=BOOTSTRAP_ADMIN_DISPLAY_NAME,
        admin_department_name=BOOTSTRAP_ADMIN_DEPARTMENT,
        # Dominio do hubloc explicito (nao derivavel do email founder, que e
        # outlook/gmail publico): reconciliado no boot -> duravel em DR/restore,
        # nao depende do backfill manual via Admin SDK.
        allowed_email_domains=["hubloc.com.br"],
    )
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
        "perfis_acesso": f"{tenants_root}/{tenant_id}/perfis_acesso",
        "wa_contacts": f"{tenants_root}/{tenant_id}/wa_contacts",
        "wa_messages": f"{tenants_root}/{tenant_id}/wa_messages",
        "wa_conversations": f"{tenants_root}/{tenant_id}/wa_conversations",
        "wa_transfer_log": f"{tenants_root}/{tenant_id}/wa_transfer_log",
        "gc_conversations": f"{tenants_root}/{tenant_id}/gc_conversations",
        "gc_messages": f"{tenants_root}/{tenant_id}/gc_messages",
    }
    # M-B2: mapa EFETIVO de toggles (perfil do usuario + fallback de role no
    # dual-check) — o useCan do frontend le daqui e do snapshot do perfil.
    perfil_id = str(current_user.get("perfil_acesso_id") or "") or default_perfil_for_role(current_user.get("role"))
    # Entitlements: plano + modulos derivados (fonte: PLAN_MODULES em codigo).
    # Falha de leitura do tenant NAO derruba a sessao — cai no plano default.
    from tenant_service import get_tenant, modules_for_plan, normalize_plan

    try:
        tenant_doc = get_tenant(tenant_id) or {}
    except Exception as exc:
        logger.warning("session_info: get_tenant(%s) falhou: %s", tenant_id, exc)
        tenant_doc = {}
    tenant_plan = normalize_plan(tenant_doc.get("plan"))
    return {
        "user": current_user,
        "auth_mode": AUTH_MODE,
        "tenant_id": tenant_id,
        "firestore_collections": tenant_collections,
        "perfil": {
            "id": perfil_id,
            "toggles": effective_toggles(current_user),
        },
        "tenant": {
            "id": tenant_id,
            "name": tenant_doc.get("name") or tenant_id,
            "plan": tenant_plan,
            "modules": modules_for_plan(tenant_plan),
        },
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
    ensure_permission(current_user, "gerenciar_usuarios")
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
    # Guard de escalacao (M-B2): criar um admin exige ser admin — supervisor
    # com gerenciar_usuarios nao pode provisionar alguem acima do proprio
    # nivel. (Mudanca consciente: antes o backend nao barrava.)
    if role == "admin" and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Apenas admin pode criar outro admin")
    existing = get_user_by_email(email)
    if existing:
        raise HTTPException(status_code=409, detail="Usuario ja existe")
    # M-A4b: se a conta Firebase do email JA existe, linka uid + claims
    # tenant_id/role no ato (primeiro login ja passa nas rules M-A4) com
    # guard "um email = um tenant". Conta inexistente segue o fluxo atual
    # (doc local; conta e criada no onboarding por senha/console e o claim
    # sincroniza no primeiro login) — lookup-only pra nao quebrar o runbook
    # de operador por senha (conta pre-criada nao teria provider password).
    from tenant_bootstrap import (
        DeactivatedUserError, TenantConflictError, provision_operator,
    )
    try:
        user = provision_operator(
            email,
            display_name=display_name,
            role=role,
            department_id=department_id,
        )
    except TenantConflictError:
        raise HTTPException(status_code=409, detail="Email ja vinculado a outro tenant")
    except DeactivatedUserError:
        raise HTTPException(
            status_code=409,
            detail="Usuario existe mas esta desativado. Reative-o em vez de recriar.",
        )
    if not user:
        raise HTTPException(status_code=500, detail="Falha ao provisionar usuario Firebase")
    log_audit(current_user["id"], "USER_CREATE", f"{email} ({role})")
    # Guarda-corpo SOFT (decisao 2026-07-03): operador com email fora do(s)
    # dominio(s) do tenant e permitido (o claim autoriza, nao o dominio), mas
    # devolvemos um aviso pra UI confirmar "adicionar mesmo assim?". Nao
    # bloqueia — evita botar operador no tenant errado por engano.
    domain_warning = None
    try:
        from tenant_service import get_tenant, normalize_email_domains
        creator_tid = str(current_user.get("tenant_id") or "")
        domains = normalize_email_domains((get_tenant(creator_tid) or {}).get("allowed_email_domains")) if creator_tid else []
        email_domain = email.split("@", 1)[1] if "@" in email else ""
        if domains and email_domain and email_domain not in domains:
            domain_warning = f"Email fora dos dominios do tenant ({', '.join(domains)})."
    except Exception as exc:
        logger.warning("Guarda-corpo de dominio falhou (nao-fatal): %s", exc)
    return {"status": "ok", "user_id": user["id"], "domain_warning": domain_warning}


@app.put("/api/admin/users/{user_id}")
async def admin_update_user(user_id: int, request: Request, current_user: dict = Depends(get_current_user)):
    ensure_permission(current_user, "gerenciar_usuarios")
    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    body = await request.json()
    display_name = body.get("display_name")
    department_id = body.get("department_id")
    role = body.get("role")
    perfil_acesso_id = body.get("perfil_acesso_id")
    if role and role not in ROLE_OPTIONS:
        raise HTTPException(status_code=400, detail=f"Cargo invalido. Opcoes: {', '.join(ROLE_OPTIONS)}")
    # -- Guards de escalacao (M-B2; mudanca consciente — antes nao barrava) --
    my_tid = str(current_user.get("tenant_id") or "") or "hubloc"
    role_changing = bool(role) and role != target.get("role")
    perfil_changing = perfil_acesso_id is not None and perfil_acesso_id != (target.get("perfil_acesso_id") or "")
    if (role_changing or perfil_changing) and user_id == current_user["id"]:
        raise HTTPException(status_code=403, detail="Nao e permitido alterar o proprio cargo/perfil")
    if (role_changing or perfil_changing) and current_user.get("role") != "admin":
        if target.get("role") == "admin" or role == "admin" or perfil_acesso_id == "perfil_admin":
            raise HTTPException(status_code=403, detail="Apenas admin pode promover/rebaixar admins")
    perfil_doc = None
    if perfil_acesso_id is not None:
        if not perfil_acesso_id:
            raise HTTPException(status_code=400, detail="Perfil de acesso invalido")
        perfil_doc = get_perfil(my_tid, perfil_acesso_id)
        # Seeds valem mesmo sem doc (tenant pre-seed): o dual-check resolve
        # pelo fallback da role ate o bootstrap semear.
        if not perfil_doc and perfil_acesso_id not in SEED_PERFIL_IDS:
            raise HTTPException(status_code=400, detail="Perfil de acesso inexistente")
    if perfil_changing and current_user.get("role") != "admin" and perfil_doc:
        # Anti-amplificacao por NIVEL, nao por id literal: um perfil custom
        # clonado do admin (ou com qualquer toggle que o caller nao tem)
        # nao pode ser concedido por quem nao e admin.
        if str(perfil_doc.get("role_equivalente") or "") == "admin":
            raise HTTPException(status_code=403, detail="Apenas admin pode atribuir perfis de nivel admin")
        beyond = toggles_beyond_user(perfil_doc.get("toggles") or {}, current_user)
        if beyond:
            raise HTTPException(
                status_code=403,
                detail="Perfil concede permissoes que voce nao possui: " + ", ".join(beyond),
            )
    update_user(user_id, display_name=display_name, department_id=department_id, role=role,
                perfil_acesso_id=perfil_acesso_id)
    if role_changing or perfil_changing:
        # Audit RBAC (§3.9): governanca de acesso a dados pessoais.
        log_audit(
            current_user["id"], "permission_change",
            f"scope=user id={user_id} role: {target.get('role')} -> {role or target.get('role')} | "
            f"perfil: {target.get('perfil_acesso_id') or '(derivado)'} -> "
            f"{perfil_acesso_id if perfil_acesso_id is not None else '(derivado da role)'}",
        )
    firebase_uid = (target.get("firebase_uid") or "").strip()
    if firebase_uid:
        # Cache de auth guarda role/setor antigos ate o TTL — invalida pra
        # mudanca valer na proxima request do backend.
        invalidate_auth_cache(firebase_uid)
    if (role or perfil_changing) and firebase_uid:
        # M-A4b (role stale): o claim role alimenta as Firestore rules
        # (isPrivilegedInTenant usa tokenRole) e o _resolve_tenant_id do auth
        # early-returna com claim presente (nunca ressincroniza). Sem reemitir
        # aqui, um admin rebaixado manteria leitura privilegiada via client
        # SDK. Decide reemissao pela divergencia do CLAIM (nao do doc) — assim
        # re-salvar o mesmo cargo funciona como RETRY se um set anterior
        # falhou. Reemite + revoga refresh (ID token corrente expira em ~1h).
        try:
            from firebase_admin_client import (
                get_user_claims_strict, revoke_refresh_tokens, set_tenant_claims,
            )
            claims = get_user_claims_strict(firebase_uid)
            claim_tid = str(claims.get("tenant_id") or "")
            claim_role = str(claims.get("role") or "")
            claim_perfil = str(claims.get("perfil_acesso_id") or "")
            desired_role = role or target.get("role") or "operador"
            desired_perfil = (perfil_acesso_id if perfil_acesso_id is not None
                              else str(target.get("perfil_acesso_id") or "")
                              or default_perfil_for_role(desired_role))
            # Claim perfil ausente + desejado == seed derivado da role NAO e
            # divergencia real (estado de todo usuario pre-M-B2): reemitir/
            # revogar aqui deslogaria o operador na primeira edicao inocua.
            perfil_stale = claim_perfil != desired_perfil and (
                bool(claim_perfil) or desired_perfil != default_perfil_for_role(desired_role)
            )
            if claim_tid and claim_tid != my_tid:
                # Nao deveria ocorrer (lookup e tenant-scoped); nunca
                # re-apontar claim de outro tenant como efeito colateral.
                logger.error(
                    "USER_UPDATE: claim de outro tenant (%s) p/ user id=%s — "
                    "claim NAO alterado", claim_tid, user_id,
                )
            elif claim_role != desired_role or perfil_stale or not claim_tid:
                # Claim desatualizado (ou ausente) -> reemite. Se ja bate,
                # nao faz nada (idempotente).
                if set_tenant_claims(firebase_uid, claim_tid or my_tid, role=desired_role,
                                     base_claims=claims, perfil_acesso_id=desired_perfil):
                    revoke_refresh_tokens(firebase_uid)
                else:
                    logger.warning(
                        "USER_UPDATE: set_tenant_claims falhou p/ id=%s — "
                        "re-salvar o mesmo cargo re-tenta", user_id,
                    )
        except Exception as exc:
            logger.warning(
                "USER_UPDATE: claim role nao reemitido p/ id=%s (%s) — "
                "re-salvar o mesmo cargo re-tenta", user_id, exc,
            )
    log_audit(current_user["id"], "USER_UPDATE", f"id={user_id}")
    return {"status": "ok"}


@app.delete("/api/admin/users/{user_id}")
async def admin_deactivate_user(user_id: int, current_user: dict = Depends(get_current_user)):
    ensure_permission(current_user, "desativar_usuarios")
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Nao pode desativar a si mesmo")
    # Lookup RAW (sem filtro is_active): permite RE-EXECUTAR o offboarding em
    # um usuario ja desativado (retry idempotente) em vez de 404 — importante
    # se um clear/revoke anterior falhou (blip do Admin SDK).
    target = get_user_raw_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    already_inactive = not target.get("is_active", 1)
    deactivate_user(user_id)  # set is_active=0 (idempotente)
    # M-A4b (offboarding): as rules M-A4 autorizam por claim tenant_id, e as
    # subcolecoes gateadas so por ownsTenant nao checam operator_profile —
    # sem limpar o claim, o desativado re-loga (revoke nao impede novo login)
    # e segue lendo PII do tenant via client SDK. Limpa claim + revoga
    # refresh (ID token corrente expira em ate ~1h) + derruba o cache de
    # auth (que retorna antes do check de is_active). O guard anti-
    # ressurreicao em auth.py fecha o re-login com AUTO_PROVISION.
    firebase_uid = (target.get("firebase_uid") or "").strip()
    claims_cleared = True
    if firebase_uid:
        from firebase_admin_client import clear_tenant_claims, revoke_refresh_tokens
        claims_cleared = clear_tenant_claims(firebase_uid)
        revoke_refresh_tokens(firebase_uid)
        invalidate_auth_cache(firebase_uid)
        if not claims_cleared:
            logger.warning(
                "USER_DEACTIVATE: claims NAO limpos p/ id=%s (blip do Admin "
                "SDK) — repetir o DELETE re-tenta o clear", user_id,
            )
    log_audit(
        current_user["id"], "USER_DEACTIVATE",
        f"id={user_id} ({target.get('display_name')}) "
        f"claims_cleared={claims_cleared} already_inactive={already_inactive}",
    )
    return {"status": "ok", "claims_cleared": claims_cleared}


@app.post("/api/admin/users/{user_id}/coex")
async def admin_authorize_coex(user_id: int, request: Request, current_user: dict = Depends(get_current_user)):
    """Autoriza um usuario (tipicamente operador) a fazer o proprio Embedded
    Signup coexistence. O admin/supervisor pre-cadastra o numero corporativo
    que sera conectado: isso libera a tela 'WhatsApp Coexistence' pra esse
    operador e o /exchange exige que o numero conectado bata com o autorizado.
    """
    ensure_permission(current_user, "autorizar_coex_para_operador")
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
    ensure_permission(current_user, "autorizar_coex_para_operador")
    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    set_coex_authorization(user_id, "", authorized=False)
    log_audit(current_user["id"], "COEX_REVOKE", f"user={user_id}")
    return {"status": "ok", "user_id": user_id}


@app.get("/api/admin/roles")
async def list_roles(current_user: dict = Depends(get_current_user)):
    return {"roles": ROLE_OPTIONS}


# -- API: Admin - Perfis de acesso (RBAC dinamico, M-B2) --

def _perfil_toggle_diff(before: dict, after: dict) -> str:
    """Diff compacto so das chaves alteradas, p/ audit legivel (§3.9)."""
    b = (before or {}).get("toggles") or {}
    a = (after or {}).get("toggles") or {}
    changes = [f"{k}: {bool(b.get(k))} -> {bool(a.get(k))}"
               for k in PERMISSION_KEYS if bool(b.get(k)) != bool(a.get(k))]
    return "; ".join(changes) or "(sem mudanca de toggle)"


@app.get("/api/admin/perfis-acesso")
async def list_perfis_acesso(current_user: dict = Depends(get_current_user)):
    """Lista perfis do tenant + catalogo de toggles (grupo/rotulo p/ UI).

    Alem do gestor de perfis, a tela de usuarios (gerenciar_usuarios) usa a
    listagem no dropdown de atribuicao de perfil.
    """
    if not (has_permission(current_user, "gerenciar_perfis_acesso")
            or has_permission(current_user, "gerenciar_usuarios")):
        raise HTTPException(status_code=403, detail="Permissao negada (gerenciar_perfis_acesso)")
    from rbac import list_perfis
    return {
        "perfis": list_perfis(str(current_user.get("tenant_id") or "") or "hubloc"),
        "catalogo": [
            {"grupo": grupo, "chave": chave, "rotulo": rotulo}
            for grupo, chave, rotulo in PERMISSION_CATALOG
        ],
    }


@app.post("/api/admin/perfis-acesso")
async def create_perfil_acesso(request: Request, current_user: dict = Depends(get_current_user)):
    ensure_permission(current_user, "gerenciar_perfis_acesso")
    body = await request.json()
    from rbac import SEED_PERFIS, create_perfil, sanitize_toggles
    # Anti-amplificacao: quem cria perfil nao pode ligar toggle que nao tem
    # (base + overrides). Admin (tudo true) nunca e limitado.
    base_id = body.get("base_perfil_id") or "perfil_operador"
    candidate = dict(SEED_PERFIS.get(base_id, {}).get("toggles") or {})
    candidate.update(sanitize_toggles(body.get("toggles") or {}))
    beyond = toggles_beyond_user(candidate, current_user)
    if beyond:
        raise HTTPException(
            status_code=403,
            detail="Voce nao pode conceder permissoes que nao possui: " + ", ".join(beyond),
        )
    try:
        doc = create_perfil(
            str(current_user.get("tenant_id") or "") or "hubloc",
            nome=body.get("nome", ""),
            descricao=body.get("descricao", ""),
            toggles=body.get("toggles") or {},
            base_perfil_id=body.get("base_perfil_id"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    log_audit(
        current_user["id"], "permission_change",
        f"scope=perfil op=create id={doc['id']} nome={doc['nome']}",
    )
    return {"status": "ok", "perfil": doc}


@app.put("/api/admin/perfis-acesso/{perfil_id}")
async def update_perfil_acesso(perfil_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    ensure_permission(current_user, "gerenciar_perfis_acesso")
    body = await request.json()
    from rbac import update_perfil
    try:
        result = update_perfil(
            str(current_user.get("tenant_id") or "") or "hubloc",
            perfil_id,
            nome=body.get("nome"),
            descricao=body.get("descricao"),
            toggles=body.get("toggles"),
            editor_user=current_user,
        )
    except PermissionError as exc:
        # Lock do perfil_admin (§3.3) e anti-amplificacao ("nao concede o
        # que nao tem"): UI desabilita, backend reforca.
        raise HTTPException(status_code=403, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="Perfil nao encontrado")
    before, after = result
    log_audit(
        current_user["id"], "permission_change",
        f"scope=perfil op=update id={perfil_id} | {_perfil_toggle_diff(before, after)}",
    )
    return {"status": "ok"}


@app.delete("/api/admin/perfis-acesso/{perfil_id}")
async def delete_perfil_acesso(perfil_id: str, current_user: dict = Depends(get_current_user)):
    ensure_permission(current_user, "gerenciar_perfis_acesso")
    # Guard de uso: perfil referenciado por usuario ATIVO (explicito ou
    # derivado da role) nao pode sumir — o dual-check cairia no fallback da
    # role silenciosamente, mudando permissoes sem acao explicita.
    in_use = [
        u["id"] for u in get_all_users()
        if u.get("is_active", 1)
        and (u.get("perfil_acesso_id") or default_perfil_for_role(u.get("role"))) == perfil_id
    ]
    if in_use:
        raise HTTPException(
            status_code=409,
            detail=f"Perfil em uso por {len(in_use)} usuario(s) ativo(s). Reatribua antes de excluir.",
        )
    from rbac import delete_perfil
    try:
        removed = delete_perfil(str(current_user.get("tenant_id") or "") or "hubloc", perfil_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    if not removed:
        raise HTTPException(status_code=404, detail="Perfil nao encontrado")
    log_audit(current_user["id"], "permission_change", f"scope=perfil op=delete id={perfil_id}")
    return {"status": "ok"}


# -- API: Configuracoes do sistema --

@app.get("/api/settings/system")
async def get_settings_system(current_user: dict = Depends(get_current_user)):
    return get_system_settings()


@app.put("/api/settings/system")
async def update_settings_system(request: Request, current_user: dict = Depends(get_current_user)):
    ensure_permission(current_user, "gerenciar_config_sistema")
    body = await request.json()
    # tags_global SO pelo endpoint proprio (/api/settings/tags-global, toggle
    # gerenciar_tags_globais). Revisao B: aceitar aqui (1) contornava o
    # toggle e (2) o frontend manda o objeto INTEIRO — salvar sons com estado
    # stale apagava/revertia o registry que um supervisor editou no meio.
    if isinstance(body, dict):
        body.pop("tags_global", None)
    try:
        result = save_system_settings(body)
    except ValueError as exc:  # mensagem rapida vazia/atalho repetido
        raise HTTPException(status_code=400, detail=str(exc))
    log_audit(current_user["id"], "SYSTEM_SETTINGS_UPDATE", str(body))
    return result


@app.get("/api/settings/user")
async def get_settings_user(current_user: dict = Depends(get_current_user)):
    return get_user_settings(current_user["id"])


@app.put("/api/settings/user")
async def update_settings_user(request: Request, current_user: dict = Depends(get_current_user)):
    body = await request.json()
    try:
        result = save_user_settings(current_user["id"], body)
    except ValueError as exc:  # mensagem rapida vazia/atalho repetido/limite
        raise HTTPException(status_code=400, detail=str(exc))
    # So as CHAVES no audit (revisao B): o body agora carrega tags pessoais,
    # cujo conteudo pode ser dado de saude — nao vai em claro pro log.
    _keys = sorted(body.keys()) if isinstance(body, dict) else []
    log_audit(current_user["id"], "USER_SETTINGS_UPDATE", f"keys={_keys}")
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
    ensure_permission(current_user, "gerenciar_config_sistema")
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
    # Escopado por operador (admin/supervisor veem tudo). Alinha o fallback
    # de polling com as Firestore rules do snapshot: operador comum nao
    # recebe a agenda inteira do tenant (custo de leitura + isolamento LGPD).
    contacts = get_wa_contacts_visible_to(
        current_user.get("id"),
        current_user.get("department_id"),
        see_all=can_see_all_tenant(current_user),
    )
    for c in contacts:
        c["unread"] = int(c.get("unread_count", 0))
    return {"contacts": contacts}


@app.get("/api/wa/contacts/all")
async def wa_contacts_all(
    q: str | None = Query(default=None, description="Busca por nome ou telefone"),
    limit: int = Query(default=5000, ge=1, le=10000),
    count_only: int = Query(default=0, description="1 = retorna so o total via aggregate count (~7 reads em vez de full scan)"),
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

    count_only=1: retorna apenas {"total": N} via aggregate count().
    O header da sidebar so exibe o numero, mas carregava a agenda
    INTEIRA (~6.5k docs) a cada page-load de cada usuario — era o maior
    dreno de leitura do Firestore (~250k reads/dia; ver
    docs/INVESTIGACAO_READS_FIRESTORE_2026-07.md). Aggregate custa
    1 read por 1000 docs. O filtro q e ignorado nesse modo.
    """
    from firestore_common import collection as fs_coll
    privileged = can_see_all_tenant(current_user)

    if count_only:
        if privileged:
            # Total do tenant menos arquivados (is_archived e sempre int
            # 0/1 — archive_contact grava 1). Docs sem o campo nao casam
            # o where — exatamente o comportamento do filtro do full scan.
            res_all = fs_coll("wa_contacts").count(alias="n").get()
            res_arch = fs_coll("wa_contacts").where("is_archived", "==", 1).count(alias="n").get()
            total = int(res_all[0][0].value) - int(res_arch[0][0].value)
        else:
            from database import count_wa_contacts_scoped_for_user
            total = count_wa_contacts_scoped_for_user(current_user.get("id"))
        return {"contacts": [], "total": total, "returned": 0}

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
    # Isolamento LGPD ENTRE operadores: operador comum so abre conversa de
    # contato proprio, do pool sem dono, ou de thread que ja atende
    # (admin/supervisor irrestrito). Espelha GET /api/wa/contact/{id} e fecha o
    # IDOR horizontal — sem isto, qualquer operador abriria (e o upsert
    # auto-atribuiria) o lead de outro operador por contact_id enumeravel.
    _require_contact_access(contact, current_user)
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
    # Modo Recepcao (ADR 0010): abrir do picker NAO atribui a thread — o
    # pool compartilhado fica sem dono ate alguem assumir de fato.
    # Legacy: a thread so e auto-atribuida a quem abre se o LEAD ja e dele
    # (thread do proprio lead, mesma heranca que save_wa_message faz). Lead da
    # POOL (sem dono) aberto pelo picker fica orfao ate o "Assumir atendimento"
    # explicito — antes o open carimbava a thread no operador SEM tocar o
    # contato (nem RBAC, nem 409, nem audit/system message): o lead sumia de
    # "Novos" de todo mundo, o colega que assumia ficava com contato=A e
    # thread=B, e B seguia vendo a conversa inteira (fix 2026-08-19).
    from database import is_reception_mode
    try:
        _my_lead = contact.get("assigned_to") is not None and int(contact.get("assigned_to")) == int(current_user["id"])
    except (TypeError, ValueError):
        _my_lead = False
    conversation_id = upsert_wa_conversation(
        contact_id=int(contact_id),
        wa_id=wa_id,
        channel_id=int(channel_id),
        source_channel_type=str(contact.get("source_channel_type", "") or ""),
        phone_number_id=str(contact.get("phone_number_id", "") or ""),
        auto_assign_user_id=current_user["id"] if (_my_lead and not is_reception_mode()) else None,
        direction_for_unread=None,
    )
    log_audit(
        current_user["id"],
        "WA_CONVERSATION_OPEN",
        f"contact_id={contact_id} channel_id={channel_id} conv_id={conversation_id}",
    )
    # Devolve o dono REAL: upsert_wa_conversation so auto-atribui se a conversa
    # nao tinha dono; se ja era de outro operador (coex multi-canal), o dono
    # original permanece. O front usa isso pra nao forjar "assigned_to=eu" na
    # entrada otimista do picker.
    conv = get_wa_conversation_by_id(conversation_id) or {}
    # Lead self-service do bot CX aberto pelo picker: se a thread ficou deste
    # operador (auto-assign de thread sem dono), emite o resumo/temperatura
    # coletados pela IA (idempotente por marcador; nao-fatal). Compara int com
    # int — assigned_to pode vir como str de docs legados.
    try:
        _conv_owner = int(conv.get("assigned_to")) if conv.get("assigned_to") is not None else None
    except (TypeError, ValueError):
        _conv_owner = None
    if _conv_owner is not None and _conv_owner == int(current_user["id"]):
        try:
            from bot_service import apply_cx_snapshot_on_assume, mark_human_active
            mark_human_active(int(contact_id))
            apply_cx_snapshot_on_assume(
                int(contact_id), contact, conversation_id=conversation_id,
            )
        except Exception:
            logger.exception("[CONVERSATION-OPEN] resumo do bot CX falhou | contato=%s", contact_id)
    return {
        "conversation_id": conversation_id,
        "contact_id": int(contact_id),
        "channel_id": int(channel_id),
        "assigned_to": conv.get("assigned_to"),
        "assigned_to_uid": conv.get("assigned_to_uid") or "",
    }


def _require_contact_access(contact: dict, current_user: dict):
    """Isolamento LGPD: operador comum so acessa contato proprio (assigned_to
    == ele), do pool/fila (sem dono), OU de uma thread que ELE atende
    (coex multi-canal: o mesmo cliente vive em varios numeros — o Dono do
    Lead pode ser outra operadora enquanto a thread e dele; sem o nome do
    contato a conversa dele vira fantasma na sidebar). admin/supervisor
    acessam tudo. Espelha get_wa_contacts_scoped_for_user (DB) e
    canSeeContactScoped (rules); o caso thread-propria nao e expressavel em
    rules — coberto via REST (lazy-load extraContacts do frontend).
    Levanta 403 caso contrario. contact pode ser {} (trata como sem acesso)."""
    if can_see_all_tenant(current_user):
        return
    if contact and contact.get("assigned_to") == current_user.get("id"):
        return
    if contact and not contact.get("assigned_to_uid"):  # pool: '' ou None
        return
    if contact:
        # Thread atribuida ao operador para este contato? (2 igualdades —
        # zigzag merge, sem indice composto novo.)
        try:
            from firestore_common import collection as _fs_coll
            _uid = str(current_user.get("firebase_uid") or "")
            if _uid:
                _q = (_fs_coll("wa_conversations")
                      .where("contact_id", "==", contact.get("id"))
                      .where("assigned_to_uid", "==", _uid)
                      .limit(1))
                if any(True for _ in _q.stream()):
                    return
        except Exception as exc:
            logger.warning("_require_contact_access thread-check falhou: %s", exc)
    raise HTTPException(status_code=403, detail="Acesso negado: contato de outro operador")


@app.get("/api/wa/conversations")
async def wa_conversations(
    limit: int = Query(default=500, ge=1, le=2000),
    current_user: dict = Depends(get_current_user),
):
    """Retorna lista de conversations enriquecidas (Fase 3 multi-canal).

    Cada conversation representa uma thread (channel_id + wa_id).
    O mesmo wa_id em mais de um canal aparece como entradas distintas,
    cada uma com seu proprio assigned_to/unread/last_message_at.
    Dados do cliente (nome, telefone formatado, notas, qualificacao,
    rating) sao mesclados via join in-memory com wa_contacts.

    Paginado server-side (mais recentes primeiro): a colecao cresceu (~3k+)
    e o stream integral custava a colecao inteira por tick de polling.
    Backup (last_message_at antigo) vem por query propria p/ privilegiado,
    espelhando os snapshot targets do frontend.
    """
    from firestore_common import collection as fs_coll
    from channel_service import get_channel
    from google.cloud.firestore_v1 import Query as FsQuery
    convs_raw = []
    _seen_conv_ids = set()
    _streams = [fs_coll("wa_conversations").order_by(
        "last_message_at", direction=FsQuery.DESCENDING).limit(limit).stream()]
    if can_see_all_tenant(current_user):
        _streams.append(fs_coll("wa_conversations").where("is_backup", "==", True).stream())
    for _stream in _streams:
        for snap in _stream:
            data = snap.to_dict() or {}
            if "id" not in data:
                data["id"] = snap.id
            if data["id"] in _seen_conv_ids:
                continue
            _seen_conv_ids.add(data["id"])
            convs_raw.append(data)

    # Cache de contatos por id (evita N queries). Operador comum: SO contatos
    # visiveis a ele (proprios + pool sem dono); conversas cujo contato nao e
    # visivel sao descartadas pelo `if not contact: continue` abaixo
    # (isolamento LGPD, espelha o snapshot). admin/supervisor: todos.
    _convs_privileged = can_see_all_tenant(current_user)
    contacts_by_id = {}
    _contacts_src = get_wa_contacts_visible_to(
        current_user.get("id"), current_user.get("department_id"),
        see_all=_convs_privileged,
    )
    for c in _contacts_src:
        contacts_by_id[c["id"]] = c

    enriched = []
    for conv in convs_raw:
        # Backup: nunca exposto a operador comum (defesa-em-profundidade; o
        # sentinela "__backup__" ja barra via contato nao-visivel). Privilegiado
        # recebe — a aba Backup do frontend filtra is_backup.
        if conv.get("is_backup") and not _convs_privileged:
            continue
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
            # Canal inativo/removido (fora do cache so-ativos) => cai no valor
            # denormalizado na propria conversation (Fase 2: apresentacao
            # honesta), senao a thread perde o numero/label na UI em polling.
            "channel_label": (channel.get("label", "") if channel else conv.get("channel_label", "")),
            "channel_type": (channel.get("channel_type", "") if channel else (conv.get("channel_type") or conv.get("source_channel_type") or "")),
            "channel_phone_number": (channel.get("display_phone_number", "") if channel else conv.get("channel_phone_number", "")),
            "channel_active": bool(channel),
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
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    _require_contact_access(contact, current_user)  # LGPD: so dono/pool/admin
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
    # LGPD: so o dono do contato (ou pool/admin) pode transcrever o audio.
    _require_contact_access(get_wa_contact(msg.get("contact_id")) or {}, current_user)
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


def _reception_send_allowed(conversation: dict, channel: dict | None) -> bool:
    """Modo Recepcao (ADR 0010) libera envio nesta thread orfa?

    Coexistence fica FORA do modo recepcao (o auto-assign coex e semantico:
    dono fisico do numero). Doc legado sem source_channel_type cai no
    channel_type denormalizado da PROPRIA conversation (_ch_fields) e, por
    ultimo, no canal resolvido pelo caller — callers sem canal (ex.:
    set-attendance) ficam cobertos sem read extra. A config so e lida quando
    o ramo orfao e atingido (1 read por envio orfao).
    """
    ch_type = str(conversation.get("source_channel_type") or "")
    if not ch_type:
        ch_type = str(conversation.get("channel_type") or "")
    if not ch_type and channel:
        ch_type = str(channel.get("channel_type") or "")
    if ch_type == CHANNEL_TYPE_COEXISTENCE:
        return False
    from database import is_reception_mode
    return is_reception_mode()


def _check_conv_send_permission(conversation: dict, current_user: dict, contact: dict | None = None, channel: dict | None = None):
    """Permission check baseado na conversation (Fase 2C).

    Bloqueia envio se a thread esta atribuida a outro operador. Sem
    atribuicao, exige role admin/supervisor (mesma regra anterior, mas
    por thread em vez de por contato — admite que o mesmo cliente em
    canais diferentes seja atendido por gente diferente).

    Excecao (Opcao A): o DONO DO LEAD (contact.assigned_to) sempre pode
    responder em qualquer thread do proprio contato, mesmo que a thread
    viva no numero de outro operador (canal coex diferente) e esteja em
    takeover 'pending'/'active'. Cenario: lead transferido para o teste1,
    mas a conversa real esta no numero do Izael. Ao responder, o dono
    assume de fato -> zera o takeover (some o prompt 'assuma' do handler).
    """
    lead_owner = (contact or {}).get("assigned_to")
    if lead_owner is not None and lead_owner == current_user["id"]:
        # O toggle amplo (qualquer thread) engloba o restrito: quem pode
        # co-pilotar qualquer thread nao pode ficar 403 justo nas proprias.
        if not has_permission(current_user, "enviar_mensagem_qualquer_thread"):
            ensure_permission(current_user, "enviar_mensagem_propria_thread")
        if conversation.get("takeover_status") in ("pending", "active"):
            try:
                clear_conversation_takeover(conversation["id"])
            except Exception as exc:
                logger.warning(
                    "Falha ao limpar takeover da conversa %s: %s",
                    conversation.get("id"), exc,
                )
        return

    # Modo 2 (co-pilotagem): admin/supervisor pode enviar em QUALQUER thread.
    # Quando nao e o dono do atendimento, e intervencao de supervisao -> retorna
    # "intervention" e o caller assina o texto ([Supervisao - nome]:).
    is_manager = has_permission(current_user, "enviar_mensagem_qualquer_thread")
    assigned = conversation.get("assigned_to")
    if is_manager:
        if assigned and assigned != current_user["id"]:
            return "intervention"
        return None
    # --- operadores comuns: regras estritas ---
    # RBAC: toggle de envio na propria thread (perfil "read-only" desliga).
    ensure_permission(current_user, "enviar_mensagem_propria_thread")
    # Takeover 'pending' (coex): o handler precisa assumir antes de responder.
    if conversation.get("takeover_status") == "pending":
        raise HTTPException(status_code=403, detail="Assuma o atendimento temporario antes de responder")
    if assigned and assigned != current_user["id"]:
        raise HTTPException(status_code=403, detail="Atendimento atribuido a outro operador")
    if not assigned:
        # Modo Recepcao (ADR 0010): pool compartilhada por tenant — operador
        # comum responde thread SEM dono sem assumir; a thread segue orfa e a
        # autoria fica na mensagem (sender_user_id/sent_by_name).
        # So vale pra POOL de verdade: thread lateral orfa de um LEAD com
        # dono (outro operador) fica 403, espelhando o escopo de leitura
        # (_require_contact_access — quem nao pode LER nao pode escrever).
        if not (contact or {}).get("assigned_to") and _reception_send_allowed(conversation, channel):
            # Contato ainda em fluxo de bot: silencia o motor (CX le
            # human_active) E carimba bot_completed=True — engajamento
            # humano real tira o contato do funil e faz a thread orfa
            # APARECER na aba Recepcao de todos (o filtro exige
            # bot_completed; sem isso o retorno aberto pelo picker ficava
            # invisivel — canario #4). O release re-arma o bot no proximo
            # fechamento. Best-effort, mesmo padrao do clear de takeover.
            if contact and not contact.get("bot_completed"):
                try:
                    from bot_service import mark_human_active
                    from database import mark_contact_bot_done
                    mark_human_active(int(contact["id"]))
                    mark_contact_bot_done(int(contact["id"]))
                except Exception as exc:
                    logger.warning(
                        "reception: silenciar bot falhou p/ contato %s: %s",
                        contact.get("id"), exc,
                    )
            return None
        raise HTTPException(status_code=403, detail="Assuma o atendimento antes de enviar mensagem")
    return None


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
    _check_conv_send_permission(conv, current_user, contact, channel=channel)
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
            sent_by_name=str(current_user.get("display_name") or ""),
            channel_owner_user_id=(channel or {}).get("owner_user_id"),
            **reply_fields,
        )
        log_audit(current_user["id"], "WA_SEND_LOCATION", f"Para {wa_id}: {body.latitude},{body.longitude}")
        return {"status": "sent", "wa_message_id": wa_msg_id}

    error_msg = result.get("error", {}).get("message", "Erro desconhecido")
    raise HTTPException(status_code=502, detail=error_msg)


def _maybe_credit_assume_counter(contact: dict, operator_id: int):
    """Incrementa o contador do operador se esta e a primeira resposta apos assumir.

    Roda mesmo com FEATURE_ASSUME_COUNTER desligada: quita flags/contadores
    pendentes de antes do desligamento (senao religar bloqueia por divida velha).
    Sem divida antiga vira no-op — o assume nao marca mais pendencia.
    """
    if contact.get("assume_pending_response") and contact.get("assigned_to") == operator_id:
        clear_contact_pending_response(contact["id"])
        increment_assume_counter(operator_id)


@app.post("/api/wa/send")
async def wa_send(body: WaSendRequest, current_user: dict = Depends(get_current_user)):
    conv, contact, channel = _resolve_send_target(body.conversation_id, body.contact_id)
    token, phone_id, api_base = _resolve_channel_creds_by_id(
        channel["id"] if channel else conv.get("channel_id")
    )
    send_mode = _check_conv_send_permission(conv, current_user, contact, channel=channel)
    _check_24h_window(contact)
    reply_fields = _build_reply_fields(contact["id"], body.reply_to_message_id, body.reply_to_preview, body.reply_to_sender_name)
    reply_context = _build_reply_context(contact["id"], body.reply_to_message_id)

    # Modo 2 (co-pilotagem): intervencao de supervisao -> assina o texto.
    content = body.content
    if send_mode == "intervention":
        _sup_name = (current_user.get("display_name") or "Supervisao").split()[0]
        content = f"[Supervisao - {_sup_name}]: {content}"

    wa_id = _wa_target(contact["wa_id"])
    url = f"{api_base}/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": wa_id, "type": "text", "text": {"body": content, "preview_url": True}, **reply_context}

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        result = resp.json()

    if resp.status_code == 200:
        wa_msg_id = result.get("messages", [{}])[0].get("id", "")
        save_wa_message(
            wa_message_id=wa_msg_id, contact_id=contact["id"], direction="outbound",
            msg_type="text", content=content, status="sent",
            timestamp_wa=datetime.now(timezone.utc).isoformat(), operator_id=current_user["id"],
            channel_id=channel["id"] if channel else conv.get("channel_id"),
            conversation_id=conv["id"],
            sender_user_id=current_user["id"],
            sent_by_name=str(current_user.get("display_name") or ""),
            channel_owner_user_id=(channel or {}).get("owner_user_id"),
            **reply_fields,
        )
        _maybe_credit_assume_counter(contact, current_user["id"])
        log_audit(current_user["id"], "WA_SEND", f"Para {wa_id}: {content[:80]}")
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
    _check_conv_send_permission(conv, current_user, contact, channel=channel)
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
        sent_by_name=str(current_user.get("display_name") or ""),
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
    _check_conv_send_permission(conv, current_user, contact, channel=channel)
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
        sent_by_name=str(current_user.get("display_name") or ""),
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
            # Meta oscila com 500/erro transitorio neste endpoint (visto em
            # 2026-06-12). Retry curto antes de desistir — sem ele a UI mostra
            # "nenhum template" para uma WABA que TEM templates aprovados.
            resp = None
            for _attempt in range(3):
                resp = await client.get(next_url, params=next_params, headers=headers)
                if resp.status_code < 500:
                    break
                await asyncio.sleep(1.5 * (_attempt + 1))
            if resp is None or resp.status_code >= 400:
                try:
                    err = resp.json().get("error", {}).get("message", resp.text[:300]) if resp is not None else "sem resposta"
                except Exception:
                    err = resp.text[:300] if resp is not None else "sem resposta"
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
    ensure_permission(current_user, "enviar_template")
    _check_conv_send_permission(conv, current_user, contact, channel=channel)
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
            sent_by_name=str(current_user.get("display_name") or ""),
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


# ---------------------------------------------------------------------------
# Reabertura automatica (template de inatividade)
# ---------------------------------------------------------------------------

# Nome/idioma do template de reabertura, configuraveis por env (default = o
# template utility atual). {{1}} = primeiro nome do cliente, {{2}} = data da
# ultima conversa. A resposta do cliente (Retomar/Encerrar) e tratada em
# webhook._handle_reopen_button.
REOPEN_TEMPLATE_NAME = os.getenv("REOPEN_TEMPLATE_NAME", "atualizao_de_solicitao")
REOPEN_TEMPLATE_LANG = os.getenv("REOPEN_TEMPLATE_LANG", "pt_BR")


class WaReopenRequest(BaseModel):
    # Nome/idioma do template enviado pelo frontend (que ja sabe qual o
    # operador escolheu). Ausentes -> usa os defaults de env. Evita acoplar
    # o nome exato (que a Meta gera sem acentos, ex.: atualizao_de_solicitao).
    template_name: str | None = None
    language: str | None = None


def _reopen_first_name(contact: dict) -> str:
    """{{1}}: primeiro nome do cliente. Prioriza o profile name do WhatsApp,
    cai em declared_name/display_name e, por fim, 'cliente'."""
    name = (
        str((contact or {}).get("whatsapp_profile_name") or "").strip()
        or str((contact or {}).get("declared_name") or "").strip()
        or str((contact or {}).get("display_name") or "").strip()
    )
    return name.split()[0] if name else "cliente"


def _reopen_last_conv_date(conv: dict, contact: dict) -> str:
    """{{2}}: data da ultima conversa em DD/MM/AAAA (BRT). Usa o
    last_message_at da thread aberta (ja em maos, sem query extra) com
    fallback no contato. So formata data — nenhum search/protocolo."""
    raw = (
        (conv or {}).get("last_message_at")
        or (contact or {}).get("last_message_at")
        or (contact or {}).get("last_inbound_at")
    )
    dt = None
    if raw:
        try:
            dt = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw))
        except (ValueError, TypeError):
            dt = None
    if dt is None:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y")


@app.post("/api/wa/conversation/{conversation_id}/reopen")
async def wa_reopen_conversation(
    conversation_id: str,
    body: WaReopenRequest | None = None,
    current_user: dict = Depends(get_current_user),
):
    """Reabre um atendimento enviando o template de reabertura com {{1}} e
    {{2}} preenchidos automaticamente (primeiro nome do cliente + data da
    ultima conversa). Reusa /send-template (guard WABA + billing + persist).
    Nome/idioma do template vem do frontend (ou env default)."""
    conv, contact, channel = _resolve_send_target(conversation_id, None)
    _check_conv_send_permission(conv, current_user, contact, channel=channel)

    template_name = (body.template_name if body else None) or REOPEN_TEMPLATE_NAME
    language = (body.language if body else None) or REOPEN_TEMPLATE_LANG

    nome = _reopen_first_name(contact)
    data = _reopen_last_conv_date(conv, contact)
    # Introspecta o template REAL em vez de hardcodar 2 parametros: a versao
    # aprovada no console pode ter so {{1}} (=data, caso atual) ou {{1}}/{{2}}
    # (desenho original). Hardcodar causava #132000 (param count mismatch).
    # Semantica por posicao decidida pelo EXEMPLO do template (data dd/mm/aaaa
    # -> preenche a data; senao nome na 1a posicao, data nas demais).
    import re as _re
    params: list[dict] = []
    tpl = None
    if channel:
        try:
            tpl_data = await _load_approved_templates_for_channel(channel)
            tpl = next((t for t in tpl_data.get("templates", [])
                        if t.get("name") == template_name and t.get("language") == language), None)
        except Exception as exc:
            logger.warning("reopen: introspeccao de template falhou (%s); usando 2 params legados", exc)
    if tpl:
        body_comp = next((c for c in (tpl.get("components") or [])
                          if str(c.get("type", "")).upper() == "BODY"), None) or {}
        n_params = len(set(_re.findall(r"\{\{(\d+)\}\}", str(body_comp.get("text") or ""))))
        _ex_rows = ((body_comp.get("example") or {}).get("body_text") or [])
        examples = _ex_rows[0] if _ex_rows else []
        _date_re = _re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$")
        for i in range(n_params):
            ex = str(examples[i]).strip() if i < len(examples) else ""
            if _date_re.match(ex):
                params.append({"type": "text", "text": data})
            else:
                params.append({"type": "text", "text": nome if i == 0 else data})
    else:
        params = [
            {"type": "text", "text": nome},
            {"type": "text", "text": data},
        ]
    components = [{"type": "body", "parameters": params}] if params else None
    send_body = WaSendTemplateRequest(
        conversation_id=conversation_id,
        template_name=template_name,
        language=language,
        components=components,
        template_category="utility",
    )
    result = await wa_send_template(body=send_body, current_user=current_user)
    log_audit(current_user["id"], "WA_REOPEN_SENT", f"conv={conversation_id} template={template_name} nome={nome} data={data}")
    out = result if isinstance(result, dict) else {"status": "sent"}
    return {**out, "rendered": {"nome": nome, "data": data}}


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
    # Mesmo gate de thread dos demais envios (era o unico caminho de texto
    # sem ele); retorno "intervention" descartado como nos outros callers.
    _check_conv_send_permission(conv, current_user, contact, channel=channel)
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
        sent_by_name=str(current_user.get("display_name") or ""),
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
    ensure_permission(current_user, "adicionar_contato_manual")
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

    allow_override = has_permission(current_user, "editar_dono_lead")
    # ADR 0010: o picker NAO pode ser assuncao disfarcada — em reception o
    # contato nasce/reabre no pool; perfil sem assumir_atendimento idem.
    from database import is_reception_mode
    _auto_assume = (has_permission(current_user, "assumir_atendimento")
                    and not is_reception_mode())
    contact_id, error = create_manual_wa_contact(
        declared_name=body.declared_name,
        wa_id=wa_id,
        channel_id=channel_id,
        user_id=current_user["id"],
        allow_admin_override=allow_override,
        auto_assume=_auto_assume,
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
    _require_contact_access(contact, current_user)  # LGPD: so dono/pool/admin
    ensure_permission(current_user, "editar_declared_name")
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
    _require_contact_access(contact, current_user)  # LGPD: so dono/pool/admin
    ensure_permission(current_user, "qualificar_lead")
    # Reforma 2026-09: "novo" = nunca teve interacao humana; lead ja promovido
    # nao regride por save do painel. Sem esta guarda, form semeado ANTES da
    # promocao automatica (A2) e salvo depois gravava "novo" de volta e
    # disparava nova promocao com nota duplicada (revisao adversarial).
    _kept = ""
    if (qualification == "novo"
            and str(contact.get("qualification") or "novo") != "novo"):
        _kept = str(contact.get("qualification"))
        qualification = ""  # mantem a atual; notas seguem salvas normalmente
    update_wa_contact_qualification(contact_id, qualification, notes)
    _effective = qualification or _kept or str(contact.get("qualification") or "novo")
    log_audit(current_user["id"], "CONTACT_QUALIFY",
              f"Contato {contact_id}: {_effective}" + (" (downgrade p/ novo ignorado)" if _kept else ""))

    # qualification_effective: o valor que VALE apos o save — o frontend
    # patcha com a verdade do servidor (sem isto, o guard acima fazia a UI
    # mostrar "novo" salvo com sucesso enquanto o servidor mantinha
    # em_atendimento — revisao adversarial 2026-09-01).
    result = {"status": "ok", "qualification_effective": _effective}

    # Ao marcar como convertido: gravar quem converteu. O pedido de avaliacao
    # NAO dispara mais aqui — desde o recibo v2 (2026-09) ele vai junto do
    # protocolo no FECHAMENTO do atendimento (_close_daily_and_send_protocol),
    # com carimbo pos-envio e captura por botao (fim do digito engolido que
    # gerou o falso positivo do contato 193).
    if qualification == "convertido":

        fs_document("wa_contacts", contact_id).set({
            "converted_by_user_id": current_user["id"],
        }, merge=True)

    return result


def _register_personal_tags(current_user, label_map, slugs):
    """Frente B: tag DIGITADA como nova vira tag PESSOAL do operador
    (criacao on-the-fly — PO 2026-09-02). `label_map` {slug: rotulo} vem do
    frontend e contem SO o que o usuario digitou de novo nesta acao —
    revisao B: registrar tudo que estava aplicado adotava como "minhas" as
    tags de colegas a cada re-save da lista. Best-effort: falha aqui nunca
    bloqueia a aplicacao no lead."""
    try:
        if not isinstance(label_map, dict) or not label_map:
            return
        from database import (
            get_system_settings, get_user_settings, save_user_settings,
            normalize_tag_slug,
        )
        known = {t.get("slug") for t in (get_system_settings().get("tags_global") or [])}
        personal = list(get_user_settings(current_user["id"]).get("tags") or [])
        known.update(t.get("slug") for t in personal)
        slug_set = set(slugs)
        novos = []
        for raw_slug, raw_label in label_map.items():
            s = normalize_tag_slug(raw_slug)
            if s and s in slug_set and s not in known:
                novos.append({"slug": s, "label": str(raw_label or "").strip()[:60] or s})
                known.add(s)
        if not novos:
            return
        if len(personal) + len(novos) > 100:
            logger.info("tags pessoais no limite (100) p/ user %s — novas nao registradas",
                        current_user.get("id"))
            return
        save_user_settings(current_user["id"], {"tags": personal + novos})
    except Exception as exc:
        logger.warning("registro de tag pessoal falhou (nao-fatal): %s", exc)


@app.put("/api/wa/contact/{contact_id}/tags")
async def wa_set_contact_tags(contact_id: int, request: Request, current_user: dict = Depends(get_current_user)):
    """Frente B: substitui as tags do lead. body: {tags: [str]}.

    Qualquer operador com acesso ao lead (LGPD via _require_contact_access) —
    aplicar tag e parte do atendimento, sem toggle proprio. Slugs
    normalizados no write (licao do legado crm_tags); tag inedita vira
    pessoal do operador."""
    body = await request.json()
    raw_tags = body.get("tags")
    from database import clean_lead_tags, update_wa_contact_tags
    try:
        slugs = clean_lead_tags(raw_tags)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    _require_contact_access(contact, current_user)  # LGPD: so dono/pool/admin
    update_wa_contact_tags(contact_id, slugs)
    _register_personal_tags(current_user, body.get("tag_labels"), slugs)
    log_audit(current_user["id"], "CONTACT_TAGS", f"Contato {contact_id}: {len(slugs)} tag(s)")
    return {"status": "ok", "tags": slugs}


@app.put("/api/settings/tags-global")
async def save_tags_global_settings(request: Request, current_user: dict = Depends(get_current_user)):
    """Frente B: registry de tags GLOBAIS do tenant. Toggle proprio
    (gerenciar_tags_globais, seed ON p/ supervisor e admin — PO 2026-09-02);
    nao reusa gerenciar_config_sistema, que e so-admin por seed."""
    ensure_permission(current_user, "gerenciar_tags_globais")
    body = await request.json()
    from database import save_system_settings as _save_sys
    try:
        result = _save_sys({"tags_global": body.get("tags_global")})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    log_audit(current_user["id"], "TAGS_GLOBAL_UPDATE",
              f"{len(result.get('tags_global') or [])} tag(s)")
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
    _require_contact_access(contact, current_user)  # LGPD: so dono/pool/admin
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
    # Autorizacao (IDOR horizontal): conversation_id e deterministico
    # ("{channel_id}__{wa_id}"), entao qualquer usuario do tenant poderia zerar
    # o nao-lido da thread de outro operador. Atalhos baratos primeiro (thread
    # minha / pool / takeover meu); senao a regra geral do contato (dono, pool,
    # thread propria, privilegiado).
    contact_id = conv.get("contact_id")
    contact = get_wa_contact(int(contact_id)) if contact_id is not None else None
    _uid = str(current_user.get("firebase_uid") or "")
    _conv_uid = str(conv.get("assigned_to_uid") or "")
    _thread_mine = bool(_uid) and _conv_uid == _uid
    _thread_pool = (not _conv_uid) and not conv.get("is_backup")
    try:
        _takeover_mine = conv.get("takeover_handler_user_id") is not None and \
            int(conv.get("takeover_handler_user_id")) == int(current_user["id"])
    except (TypeError, ValueError):
        _takeover_mine = False
    if not (_thread_mine or _thread_pool or _takeover_mine):
        _require_contact_access(contact or {}, current_user)
    if int(conv.get("unread_count", 0) or 0) <= 0:
        # Thread ja lida: rede de seguranca pro contador do CONTATO (drift
        # anterior ao ADR 0011 — so a thread zerava). O estoque antigo e
        # corrigido pelo backfill (scripts/backfill_contact_unread_from_threads.py);
        # o frontend normalmente nem chama aqui com a thread em 0.
        if contact and int(contact.get("unread_count", 0) or 0) > 0:
            recompute_wa_contact_unread(int(contact_id), current=int(contact.get("unread_count", 0) or 0))
        return {"status": "ok", "updated_count": 0}
    updated_count = mark_wa_conversation_read_by_id(
        conversation_id, contact_id=int(contact_id) if contact_id is not None else None,
    )
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
    privileged = has_permission(current_user, "assumir_supervisor")
    if handler and int(handler) != current_user["id"] and not privileged:
        raise HTTPException(status_code=403, detail="Apenas o dono do numero pode assumir este atendimento")
    if not privileged:
        # RBAC: dono do numero coex assumindo a propria thread.
        ensure_permission(current_user, "assumir_coex_proprio")
    set_conversation_takeover_active(conversation_id, current_user["id"])
    # Lead self-service do bot CX: quem assume temporariamente tambem precisa
    # do resumo/temperatura do que a IA coletou. Idempotente por marcador
    # (nao descarta o snapshot — o bot pode seguir coletando). Nao-fatal.
    # human_active silencia o bot: takeover assume a THREAD, nao o Lead, entao
    # o gate por contato do webhook nao pegaria e o bot responderia por cima.
    try:
        from bot_service import apply_cx_snapshot_on_assume, mark_human_active
        if conv.get("contact_id") is not None:
            mark_human_active(int(conv["contact_id"]))
            apply_cx_snapshot_on_assume(
                int(conv["contact_id"]), conversation_id=conversation_id,
            )
    except Exception:
        logger.exception("[TAKEOVER] resumo do bot CX falhou | conv=%s", conversation_id)
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
    _require_contact_access(contact, current_user)  # LGPD: so dono/pool/admin
    ensure_permission(current_user, "arquivar_lead")
    archive_wa_contact(contact_id)
    log_audit(current_user["id"], "CONTACT_ARCHIVE", f"Contato {contact_id}")
    return {"status": "ok"}


@app.post("/api/wa/contact/{contact_id}/restore")
async def restore_contact(contact_id: int, current_user: dict = Depends(get_current_user)):
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    _require_contact_access(contact, current_user)  # LGPD: so dono/pool/admin
    ensure_permission(current_user, "arquivar_lead")
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
    ensure_permission(current_user, "gerenciar_departamentos")
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
    ensure_permission(current_user, "gerenciar_departamentos")
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
    ensure_permission(current_user, "desativar_departamentos")
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
    if has_permission(current_user, "gerenciar_canais"):
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


@app.get("/api/admin/conflicts")
async def admin_conflicts(current_user: dict = Depends(get_current_user)):
    """Painel de Conflitos (Fase 3A): Leads com >=2 atendimentos ATIVOS
    atribuidos a operadores DISTINTOS. Read-only, admin/supervisor.

    "Ativo" = conversation com assigned_to setado, channel_active != False e
    last_message_at nos ultimos 30 dias (ainda nao ha attendance_status —
    Fase 4). Conflito = >=2 assignees distintos no mesmo contato. O nome do
    operador e resolvido no frontend (ja tem `operators` em memoria).
    """
    ensure_permission(current_user, "ver_painel_conflitos")
    from firestore_common import collection as fs_coll

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    def _to_dt(v):
        if isinstance(v, datetime):
            return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        if isinstance(v, str) and v:
            try:
                d = datetime.fromisoformat(v)
                return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
            except ValueError:
                return None
        return None

    by_contact: dict = {}
    for snap in fs_coll("wa_conversations").stream():
        c = snap.to_dict() or {}
        if c.get("assigned_to") is None or c.get("channel_active") is False:
            continue
        lm = _to_dt(c.get("last_message_at"))
        if lm is None or lm < cutoff:
            continue
        cid = c.get("contact_id")
        if cid is None:
            continue
        if "id" not in c:
            c["id"] = snap.id
        by_contact.setdefault(cid, []).append((c, lm))

    contacts_by_id = {ct["id"]: ct for ct in get_all_wa_contacts()}
    conflicts = []
    for cid, items in by_contact.items():
        if len({c.get("assigned_to") for c, _ in items}) < 2:
            continue
        contact = contacts_by_id.get(cid) or {}
        items_sorted = sorted(items, key=lambda t: t[1], reverse=True)
        conflicts.append({
            "contact_id": cid,
            "display_name": contact.get("display_name") or contact.get("wa_id") or f"#{cid}",
            "phone_formatted": contact.get("phone_formatted") or "",
            "lead_owner_user_id": contact.get("assigned_to"),
            "conversations": [
                {
                    "conversation_id": c.get("id"),
                    "channel_id": c.get("channel_id"),
                    "channel_label": c.get("channel_label") or "",
                    "channel_phone_number": c.get("channel_phone_number") or "",
                    "channel_active": c.get("channel_active", True),
                    "assigned_to": c.get("assigned_to"),
                    "unread": int(c.get("unread_count", 0) or 0),
                    "last_message_at": lm.isoformat(),
                }
                for c, lm in items_sorted
            ],
        })
    conflicts.sort(key=lambda k: k["conversations"][0]["last_message_at"], reverse=True)
    return {"conflicts": conflicts, "count": len(conflicts)}


@app.get("/api/admin/protocol/{protocol_id}")
async def admin_get_protocol(protocol_id: str, current_user: dict = Depends(get_current_user)):
    """Fase 5A: busca por protocolo (admin/supervisor) — retorna o Atendimento
    diario + timeline de mensagens daquele dia pra aquele Lead (todas as
    threads/canais, pois protocolo e 1 por Lead/dia)."""
    ensure_permission(current_user, "buscar_protocolo")
    atendimento = get_daily_attendance(protocol_id)
    if not atendimento:
        raise HTTPException(status_code=404, detail="Protocolo nao encontrado")
    messages = get_messages_by_protocol(protocol_id)
    contact = get_wa_contact(atendimento.get("contact_id"))
    contact_brief = None
    if contact:
        contact_brief = {
            "id": contact.get("id"),
            "display_name": contact.get("display_name"),
            "phone_formatted": contact.get("phone_formatted"),
            "wa_id": contact.get("wa_id"),
        }
    return {
        "atendimento": atendimento,
        "contact": contact_brief,
        "messages": messages,
        "count": len(messages),
    }


@app.post("/api/admin/channels")
async def create_channel_endpoint(request: Request, current_user: dict = Depends(get_current_user)):
    ensure_permission(current_user, "gerenciar_canais")
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
    ensure_permission(current_user, "gerenciar_canais")
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
    ensure_permission(current_user, "desativar_canais")
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
    ensure_permission(current_user, "gerenciar_canais")
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
    ensure_permission(current_user, "gerenciar_canais")
    from pending_events import list_pending_events
    events = list_pending_events(status=status, limit=limit)
    return {"events": events, "count": len(events)}


@app.post("/api/admin/pending-webhook-events/{event_id}/retry")
async def retry_pending_webhook_event(event_id: str, current_user: dict = Depends(get_current_user)):
    """Re-roda process_webhook_payload com o payload original. Idempotente
    via wa_message_id (save_wa_message detecta duplicata)."""
    ensure_permission(current_user, "gerenciar_canais")
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
async def dismiss_pending_webhook_event(event_id: str, current_user: dict = Depends(get_current_user)):
    """Marca evento como definitivamente falho (nao retentar). Usar quando
    intervencao confirma que o evento nao tem como ser recuperado."""
    ensure_permission(current_user, "desativar_canais")
    from pending_events import mark_event_failed, get_pending_event
    if not get_pending_event(event_id):
        raise HTTPException(status_code=404, detail="Evento nao encontrado")
    mark_event_failed(event_id, error="dismissed_by_admin")
    log_audit(current_user["id"], "PENDING_EVENT_DISMISS", f"id={event_id}")
    return {"status": "dismissed", "id": event_id}


@app.delete("/api/admin/pending-webhook-events/{event_id}")
async def delete_pending_webhook_event_endpoint(event_id: str, current_user: dict = Depends(get_current_user)):
    """Remove evento da fila. Use apos retry confirmado ou eventos sem
    valor de retencao."""
    ensure_permission(current_user, "desativar_canais")
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


@app.post("/api/internal/cron/expire-takeovers")
async def cron_expire_takeovers(request: Request):
    """Cloud Scheduler chama periodicamente. Devolve automaticamente as sessoes
    de takeover 'active' inativas ha mais de TAKEOVER_TIMEOUT_HOURS (inatividade
    total: sem inbound nem outbound). Mesma auth do health-check.

    OBS: enquanto o Cloud Scheduler de prod nao existir, este endpoint so roda
    se chamado manualmente (armado, mas dormente).
    """
    _verify_cron_auth(request)
    from firestore_common import set_tenant_context, reset_tenant_context
    from tenant_service import list_tenants

    summary: list[dict] = []
    total = 0
    for tenant in list_tenants(active_only=True):
        tid = str(tenant.get("id") or "")
        if not tid:
            continue
        token = set_tenant_context(tid)
        try:
            expired = expire_stale_takeovers(TAKEOVER_TIMEOUT_HOURS)
            for e in expired:
                contact_id = e.get("contact_id")
                if contact_id is not None:
                    insert_transfer_system_message(
                        contact_id,
                        "Atendimento temporario devolvido automaticamente por inatividade.",
                        None,
                        advance_recency=False,  # banner automatico nao infla recencia
                    )
                log_audit(None, "TAKEOVER_AUTO_RETURN", f"conv={e.get('conversation_id')} lead_owner={e.get('lead_owner_user_id')}")
            if expired:
                summary.append({"tenant_id": tid, "expired": len(expired)})
            total += len(expired)
            # Fase 4: fecha atendimentos ATRIBUIDOS ociosos por inatividade.
            # Toggle por tenant (auto_close_enabled): desligado, so a valvula
            # de orfaos do Modo Recepcao fecha (PO 2026-09-01).
            from database import is_auto_close_enabled
            closed = close_stale_attendances(
                ATTENDANCE_AUTOCLOSE_HOURS, RECEPTION_UNATTENDED_RELEASE_DAYS,
                inactivity_enabled=is_auto_close_enabled(),
            )
            for c in closed:
                cc_id = c.get("contact_id")
                if cc_id is not None:
                    insert_transfer_system_message(
                        cc_id,
                        "Atendimento fechado automaticamente por inatividade.",
                        None, conversation_id=c.get("conversation_id"),
                        advance_recency=False,  # banner automatico nao infla recencia
                    )
                    # Fase 5A: envia o protocolo ao lead (recibo) se ainda nao
                    # informado e dentro de 24h. Idempotente entre threads do
                    # mesmo dia (a flag protocolo_informado bloqueia duplicata).
                    try:
                        contact_c = get_wa_contact(cc_id)
                        if contact_c:
                            from channel_service import get_channel as _get_channel
                            channel_c = _get_channel(c.get("channel_id")) if c.get("channel_id") else None
                            conv_stub = {
                                "id": c.get("conversation_id"),
                                "contact_id": cc_id,
                                "channel_id": c.get("channel_id"),
                            }
                            await _close_daily_and_send_protocol(
                                contact_c, conv_stub, channel_c, None, "fechado_inatividade",
                            )
                    except Exception as exc:
                        logger.warning(
                            "cron protocol send conv=%s falhou: %s",
                            c.get("conversation_id"), exc,
                        )
                log_audit(None, "ATTENDANCE_AUTO_CLOSE", f"conv={c.get('conversation_id')} assigned={c.get('assigned_to')}")
            if closed:
                summary.append({"tenant_id": tid, "closed": len(closed)})
            total += len(closed)
        except Exception as exc:
            logger.error("expire-takeovers tenant %s falhou: %s", tid, exc)
            summary.append({"tenant_id": tid, "error": str(exc)})
        finally:
            reset_tenant_context(token)

    return {"status": "ok", "timeout_hours": TAKEOVER_TIMEOUT_HOURS, "expired_total": total, "tenants": summary}


@app.get("/api/wa/contact/{contact_id}")
async def wa_contact_detail(contact_id: int, current_user: dict = Depends(get_current_user)):
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    _require_contact_access(contact, current_user)  # LGPD: so dono/pool/admin
    return {"contact": contact}


def _validate_transfer_department(to_department_id):
    """Rejeita transferir/reatribuir para um setor inexistente ou inativo —
    senao a conversa fica carimbada com setor fantasma e some da pool dos
    operadores. None/vazio = sem troca de setor (permitido)."""
    if to_department_id in (None, "", 0, "0"):
        return
    dept = get_department_by_id(to_department_id)
    if not dept or not dept.get("is_active", 1):
        raise HTTPException(status_code=400, detail="Setor destino invalido ou inativo")


@app.post("/api/wa/transfer")
async def wa_transfer(request: Request, current_user: dict = Depends(get_current_user)):
    ensure_permission(current_user, "transferir_atendimento")
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
    # ADR 0010: transferir PRA SI MESMO e assuncao disfarcada (em canal
    # standard also_lead grava dono do lead) — exige o mesmo toggle do
    # /api/wa/assume, senao o perfil "so recepcao" contorna o gate num POST.
    try:
        _self_transfer = int(to_user_id) == int(current_user["id"])
    except (TypeError, ValueError):
        _self_transfer = False
    if _self_transfer:
        ensure_permission(current_user, "assumir_atendimento")
    if not summary:
        raise HTTPException(status_code=400, detail="Resumo do atendimento e obrigatorio")
    _validate_transfer_department(to_department_id)

    conv, contact, channel = _resolve_send_target(conversation_id, contact_id)

    # Fase 2C: transferencia atua na conversation. Quando vier so contact_id
    # (legado), assign_wa_contact espelha em todas as conversations do contato
    # — mas no fluxo novo so transferimos a thread aberta, deixando outras
    # threads coexistence intactas.
    if conversation_id:
        # Canal standard compartilhado: transferir a thread move o Lead junto
        # (also_lead) — o operador destino vira dono do contato E da conversa.
        # Sem isso ele recebe a conversa mas, em snapshot mode, nao consegue
        # ler o contato (rules canSeeContactScoped) nem renderiza-lo, e a
        # conversa fica "fantasma" no Meus dele. Coex mantem Fase 3B
        # (also_lead=False): o mesmo contato pode viver em varios numeros.
        also_lead = bool(channel and str(channel.get("channel_type", "")) == CHANNEL_TYPE_STANDARD)
        result = assign_wa_conversation(conv["id"], to_user_id, to_department_id, current_user["id"], reason, summary, also_lead=also_lead)
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


@app.post("/api/admin/reassign-lead")
async def admin_reassign_lead(request: Request, current_user: dict = Depends(get_current_user)):
    """Fase 3B: reatribui o DONO DO LEAD (contact.assigned_to) SEM mover os
    atendimentos — as threads mantem seus donos (Dono do Atendimento). Acao
    explicita e separada da transferencia de thread. Apenas admin/supervisor.
    """
    ensure_permission(current_user, "editar_dono_lead")
    body = await request.json()
    contact_id = body.get("contact_id")
    to_user_id = body.get("to_user_id")
    to_department_id = body.get("to_department_id")
    reason = body.get("reason", "")
    summary = body.get("summary", "")
    if not contact_id:
        raise HTTPException(status_code=400, detail="contact_id obrigatorio")
    if not to_user_id:
        raise HTTPException(status_code=400, detail="Selecione o operador destino")
    _validate_transfer_department(to_department_id)
    result = assign_wa_contact(contact_id, to_user_id, to_department_id, current_user["id"], reason, summary)
    if result is None:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    # Admin/supervisor trocando o Dono do Lead -> a dona de origem (sale_owner)
    # ACOMPANHA: futuros fechamentos revertem p/ o novo dono.
    set_sale_owner(contact_id, to_user_id)
    # Threads ORFAS do contato acompanham o novo dono (mesmo carimbo explicito
    # do /api/wa/assume; nao move thread que JA tem dono — "reatribui o Lead
    # SEM mover os atendimentos" continua valendo pra thread com dono). Sem
    # isto, num lead multi-canal a thread orfa continuava na pool, legivel por
    # todo operador (mesmo vetor do fix 2026-08-19 pelo caminho do admin).
    try:
        _n_threads = assign_orphan_threads_to_lead_owner(contact_id, to_user_id)
    except Exception:
        _n_threads = -1
        logger.exception("[REASSIGN-LEAD] carimbar threads orfas falhou | contato=%s", contact_id)
    # Reatribuir o Lead reconcilia o takeover das threads: se o novo dono ja e o
    # handler (dono do numero), o conflito acabou -> limpa o takeover stale (senao
    # o PROPRIO dono do Lead veria "Assumir atendimento"). Threads que seguem em
    # conflito so tem o lead_owner_user_id atualizado p/ o banner ficar correto.
    try:
        for cv in get_conversations_by_contact(contact_id):
            if cv.get("takeover_status") not in ("pending", "active"):
                continue
            if cv.get("takeover_handler_user_id") == to_user_id:
                clear_conversation_takeover(cv["id"])
            elif cv.get("lead_owner_user_id") != to_user_id:
                fs_document("wa_conversations", cv["id"]).set({"lead_owner_user_id": to_user_id}, merge=True)
    except Exception as exc:
        logger.warning("reassign-lead: falha ao reconciliar takeover do contato %s: %s", contact_id, exc)
    to_user = get_user_by_id(to_user_id) if to_user_id else None
    to_name = to_user["display_name"] if to_user else "Nenhum"
    insert_transfer_system_message(
        contact_id,
        f"Lead reatribuido para {to_name} por {current_user['display_name']}"
        + (f" | Motivo: {reason}" if reason else ""),
        current_user["id"],
    )
    log_audit(current_user["id"], "WA_REASSIGN_LEAD", f"Contato {contact_id} -> {to_name}: {reason} | threads={_n_threads}")
    await broadcast_to_operators({
        "event": "wa_contact_reassigned",
        "data": {"contact_id": contact_id, "assigned_to": to_user_id, "assigned_name": to_name},
    })
    return {"status": "reassigned", "to_user": to_name}


@app.post("/api/wa/internal-note")
async def wa_internal_note(request: Request, current_user: dict = Depends(get_current_user)):
    """Modo 1 (Sussurro): nota interna na thread — orienta o operador em
    tempo real; o cliente NAO recebe (nada vai pra Meta). Apenas
    admin/supervisor escrevem; operador da thread + managers leem.
    """
    ensure_permission(current_user, "enviar_nota_interna")
    body = await request.json()
    content = (body.get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Nota vazia")
    conv, contact, channel = _resolve_send_target(body.get("conversation_id"), body.get("contact_id"))
    insert_internal_note(
        contact_id=contact["id"],
        content=content,
        sender_user_id=current_user["id"],
        sent_by_name=str(current_user.get("display_name") or ""),
        conversation_id=conv["id"] if conv else None,
        channel_id=(channel["id"] if channel else (conv.get("channel_id") if conv else contact.get("channel_id"))),
    )
    log_audit(current_user["id"], "WA_INTERNAL_NOTE", f"Conv {conv['id'] if conv else contact['id']}")
    return {"status": "ok"}


@app.post("/api/wa/conversation/{conversation_id}/supervisor-takeover")
async def wa_supervisor_takeover(conversation_id: str, current_user: dict = Depends(get_current_user)):
    """Modo 3: supervisor ASSUME o atendimento (thread) — vira Dono do
    Atendimento (nao muda o Dono do Lead). Avisa o lead com texto livre se
    dentro da janela de 24h; fora, assume sem mensagem. Apenas admin/supervisor.
    """
    ensure_permission(current_user, "assumir_supervisor")
    conv, contact, channel = _resolve_send_target(conversation_id, None)
    if not conv:
        raise HTTPException(status_code=404, detail="Atendimento nao encontrado")
    # Assume a thread (thread-only — nao mexe no Dono do Lead, Fase 3B).
    assign_wa_conversation(
        conv["id"], current_user["id"], conv.get("department_id"), current_user["id"],
        reason="Assumido pela supervisao", summary="Supervisor assumiu o atendimento",
    )
    # Lead self-service do bot CX: supervisao que assume a thread recebe o
    # resumo/temperatura coletados pela IA (idempotente por marcador;
    # nao-fatal). human_active silencia o bot (assume thread, nao o Lead).
    try:
        from bot_service import apply_cx_snapshot_on_assume, mark_human_active
        mark_human_active(contact["id"])
        apply_cx_snapshot_on_assume(contact["id"], contact, conversation_id=conv["id"])
    except Exception:
        logger.exception("[SUPERVISOR-TAKEOVER] resumo do bot CX falhou | conv=%s", conv["id"])
    # Aviso ao lead: texto livre so dentro da janela de 24h (fora, sem msg).
    within_24h = False
    li = contact.get("last_inbound_at")
    if li:
        try:
            li_dt = li if isinstance(li, datetime) else datetime.fromisoformat(str(li))
            if li_dt.tzinfo is None:
                li_dt = li_dt.replace(tzinfo=timezone.utc)
            within_24h = (datetime.now(timezone.utc) - li_dt) <= timedelta(hours=24)
        except Exception:
            within_24h = False
    announced = False
    if within_24h:
        try:
            token, phone_id, api_base = _resolve_channel_creds_by_id(channel["id"] if channel else conv.get("channel_id"))
            msg = (
                f"Ola, aqui e {current_user.get('display_name', 'a supervisao')}. "
                "Estou assumindo seu atendimento a partir de agora para agilizar sua solicitacao."
            )
            wa_id = _wa_target(contact["wa_id"])
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{api_base}/{phone_id}/messages",
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    json={"messaging_product": "whatsapp", "to": wa_id, "type": "text", "text": {"body": msg}},
                )
            if resp.status_code == 200:
                wa_msg_id = (resp.json().get("messages", [{}])[0].get("id", ""))
                save_wa_message(
                    wa_message_id=wa_msg_id, contact_id=contact["id"], direction="outbound",
                    msg_type="text", content=msg, status="sent",
                    timestamp_wa=datetime.now(timezone.utc).isoformat(), operator_id=current_user["id"],
                    channel_id=channel["id"] if channel else conv.get("channel_id"),
                    conversation_id=conv["id"], sender_user_id=current_user["id"],
                    sent_by_name=str(current_user.get("display_name") or ""),
                    channel_owner_user_id=(channel or {}).get("owner_user_id"),
                )
                announced = True
        except Exception as exc:
            logger.warning("supervisor-takeover: falha ao avisar lead conv=%s: %s", conv["id"], exc)
    insert_transfer_system_message(
        contact["id"],
        f"Atendimento assumido pela supervisao ({current_user['display_name']}).",
        current_user["id"], conversation_id=conv["id"],
        channel_id=channel["id"] if channel else conv.get("channel_id"),
    )
    log_audit(current_user["id"], "WA_SUPERVISOR_TAKEOVER", f"Conv {conv['id']} (aviso={announced})")
    await broadcast_to_operators({
        "event": "wa_contact_reassigned",
        "data": {"conversation_id": conv["id"], "contact_id": contact["id"], "assigned_to": current_user["id"], "assigned_name": current_user["display_name"]},
    })
    return {"status": "taken_over", "announced": announced}


async def _close_template_available(channel, name) -> bool:
    """True se `name` esta APPROVED no WABA do canal (cache 60s do picker).

    Guard do template SIMPLES de encerramento (CLOSE_TEMPLATE_NAME): evita 1
    chamada Graph fadada a falhar POR FECHAMENTO em tenant que nao criou o
    template — ruido cronico de log. O rating_request nao passa por aqui (ja
    verificado/replicado nos 3 WABAs). Falha de cache/Meta = False (mudo,
    comportamento historico)."""
    try:
        data = await _load_approved_templates_for_channel(channel)
        return any(t.get("name") == name for t in (data or {}).get("templates", []))
    except Exception:
        return False


def _rating_recently_asked(contact) -> bool:
    """True se ja pedimos avaliacao a este lead ha menos de RATING_REASK_DAYS.
    Timestamp ilegivel = nao bloqueia (carimbos legados ja limpos/velhos)."""
    raw = (contact or {}).get("rating_requested_at")
    if not raw:
        return False
    try:
        dt = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt) < timedelta(days=RATING_REASK_DAYS)
    except Exception:
        return False


async def _close_daily_and_send_protocol(contact, conv, channel, current_user, close_status):
    """Fase 5A: no fechamento de uma thread, fecha o Atendimento DIARIO do
    contato e (se ainda nao informado) envia o protocolo ao lead como
    "recibo". O CARIMBO de fechamento roda SEMPRE que o protocolo existe,
    inclusive pra protocolo de dia anterior (fix 3a); o ENVIO segue gateado a
    protocolo do proprio dia. Idempotente — a flag protocolo_informado
    bloqueia reenvio no retorno-zumbi.

    Recibo v2 (2026-09, toggle por tenant rating_request_enabled): a pergunta de avaliacao
    (Ruim/Bom/Excelente) vai JUNTO do protocolo — dentro da janela de 24h
    como mensagem interativa de sessao (gratis), fora dela via template
    aprovado (RATING_TEMPLATE_NAME). Carimbo rating_requested_at SO com envio
    confirmado; re-pergunta bloqueada por RATING_REASK_DAYS. Com a flag
    desligada, comportamento historico: texto do protocolo dentro da janela,
    silencio fora dela.

    close_status: 'fechado_manual' | 'fechado_inatividade'.
    """
    pid = (contact or {}).get("attendance_protocol")
    if not pid:
        return False  # lead nunca teve Atendimento diario espelhado
    atendimento = get_daily_attendance(pid)
    if not atendimento:
        return False
    # Gate de MESMO-DIA vale so pro ENVIO do recibo (a frase diz "de hoje", e
    # o espelho no contato pode apontar protocolo de dia anterior). O CARIMBO
    # de fechamento (fim da funcao) NAO passa por ele: com autoclose de 20h o
    # fechamento quase sempre cruza a meia-noite BR, e o early-return antigo
    # deixava o attendances_daily "aberto" pra sempre, sem fechado_em e sem
    # recibo mesmo dentro da janela (fix 3a, 2026-08-10).
    today_br = datetime.now(timezone(timedelta(hours=-3))).strftime("%Y%m%d")
    is_today = pid.startswith(today_br + "-")
    sender_uid = (current_user or {}).get("id")
    _informado = bool(atendimento.get("protocolo_informado"))
    within_24h = False
    li = contact.get("last_inbound_at")
    if li:
        try:
            li_dt = li if isinstance(li, datetime) else datetime.fromisoformat(str(li))
            if li_dt.tzinfo is None:
                li_dt = li_dt.replace(tzinfo=timezone.utc)
            within_24h = (datetime.now(timezone.utc) - li_dt) <= timedelta(hours=24)
        except Exception:
            within_24h = False
    # So fechamento MANUAL (operador identificado) pergunta avaliacao —
    # cron e fechado_cliente passam current_user=None e ficam mudos fora
    # da janela (PO 2026-09-01; um cron falante viraria template pago em
    # massa toda madrugada). O liga/desliga e POR TENANT (checkbox na aba
    # Sistema — PO 2026-09-02); import local: database reexporta.
    from database import is_rating_request_enabled
    ask_rating = bool(is_rating_request_enabled() and channel
                      and current_user is not None
                      and not _rating_recently_asked(contact))
    # Pernas de envio (revisao adversarial 2026-09-01 — o ramo do template
    # era INALCANCAVEL: protocolo de HOJE implica inbound hoje implica janela
    # aberta):
    # - janela ABERTA: recibo do dia (frase diz "de hoje") — exige protocolo
    #   de hoje e nao-informado.
    # - janela FECHADA: SO o template de avaliacao, que cita o protocolo sem
    #   dizer "hoje" — vale tambem pra protocolo de dia anterior (fechar
    #   conversa fria e exatamente o caso de uso do PO pro template).
    _send_janela = within_24h and is_today and not _informado
    _send_template = (not within_24h) and ask_rating and not _informado
    # Encerramento COMUM fora da janela (PO 2026-09-02): avaliacao desligada
    # neste tenant, mas existe o template simples de recibo no WABA -> envia
    # ele (sem botoes). Sem o template, mudo — comportamento historico. So
    # fechamento manual, mesmo racional do ask_rating.
    _send_plain = ((not within_24h) and not ask_rating and not _informado
                   and current_user is not None and channel is not None
                   and await _close_template_available(channel, CLOSE_TEMPLATE_NAME))
    if pid:  # sempre True aqui (early-return acima); nivel preservado p/ diff enxuto
        if channel and (_send_janela or _send_template or _send_plain):
            try:
                token, phone_id, api_base = _resolve_channel_creds_by_id(channel["id"])
                wa_id = _wa_target(contact["wa_id"])
                first_name = _reopen_first_name(contact)
                body_v2 = (
                    f"Olá, {first_name}! Seu atendimento (protocolo {pid}) foi encerrado. "
                    "Obrigado por confiar na nossa empresa. Para nos ajudar a manter a "
                    "qualidade, como você avalia o atendimento recebido hoje?"
                )
                payload = None
                msg_saved_type = "text"
                template_cat = None
                content_txt = ""
                if _send_janela and ask_rating:
                    # Janela aberta: interativa de sessao (gratis, sem template).
                    # IDs rating_* sao o contrato do webhook (captura por botao).
                    content_txt = body_v2
                    payload = {
                        "messaging_product": "whatsapp", "to": wa_id, "type": "interactive",
                        "interactive": {
                            "type": "button",
                            "body": {"text": body_v2},
                            "action": {"buttons": [
                                {"type": "reply", "reply": {"id": "rating_ruim", "title": "Ruim"}},
                                {"type": "reply", "reply": {"id": "rating_bom", "title": "Bom"}},
                                {"type": "reply", "reply": {"id": "rating_excelente", "title": "Excelente"}},
                            ]},
                        },
                    }
                elif _send_janela:
                    # Flag desligada (ou re-pergunta bloqueada): so o protocolo.
                    content_txt = f"Seu protocolo de hoje é {pid}. Agradecemos pela confiança em nossa empresa."
                    payload = {"messaging_product": "whatsapp", "to": wa_id,
                               "type": "text", "text": {"body": content_txt}}
                elif _send_template:
                    # Fora da janela COM avaliacao: template rating_request
                    # (conversa paga iniciada pela empresa). Ausente/reprovado
                    # no WABA -> a Meta recusa, logamos e o fechamento segue
                    # mudo (comportamento historico).
                    content_txt = body_v2
                    msg_saved_type = "template"
                    template_cat = "utility"
                    payload = {
                        "messaging_product": "whatsapp", "to": wa_id, "type": "template",
                        "template": {
                            "name": RATING_TEMPLATE_NAME,
                            "language": {"code": RATING_TEMPLATE_LANG},
                            "components": [{"type": "body", "parameters": [
                                {"type": "text", "text": first_name},
                                {"type": "text", "text": pid},
                            ]}],
                        },
                    }
                else:
                    # Fora da janela SEM avaliacao (_send_plain): template
                    # simples de recibo, ja confirmado APPROVED no WABA.
                    content_txt = (
                        f"Olá, {first_name}! Seu atendimento (protocolo {pid}) foi "
                        "encerrado. Obrigado por confiar na nossa empresa."
                    )
                    msg_saved_type = "template"
                    template_cat = "utility"
                    payload = {
                        "messaging_product": "whatsapp", "to": wa_id, "type": "template",
                        "template": {
                            "name": CLOSE_TEMPLATE_NAME,
                            "language": {"code": RATING_TEMPLATE_LANG},
                            "components": [{"type": "body", "parameters": [
                                {"type": "text", "text": first_name},
                                {"type": "text", "text": pid},
                            ]}],
                        },
                    }
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(
                        f"{api_base}/{phone_id}/messages",
                        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                        json=payload,
                    )
                if resp.status_code == 200:
                    wa_msg_id = (resp.json().get("messages", [{}])[0].get("id", ""))
                    save_wa_message(
                        wa_message_id=wa_msg_id, contact_id=contact["id"], direction="outbound",
                        msg_type=msg_saved_type, content=content_txt, status="sent",
                        timestamp_wa=datetime.now(timezone.utc).isoformat(),
                        operator_id=sender_uid,
                        channel_id=channel["id"],
                        conversation_id=conv["id"] if conv else None,
                        sender_user_id=sender_uid,
                        channel_owner_user_id=channel.get("owner_user_id"),
                        template_category=template_cat,
                        # Recibo de sistema no fechamento nao e "inicio de
                        # atendimento" — nao promove lead novo (reforma 2026-09).
                        promote_qualification=False,
                        # Nem "atividade": sem isto o proprio recibo reabria o
                        # attendance_status que este request acabou de fechar
                        # (revisao adversarial 2026-09-01).
                        reopen_attendance=False,
                    )
                    mark_protocol_informed(pid)
                    if ask_rating:
                        # Carimbo SO com envio confirmado (fix da classe do
                        # "Avaliacao pendente" eterno + digito engolido).
                        fs_document("wa_contacts", contact["id"]).set(
                            {"rating_requested_at": fs_utcnow().isoformat()}, merge=True,
                        )
                else:
                    try:
                        _err = (resp.json().get("error") or {}).get("message", "")
                    except Exception:
                        _err = f"http {resp.status_code}"
                    logger.warning("close_daily_protocol: Meta recusou pid=%s: %s", pid, _err)
            except Exception as exc:
                logger.warning("close_daily_protocol: falha ao enviar pid=%s: %s", pid, exc)
    close_daily_attendance(pid, close_status, sender_uid)
    return True


@app.post("/api/wa/conversation/{conversation_id}/set-attendance")
async def wa_set_attendance(conversation_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    """Fase 4 (ciclo de vida): fecha/reabre um atendimento manualmente.
    body: {status: 'fechado_manual' | 'aberto', qualification?, notes?}.
    Dono do atendimento ou admin/supervisor. Fechar manual zera o takeover.

    Gate de desfecho (reforma 2026-09): fechar manualmente um lead ainda
    "novo"/"em_atendimento" EXIGE a qualificacao final no mesmo request
    (convertido | nao_convertido | qualificado | nao_qualificado) — o modal
    do frontend coleta, esta trava e a camada real. Cron e fechamento pelo
    proprio cliente (fechado_cliente) nao passam por aqui; backup fora."""
    body = await request.json()
    status = (body.get("status") or "").strip()
    if status not in ("fechado_manual", "aberto"):
        raise HTTPException(status_code=400, detail="status invalido (use fechado_manual ou aberto)")
    conv = get_wa_conversation_by_id(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Atendimento nao encontrado")
    # Gerir atendimento de terceiros e coberto por QUALQUER um dos toggles
    # de supervisao — desligar so a co-pilotagem (mensagem em thread alheia)
    # nao pode quebrar fechar/reabrir da equipe.
    is_manager = (has_permission(current_user, "enviar_mensagem_qualquer_thread")
                  or has_permission(current_user, "assumir_supervisor"))
    if not is_manager and conv.get("assigned_to") != current_user["id"]:
        # Modo Recepcao (ADR 0010): thread da POOL (sem dono) pode ser
        # fechada/reaberta por qualquer operador (o toggle RBAC da acao em
        # si continua valendo logo abaixo). Thread de OUTRO segue 403; e
        # orfa de LEAD com dono nao e pool (espelha o gate de envio).
        _pool_ok = False
        if not conv.get("assigned_to") and _reception_send_allowed(conv, None):
            _ctc = get_wa_contact(conv.get("contact_id")) if conv.get("contact_id") is not None else None
            _pool_ok = bool(_ctc) and not _ctc.get("assigned_to")
        if not _pool_ok:
            raise HTTPException(status_code=403, detail="Apenas o dono do atendimento ou admin/supervisor")
    # RBAC: toggle da acao em si (fechar/reabrir), alem do escopo acima.
    ensure_permission(
        current_user,
        "fechar_atendimento_manual" if status == "fechado_manual" else "reabrir_atendimento_manual",
    )
    contact_id = conv.get("contact_id")
    contact = get_wa_contact(contact_id) if contact_id is not None else None
    qualification = str(body.get("qualification") or "").strip()
    notes = body.get("notes")
    if status == "fechado_manual":
        _terminais = ("qualificado", "nao_qualificado", "convertido", "nao_convertido")
        if qualification and qualification not in _terminais:
            raise HTTPException(
                status_code=400,
                detail=f"Desfecho invalido. Opcoes: {', '.join(_terminais)}",
            )
        # Tags do modal (Frente B): valida ANTES de qualquer escrita — um 400
        # aqui nao pode deixar qualificacao gravada com fechamento abortado.
        _tags_raw = body.get("tags")
        _tag_slugs = None
        if _tags_raw is not None:
            from database import clean_lead_tags as _clean_lead_tags
            try:
                _tag_slugs = _clean_lead_tags(_tags_raw)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
        _cur_q = str((contact or {}).get("qualification") or "novo")
        _gate = (contact is not None and not conv.get("is_backup")
                 and not contact.get("is_backup")
                 and _cur_q in ("novo", "em_atendimento"))
        if _gate and not qualification:
            raise HTTPException(
                status_code=400,
                detail="Qualifique o desfecho antes de encerrar (convertido, nao_convertido, qualificado ou nao_qualificado).",
            )
        if qualification and contact is not None:
            if not _gate:
                # FORA do caso do gate (lead ja terminal/backup), mudar
                # qualificacao por este endpoint exige o MESMO toggle do
                # /qualify — sem isto, perfil "so fecha" reescrevia desfecho
                # terminal de qualquer thread da pool e carimbava
                # converted_by_user_id pra si (revisao adversarial 2026-09-01).
                ensure_permission(current_user, "qualificar_lead")
            # No caso do gate, cobre pelo toggle do FECHAMENTO (ja checado
            # acima), sem exigir qualificar_lead: o gate torna o desfecho
            # OBRIGATORIO pra fechar — exigir um segundo toggle criaria
            # perfil que nao consegue encerrar nunca (deadlock). Auditado.
            update_wa_contact_qualification(contact_id, qualification, notes)
            if qualification == "convertido":
                fs_document("wa_contacts", contact_id).set(
                    {"converted_by_user_id": current_user["id"]}, merge=True,
                )
            log_audit(current_user["id"], "CONTACT_QUALIFY",
                      f"Contato {contact_id}: {qualification} (no encerramento)")
            contact = dict(contact)
            contact["qualification"] = qualification
        if _tag_slugs is not None and contact is not None:
            from database import update_wa_contact_tags as _upd_tags
            _upd_tags(contact_id, _tag_slugs)
            _register_personal_tags(current_user, body.get("tag_labels"), _tag_slugs)
            log_audit(current_user["id"], "CONTACT_TAGS",
                      f"Contato {contact_id}: {len(_tag_slugs)} tag(s) (no encerramento)")
    set_attendance_status(conversation_id, status, clear_takeover=(status == "fechado_manual"))
    if contact_id is not None:
        verb = "fechado" if status == "fechado_manual" else "reaberto"
        insert_transfer_system_message(
            contact_id, f"Atendimento {verb} por {current_user['display_name']}.",
            current_user["id"], conversation_id=conversation_id, channel_id=conv.get("channel_id"),
        )
    # Fase 5A: ao fechar a thread, fecha o Atendimento DIARIO + envia o
    # protocolo ao lead (recibo). Idempotente: a flag protocolo_informado
    # bloqueia reenvio se outra thread do mesmo dia ja fechou antes.
    if contact_id is not None and status == "fechado_manual":
        # `contact` ja carregado acima (gate de desfecho) — 1 read a menos.
        from channel_service import get_channel as _get_channel
        channel = _get_channel(conv.get("channel_id")) if conv.get("channel_id") else None
        if contact:
            await _close_daily_and_send_protocol(contact, conv, channel, current_user, "fechado_manual")
    elif contact_id is not None and status == "aberto":
        # Reopen manual: volta o Atendimento diario p/ 'aberto' mantendo
        # protocolo_informado (consistencia com o que ensure_daily_attendance
        # faz no proximo inbound).
        pid = get_current_protocol_id(contact_id)
        if pid:
            try:
                fs_document("attendances_daily", pid).set(
                    {"status": "aberto", "fechado_em": None, "fechado_por_user_id": None}, merge=True,
                )
            except Exception as exc:
                logger.warning("reopen daily attendance pid=%s falhou: %s", pid, exc)
    log_audit(current_user["id"], "ATTENDANCE_SET_STATUS", f"conv={conversation_id} -> {status}")
    return {"status": "ok", "attendance_status": status}


@app.post("/api/wa/assume/{contact_id}")
async def wa_assume_contact(contact_id: int, request: Request, current_user: dict = Depends(get_current_user)):
    """Operador assume o atendimento de um contato nao atribuido.

    Body opcional: { conversation_id } = a thread que o operador esta olhando.
    Quando vem (e pertence ao contato), a system message do assume e gravada
    NELA (e nao na thread derivada de contact.channel_id, que pode ser outro
    canal num lead multi-canal). Independente do body, todas as threads orfas
    do contato herdam o dono (assign_orphan_threads_to_lead_owner).
    """
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    try:
        body = await request.json()
    except Exception:
        body = {}
    conversation_id = str((body or {}).get("conversation_id") or "").strip() or None
    conv_channel_id = None
    if conversation_id:
        _conv = get_wa_conversation_by_id(conversation_id)
        try:
            _conv_contact = int(_conv.get("contact_id")) if _conv and _conv.get("contact_id") is not None else None
        except (TypeError, ValueError):
            _conv_contact = None
        if _conv_contact != int(contact_id):
            conversation_id = None  # thread de outro contato / inexistente: ignora, cai no legado
        else:
            # channel_id junto: save_wa_message deriva a thread do upsert
            # (recencia/dono) de channel+wa_id, nao do conversation_id.
            conv_channel_id = _conv.get("channel_id")
    # RBAC: perfil "so recepcao" (pool compartilhada) tem este toggle OFF e
    # atende sem virar dono do lead (ADR 0010). Default ON em todos os seeds.
    ensure_permission(current_user, "assumir_atendimento")
    try:
        existing_id = int(contact.get("assigned_to") or 0) or None
        current_id = int(current_user["id"])
    except (TypeError, ValueError):
        existing_id = None
        current_id = None
    if existing_id is not None and existing_id != current_id:
        raise HTTPException(status_code=409, detail="Atendimento ja assumido por outro operador")
    # -- Regra do contador de assumidas sem resposta (FEATURE_ASSUME_COUNTER) --
    if FEATURE_ASSUME_COUNTER:
        assume_counter = get_assume_counter(current_user["id"])
        if assume_counter <= -2:
            raise HTTPException(
                status_code=403,
                detail="Voce atingiu o limite de atendimentos assumidos sem resposta. Responda as conversas pendentes antes de assumir novas.",
            )
    result = assign_wa_contact(contact_id, current_user["id"], contact.get("department_id"), current_user["id"], reason="Assumido pelo operador", summary="Assumido pelo operador")
    if result is None:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    # Dono do Atendimento: carimba EXPLICITAMENTE o operador em toda thread
    # orfa do contato. Antes a thread so herdava o dono pelo efeito colateral
    # da system message abaixo (upsert em save_wa_message), que alcanca uma
    # unica thread e engole falha — a thread da pool podia continuar orfa e
    # visivel (listener + rules) pra todos os operadores depois do assume.
    try:
        _n_threads = assign_orphan_threads_to_lead_owner(contact_id, current_user["id"])
    except Exception:
        _n_threads = -1
        logger.exception("[ASSUME] carimbar dono nas threads falhou | contato=%s", contact_id)
    if FEATURE_ASSUME_COUNTER:
        # Decrementar contador e marcar contato como pendente de resposta
        decrement_assume_counter(current_user["id"])
        mark_contact_pending_response(contact_id)
    # Gravar original_operator_id se ainda nao definido (para roteamento de lead retornante)
    if not contact.get("original_operator_id"):

        fs_document("wa_contacts", contact_id).set({"original_operator_id": current_user["id"]}, merge=True)
    # Dona de origem (sale_owner): grava na 1a assuncao. Handoff entre operadores
    # NAO altera (so admin via reassign-lead). Restaurada no fechamento da conversa.
    if not contact.get("sale_owner_user_id"):
        set_sale_owner(contact_id, current_user["id"])
    # Fase 5A: protocolo NAO e mais gerado no assume (so no 1o inbound do dia
    # via webhook -> ensure_daily_attendance). Reusa o atual se ja existe.
    protocol = get_current_protocol_id(contact_id) or ""
    # Lead self-service do bot CX (conversou com a IA mas NUNCA pediu handoff,
    # ex.: foi agendar online): classifica a temperatura e emite o resumo do
    # que a IA coletou, a partir do snapshot em bot_states. Sem isto o lead
    # ficava sem badge e sem resumo justamente pra quem assume. Antes da
    # system message do assume pra ordem de leitura ficar cronologica.
    # Nao-fatal: falha aqui nunca derruba o assume.
    try:
        from bot_service import apply_cx_snapshot_on_assume
        apply_cx_snapshot_on_assume(contact_id, contact)
    except Exception:
        logger.exception("[ASSUME] resumo do bot CX falhou | contato=%s", contact_id)
    sys_content = f"Atendimento assumido por {current_user['display_name']}" + (f" | Protocolo: {protocol}" if protocol else "")
    insert_transfer_system_message(
        contact_id, sys_content, current_user["id"],
        conversation_id=conversation_id, channel_id=conv_channel_id,
    )
    log_audit(
        current_user["id"], "WA_ASSUME",
        f"Contato {contact_id}" + (f" | Protocolo {protocol}" if protocol else "")
        + (f" | conv={conversation_id}" if conversation_id else "") + f" | threads={_n_threads}",
    )
    await broadcast_to_operators({
        "event": "wa_contact_reassigned",
        "data": {"contact_id": contact_id, "assigned_to": current_user["id"], "assigned_name": current_user["display_name"]},
    })
    return {"status": "assumed", "assigned_to": current_user["id"], "assigned_name": current_user["display_name"], "protocol": protocol or None}


@app.post("/api/admin/operator/{user_id}/reset-assume-counter")
async def admin_reset_assume_counter(user_id: int, current_user: dict = Depends(get_current_user)):
    """Reseta o contador de assumidas sem resposta de um operador. Apenas admin/supervisor."""
    ensure_permission(current_user, "gerenciar_usuarios")
    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Operador nao encontrado")
    reset_assume_counter(user_id)
    log_audit(current_user["id"], "RESET_ASSUME_COUNTER", f"Operador {target.get('display_name', user_id)} (id={user_id})")
    return {"status": "reset", "user_id": user_id, "counter": 0}


@app.get("/api/wa/transfer-history/{contact_id}")
async def wa_transfer_hist(contact_id: int, current_user: dict = Depends(get_current_user)):
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    _require_contact_access(contact, current_user)  # LGPD: so dono/pool/admin
    return {"history": get_transfer_history(contact_id)}


@app.post("/api/wa/contact/{contact_id}/return-to-bot")
async def wa_return_to_bot(contact_id: int, current_user: dict = Depends(get_current_user)):
    """Devolve o contato para a fila do bot. Apenas admin/supervisor."""
    ensure_permission(current_user, "editar_dono_lead")
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


@app.post("/api/wa/contact/{contact_id}/return-to-pool")
async def wa_return_to_pool(contact_id: int, current_user: dict = Depends(get_current_user)):
    """Devolve o lead a POOL da recepcao (ADR 0010) — acao explicita do menu.

    So em pool_mode=reception. Escopo: dono do lead ou admin/supervisor
    (mesma regra do fechar). NAO volta pro bot — o lead cai na aba Recepcao
    de todos, com bot_completed/qualification/protocolo preservados.
    """
    from database import is_reception_mode
    if not is_reception_mode():
        raise HTTPException(status_code=409, detail="Disponivel apenas no modo Recepcao (pool compartilhada)")
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    is_manager = (has_permission(current_user, "enviar_mensagem_qualquer_thread")
                  or has_permission(current_user, "assumir_supervisor"))
    if not is_manager and contact.get("assigned_to") not in (None, current_user["id"]):
        raise HTTPException(status_code=403, detail="Apenas o dono do lead ou admin/supervisor")
    result = return_contact_to_pool(contact_id, current_user["id"])
    if not result:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    insert_transfer_system_message(
        contact_id,
        f"Lead devolvido à recepção por {current_user['display_name']}.",
        current_user["id"], advance_recency=False,
    )
    log_audit(current_user["id"], "WA_RETURN_TO_POOL", f"Contato {contact_id}")
    return {"status": "returned_to_pool"}


@app.post("/api/admin/bulk-reassign")
async def admin_bulk_reassign(request: Request, current_user: dict = Depends(get_current_user)):
    """Reatribuicao em lote de contatos de um operador.

    Body: { from_user_id, action: "return_to_bot" | "transfer", to_user_id? }

    Exclui automaticamente contatos cujo canal e coexistence proprio do
    operador X (i.e. `channel.owner_user_id == from_user_id`). Esses
    contatos pertencem ao WhatsApp pessoal dele e nao podem ser
    transferidos sem perder acesso ao numero — o operador continua dono.
    """
    ensure_permission(current_user, "editar_dono_lead")
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
            "perfil_acesso_id": u.get("perfil_acesso_id", ""),
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
    ensure_permission(current_user, "ver_dashboard_uso")
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
    ensure_permission(current_user, "ver_dashboard_uso")
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
    ensure_permission(current_user, "ver_dashboard_uso")
    return get_monthly_usage()


@app.get("/api/wa/usage/history")
async def wa_usage_history(
    months: int = Query(3, ge=1, le=24),
    current_user: dict = Depends(get_current_user),
):
    """Retorna ultimos N meses de usage do tenant atual (mes corrente primeiro)."""
    ensure_permission(current_user, "ver_dashboard_uso")
    return {"months": get_usage_history(months)}


@app.get("/api/wa/usage/{year_month}")
async def wa_usage_specific_month(
    year_month: str,
    current_user: dict = Depends(get_current_user),
):
    """Retorna usage de um mes especifico (formato YYYY-MM)."""
    ensure_permission(current_user, "ver_dashboard_uso")
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
    ensure_permission(current_user, "exportar_contatos")

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
async def embedded_signup_config(type: str = "coexistence", current_user: dict = Depends(get_current_user)):
    """Retorna configuracao para o frontend iniciar o Embedded Signup.

    type=coexistence (default): canal coex do operador (admin/sup ou coex_authorized).
    type=standard: canal Cloud API padrao — APENAS admin/supervisor, config_id proprio.
    """
    is_standard = type == "standard"
    if is_standard:
        ensure_permission(current_user, "gerenciar_canais")
    else:
        if not has_permission(current_user, "gerenciar_canais") and not current_user.get("coex_authorized"):
            raise HTTPException(status_code=403, detail="Sem permissao para o signup. Peca a um admin para autorizar seu numero coexistence.")
    missing: list[str] = []
    if not META_APP_ID:
        missing.append("META_APP_ID")
    if not META_APP_SECRET:
        missing.append("META_APP_SECRET")
    cfg_id = EMBEDDED_SIGNUP_CONFIG_ID_STANDARD if is_standard else EMBEDDED_SIGNUP_CONFIG_ID
    if not cfg_id:
        missing.append("EMBEDDED_SIGNUP_CONFIG_ID_STANDARD" if is_standard else "EMBEDDED_SIGNUP_CONFIG_ID")
    if missing:
        raise HTTPException(
            status_code=503,
            detail=f"Configuracao de Embedded Signup incompleta: {', '.join(missing)}",
        )
    return {
        "app_id": META_APP_ID,
        "config_id": cfg_id,
        "graph_api_version": GRAPH_API_VERSION,
    }


class EmbeddedSignupExchange(BaseModel):
    code: str
    channel_type: str = "coexistence"
    owner_user_id: int | None = None
    label: str = ""
    default_department_id: int | None = None
    # session-info do popup (Embedded Signup v4 entrega a WABA/numero AQUI,
    # nao mais nos granular_scopes do token). O frontend captura via postMessage.
    phone_number_id: str = ""
    waba_id: str = ""


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
    if not has_permission(current_user, "gerenciar_canais") and not current_user.get("coex_authorized"):
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
    _dbg = debug_data.get("data", {}) or {}
    granular_scopes = _dbg.get("granular_scopes", [])

    # [DIAGNOSTICO TEMPORARIO] introspeccao crua do token p/ depurar granted=<vazio>.
    # Nao loga o token nem PII; target_ids sao IDs de WABA (ativos de negocio).
    # scopes (flat) revela se o token tem QUALQUER permissao mesmo com granular vazio:
    #  - scopes vazio  -> login nao concedeu nada (acesso do app/modo, ou conta sem ativo)
    #  - scopes tem whatsapp_business_management mas granular vazio -> problema de ativo/targeting
    logger.info(
        "Embedded Signup debug_token | channel_type=%s valid=%s app_id=%s type=%s scopes=[%s] granular=%s",
        body.channel_type,
        _dbg.get("is_valid"),
        _dbg.get("app_id"),
        _dbg.get("type"),
        ",".join(_dbg.get("scopes") or []) or "<vazio>",
        [
            {"scope": s.get("scope"), "targets": s.get("target_ids")}
            for s in (granular_scopes or [])
        ],
    )

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

    # WABA: o Embedded Signup v4 entrega waba_id/phone_number_id na MENSAGEM de
    # session-info do popup (o frontend captura via postMessage e envia no body),
    # NAO mais nos granular_scopes do token (que no v4 voltam so public_profile).
    # Usa a session-info como fonte primaria; granular_scopes (v3) como fallback.
    session_waba = (body.waba_id or "").strip()
    waba_id = session_waba or (waba_ids[0] if waba_ids else "")
    if not waba_id:
        logger.warning(
            "Embedded Signup: nenhum WABA (granted=%s, session-info vazio)",
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

    # Token para LER/GERENCIAR a WABA: o token do popup (public_profile no v4)
    # nao tem permissao. Usa o System User token global do portfolio Castro
    # Operacoes (Secret Manager), que acessa todas as WABAs onboardadas no app.
    wa_token = (WHATSAPP_SYSTEM_USER_TOKEN or "").strip() or access_token
    logger.info(
        "Embedded Signup: WABA ID = %s (fonte=%s, system_user_token=%s)",
        waba_id,
        "session-info" if session_waba else "granular_scopes",
        bool((WHATSAPP_SYSTEM_USER_TOKEN or "").strip()),
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
                headers={"Authorization": f"Bearer {wa_token}"},
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
    is_privileged = has_permission(current_user, "gerenciar_canais")
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
                headers={"Authorization": f"Bearer {wa_token}"},
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

    # 6. Criar OU rebindar canal no registry.
    #    Re-onboarding do MESMO numero NAO cria canal novo (decisao #1 do
    #    docs/PLANO_LEAD_ATENDIMENTO_E_REGRAS): detecta canal existente por
    #    phone_number_id lendo o Firestore DIRETO (o cache so-ativos nao
    #    enxerga canal desativado) e da UPDATE — reativa + token novo +
    #    reaponta phone_routing. Mantendo o channel_id, as threads
    #    {channel_id}__{wa_id} sobrevivem (sem duplicar conversa).
    owner_user = get_user_by_id(owner_id) if owner_id else None
    channel_label = body.label or (
        f"{(owner_user or {}).get('display_name', 'Operador')} - {display_phone}"
        if is_coexistence
        else f"Canal {display_phone}"
    )

    existing_channel = get_channel_by_phone_id_from_db(phone_number_id)
    rebound = False
    if existing_channel:
        existing_owner = existing_channel.get("owner_user_id")
        # Guard de autoria: um operador nao pode "roubar" via re-signup o
        # canal de OUTRO operador. Admin/supervisor pode reatribuir (audit).
        if (
            owner_id is not None
            and existing_owner is not None
            and existing_owner != owner_id
            and not is_privileged
        ):
            logger.warning(
                "Embedded Signup: rebind bloqueado | channel=%s owner_existente=%s tentando=%s",
                existing_channel.get("id"), existing_owner, owner_id,
            )
            raise HTTPException(
                status_code=409,
                detail=(
                    "Este numero ja esta vinculado a outro operador. "
                    "Peca a um admin para transferir o canal."
                ),
            )
        new_channel_id = rebind_channel(
            existing_channel["id"],
            waba_id=waba_id,
            phone_number_id=phone_number_id,
            display_phone_number=display_phone,
            access_token=wa_token,
            token_expires_at=token_expires_at_iso,
            owner_user_id=owner_id,
            owner_firebase_uid=(owner_user or {}).get("firebase_uid", ""),
            webhook_subscribed=webhook_subscribed,
            platform_type=platform_type,
            is_official_business_account=is_official,
            code_verification_status=code_verification_status,
            messaging_limit_tier=messaging_limit_tier,
            verified_name=verified_name,
            quality_rating=quality_rating,
        )
        rebound = True
        logger.info(
            "Embedded Signup: REBIND canal existente id=%s phone=%s owner=%s privileged=%s",
            new_channel_id, phone_number_id, owner_id, is_privileged,
        )
    else:
        new_channel_id = create_channel(
            channel_type=channel_type,
            label=channel_label,
            waba_id=waba_id,
            phone_number_id=phone_number_id,
            display_phone_number=display_phone,
            access_token=wa_token,
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
        # Um unico AsyncClient para os dois POSTs (reuso de conexao). O
        # try/except continua por sync_type pra que falha em um nao aborte
        # o outro.
        async with httpx.AsyncClient(timeout=30.0) as client:
            for sync_type in ("smb_app_state_sync", "history"):
                try:
                    sync_resp = await client.post(
                        smb_data_url,
                        headers={
                            "Authorization": f"Bearer {wa_token}",
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
        "EMBEDDED_SIGNUP_REBIND" if rebound else "EMBEDDED_SIGNUP",
        f"WABA={waba_id} Phone={phone_number_id} ({display_phone}) status={status} channel_id={new_channel_id} rebound={rebound} syncs={list(sync_results.keys())}",
    )

    return {
        "status": "ok",
        "channel_id": new_channel_id,
        "rebound": rebound,
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
