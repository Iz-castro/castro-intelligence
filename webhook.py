# -*- coding: utf-8 -*-

"""
Processamento de eventos recebidos via webhook da Meta Cloud API.
Trata mensagens de texto, imagem, audio, video, sticker, localizacao e documentos.
"""

import hmac
import hashlib
import logging
from datetime import datetime, timezone

from config import REQUIRE_WEBHOOK_SIGNATURE, WHATSAPP_APP_SECRET, FEATURE_AUDIO_TRANSCRIPTION, FEATURE_MESSAGE_STATUS, STT_LANGUAGE_CODE, STT_TIMEOUT_SECONDS, STT_FALLBACK_TEXT
from database import (
    upsert_wa_contact, save_wa_message, update_wa_message_status, log_audit,
    update_wa_message_transcription,
    get_user_by_id, get_wa_message_by_wa_message_id,
)
from media import download_media

logger = logging.getLogger("castro_crm.webhook")


def _fallback_reply_preview(message):
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


def _fallback_reply_sender(message):
    direction = str(message.get("direction") or "").strip().lower()
    if direction == "inbound":
        return "Cliente"
    if direction == "system":
        return "Sistema"
    operator_id = message.get("operator_id")
    operator = get_user_by_id(operator_id) if operator_id else None
    return str((operator or {}).get("display_name") or "Equipe")


def _resolve_reply_reference(contact_id, message_context):
    context = message_context if isinstance(message_context, dict) else {}
    original_wa_message_id = str(context.get("id") or "").strip()
    if not original_wa_message_id:
        return {}

    original_message = get_wa_message_by_wa_message_id(original_wa_message_id)
    if not original_message:
        logger.info("Resposta recebida sem mensagem original local | wa_context_id=%s", original_wa_message_id[:32])
        return {}
    if int(original_message.get("contact_id") or 0) != int(contact_id):
        logger.warning(
            "Resposta recebida com contexto de outro contato | contact_id=%s original_contact_id=%s wa_context_id=%s",
            contact_id,
            original_message.get("contact_id"),
            original_wa_message_id[:32],
        )
        return {}

    return {
        "reply_to_message_id": int(original_message.get("id") or 0) or None,
        "reply_to_preview": _fallback_reply_preview(original_message)[:280],
        "reply_to_sender_name": _fallback_reply_sender(original_message)[:80],
    }


