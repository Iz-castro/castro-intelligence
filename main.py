# -*- coding: utf-8 -*-

import logging
import os
from datetime import datetime, timezone

import httpx
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
    mark_wa_conversation_read, save_wa_message, get_wa_contact,
    log_audit, normalize_br_phone,
    get_all_departments, create_department,
    get_department_by_id, update_department, deactivate_department,
    assign_wa_contact, get_transfer_history,
    return_contact_to_bot, get_contacts_by_assigned_user,
    update_user_avatar, get_user_avatar,
    update_user, deactivate_user,
    upsert_firebase_user, get_user_by_email,
    update_wa_contact_qualification, archive_wa_contact, restore_wa_contact,
    update_contact_avatar, insert_transfer_system_message, set_attendance_protocol,
    get_wa_message_by_id, update_wa_message_transcription,
    get_system_settings, save_system_settings,
    get_user_settings, save_user_settings,
    get_all_gc_conversations, get_gc_messages, save_gc_message,
    mark_gc_conversation_read, upsert_gc_conversation,
)
from channel_service import (
    get_all_active_channels, get_channels_for_user,
    create_channel, update_channel, deactivate_channel,
    get_channel_by_id_from_db,
    CHANNEL_TYPE_STANDARD, CHANNEL_TYPE_COEXISTENCE,
)
from auth import authenticate_firebase_token
from firestore_common import collection_name
from webhook import process_webhook_payload, validate_signature
from webhook_google_chat import validate_google_chat_token, process_google_chat_event
from media import (
    ensure_media_dir, upload_media_to_whatsapp, send_media_message,
    save_upload_media, convert_audio_to_ogg_opus,
    save_avatar_media, delete_media, get_media_asset,
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

if os.path.isdir(FRONTEND_ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=FRONTEND_ASSETS_DIR), name="frontend-assets")

class WaSendRequest(BaseModel):
    contact_id: int
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
    contact_id: int
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
        logger.info("Bootstrap admin Firebase sincronizado | email=%s", BOOTSTRAP_ADMIN_EMAIL)
    else:
        logger.warning("Falha ao sincronizar bootstrap admin Firebase | email=%s", BOOTSTRAP_ADMIN_EMAIL)


