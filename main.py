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

from config import (
    HOST, PORT, MAX_MESSAGE_LENGTH, BASE_DIR, LOG_FILE, LOG_LEVEL, LOG_TO_FILE,
    WHATSAPP_VERIFY_TOKEN, WHATSAPP_TOKEN,
    WHATSAPP_PHONE_NUMBER_ID, GRAPH_API_BASE,
    AVATAR_MAX_SIZE_KB, AVATAR_ALLOWED_MIME,
    QUALIFICATION_OPTIONS, ROLE_OPTIONS,
    BOOTSTRAP_ADMIN_USERNAME, BOOTSTRAP_ADMIN_PASSWORD,
    BOOTSTRAP_ADMIN_DISPLAY_NAME, BOOTSTRAP_ADMIN_DEPARTMENT,
)
from database import (
    init_database, get_user_by_id, get_all_users,
    save_internal_message, get_internal_conversation,
    mark_messages_as_read, get_unread_count,
    get_all_wa_contacts, get_wa_conversation, get_wa_unread_count,
    mark_wa_conversation_read, save_wa_message, get_wa_contact,
    log_audit, normalize_br_phone,
    get_all_departments, create_department,
    assign_wa_contact, get_transfer_history,
    update_user_avatar, get_user_avatar,
    create_user, update_user, deactivate_user, get_user_by_username,
    update_wa_contact_qualification, archive_wa_contact, restore_wa_contact,
    update_contact_avatar, insert_transfer_system_message,
)
from auth import authenticate, decode_token, hash_password
from webhook import process_webhook_payload, validate_signature
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

app = FastAPI(
    title="Castro Intelligence CRM",
    version="0.4.0",
    docs_url=None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

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


# -- Dependencias --

def get_current_user(request: Request):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token ausente")
    token = auth_header.split(" ", 1)[1]
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


def bootstrap_admin_user():
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


# -- Startup --

@app.on_event("startup")
async def startup():
    init_database()
    bootstrap_admin_user()
    ensure_media_dir()
    logger.info("CRM iniciado | host=%s port=%d", HOST, PORT)
    if WHATSAPP_TOKEN:
        logger.info("WABA configurado | phone_id=%s", WHATSAPP_PHONE_NUMBER_ID)
    else:
        logger.warning("WHATSAPP_TOKEN nao definido - webhook ativo mas envio desabilitado")


# -- Paginas HTML --

@app.get("/", response_class=HTMLResponse)
async def index():
    with open(os.path.join(BASE_DIR, "static", "index.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/chat", response_class=HTMLResponse)
async def chat_page():
    with open(os.path.join(BASE_DIR, "static", "chat.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


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
    unread_counts = get_wa_unread_count()
    for c in contacts:
        c["unread"] = unread_counts.get(c["id"], 0)
    return {"contacts": contacts}


@app.get("/api/wa/messages/{contact_id}")
async def wa_messages(contact_id: int, current_user: dict = Depends(get_current_user)):
    messages = get_wa_conversation(contact_id)
    mark_wa_conversation_read(contact_id)
    return {"messages": messages}


@app.post("/api/wa/send")
async def wa_send(body: WaSendRequest, current_user: dict = Depends(get_current_user)):
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        raise HTTPException(status_code=503, detail="WABA nao configurado")
    contact = get_wa_contact(body.contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    if contact.get("assigned_to") and contact["assigned_to"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Atendimento atribuido a outro operador")

    wa_id = normalize_br_phone(contact["wa_id"])
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

    file_content = await file.read()
    if len(file_content) > 16 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Arquivo excede 16MB")

    mime_type = file.content_type or "application/octet-stream"
    filename = file.filename or "upload"
    local_result = await save_upload_media(file_content, filename, mime_type)
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

    raw_content = await file.read()
    if len(raw_content) > 16 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio excede 16MB")

    original_mime = file.content_type or "audio/webm"

    # Converter WebM/Opus -> OGG/Opus (formato exigido pelo WhatsApp)
    converted = convert_audio_to_ogg_opus(raw_content, original_mime)
    if not converted:
        raise HTTPException(status_code=500, detail="Falha na conversao do audio. Verifique se o FFmpeg esta instalado.")

    # Salvar versao convertida localmente
    local_result = await save_upload_media(converted, "gravacao.ogg", "audio/ogg")

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
        "messaging_product": "whatsapp", "to": normalize_br_phone(contact["wa_id"]),
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


# -- Execucao --

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True, log_level="info")