def validate_signature(payload_bytes, signature_header):
    """
    Valida assinatura HMAC-SHA256 do webhook da Meta.
    Em dev pode operar sem APP_SECRET; em runtime endurecido a assinatura e obrigatoria.
    """
    if not WHATSAPP_APP_SECRET:
        return not REQUIRE_WEBHOOK_SIGNATURE

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

            if "statuses" in value and FEATURE_MESSAGE_STATUS:
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
        reply_fields = _resolve_reply_reference(contact_id, msg.get("context"))

        # Extrair conteudo conforme o tipo
        content = ""
        media_path = ""
        media_mime = ""
        media_id_str = ""
        latitude = None
        longitude = None
        filename = ""
        effective_msg_type = msg_type
        _audio_bytes_for_stt = None
        _audio_mime_for_stt = None
        image = msg.get("image", {}) if isinstance(msg.get("image"), dict) else {}
        audio = msg.get("audio", {}) if isinstance(msg.get("audio"), dict) else {}
        video = msg.get("video", {}) if isinstance(msg.get("video"), dict) else {}
        sticker = msg.get("sticker", {}) if isinstance(msg.get("sticker"), dict) else {}
        document_msg = msg.get("document", {}) if isinstance(msg.get("document"), dict) else {}
        unsupported = msg.get("unsupported", {}) if isinstance(msg.get("unsupported"), dict) else {}

        if msg_type == "text":
            content = msg.get("text", {}).get("body", "")

        elif msg_type == "image" or image.get("id"):
            effective_msg_type = "image"
            media_id_str = image.get("id", "")
            media_mime = image.get("mime_type", "")
            content = image.get("caption", "")
            media_result = await download_media(media_id_str, "image")
            if media_result:
                media_path = media_result["path"]
                media_mime = media_result["mime_type"]

        elif msg_type == "audio" or audio.get("id"):
            effective_msg_type = "audio"
            media_id_str = audio.get("id", "")
            media_mime = audio.get("mime_type", "")
            media_result = await download_media(media_id_str, "audio")
            if media_result:
                media_path = media_result["path"]
                media_mime = media_result["mime_type"]
            _audio_bytes_for_stt = media_result.get("content") if media_result else None
            _audio_mime_for_stt = media_mime

        elif msg_type == "video" or video.get("id"):
            effective_msg_type = "gif" if video.get("gif") else "video"
            media_id_str = video.get("id", "")
            media_mime = video.get("mime_type", "")
            content = video.get("caption", "")
            media_result = await download_media(media_id_str, "video")
            if media_result:
                media_path = media_result["path"]
                media_mime = media_result["mime_type"]

        elif msg_type == "sticker" or sticker.get("id"):
            effective_msg_type = "sticker"
            media_id_str = sticker.get("id", "")
            media_mime = sticker.get("mime_type", "image/webp")
            media_result = await download_media(media_id_str, "sticker")
            if media_result:
                media_path = media_result["path"]
                media_mime = media_result["mime_type"]

        elif msg_type == "document" or document_msg.get("id"):
            effective_msg_type = "document"
            media_id_str = document_msg.get("id", "")
            media_mime = document_msg.get("mime_type", "")
            filename = document_msg.get("filename", "")
            content = document_msg.get("caption", "")
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

        elif msg_type == "unsupported":
            errors = msg.get("errors", []) if isinstance(msg.get("errors"), list) else []
            error_code = ""
            if errors and isinstance(errors[0], dict):
                error_code = str(errors[0].get("code") or "")
            detail = unsupported.get("type", "") or error_code or "unsupported"
            content = f"[{detail}]"
            logger.info(
                "Mensagem unsupported sem midia tratavel | keys=%s | wa_id=%s | id=%s",
                sorted(msg.keys()),
                wa_id,
                msg_id[:20],
            )

        else:
            content = f"[{msg_type}]"
            logger.info("Tipo de mensagem nao tratado: %s", msg_type)

        # Persistir
        db_id = save_wa_message(
            wa_message_id=msg_id,
            contact_id=contact_id,
            direction="inbound",
            msg_type=effective_msg_type,
            content=content,
            media_path=media_path,
            media_mime=media_mime,
            media_id=media_id_str,
            latitude=latitude,
            longitude=longitude,
            filename=filename,
            status="received",
            timestamp_wa=ts_iso,
            **reply_fields,
        )

        logger.info(
            "[WA IN] %s (%s) | tipo=%s | id=%s",
            contact_name, wa_id, effective_msg_type, msg_id[:20]
        )

        # Transcricao de audio inbound
        if FEATURE_AUDIO_TRANSCRIPTION and _audio_bytes_for_stt and db_id:
            try:
                from transcription_service import get_speech_client, transcribe_audio_bytes
                speech_client = get_speech_client()
                if speech_client:
                    transcript = transcribe_audio_bytes(
                        _audio_bytes_for_stt,
                        media_mime=_audio_mime_for_stt,
                        language_code=STT_LANGUAGE_CODE,
                        timeout_s=STT_TIMEOUT_SECONDS,
                    )
                    if not transcript and STT_FALLBACK_TEXT:
                        transcript = STT_FALLBACK_TEXT
                    if transcript:
                        update_wa_message_transcription(db_id, transcript)
                        logger.info("[STT] Transcricao salva | msg_id=%s | len=%d", db_id, len(transcript))
            except Exception as stt_exc:
                logger.error("[STT] Falha na transcricao: %s", stt_exc, exc_info=True)

        # Notificar operadores conectados via WebSocket
        if ws_notify_callback:
            await ws_notify_callback({
                "event": "wa_new_message",
                "data": {
                    "id": db_id,
                    "contact_id": contact_id,
                    "contact_name": contact_name,
                    "wa_id": wa_id,
                    "msg_type": effective_msg_type,
                    "content": content,
                    "media_path": media_path,
                    "media_mime": media_mime,
                    "latitude": latitude,
                    "longitude": longitude,
                    "filename": filename,
                    "timestamp": ts_iso,
                    **reply_fields,
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
