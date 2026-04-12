# -*- coding: utf-8 -*-

"""
Processamento de eventos recebidos via webhook da Meta Cloud API.
Trata mensagens de texto, imagem, audio, video, sticker, localizacao e documentos.
"""

import hmac
import hashlib
import logging
from datetime import datetime, timezone

from config import (
    REQUIRE_WEBHOOK_SIGNATURE, WHATSAPP_APP_SECRET,
    FEATURE_AUDIO_TRANSCRIPTION, FEATURE_MESSAGE_STATUS,
    STT_LANGUAGE_CODE, STT_TIMEOUT_SECONDS, STT_FALLBACK_TEXT,
    WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_TOKEN,
)
from database import (
    upsert_wa_contact, save_wa_message, update_wa_message_status, log_audit,
    update_wa_message_transcription,
    get_user_by_id, get_wa_message_by_wa_message_id, get_wa_contact,
    assign_wa_contact, update_wa_contact_qualification,
    normalize_br_phone,
)
from media import download_media
from channel_service import get_channel_by_phone_id, get_default_channel, CHANNEL_TYPE_COEXISTENCE
from bot_service import process_bot_message

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


def _resolve_webhook_channel(value):
    """Resolve o canal a partir dos metadados do webhook.

    Retorna dict do canal ou None se nao encontrado.
    """
    metadata = value.get("metadata", {})
    phone_number_id = str(metadata.get("phone_number_id", "")).strip()

    if phone_number_id:
        channel = get_channel_by_phone_id(phone_number_id)
        if channel:
            return channel

    # Fallback: canal default
    return get_default_channel()


async def _send_bot_reply(wa_id: str, text: str, contact_id: int, token: str, phone_id: str):
    """Envia resposta do bot via WhatsApp Cloud API e salva no banco."""
    import httpx
    from config import GRAPH_API_BASE
    from database import save_wa_message

    wa_target = "".join(ch for ch in str(wa_id) if ch.isdigit())
    url = f"{GRAPH_API_BASE}/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload_msg = {
        "messaging_product": "whatsapp",
        "to": wa_target,
        "type": "text",
        "text": {"body": text},
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload_msg, headers=headers)
            result = resp.json()
        wa_msg_id = result.get("messages", [{}])[0].get("id", "") if resp.status_code == 200 else ""
        save_wa_message(
            wa_message_id=wa_msg_id,
            contact_id=contact_id,
            direction="outbound",
            msg_type="text",
            content=text,
            status="sent" if resp.status_code == 200 else "failed",
            timestamp_wa=datetime.now(timezone.utc).isoformat(),
            operator_id=None,
        )
        if resp.status_code == 200:
            logger.info("[BOT] Resposta enviada para %s | contact=%d", wa_id, contact_id)
        else:
            logger.warning("[BOT] Falha ao enviar resposta | status=%s | erro=%s", resp.status_code, result)
    except Exception as e:
        logger.error("[BOT] Erro ao enviar resposta: %s", e, exc_info=True)


async def process_webhook_payload(payload, ws_notify_callback=None):
    """
    Processa o payload completo do webhook.
    Roteia por campo 'field' para suportar webhooks padrao e de coexistence.
    Resolve o canal automaticamente a partir de metadata.phone_number_id.
    ws_notify_callback: funcao async para notificar clientes via WebSocket.
    """
    if payload.get("object") != "whatsapp_business_account":
        return

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            field = change.get("field", "")

            # Resolve canal para este change
            channel = _resolve_webhook_channel(value)

            if field == "smb_message_echoes":
                await _process_smb_message_echoes(value, ws_notify_callback, channel=channel)

            elif field == "smb_app_state_sync":
                _process_smb_app_state_sync(value)

            elif field == "history":
                await _process_history(value, ws_notify_callback, channel=channel)

            elif field == "account_update":
                _process_account_update(value)

            else:
                # Webhooks padrao da Cloud API (messages, statuses)
                if "messages" in value:
                    await _process_messages(value, ws_notify_callback, channel=channel)

                if "statuses" in value and FEATURE_MESSAGE_STATUS:
                    _process_statuses(value)


