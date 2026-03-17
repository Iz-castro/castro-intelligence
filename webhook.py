# -*- coding: utf-8 -*-

"""
Processamento de eventos recebidos via webhook da Meta Cloud API.
Trata mensagens de texto, imagem, audio, video, sticker, localizacao e documentos.
"""

import hmac
import hashlib
import logging
from datetime import datetime, timezone

from config import WHATSAPP_APP_SECRET
from database import (
    upsert_wa_contact, save_wa_message, update_wa_message_status, log_audit,
)
from media import download_media

logger = logging.getLogger("castro_crm.webhook")


def validate_signature(payload_bytes, signature_header):
    """
    Valida assinatura HMAC-SHA256 do webhook da Meta.
    Retorna True se valido ou se APP_SECRET nao esta configurado (modo dev).
    """
    if not WHATSAPP_APP_SECRET:
        return True  # Pular validacao em dev

    if not signature_header:
        logger.warning("Webhook recebido sem assinatura")
        return False

    expected = hmac.new(
        WHATSAPP_APP_SECRET.encode("utf-8"),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()

    received = signature_header.replace("sha256=", "")
    return hmac.compare_digest(expected, received)


async def process_webhook_payload(payload, ws_notify_callback=None):
    """
    Processa o payload completo do webhook.
    ws_notify_callback: funcao async para notificar clientes via WebSocket.
    """
    if payload.get("object") != "whatsapp_business_account":
        return

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})

            if "messages" in value:
                await _process_messages(value, ws_notify_callback)

            if "statuses" in value:
                _process_statuses(value)


async def _process_messages(value, ws_notify_callback):
    """Processa mensagens recebidas de clientes."""
    contacts_data = value.get("contacts", [])
    contact_info = contacts_data[0] if contacts_data else {}
    contact_name = contact_info.get("profile", {}).get("name", "")

    for msg in value.get("messages", []):
        wa_id = msg.get("from", "")
        msg_id = msg.get("id", "")
        msg_type = msg.get("type", "unknown")
        timestamp = msg.get("timestamp", "")

        # Converter timestamp Unix para ISO
        ts_iso = ""
        if timestamp:
            try:
                dt = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
                ts_iso = dt.isoformat()
            except (ValueError, OSError):
                ts_iso = datetime.now(timezone.utc).isoformat()

        # Registrar ou atualizar contato
        contact_id = upsert_wa_contact(wa_id, contact_name)

        # Extrair conteudo conforme o tipo
        content = ""
        media_path = ""
        media_mime = ""
        media_id_str = ""
        latitude = None
        longitude = None
        filename = ""

        if msg_type == "text":
            content = msg.get("text", {}).get("body", "")

        elif msg_type == "image":
            image = msg.get("image", {})
            media_id_str = image.get("id", "")
            media_mime = image.get("mime_type", "")
            content = image.get("caption", "")
            media_result = await download_media(media_id_str, "image")
            if media_result:
                media_path = media_result["path"]
                media_mime = media_result["mime_type"]

        elif msg_type == "audio":
            audio = msg.get("audio", {})
            media_id_str = audio.get("id", "")
            media_mime = audio.get("mime_type", "")
            media_result = await download_media(media_id_str, "audio")
            if media_result:
                media_path = media_result["path"]
                media_mime = media_result["mime_type"]

        elif msg_type == "video":
            video = msg.get("video", {})
            media_id_str = video.get("id", "")
            media_mime = video.get("mime_type", "")
            content = video.get("caption", "")
            media_result = await download_media(media_id_str, "video")
            if media_result:
                media_path = media_result["path"]
                media_mime = media_result["mime_type"]

        elif msg_type == "sticker":
            sticker = msg.get("sticker", {})
            media_id_str = sticker.get("id", "")
            media_mime = sticker.get("mime_type", "image/webp")
            media_result = await download_media(media_id_str, "sticker")
            if media_result:
                media_path = media_result["path"]
                media_mime = media_result["mime_type"]

        elif msg_type == "document":
            doc = msg.get("document", {})
            media_id_str = doc.get("id", "")
            media_mime = doc.get("mime_type", "")
            filename = doc.get("filename", "")
            content = doc.get("caption", "")
            media_result = await download_media(media_id_str, "document", filename)
            if media_result:
                media_path = media_result["path"]
                media_mime = media_result["mime_type"]

        elif msg_type == "location":
            loc = msg.get("location", {})
            latitude = loc.get("latitude")
            longitude = loc.get("longitude")
            loc_name = loc.get("name", "")
            loc_address = loc.get("address", "")
            content = f"{loc_name} {loc_address}".strip() if (loc_name or loc_address) else ""

        elif msg_type == "contacts":
            # Cartao de contato - salvar como texto JSON
            content = str(msg.get("contacts", []))

        elif msg_type == "reaction":
            reaction = msg.get("reaction", {})
            content = reaction.get("emoji", "")

        else:
            content = f"[{msg_type}]"
            logger.info("Tipo de mensagem nao tratado: %s", msg_type)

        # Persistir
        db_id = save_wa_message(
            wa_message_id=msg_id,
            contact_id=contact_id,
            direction="inbound",
            msg_type=msg_type,
            content=content,
            media_path=media_path,
            media_mime=media_mime,
            media_id=media_id_str,
            latitude=latitude,
            longitude=longitude,
            filename=filename,
            status="received",
            timestamp_wa=ts_iso,
        )

        logger.info(
            "[WA IN] %s (%s) | tipo=%s | id=%s",
            contact_name, wa_id, msg_type, msg_id[:20]
        )

        # Notificar operadores conectados via WebSocket
        if ws_notify_callback:
            await ws_notify_callback({
                "event": "wa_new_message",
                "data": {
                    "id": db_id,
                    "contact_id": contact_id,
                    "contact_name": contact_name,
                    "wa_id": wa_id,
                    "msg_type": msg_type,
                    "content": content,
                    "media_path": media_path,
                    "media_mime": media_mime,
                    "latitude": latitude,
                    "longitude": longitude,
                    "filename": filename,
                    "timestamp": ts_iso,
                },
            })


def _process_statuses(value):
    """Processa atualizacoes de status de mensagens enviadas."""
    for status in value.get("statuses", []):
        msg_id = status.get("id", "")
        state = status.get("status", "")
        timestamp = status.get("timestamp", "")

        ts_iso = ""
        if timestamp:
            try:
                dt = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
                ts_iso = dt.isoformat()
            except (ValueError, OSError):
                pass

        update_wa_message_status(msg_id, state, ts_iso)
        logger.info("[WA STATUS] %s -> %s", msg_id[:20], state)
