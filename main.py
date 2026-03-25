# -*- coding: utf-8 -*-

import html
import logging
import os
from datetime import datetime, timezone

import httpx
from fastapi import (
    FastAPI, WebSocket, WebSocketDisconnect, Request,
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
    WHATSAPP_PHONE_NUMBER_ID, GRAPH_API_BASE,
    AVATAR_MAX_SIZE_KB, AVATAR_ALLOWED_MIME,
    QUALIFICATION_OPTIONS, ROLE_OPTIONS,
    BOOTSTRAP_ADMIN_USERNAME, BOOTSTRAP_ADMIN_PASSWORD,
    BOOTSTRAP_ADMIN_EMAIL, BOOTSTRAP_ADMIN_DISPLAY_NAME, BOOTSTRAP_ADMIN_DEPARTMENT,
    CORS_ORIGINS, GCS_MEDIA_BUCKET, IS_CLOUD_RUN,
    MEDIA_STORAGE_BACKEND, REQUIRE_WEBHOOK_SIGNATURE, WHATSAPP_APP_SECRET,
    CHAT_DELIVERY_MODE, POLLING_INTERVAL_MS, AUTH_MODE, USE_FIREBASE_AUTH,
    FIRESTORE_PROJECT_ID, FIREBASE_STORAGE_BUCKET,
    FIREBASE_WEB_API_KEY, FIREBASE_WEB_AUTH_DOMAIN, FIREBASE_WEB_APP_ID,
    FIREBASE_WEB_MESSAGING_SENDER_ID, FIREBASE_WEB_MEASUREMENT_ID,
    ALLOWED_FIREBASE_EMAIL_DOMAIN,
)
from database import (
    init_database, get_user_by_id, get_all_users,
    save_internal_message, get_internal_conversation,
    mark_messages_as_read, get_unread_count,
    get_all_wa_contacts, get_wa_conversation,
    mark_wa_conversation_read, save_wa_message, get_wa_contact,
    log_audit, normalize_br_phone,
    get_all_departments, create_department,
    assign_wa_contact, get_transfer_history,
    update_user_avatar, get_user_avatar,
    create_user, update_user, deactivate_user, get_user_by_username,
    upsert_firebase_user, get_user_by_email,
    update_wa_contact_qualification, archive_wa_contact, restore_wa_contact,
    update_contact_avatar, insert_transfer_system_message, set_attendance_protocol,
    get_wa_message_by_id, update_wa_message_transcription,
    get_system_settings, save_system_settings,
    get_user_settings, save_user_settings,
    get_all_gc_conversations, get_gc_messages, save_gc_message,
    mark_gc_conversation_read, upsert_gc_conversation,
)
from auth import authenticate, authenticate_firebase_token, decode_token, hash_password
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

# -- Modelos --