def bootstrap_departments():
    dept_map = ensure_default_departments(create_department)
    logger.info("Departamentos padrao sincronizados | total=%d", len(dept_map))


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
    bootstrap_departments()
    bootstrap_admin_user()
    ensure_media_dir()
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
    logger.warning("Falha na verificacao do webhook (token=%s)", hub_verify_token)
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
    return {
        "user": current_user,
        "auth_mode": AUTH_MODE,
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


# -- API: WhatsApp --

@app.get("/api/wa/contacts")
async def wa_contacts(current_user: dict = Depends(get_current_user)):
    contacts = get_all_wa_contacts()
    for c in contacts:
        c["unread"] = int(c.get("unread_count", 0))
    return {"contacts": contacts}


@app.get("/api/wa/messages/{contact_id}")
async def wa_messages(contact_id: int, limit: int = Query(default=10, ge=1, le=200), current_user: dict = Depends(get_current_user)):
    messages = get_wa_conversation(contact_id, limit=limit)
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

from datetime import timedelta

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


def _resolve_channel_creds(contact: dict) -> tuple[str, str, str]:
    """Resolve credenciais do canal a partir do contato.

    Tenta channel_id do contato, senao usa canal default.
    Returns (token, phone_number_id, graph_api_base).
    """
    from channel_service import get_send_credentials
    channel_id = contact.get("channel_id")
    try:
        return get_send_credentials(channel_id)
    except ValueError:
        # Fallback para env vars legadas
        if WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID:
            return WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID, GRAPH_API_BASE
        raise HTTPException(status_code=503, detail="Nenhum canal WhatsApp configurado")


@app.post("/api/wa/send-location")
async def wa_send_location(body: WaSendLocationRequest, current_user: dict = Depends(get_current_user)):
    contact = get_wa_contact(body.contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    token, phone_id, api_base = _resolve_channel_creds(contact)
    _check_24h_window(contact)
    reply_fields = _build_reply_fields(body.contact_id, body.reply_to_message_id, body.reply_to_preview, body.reply_to_sender_name)
    reply_context = _build_reply_context(body.contact_id, body.reply_to_message_id)

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
            contact_id=body.contact_id,
            direction="outbound",
            msg_type="location",
            content=content,
            latitude=body.latitude,
            longitude=body.longitude,
            status="sent",
            timestamp_wa=datetime.now(timezone.utc).isoformat(),
            operator_id=current_user["id"],
            **reply_fields,
        )
        log_audit(current_user["id"], "WA_SEND_LOCATION", f"Para {wa_id}: {body.latitude},{body.longitude}")
        return {"status": "sent", "wa_message_id": wa_msg_id}

    error_msg = result.get("error", {}).get("message", "Erro desconhecido")
    raise HTTPException(status_code=502, detail=error_msg)


@app.post("/api/wa/send")
async def wa_send(body: WaSendRequest, current_user: dict = Depends(get_current_user)):
    contact = get_wa_contact(body.contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    token, phone_id, api_base = _resolve_channel_creds(contact)
    if contact.get("assigned_to") and contact["assigned_to"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Atendimento atribuido a outro operador")
    _check_24h_window(contact)
    reply_fields = _build_reply_fields(body.contact_id, body.reply_to_message_id, body.reply_to_preview, body.reply_to_sender_name)
    reply_context = _build_reply_context(body.contact_id, body.reply_to_message_id)

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
            wa_message_id=wa_msg_id, contact_id=body.contact_id, direction="outbound",
            msg_type="text", content=body.content, status="sent",
            timestamp_wa=datetime.now(timezone.utc).isoformat(), operator_id=current_user["id"],
            **reply_fields,
        )
        log_audit(current_user["id"], "WA_SEND", f"Para {wa_id}: {body.content[:80]}")
        return {"status": "sent", "wa_message_id": wa_msg_id}
    else:
        error_msg = result.get("error", {}).get("message", "Erro desconhecido")
        logger.warning("Falha ao enviar texto para %s | status=%s | erro=%s", wa_id, resp.status_code, error_msg)
        raise HTTPException(status_code=502, detail=error_msg)


@app.post("/api/wa/send-media")
async def wa_send_media(
    request: Request, contact_id: int = Form(...),
    caption: str = Form(""), file: UploadFile = File(...),
    reply_to_message_id: int | None = Form(None),
    reply_to_preview: str = Form(""),
    reply_to_sender_name: str = Form(""),
):
    current_user = get_current_user(request)
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    token, phone_id, api_base = _resolve_channel_creds(contact)
    if contact.get("assigned_to") and contact["assigned_to"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Atendimento atribuido a outro operador")
    _check_24h_window(contact)
    reply_fields = _build_reply_fields(contact_id, reply_to_message_id, reply_to_preview, reply_to_sender_name)
    reply_context = _build_reply_context(contact_id, reply_to_message_id)

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
        wa_message_id=wa_msg_id, contact_id=contact_id, direction="outbound",
        msg_type=msg_type, content=caption, media_path=local_result["path"],
        media_mime=mime_type, media_id=media_id, filename=filename,
        status="sent", timestamp_wa=datetime.now(timezone.utc).isoformat(),
        operator_id=current_user["id"],
        **reply_fields,
    )
    log_audit(current_user["id"], "WA_SEND_MEDIA", f"{msg_type} para {contact['wa_id']}: {filename}")
    return {"status": "sent", "wa_message_id": wa_msg_id, "msg_type": msg_type, "media_path": local_result["path"]}


@app.post("/api/wa/send-audio")
async def wa_send_audio(
    request: Request, contact_id: int = Form(...), file: UploadFile = File(...),
    reply_to_message_id: int | None = Form(None),
    reply_to_preview: str = Form(""),
    reply_to_sender_name: str = Form(""),
):
    """Envia audio gravado pelo microfone para contato WhatsApp.
    Converte WebM/Opus do navegador para OGG/Opus via FFmpeg."""
    current_user = get_current_user(request)

    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    token, phone_id, api_base = _resolve_channel_creds(contact)
    if contact.get("assigned_to") and contact["assigned_to"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Atendimento atribuido a outro operador")
    _check_24h_window(contact)
    reply_fields = _build_reply_fields(contact_id, reply_to_message_id, reply_to_preview, reply_to_sender_name)
    reply_context = _build_reply_context(contact_id, reply_to_message_id)

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
        wa_message_id=wa_msg_id, contact_id=contact_id, direction="outbound",
        msg_type="audio", content="", media_path=local_result["path"],
        media_mime="audio/ogg", media_id=media_id, filename="gravacao.ogg",
        status="sent", timestamp_wa=datetime.now(timezone.utc).isoformat(),
        operator_id=current_user["id"],
        **reply_fields,
    )
    log_audit(current_user["id"], "WA_SEND_AUDIO", f"Para {contact['wa_id']}")
    return {"status": "sent", "wa_message_id": wa_msg_id, "msg_type": "audio", "media_path": local_result["path"]}


@app.post("/api/wa/send-template")
async def wa_send_template(
    contact_id: int, template_name: str = "hello_world",
    language: str = "pt_BR", current_user: dict = Depends(get_current_user),
):
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    token, phone_id, api_base = _resolve_channel_creds(contact)
    url = f"{api_base}/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp", "to": _wa_target(contact["wa_id"]),
        "type": "template", "template": {"name": template_name, "language": {"code": language}},
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        result = resp.json()
    if resp.status_code == 200:
        wa_msg_id = result.get("messages", [{}])[0].get("id", "")
        save_wa_message(
            wa_message_id=wa_msg_id, contact_id=contact_id, direction="outbound",
            msg_type="template", content=f"[template: {template_name}]",
            status="sent", timestamp_wa=datetime.now(timezone.utc).isoformat(),
            operator_id=current_user["id"],
        )
        return {"status": "sent", "wa_message_id": wa_msg_id}
    else:
        raise HTTPException(status_code=502, detail=result.get("error", {}).get("message", "Erro desconhecido"))


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
        from firestore_common import document as fs_document, utcnow as fs_utcnow
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
                save_wa_message(
                    wa_message_id=wa_msg_id, contact_id=contact_id, direction="outbound",
                    msg_type="template", content="[avaliacao: responda de 1 a 10]",
                    status="sent", timestamp_wa=datetime.now(timezone.utc).isoformat(),
                    operator_id=current_user["id"],
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
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    if int(contact.get("unread_count", 0) or 0) <= 0:
        return {"status": "ok", "updated_count": 0}
    updated_count = mark_wa_conversation_read(contact_id)
    return {"status": "ok", "updated_count": updated_count}


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
    department_id = create_department(name, body.get("description", ""))
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
    ok, error = update_department(
        department_id,
        name=body.get("name"),
        description=body.get("description"),
        is_active=body.get("is_active"),
        sort_order=body.get("sort_order"),
    )
    if not ok:
        raise HTTPException(status_code=400, detail=error)
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


@app.get("/api/wa/contact/{contact_id}")
async def wa_contact_detail(contact_id: int, current_user: dict = Depends(get_current_user)):
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    return {"contact": contact}


@app.post("/api/wa/transfer")
async def wa_transfer(request: Request, current_user: dict = Depends(get_current_user)):
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
    if not summary:
        raise HTTPException(status_code=400, detail="Resumo do atendimento e obrigatorio")
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")

    result = assign_wa_contact(contact_id, to_user_id, to_department_id, current_user["id"], reason, summary)
    if result is None:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")

    to_user = get_user_by_id(to_user_id) if to_user_id else None
    to_name = to_user["display_name"] if to_user else "Nenhum"

    sys_content = (
        f"Transferido de {current_user['display_name']} para {to_name}"
        + (f" | Motivo: {reason}" if reason else "")
        + (f" | Resumo: {summary}" if summary else "")
    )
    insert_transfer_system_message(contact_id, sys_content, current_user["id"])
    log_audit(current_user["id"], "WA_TRANSFER", f"Contato {contact_id} -> {to_name} (dept={to_department_id}): {reason}")

    await broadcast_to_operators({
        "event": "wa_contact_reassigned",
        "data": {"contact_id": contact_id, "assigned_to": to_user_id, "assigned_name": to_name},
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
    result = assign_wa_contact(contact_id, current_user["id"], contact.get("department_id"), current_user["id"], reason="Assumido pelo operador", summary="Assumido pelo operador")
    if result is None:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    # Gravar original_operator_id se ainda nao definido (para roteamento de lead retornante)
    if not contact.get("original_operator_id"):
        from firestore_common import document as fs_document, utcnow as fs_utcnow
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

    count = 0
    for contact in contacts:
        cid = contact["id"]
        if action == "return_to_bot":
            return_contact_to_bot(cid, current_user["id"])
            insert_transfer_system_message(cid, f"Devolvido ao bot (reatribuicao em lote) por {current_user['display_name']}", current_user["id"])
        elif action == "transfer" and to_user_id:
            to_user = get_user_by_id(to_user_id)
            assign_wa_contact(cid, to_user_id, (to_user or {}).get("department_id"), current_user["id"], reason="Reatribuicao em lote", summary=f"Reatribuido de operador {from_user_id}")
            insert_transfer_system_message(cid, f"Reatribuido para {(to_user or {}).get('display_name', '?')} por {current_user['display_name']} (lote)", current_user["id"])
        count += 1

    log_audit(current_user["id"], "BULK_REASSIGN", f"from={from_user_id} action={action} to={to_user_id} count={count}")
    return {"status": "ok", "count": count}


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


# -- API: Embedded Signup (Coexistence) --


@app.get("/api/admin/embedded-signup/config")
async def embedded_signup_config(current_user: dict = Depends(get_current_user)):
    """Retorna configuracao necessaria para o frontend iniciar o Embedded Signup."""
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Permissao negada")
    if not META_APP_ID:
        raise HTTPException(status_code=503, detail="META_APP_ID nao configurado no servidor")
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


@app.post("/api/admin/embedded-signup/exchange")
async def embedded_signup_exchange(
    body: EmbeddedSignupExchange,
    current_user: dict = Depends(get_current_user),
):
    """Troca o code do Embedded Signup por token e descobre WABA/Phone IDs."""
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Permissao negada")
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
        token_data = token_resp.json()

    if "access_token" not in token_data:
        error_msg = token_data.get("error", {}).get("message", "Falha ao trocar code por token")
        logger.error("Embedded Signup token exchange falhou: %s", error_msg)
        raise HTTPException(status_code=502, detail=f"Erro na troca do code: {error_msg}")

    access_token = token_data["access_token"]
    logger.info("Embedded Signup: token obtido com sucesso")

    # 2. Buscar shared WABAs para descobrir WABA ID e Phone Number ID
    debug_url = (
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/debug_token"
        f"?input_token={access_token}&access_token={META_APP_ID}|{META_APP_SECRET}"
    )
    async with httpx.AsyncClient(timeout=20.0) as client:
        debug_resp = await client.get(debug_url)
        debug_data = debug_resp.json()

    granular_scopes = debug_data.get("data", {}).get("granular_scopes", [])
    waba_ids = []
    for scope in granular_scopes:
        if scope.get("scope") == "whatsapp_business_management":
            waba_ids = scope.get("target_ids", [])
            break

    if not waba_ids:
        logger.warning("Embedded Signup: nenhum WABA encontrado nos scopes")
        raise HTTPException(status_code=400, detail="Nenhuma conta WhatsApp Business retornada pelo signup")

    waba_id = waba_ids[0]
    logger.info("Embedded Signup: WABA ID descoberto = %s", waba_id)

    # 3. Buscar Phone Number ID dentro do WABA
    phones_url = f"{GRAPH_API_BASE}/{waba_id}/phone_numbers"
    async with httpx.AsyncClient(timeout=20.0) as client:
        phones_resp = await client.get(
            phones_url,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        phones_data = phones_resp.json()

    phone_numbers = phones_data.get("data", [])
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

    logger.info(
        "Embedded Signup concluido | waba=%s phone_id=%s display=%s status=%s platform=%s",
        waba_id, phone_number_id, display_phone, status, platform_type,
    )

    # 4. Registrar o webhook do app no WABA
    subscribe_url = f"{GRAPH_API_BASE}/{waba_id}/subscribed_apps"
    async with httpx.AsyncClient(timeout=15.0) as client:
        sub_resp = await client.post(
            subscribe_url,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        sub_data = sub_resp.json()

    webhook_subscribed = sub_data.get("success", False)
    logger.info("Embedded Signup: webhook subscription = %s", webhook_subscribed)

    # 5. Criar canal no registry
    # Determinar tipo: coexistence se platform_type indica app onboarding
    is_coexistence = platform_type in ("CLOUD_API",) and body.channel_type == "coexistence"
    channel_type = CHANNEL_TYPE_COEXISTENCE if is_coexistence else CHANNEL_TYPE_STANDARD
    owner_id = body.owner_user_id if is_coexistence else None

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
        owner_user_id=owner_id,
        owner_firebase_uid=(owner_user or {}).get("firebase_uid", ""),
        default_department_id=body.default_department_id,
        is_bot_enabled=not is_coexistence,
    )

    log_audit(
        current_user["id"],
        "EMBEDDED_SIGNUP",
        f"WABA={waba_id} Phone={phone_number_id} ({display_phone}) status={status} channel_id={new_channel_id}",
    )

    return {
        "status": "ok",
        "channel_id": new_channel_id,
        "channel_type": channel_type,
        "access_token": access_token,
        "waba_id": waba_id,
        "phone_number_id": phone_number_id,
        "display_phone_number": display_phone,
        "verified_name": verified_name,
        "quality_rating": quality_rating,
        "platform_type": platform_type,
        "phone_status": status,
        "webhook_subscribed": webhook_subscribed,
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
