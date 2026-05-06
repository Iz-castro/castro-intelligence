# -*- coding: utf-8 -*-

"""
Processamento de eventos recebidos via webhook do Google Chat.
Valida JWT do Google e processa mensagens (texto, audio, anexos).
"""

import logging

import httpx
import jwt

from config import GOOGLE_CHAT_PROJECT_NUMBER
from database import (
    upsert_gc_conversation, save_gc_message, log_audit,
)
from google_chat import download_attachment
from media import save_upload_media
from pii_redaction import redact_name

logger = logging.getLogger("castro_crm.webhook_gchat")

# Chaves publicas do Google para validar JWT
GOOGLE_CHAT_CERTS_URL = (
    "https://www.googleapis.com/service_accounts/v1/metadata/x509/"
    "chat@system.gserviceaccount.com"
)

_cached_certs = None


async def _fetch_google_certs():
    """Busca (e cacheia) certificados publicos do Google Chat."""
    global _cached_certs
    if _cached_certs:
        return _cached_certs
    async with httpx.AsyncClient() as client:
        resp = await client.get(GOOGLE_CHAT_CERTS_URL)
        resp.raise_for_status()
        _cached_certs = resp.json()
        return _cached_certs


def _get_public_key(certs, kid):
    """Extrai chave publica pelo kid do header JWT."""
    pem = certs.get(kid)
    if not pem:
        return None
    from cryptography.x509 import load_pem_x509_certificate
    cert = load_pem_x509_certificate(pem.encode("utf-8"))
    return cert.public_key()


async def validate_google_chat_token(auth_header):
    """Valida Bearer token JWT enviado pelo Google Chat.

    Verifica:
    - Assinatura com chave publica do Google
    - Emissor (iss) e chat@system.gserviceaccount.com
    - Audience corresponde ao project number
    """
    if not auth_header or not auth_header.startswith("Bearer "):
        logger.warning("Webhook Google Chat: header Authorization ausente")
        return False

    token = auth_header.split(" ", 1)[1]

    try:
        # Decodificar header para pegar kid
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        if not kid:
            logger.warning("Webhook Google Chat: JWT sem kid no header")
            return False

        certs = await _fetch_google_certs()
        public_key = _get_public_key(certs, kid)
        if not public_key:
            # Tentar refresh dos certs (pode ter rotacionado)
            global _cached_certs
            _cached_certs = None
            certs = await _fetch_google_certs()
            public_key = _get_public_key(certs, kid)
            if not public_key:
                logger.warning("Webhook Google Chat: kid=%s nao encontrado nos certs", kid)
                return False

        # Validar JWT
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=GOOGLE_CHAT_PROJECT_NUMBER,
            issuer="chat@system.gserviceaccount.com",
        )
        logger.debug("Webhook Google Chat: JWT validado | sub=%s", payload.get("sub"))
        return True

    except jwt.ExpiredSignatureError:
        logger.warning("Webhook Google Chat: JWT expirado")
        return False
    except jwt.InvalidAudienceError:
        logger.warning("Webhook Google Chat: audience invalido")
        return False
    except jwt.InvalidIssuerError:
        logger.warning("Webhook Google Chat: issuer invalido")
        return False
    except Exception as exc:
        logger.error("Webhook Google Chat: erro na validacao JWT: %s", exc, exc_info=True)
        return False


async def process_google_chat_event(event):
    """Processa evento recebido do Google Chat.

    Tipos de eventos:
    - ADDED_TO_SPACE: Bot adicionado a um space
    - REMOVED_FROM_SPACE: Bot removido de um space
    - MESSAGE: Nova mensagem no space
    - CARD_CLICKED: Acao em card interativo (futuro)
    """
    event_type = event.get("type", "")
    space = event.get("space", {})
    space_id = space.get("name", "")
    space_name = space.get("displayName", "")
    user = event.get("user", {})
    sender_email = user.get("email", "")
    sender_name = user.get("displayName", "")

    if event_type == "ADDED_TO_SPACE":
        logger.info("[GC] Bot adicionado ao space: %s (%s)", space_name, space_id)
        upsert_gc_conversation(
            space_id=space_id,
            space_name=space_name or space_id,
        )
        return {"text": "Hubloc CRM conectado! Mensagens deste space serao sincronizadas com o CRM."}

    elif event_type == "REMOVED_FROM_SPACE":
        logger.info("[GC] Bot removido do space: %s", space_id)
        return {}

    elif event_type == "MESSAGE":
        message = event.get("message", {})
        return await _process_gchat_message(
            message=message,
            space_id=space_id,
            space_name=space_name,
            sender_email=sender_email,
            sender_name=sender_name,
        )

    else:
        logger.info("[GC] Evento nao tratado: %s", event_type)
        return {}


async def _process_gchat_message(message, space_id, space_name, sender_email, sender_name):
    """Processa uma mensagem recebida do Google Chat."""
    gchat_message_id = message.get("name", "")
    text = message.get("text", "") or message.get("argumentText", "")
    create_time = message.get("createTime", "")
    attachments = message.get("attachment", [])

    # Garantir que a conversa existe
    conversation_id = upsert_gc_conversation(
        space_id=space_id,
        space_name=space_name or space_id,
    )

    # Processar anexos (audio, imagens, documentos)
    media_path = ""
    media_mime = ""
    msg_type = "text"

    if attachments:
        attachment = attachments[0]  # Processar primeiro anexo
        content_type = attachment.get("contentType", "")
        resource_name = attachment.get("attachmentDataRef", {}).get("resourceName", "")

        if content_type.startswith("audio/"):
            msg_type = "audio"
        elif content_type.startswith("image/"):
            msg_type = "image"
        elif content_type.startswith("video/"):
            msg_type = "video"
        else:
            msg_type = "document"

        media_mime = content_type

        # Baixar e armazenar o anexo
        if resource_name:
            try:
                content_bytes = download_attachment(resource_name)
                if content_bytes:
                    ext = _mime_to_ext(content_type)
                    filename = f"gchat_{gchat_message_id.split('/')[-1]}{ext}"
                    result = await save_upload_media(content_bytes, filename, content_type)
                    if result:
                        media_path = result.get("path", "")
            except Exception as exc:
                logger.error("[GC] Erro ao baixar anexo: %s", exc, exc_info=True)

    # Salvar mensagem no Firestore
    message_id = save_gc_message(
        conversation_id=conversation_id,
        gchat_message_id=gchat_message_id,
        sender_email=sender_email,
        sender_name=sender_name,
        msg_type=msg_type,
        content=text,
        media_path=media_path,
        media_mime=media_mime,
        source="google_chat",
        create_time=create_time,
    )

    logger.info(
        "[GC IN] %s (%s) | tipo=%s | space=%s",
        redact_name(sender_name), redact_name(sender_email), msg_type, space_id,
    )

    return {}


def _mime_to_ext(mime_type):
    """Converte MIME type para extensao de arquivo."""
    mapping = {
        "audio/ogg": ".ogg",
        "audio/mp4": ".m4a",
        "audio/mpeg": ".mp3",
        "audio/webm": ".webm",
        "audio/3gpp": ".3gp",
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "video/mp4": ".mp4",
        "video/3gpp": ".3gp",
        "application/pdf": ".pdf",
    }
    return mapping.get(mime_type, ".bin")