class LoginRequest(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def sanitize_username(cls, v):
        v = v.strip().lower()
        if not v or len(v) > 50:
            raise ValueError("Nome de usuario invalido")
        return v


class SendMessageRequest(BaseModel):
    receiver_id: int
    content: str
    msg_type: str = "text"

    @field_validator("content")
    @classmethod
    def validate_content(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Mensagem vazia")
        if len(v) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"Mensagem excede {MAX_MESSAGE_LENGTH} caracteres")
        return v


class WaSendRequest(BaseModel):
    contact_id: int
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


class WaSendLocationRequest(BaseModel):
    contact_id: int
    latitude: float
    longitude: float
    name: str = ""
    address: str = ""


# -- Dependencias --

def get_current_user(request: Request):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token ausente")
    token = auth_header.split(" ", 1)[1]
    ip = request.client.host if request.client else "unknown"

    if USE_FIREBASE_AUTH:
        result = authenticate_firebase_token(token, ip)
        if not result["success"]:
            raise HTTPException(status_code=result.get("status_code", 401), detail=result["error"])
        return result["user"]

    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token invalido ou expirado")
    user = get_user_by_id(payload["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="Usuario nao encontrado")
    return user


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
    return USE_FIREBASE_AUTH and os.path.isfile(FRONTEND_INDEX_FILE)


def _serve_frontend_or_static(_filename):
    if not os.path.isfile(FRONTEND_INDEX_FILE):
        return HTMLResponse(content="<h1>Frontend nao compilado. Execute: cd frontend && npm run build</h1>", status_code=503)
    return FileResponse(FRONTEND_INDEX_FILE)


def bootstrap_admin_user():
    if USE_FIREBASE_AUTH:
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
        return

    if not BOOTSTRAP_ADMIN_USERNAME or not BOOTSTRAP_ADMIN_PASSWORD:
        logger.info("Bootstrap admin nao configurado")
        return

    existing = get_user_by_username(BOOTSTRAP_ADMIN_USERNAME)
    if existing:
        logger.info("Bootstrap admin ja existe | username=%s", BOOTSTRAP_ADMIN_USERNAME)
        return

    department_id = create_department(
        BOOTSTRAP_ADMIN_DEPARTMENT,
        "Setor criado automaticamente no primeiro deploy",
    )
    user_id = create_user(
        BOOTSTRAP_ADMIN_USERNAME,
        BOOTSTRAP_ADMIN_DISPLAY_NAME,
        hash_password(BOOTSTRAP_ADMIN_PASSWORD),
        department_id,
        "admin",
    )
    if user_id:
        logger.info("Bootstrap admin criado | username=%s", BOOTSTRAP_ADMIN_USERNAME)
    else:
        logger.warning("Falha ao criar bootstrap admin | username=%s", BOOTSTRAP_ADMIN_USERNAME)


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
    if FEATURE_AUDIO_TRANSCRIPTION:
        from transcription_service import init_speech_client
        if init_speech_client():
            logger.info("Transcricao de audio habilitada (Faster Whisper)")
        else:
            logger.warning("Transcricao de audio desabilitada (Faster Whisper falhou)")
    logger.info("CRM iniciado | host=%s port=%d", HOST, PORT)
    if WHATSAPP_TOKEN:
        logger.info("WABA configurado | phone_id=%s", WHATSAPP_PHONE_NUMBER_ID)
    else:
        logger.warning("WHATSAPP_TOKEN nao definido - webhook ativo mas envio desabilitado")


# -- Paginas HTML --

@app.get("/", response_class=HTMLResponse)
async def index():
    return _serve_frontend_or_static("index.html")


@app.get("/chat", response_class=HTMLResponse)
async def chat_page():
    return _serve_frontend_or_static("chat.html")


@app.get("/app", response_class=HTMLResponse)
async def app_shell():
    if not _frontend_build_available():
        raise HTTPException(status_code=404, detail="Frontend React nao buildado")
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
async def login(body: LoginRequest, request: Request):
    if USE_FIREBASE_AUTH:
        raise HTTPException(status_code=405, detail="Use Firebase Auth no frontend e envie o ID token nas chamadas da API")
    ip = request.client.host if request.client else "unknown"
    result = authenticate(body.username, body.password, ip)
    if not result["success"]:
        return JSONResponse(status_code=401, content={"error": result["error"]})
    avatar = get_user_avatar(result["user"]["id"])
    user_data = result["user"]
    user_data["avatar_path"] = avatar or ""
    full_user = get_user_by_id(result["user"]["id"])
    user_data["role"] = full_user.get("role", "operador") if full_user else "operador"
    return {"token": result["token"], "user": user_data}


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
    username = (body.get("username", "")).strip().lower()
    display_name = (body.get("display_name", "")).strip()
    password = body.get("password", "")
    department_id = body.get("department_id")
    role = body.get("role", "operador")
    if not username or not display_name or not password:
        raise HTTPException(status_code=400, detail="Campos obrigatorios: username, display_name, password")
    if len(username) > 50 or len(display_name) > 100:
        raise HTTPException(status_code=400, detail="Nome excede limite de caracteres")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Senha deve ter pelo menos 6 caracteres")
    if role not in ROLE_OPTIONS:
        raise HTTPException(status_code=400, detail=f"Cargo invalido. Opcoes: {', '.join(ROLE_OPTIONS)}")
    pw_hash = hash_password(password)
    user_id = create_user(username, display_name, pw_hash, department_id, role)
    if not user_id:
        raise HTTPException(status_code=409, detail="Usuario ja existe")
    log_audit(current_user["id"], "USER_CREATE", f"{username} ({role})")
    return {"status": "ok", "user_id": user_id}


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


# -- API: Chat Interno --

@app.get("/api/users")
async def list_users(current_user: dict = Depends(get_current_user)):
    users = get_all_users()
    return [
        {
            "id": u["id"], "display_name": u["display_name"],
            "last_login": u["last_login"], "avatar_path": u.get("avatar_path", ""),
            "role": u.get("role", "operador"), "department_name": u.get("department_name", ""),
        }
        for u in users if u["id"] != current_user["id"] and u.get("is_active")
    ]


@app.get("/api/messages/{contact_id}")
async def get_messages(contact_id: int, current_user: dict = Depends(get_current_user)):
    messages = get_internal_conversation(current_user["id"], contact_id)
    mark_messages_as_read(current_user["id"], contact_id)
    return {"messages": messages}


@app.get("/api/unread")
async def unread(current_user: dict = Depends(get_current_user)):
    return {"unread": get_unread_count(current_user["id"])}


@app.post("/api/messages")
async def send_internal_message(body: SendMessageRequest, current_user: dict = Depends(get_current_user)):
    receiver = get_user_by_id(body.receiver_id)
    if not receiver:
        raise HTTPException(status_code=404, detail="Destinatario nao encontrado")
    sanitized = html.escape(body.content)
    msg_id = save_internal_message(current_user["id"], body.receiver_id, sanitized, body.msg_type)
    ws_conn = operator_connections.get(body.receiver_id)
    if ws_conn:
        try:
            await ws_conn.send_json({
                "event": "new_message",
                "data": {
                    "id": msg_id, "sender_id": current_user["id"],
                    "sender_name": current_user["display_name"],
                    "sender_avatar": current_user.get("avatar_path", ""),
                    "content": sanitized, "msg_type": body.msg_type,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            })
        except Exception:
            pass
    return {"id": msg_id, "status": "sent"}


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
    mark_wa_conversation_read(contact_id)
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


@app.post("/api/wa/send-location")
async def wa_send_location(body: WaSendLocationRequest, current_user: dict = Depends(get_current_user)):
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        raise HTTPException(status_code=503, detail="WABA nao configurado")
    contact = get_wa_contact(body.contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    _check_24h_window(contact)

    wa_id = contact["wa_id"]
    url = f"{GRAPH_API_BASE}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}

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
        )
        log_audit(current_user["id"], "WA_SEND_LOCATION", f"Para {wa_id}: {body.latitude},{body.longitude}")
        return {"status": "sent", "wa_message_id": wa_msg_id}

    error_msg = result.get("error", {}).get("message", "Erro desconhecido")
    raise HTTPException(status_code=502, detail=error_msg)


@app.post("/api/wa/send")
async def wa_send(body: WaSendRequest, current_user: dict = Depends(get_current_user)):
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        raise HTTPException(status_code=503, detail="WABA nao configurado")
    contact = get_wa_contact(body.contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    if contact.get("assigned_to") and contact["assigned_to"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Atendimento atribuido a outro operador")
    _check_24h_window(contact)

    wa_id = _wa_target(contact["wa_id"])
    url = f"{GRAPH_API_BASE}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": wa_id, "type": "text", "text": {"body": body.content}}

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        result = resp.json()

    if resp.status_code == 200:
        wa_msg_id = result.get("messages", [{}])[0].get("id", "")
        save_wa_message(
            wa_message_id=wa_msg_id, contact_id=body.contact_id, direction="outbound",
            msg_type="text", content=body.content, status="sent",
            timestamp_wa=datetime.now(timezone.utc).isoformat(), operator_id=current_user["id"],
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
):
    current_user = get_current_user(request)
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        raise HTTPException(status_code=503, detail="WABA nao configurado")
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    if contact.get("assigned_to") and contact["assigned_to"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Atendimento atribuido a outro operador")
    _check_24h_window(contact)

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

    media_id = await upload_media_to_whatsapp(file_content, mime_type, filename)
    if not media_id:
        raise HTTPException(status_code=502, detail="Falha no upload para a Meta")

    send_result = await send_media_message(contact["wa_id"], media_id, msg_type, caption)
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
    )
    log_audit(current_user["id"], "WA_SEND_MEDIA", f"{msg_type} para {contact['wa_id']}: {filename}")
    return {"status": "sent", "wa_message_id": wa_msg_id, "msg_type": msg_type, "media_path": local_result["path"]}


@app.post("/api/wa/send-audio")
async def wa_send_audio(
    request: Request, contact_id: int = Form(...), file: UploadFile = File(...),
):
    """Envia audio gravado pelo microfone para contato WhatsApp.
    Converte WebM/Opus do navegador para OGG/Opus via FFmpeg."""
    current_user = get_current_user(request)

    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        raise HTTPException(status_code=503, detail="WABA nao configurado")

    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    if contact.get("assigned_to") and contact["assigned_to"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Atendimento atribuido a outro operador")
    _check_24h_window(contact)

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
    media_id = await upload_media_to_whatsapp(converted, "audio/ogg", "audio.ogg")
    if not media_id:
        raise HTTPException(status_code=502, detail="Falha no upload de audio para a Meta")

    # Enviar mensagem de audio
    send_result = await send_media_message(contact["wa_id"], media_id, "audio")
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
    )
    log_audit(current_user["id"], "WA_SEND_AUDIO", f"Para {contact['wa_id']}")
    return {"status": "sent", "wa_message_id": wa_msg_id, "msg_type": "audio", "media_path": local_result["path"]}


@app.post("/api/wa/send-template")
async def wa_send_template(
    contact_id: int, template_name: str = "hello_world",
    language: str = "pt_BR", current_user: dict = Depends(get_current_user),
):
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        raise HTTPException(status_code=503, detail="WABA nao configurado")
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    url = f"{GRAPH_API_BASE}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
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
    return {"status": "ok"}


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

    if to_user_id and to_user_id in operator_connections:
        try:
            await operator_connections[to_user_id].send_json({
                "event": "wa_transfer_received",
                "data": {
                    "contact_id": contact_id, "contact_name": contact.get("display_name", ""),
                    "from_user": current_user["display_name"], "reason": reason, "summary": summary,
                },
            })
        except Exception:
            pass

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


@app.get("/api/operators")
async def list_operators(current_user: dict = Depends(get_current_user)):
    users = get_all_users()
    return [
        {
            "id": u["id"], "display_name": u["display_name"],
            "department_name": u.get("department_name", ""),
            "department_id": u.get("department_id"),
            "avatar_path": u.get("avatar_path", ""),
            "role": u.get("role", "operador"),
            "email": u.get("email", ""),
            "firebase_uid": u.get("firebase_uid", ""),
        }
        for u in users if u.get("is_active")
    ]


# -- WebSocket --

operator_connections: dict[int, WebSocket] = {}


async def broadcast_to_operators(message: dict):
    disconnected = []
    for uid, conn in operator_connections.items():
        try:
            await conn.send_json(message)
        except Exception:
            disconnected.append(uid)
    for uid in disconnected:
        operator_connections.pop(uid, None)


@app.websocket("/ws/{token}")
async def websocket_endpoint(websocket: WebSocket, token: str):
    payload = decode_token(token)
    if not payload:
        await websocket.close(code=4001, reason="Token invalido")
        return
    user_id = payload["sub"]
    user = get_user_by_id(user_id)
    if not user:
        await websocket.close(code=4001, reason="Usuario invalido")
        return

    await websocket.accept()
    operator_connections[user_id] = websocket
    logger.info("WS conectado: %s (id=%d)", user["display_name"], user_id)

    for uid, conn in operator_connections.items():
        if uid != user_id:
            try:
                await conn.send_json({
                    "event": "user_online",
                    "data": {
                        "user_id": user_id, "display_name": user["display_name"],
                        "avatar_path": user.get("avatar_path", ""), "role": user.get("role", ""),
                    },
                })
            except Exception:
                pass

    try:
        while True:
            data = await websocket.receive_json()
            event = data.get("event")

            if event == "send_message":
                receiver_id = data.get("receiver_id")
                content = data.get("content", "").strip()
                if not content or len(content) > MAX_MESSAGE_LENGTH:
                    await websocket.send_json({"event": "error", "data": {"detail": "Mensagem invalida"}})
                    continue
                receiver = get_user_by_id(receiver_id)
                if not receiver:
                    await websocket.send_json({"event": "error", "data": {"detail": "Destinatario invalido"}})
                    continue
                sanitized = html.escape(content)
                msg_id = save_internal_message(user_id, receiver_id, sanitized)
                now = datetime.now(timezone.utc).isoformat()
                await websocket.send_json({
                    "event": "message_sent",
                    "data": {"id": msg_id, "receiver_id": receiver_id, "content": sanitized, "created_at": now},
                })
                ws_dest = operator_connections.get(receiver_id)
                if ws_dest:
                    try:
                        await ws_dest.send_json({
                            "event": "new_message",
                            "data": {
                                "id": msg_id, "sender_id": user_id,
                                "sender_name": user["display_name"],
                                "sender_avatar": user.get("avatar_path", ""),
                                "content": sanitized, "msg_type": "text", "created_at": now,
                            },
                        })
                    except Exception:
                        pass

            elif event == "mark_read":
                sender_id = data.get("sender_id")
                if sender_id:
                    mark_messages_as_read(user_id, sender_id)
                    ws_sender = operator_connections.get(sender_id)
                    if ws_sender:
                        try:
                            await ws_sender.send_json({"event": "messages_read", "data": {"reader_id": user_id}})
                        except Exception:
                            pass

            elif event == "typing":
                receiver_id = data.get("receiver_id")
                ws_dest = operator_connections.get(receiver_id)
                if ws_dest:
                    try:
                        await ws_dest.send_json({"event": "typing", "data": {"user_id": user_id, "display_name": user["display_name"]}})
                    except Exception:
                        pass

    except WebSocketDisconnect:
        logger.info("WS desconectado: %s (id=%d)", user["display_name"], user_id)
    except Exception as exc:
        logger.error("Erro WS (user_id=%d): %s", user_id, exc)
    finally:
        operator_connections.pop(user_id, None)
        for uid, conn in operator_connections.items():
            try:
                await conn.send_json({"event": "user_offline", "data": {"user_id": user_id}})
            except Exception:
                pass


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


# -- Execucao --

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True, log_level="info")