async def _process_messages(value, ws_notify_callback, channel=None):
    """Processa mensagens recebidas de clientes."""
    contacts_data = value.get("contacts", [])
    contact_info = contacts_data[0] if contacts_data else {}
    contact_name = contact_info.get("profile", {}).get("name", "")

    # Extrair dados do canal para enriquecer contato/mensagem
    channel_id = channel.get("id") if channel else None
    channel_phone_id = str(channel.get("phone_number_id", "")) if channel else ""
    channel_type = str(channel.get("channel_type", "")) if channel else ""
    channel_owner_id = channel.get("owner_user_id") if channel else None
    channel_token = str(channel.get("access_token", "")).strip() if channel else ""

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

        # Registrar ou atualizar contato (com dados do canal)
        contact_id = upsert_wa_contact(
            wa_id, contact_name,
            channel_id=channel_id,
            phone_number_id=channel_phone_id,
            source_channel_type=channel_type,
            auto_assign_user_id=channel_owner_id if channel_type == CHANNEL_TYPE_COEXISTENCE else None,
        )
        reply_fields = _resolve_reply_reference(contact_id, msg.get("context"))

        # Helper para download usando token do canal correto
        _dl_token = channel_token or WHATSAPP_TOKEN or None

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
            media_result = await download_media(media_id_str, "image", token=_dl_token)
            if media_result:
                media_path = media_result["path"]
                media_mime = media_result["mime_type"]

        elif msg_type == "audio" or audio.get("id"):
            effective_msg_type = "audio"
            media_id_str = audio.get("id", "")
            media_mime = audio.get("mime_type", "")
            media_result = await download_media(media_id_str, "audio", token=_dl_token)
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
            media_result = await download_media(media_id_str, "video", token=_dl_token)
            if media_result:
                media_path = media_result["path"]
                media_mime = media_result["mime_type"]

        elif msg_type == "sticker" or sticker.get("id"):
            effective_msg_type = "sticker"
            media_id_str = sticker.get("id", "")
            media_mime = sticker.get("mime_type", "image/webp")
            media_result = await download_media(media_id_str, "sticker", token=_dl_token)
            if media_result:
                media_path = media_result["path"]
                media_mime = media_result["mime_type"]

        elif msg_type == "document" or document_msg.get("id"):
            effective_msg_type = "document"
            media_id_str = document_msg.get("id", "")
            media_mime = document_msg.get("mime_type", "")
            filename = document_msg.get("filename", "")
            content = document_msg.get("caption", "")
            media_result = await download_media(media_id_str, "document", filename, token=_dl_token)
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
            channel_id=channel_id,
            phone_number_id=channel_phone_id,
            **reply_fields,
        )

        logger.info(
            "[WA IN] %s (%s) | tipo=%s | id=%s",
            contact_name, wa_id, effective_msg_type, msg_id[:20]
        )

        # -- Bot: processar mensagem se ativo e contato sem operador --
        if effective_msg_type == "text" and content.strip():
            _contact_for_bot = get_wa_contact(contact_id)
            if _contact_for_bot and not _contact_for_bot.get("assigned_to"):
                bot_reply = process_bot_message(contact_id, content, contact_name)
                if bot_reply:
                    _bot_token = (channel_token or WHATSAPP_TOKEN or "").strip()
                    _bot_phone_id = channel_phone_id or WHATSAPP_PHONE_NUMBER_ID
                    await _send_bot_reply(wa_id, bot_reply, contact_id, _bot_token, _bot_phone_id)

        # -- Lead convertido: capturar rating ou rerouting --
        _contact_fresh = get_wa_contact(contact_id)
        if _contact_fresh and _contact_fresh.get("qualification") == "convertido":
            _has_pending_rating = (
                _contact_fresh.get("rating_requested_at")
                and _contact_fresh.get("rating") is None
            )

            if _has_pending_rating and effective_msg_type == "text" and content.strip().isdigit():
                _rating_val = int(content.strip())
                if 1 <= _rating_val <= 10:
                    # Capturar avaliacao
                    from firestore_common import document as _fs_doc, utcnow as _fs_now
                    _fs_doc("wa_contacts", contact_id).set({
                        "rating": _rating_val,
                        "rating_received_at": _fs_now().isoformat(),
                    }, merge=True)
                    # Marcar a mensagem de resposta como admin_only
                    if db_id:
                        _fs_doc("wa_messages", db_id).set({
                            "is_rating_message": True,
                            "visibility": "admin_only",
                        }, merge=True)
                    logger.info("[RATING] Contato %d avaliou com nota %d", contact_id, _rating_val)
            else:
                # Nao eh rating — lead convertido retornando, reatribuir ao operador original
                _original_op = _contact_fresh.get("original_operator_id") or _contact_fresh.get("converted_by_user_id")
                if _original_op:
                    _op_user = get_user_by_id(_original_op)
                    if _op_user:
                        assign_wa_contact(
                            contact_id, _original_op,
                            _contact_fresh.get("department_id"),
                            transferred_by=None,
                            reason="Lead convertido retornou",
                            summary="Reatribuido automaticamente ao operador original",
                        )
                        update_wa_contact_qualification(contact_id, "em_atendimento")
                        logger.info(
                            "[REROUTE] Lead convertido %d reatribuido ao operador %d (%s)",
                            contact_id, _original_op, _op_user.get("display_name"),
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


# ---------------------------------------------------------------------------
# Coexistence: smb_message_echoes
# ---------------------------------------------------------------------------

def _parse_unix_timestamp(timestamp):
    """Converte timestamp Unix para ISO 8601 UTC."""
    if not timestamp:
        return ""
    try:
        dt = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
        return dt.isoformat()
    except (ValueError, OSError):
        return datetime.now(timezone.utc).isoformat()


def _get_business_phone_number(metadata):
    """Extrai o numero do telefone comercial do metadata do webhook."""
    return str(metadata.get("display_phone_number", "")).replace("+", "").replace(" ", "").replace("-", "")


async def _process_smb_message_echoes(value, ws_notify_callback=None, channel=None):
    """
    Processa mensagens enviadas pelo app WhatsApp Business (celular/companion device).
    Estas sao mensagens OUTBOUND enviadas pela empresa, ecoadas para o CRM.
    Nao abrem janela de servico e nao disparam automacao.
    """
    metadata = value.get("metadata", {})
    echoes = value.get("message_echoes", [])

    for echo in echoes:
        business_phone = echo.get("from", "")
        customer_phone = echo.get("to", "")
        msg_id = echo.get("id", "")
        msg_type = echo.get("type", "unknown")
        timestamp = echo.get("timestamp", "")
        ts_iso = _parse_unix_timestamp(timestamp)

        if not customer_phone:
            logger.warning("[SMB ECHO] Mensagem sem destinatario | id=%s", msg_id[:20])
            continue

        # Normalizar telefone do cliente e criar/atualizar contato
        normalized_phone = normalize_br_phone(customer_phone)
        contact_id = upsert_wa_contact(normalized_phone, "")

        # Extrair conteudo conforme tipo de mensagem
        content = ""
        media_path = ""
        media_mime = ""
        media_id_str = ""
        latitude = None
        longitude = None
        filename = ""
        effective_msg_type = msg_type

        if msg_type == "text":
            text_obj = echo.get("text", {})
            content = text_obj.get("body", "") if isinstance(text_obj, dict) else ""

        elif msg_type == "image":
            image = echo.get("image", {}) if isinstance(echo.get("image"), dict) else {}
            media_id_str = image.get("id", "")
            media_mime = image.get("mime_type", "")
            content = image.get("caption", "")
            if media_id_str:
                media_result = await download_media(media_id_str, "image")
                if media_result:
                    media_path = media_result["path"]
                    media_mime = media_result["mime_type"]

        elif msg_type == "audio":
            audio = echo.get("audio", {}) if isinstance(echo.get("audio"), dict) else {}
            media_id_str = audio.get("id", "")
            media_mime = audio.get("mime_type", "")
            if media_id_str:
                media_result = await download_media(media_id_str, "audio")
                if media_result:
                    media_path = media_result["path"]
                    media_mime = media_result["mime_type"]

        elif msg_type == "video":
            video = echo.get("video", {}) if isinstance(echo.get("video"), dict) else {}
            effective_msg_type = "gif" if video.get("gif") else "video"
            media_id_str = video.get("id", "")
            media_mime = video.get("mime_type", "")
            content = video.get("caption", "")
            if media_id_str:
                media_result = await download_media(media_id_str, "video")
                if media_result:
                    media_path = media_result["path"]
                    media_mime = media_result["mime_type"]

        elif msg_type == "sticker":
            sticker = echo.get("sticker", {}) if isinstance(echo.get("sticker"), dict) else {}
            media_id_str = sticker.get("id", "")
            media_mime = sticker.get("mime_type", "image/webp")
            if media_id_str:
                media_result = await download_media(media_id_str, "sticker")
                if media_result:
                    media_path = media_result["path"]
                    media_mime = media_result["mime_type"]

        elif msg_type == "document":
            doc = echo.get("document", {}) if isinstance(echo.get("document"), dict) else {}
            media_id_str = doc.get("id", "")
            media_mime = doc.get("mime_type", "")
            filename = doc.get("filename", "")
            content = doc.get("caption", "")
            if media_id_str:
                media_result = await download_media(media_id_str, "document", filename)
                if media_result:
                    media_path = media_result["path"]
                    media_mime = media_result["mime_type"]

        elif msg_type == "location":
            loc = echo.get("location", {}) if isinstance(echo.get("location"), dict) else {}
            latitude = loc.get("latitude")
            longitude = loc.get("longitude")
            loc_name = loc.get("name", "")
            loc_address = loc.get("address", "")
            content = f"{loc_name} {loc_address}".strip() if (loc_name or loc_address) else ""

        elif msg_type == "contacts":
            content = str(echo.get("contacts", []))

        elif msg_type == "reaction":
            reaction = echo.get("reaction", {}) if isinstance(echo.get("reaction"), dict) else {}
            content = reaction.get("emoji", "")

        else:
            content = f"[{msg_type}]"

        # Salvar como outbound com source phone_app
        db_id = save_wa_message(
            wa_message_id=msg_id,
            contact_id=contact_id,
            direction="outbound",
            msg_type=effective_msg_type,
            content=content,
            media_path=media_path,
            media_mime=media_mime,
            media_id=media_id_str,
            latitude=latitude,
            longitude=longitude,
            filename=filename,
            status="sent",
            timestamp_wa=ts_iso,
        )

        logger.info(
            "[SMB ECHO] %s -> %s | tipo=%s | id=%s",
            business_phone, customer_phone, effective_msg_type, msg_id[:20],
        )

        if ws_notify_callback:
            await ws_notify_callback({
                "event": "wa_new_message",
                "data": {
                    "id": db_id,
                    "contact_id": contact_id,
                    "wa_id": normalized_phone,
                    "msg_type": effective_msg_type,
                    "content": content,
                    "media_path": media_path,
                    "media_mime": media_mime,
                    "latitude": latitude,
                    "longitude": longitude,
                    "filename": filename,
                    "timestamp": ts_iso,
                    "direction": "outbound",
                    "source": "phone_app",
                },
            })


# ---------------------------------------------------------------------------
# Coexistence: smb_app_state_sync
# ---------------------------------------------------------------------------

def _process_smb_app_state_sync(value):
    """
    Processa sincronizacao de contatos do app WhatsApp Business.
    Recebe add/remove de contatos da lista telefonica do celular.
    """
    state_sync = value.get("state_sync", [])
    if not state_sync:
        return

    for item in state_sync:
        item_type = item.get("type", "")
        if item_type != "contact":
            logger.info("[SMB SYNC] Tipo desconhecido: %s", item_type)
            continue

        contact_data = item.get("contact", {})
        action = item.get("action", "")
        phone = str(contact_data.get("phone_number", "")).strip()
        full_name = str(contact_data.get("full_name", "")).strip()
        first_name = str(contact_data.get("first_name", "")).strip()

        if not phone:
            continue

        normalized_phone = normalize_br_phone(phone)
        display_name = full_name or first_name

        if action == "add":
            contact_id = upsert_wa_contact(normalized_phone, display_name)
            logger.info(
                "[SMB SYNC] Contato sincronizado | phone=%s name=%s id=%s",
                normalized_phone, display_name, contact_id,
            )

        elif action == "remove":
            # Nao deletamos contatos, apenas logamos a remocao.
            # O contato pode ter historico de mensagens que precisa ser preservado.
            logger.info(
                "[SMB SYNC] Contato removido no celular (preservado no CRM) | phone=%s name=%s",
                normalized_phone, display_name,
            )

        else:
            logger.warning("[SMB SYNC] Acao desconhecida: %s | phone=%s", action, phone)


# ---------------------------------------------------------------------------
# Coexistence: history (importacao de 180 dias)
# ---------------------------------------------------------------------------

async def _process_history(value, ws_notify_callback=None, channel=None):
    """
    Processa webhooks de historico do app WhatsApp Business.
    Importa ate 180 dias de mensagens em fases (0, 1, 2) e chunks.
    Tambem trata media assets enviados em webhooks separados.
    """
    metadata = value.get("metadata", {})
    business_phone = _get_business_phone_number(metadata)

    # Caso 1: webhook com 'messages' - media assets do historico
    if "messages" in value and "history" not in value:
        await _process_history_media_assets(value, business_phone)
        return

    history_entries = value.get("history", [])
    if not history_entries:
        return

    for hist in history_entries:
        # Verificar se e um erro (empresa recusou compartilhar historico)
        errors = hist.get("errors", [])
        if errors:
            for err in errors:
                code = err.get("code", 0)
                title = err.get("title", "")
                logger.warning("[HISTORY] Erro na sincronizacao | code=%s title=%s", code, title)
            continue

        hist_metadata = hist.get("metadata", {})
        phase = hist_metadata.get("phase", -1)
        chunk_order = hist_metadata.get("chunk_order", 0)
        progress = hist_metadata.get("progress", 0)

        logger.info(
            "[HISTORY] Recebido | phase=%s chunk=%s progress=%s%%",
            phase, chunk_order, progress,
        )

        threads = hist.get("threads", [])
        for thread in threads:
            thread_phone = str(thread.get("id", "")).strip()
            if not thread_phone:
                continue

            normalized_thread_phone = normalize_br_phone(thread_phone)
            contact_id = upsert_wa_contact(normalized_thread_phone, "")
            messages = thread.get("messages", [])

            for msg in messages:
                msg_from = str(msg.get("from", "")).replace("+", "").replace(" ", "").replace("-", "")
                msg_to = str(msg.get("to", "")).replace("+", "").replace(" ", "").replace("-", "")
                msg_id = msg.get("id", "")
                msg_type = msg.get("type", "unknown")
                timestamp = msg.get("timestamp", "")
                ts_iso = _parse_unix_timestamp(timestamp)
                history_context = msg.get("history_context", {})
                msg_status = str(history_context.get("status", "")).lower()

                # Determinar direcao: se 'from' e o telefone da empresa, e outbound
                is_outbound = (msg_from == business_phone) or bool(msg_to)
                direction = "outbound" if is_outbound else "inbound"

                # media_placeholder: midia sera enviada em webhook separado
                if msg_type == "media_placeholder":
                    save_wa_message(
                        wa_message_id=msg_id,
                        contact_id=contact_id,
                        direction=direction,
                        msg_type="media_placeholder",
                        content="[Midia do historico - aguardando]",
                        status=msg_status or "delivered",
                        timestamp_wa=ts_iso,
                    )
                    continue

                # Extrair conteudo conforme tipo
                content = ""
                media_path = ""
                media_mime = ""
                media_id_str = ""
                latitude = None
                longitude = None
                filename = ""
                effective_msg_type = msg_type

                if msg_type == "text":
                    text_obj = msg.get("text", {})
                    content = text_obj.get("body", "") if isinstance(text_obj, dict) else ""

                elif msg_type == "image":
                    image = msg.get("image", {}) if isinstance(msg.get("image"), dict) else {}
                    media_id_str = image.get("id", "")
                    media_mime = image.get("mime_type", "")
                    content = image.get("caption", "")
                    if media_id_str:
                        media_result = await download_media(media_id_str, "image")
                        if media_result:
                            media_path = media_result["path"]
                            media_mime = media_result["mime_type"]

                elif msg_type == "audio":
                    audio = msg.get("audio", {}) if isinstance(msg.get("audio"), dict) else {}
                    media_id_str = audio.get("id", "")
                    media_mime = audio.get("mime_type", "")
                    if media_id_str:
                        media_result = await download_media(media_id_str, "audio")
                        if media_result:
                            media_path = media_result["path"]
                            media_mime = media_result["mime_type"]

                elif msg_type == "video":
                    video = msg.get("video", {}) if isinstance(msg.get("video"), dict) else {}
                    effective_msg_type = "gif" if video.get("gif") else "video"
                    media_id_str = video.get("id", "")
                    media_mime = video.get("mime_type", "")
                    content = video.get("caption", "")
                    if media_id_str:
                        media_result = await download_media(media_id_str, "video")
                        if media_result:
                            media_path = media_result["path"]
                            media_mime = media_result["mime_type"]

                elif msg_type == "document":
                    doc = msg.get("document", {}) if isinstance(msg.get("document"), dict) else {}
                    media_id_str = doc.get("id", "")
                    media_mime = doc.get("mime_type", "")
                    filename = doc.get("filename", "")
                    content = doc.get("caption", "")
                    if media_id_str:
                        media_result = await download_media(media_id_str, "document", filename)
                        if media_result:
                            media_path = media_result["path"]
                            media_mime = media_result["mime_type"]

                elif msg_type == "sticker":
                    sticker = msg.get("sticker", {}) if isinstance(msg.get("sticker"), dict) else {}
                    media_id_str = sticker.get("id", "")
                    media_mime = sticker.get("mime_type", "image/webp")
                    if media_id_str:
                        media_result = await download_media(media_id_str, "sticker")
                        if media_result:
                            media_path = media_result["path"]
                            media_mime = media_result["mime_type"]

                elif msg_type == "location":
                    loc = msg.get("location", {}) if isinstance(msg.get("location"), dict) else {}
                    latitude = loc.get("latitude")
                    longitude = loc.get("longitude")
                    loc_name = loc.get("name", "")
                    loc_address = loc.get("address", "")
                    content = f"{loc_name} {loc_address}".strip() if (loc_name or loc_address) else ""

                elif msg_type == "contacts":
                    content = str(msg.get("contacts", []))

                elif msg_type == "reaction":
                    reaction = msg.get("reaction", {}) if isinstance(msg.get("reaction"), dict) else {}
                    content = reaction.get("emoji", "")

                else:
                    content = f"[{msg_type}]"

                save_wa_message(
                    wa_message_id=msg_id,
                    contact_id=contact_id,
                    direction=direction,
                    msg_type=effective_msg_type,
                    content=content,
                    media_path=media_path,
                    media_mime=media_mime,
                    media_id=media_id_str,
                    latitude=latitude,
                    longitude=longitude,
                    filename=filename,
                    status=msg_status or ("received" if direction == "inbound" else "sent"),
                    timestamp_wa=ts_iso,
                )

            logger.info(
                "[HISTORY] Thread processada | phone=%s msgs=%d phase=%s",
                thread_phone, len(messages), phase,
            )

        if progress == 100:
            logger.info("[HISTORY] Sincronizacao completa (100%%)")
            log_audit(
                user_id=None,
                action="history_sync_complete",
                detail=f"Importacao do historico de mensagens concluida (phase={phase})",
            )


async def _process_history_media_assets(value, business_phone):
    """
    Processa webhooks de historico que contem media assets.
    Estes sao enviados separadamente dos threads, com 'messages' contendo
    a midia real de mensagens que eram media_placeholder.
    """
    for msg in value.get("messages", []):
        msg_id = msg.get("id", "")
        msg_type = msg.get("type", "unknown")
        timestamp = msg.get("timestamp", "")
        ts_iso = _parse_unix_timestamp(timestamp)

        media_path = ""
        media_mime = ""
        media_id_str = ""
        filename = ""
        content = ""

        if msg_type == "image":
            image = msg.get("image", {}) if isinstance(msg.get("image"), dict) else {}
            media_id_str = image.get("id", "")
            media_mime = image.get("mime_type", "")
            content = image.get("caption", "")
            if media_id_str:
                media_result = await download_media(media_id_str, "image")
                if media_result:
                    media_path = media_result["path"]
                    media_mime = media_result["mime_type"]

        elif msg_type == "audio":
            audio = msg.get("audio", {}) if isinstance(msg.get("audio"), dict) else {}
            media_id_str = audio.get("id", "")
            media_mime = audio.get("mime_type", "")
            if media_id_str:
                media_result = await download_media(media_id_str, "audio")
                if media_result:
                    media_path = media_result["path"]
                    media_mime = media_result["mime_type"]

        elif msg_type == "video":
            video = msg.get("video", {}) if isinstance(msg.get("video"), dict) else {}
            media_id_str = video.get("id", "")
            media_mime = video.get("mime_type", "")
            content = video.get("caption", "")
            if media_id_str:
                media_result = await download_media(media_id_str, "video")
                if media_result:
                    media_path = media_result["path"]
                    media_mime = media_result["mime_type"]

        elif msg_type == "document":
            doc = msg.get("document", {}) if isinstance(msg.get("document"), dict) else {}
            media_id_str = doc.get("id", "")
            media_mime = doc.get("mime_type", "")
            filename = doc.get("filename", "")
            content = doc.get("caption", "")
            if media_id_str:
                media_result = await download_media(media_id_str, "document", filename)
                if media_result:
                    media_path = media_result["path"]
                    media_mime = media_result["mime_type"]

        elif msg_type == "sticker":
            sticker = msg.get("sticker", {}) if isinstance(msg.get("sticker"), dict) else {}
            media_id_str = sticker.get("id", "")
            media_mime = sticker.get("mime_type", "image/webp")
            if media_id_str:
                media_result = await download_media(media_id_str, "sticker")
                if media_result:
                    media_path = media_result["path"]
                    media_mime = media_result["mime_type"]

        else:
            logger.info("[HISTORY MEDIA] Tipo nao tratado: %s | id=%s", msg_type, msg_id[:20])
            continue

        if not media_path:
            logger.warning("[HISTORY MEDIA] Nao foi possivel baixar midia | id=%s type=%s", msg_id[:20], msg_type)
            continue

        # Atualiza a mensagem placeholder existente com a midia real
        existing = get_wa_message_by_wa_message_id(msg_id)
        if existing:
            from firestore_common import document
            document("wa_messages", existing["id"]).set({
                "msg_type": msg_type,
                "content": content or existing.get("content", ""),
                "media_path": media_path,
                "media_mime": media_mime,
                "media_id": media_id_str,
                "filename": filename,
            }, merge=True)
            logger.info("[HISTORY MEDIA] Placeholder atualizado | id=%s type=%s", msg_id[:20], msg_type)
        else:
            logger.warning(
                "[HISTORY MEDIA] Mensagem original nao encontrada para media | wa_msg_id=%s",
                msg_id[:20],
            )


# ---------------------------------------------------------------------------
# Coexistence: account_update
# ---------------------------------------------------------------------------

def _process_account_update(value):
    """
    Processa eventos de atualizacao de conta para coexistence.
    Eventos: PARTNER_REMOVED, ACCOUNT_OFFBOARDED, ACCOUNT_RECONNECTED.
    """
    event = str(value.get("event", "")).upper()
    phone_number = value.get("phone_number", "")

    if event == "PARTNER_REMOVED":
        logger.warning(
            "[ACCOUNT] Cliente desconectou da API de Nuvem | phone=%s",
            phone_number,
        )
        log_audit(
            user_id=None,
            action="coexistence_partner_removed",
            detail=f"Cliente desconectou o numero {phone_number} da API de Nuvem via WhatsApp Business App",
        )

    elif event == "ACCOUNT_OFFBOARDED":
        logger.warning("[ACCOUNT] Conta removida (offboarded) | phone=%s", phone_number)
        log_audit(
            user_id=None,
            action="coexistence_offboarded",
            detail=f"Numero {phone_number} foi removido do coexistence (troca de dispositivo ou reinscricao)",
        )

    elif event == "ACCOUNT_RECONNECTED":
        logger.info("[ACCOUNT] Conta reconectada | phone=%s", phone_number)
        log_audit(
            user_id=None,
            action="coexistence_reconnected",
            detail=f"Numero {phone_number} reconectado ao coexistence",
        )

    else:
        logger.info("[ACCOUNT] Evento nao tratado: %s | phone=%s", event, phone_number)
