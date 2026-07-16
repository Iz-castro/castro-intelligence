# -*- coding: utf-8 -*-

"""
Processamento de eventos recebidos via webhook da Meta Cloud API.
Trata mensagens de texto, imagem, audio, video, sticker, localizacao e documentos.
"""

import hmac
import hashlib
import logging
from datetime import datetime, timezone

from starlette.concurrency import run_in_threadpool

from config import (
    REQUIRE_WEBHOOK_SIGNATURE, WHATSAPP_APP_SECRET,
    FEATURE_AUDIO_TRANSCRIPTION, FEATURE_MESSAGE_STATUS,
    STT_LANGUAGE_CODE, STT_TIMEOUT_SECONDS, STT_FALLBACK_TEXT,
    WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_TOKEN,
)
from database import (
    upsert_wa_contact, save_wa_message, update_wa_message_status, log_audit, flag_conversation_takeover,
    update_wa_message_transcription,
    get_user_by_id, get_wa_message_by_wa_message_id, get_wa_contact,
    assign_wa_contact, update_wa_contact_qualification,
    normalize_br_phone,
    get_wa_conversation_by_id, set_attendance_status,
    insert_transfer_system_message, get_current_protocol_id,
)
from media import download_media
from channel_service import get_channel_by_phone_id, get_default_channel, CHANNEL_TYPE_COEXISTENCE
from bot_service import process_bot_message_async
from bot_transport import build_outbound_payload, extract_interactive_inbound
from firestore_common import set_tenant_context, reset_tenant_context, document, utcnow
from tenant_service import lookup_phone_routing
from pii_redaction import redact_phone, redact_name
from pending_events import enqueue_pending_event
from contextvars import ContextVar

logger = logging.getLogger("castro_crm.webhook")

# Tenant default usado quando o webhook recebe payload sem phone_number_id
# valido OU quando phone_routing ainda nao tem entrada pra esse numero.
# Sub-fase: enquanto canais sao flat, canal default pertence a 'hubloc'.
_WEBHOOK_DEFAULT_TENANT = "hubloc"

# Reprocessamento silencioso (drain de pending_webhook_events acumulados): quando
# True no contexto async atual, _process_messages salva a mensagem/contato/conversa
# mas PULA toda a automacao pos-persistencia (botao de reabertura, flag de
# takeover, bot, rating) — zero outbound pro cliente e zero mutacao de bot_state
# de contato que esteja mid-fluxo agora. O webhook ao vivo NUNCA seta isto
# (default False) -> impacto zero no trafego real; so o script de drain seta,
# antes de chamar process_webhook_payload, pra entregar mensagens historicas sem
# disparar auto-reply em mensagem antiga.
_silent_reprocess: "ContextVar[bool]" = ContextVar("silent_reprocess", default=False)


def _resolve_webhook_tenant(channel, phone_number_id: str | None = None):
    """Resolve tenant_id pra um payload de webhook.

    Ordem de preferencia (Fase 2C):
      1. `phone_routing[phone_number_id]` se phone_number_id for fornecido
         e existir indice (caminho oficial pra multi-tenant).
      2. `channel.tenant_id` denormalizado no doc do canal (fallback
         enquanto canais nao migram pra subcolecao).
      3. `_WEBHOOK_DEFAULT_TENANT` (single-tenant Hubloc).
    """
    if phone_number_id:
        try:
            routing = lookup_phone_routing(str(phone_number_id))
        except Exception as exc:
            logger.warning("phone_routing lookup falhou para %s: %s", phone_number_id, exc)
            routing = None
        if routing and routing.get("tenant_id"):
            return str(routing["tenant_id"])
    if channel and channel.get("tenant_id"):
        return str(channel["tenant_id"])
    return _WEBHOOK_DEFAULT_TENANT


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

    Retorna (channel_dict, reason) onde reason e:
      - None: canal resolvido normalmente.
      - 'no_phone_number_id': metadata sem phone_number_id.
      - 'no_channel_for_phone': phone_id nao bate com canal cadastrado.
      - 'no_default_channel': fallback default tambem nao existe.

    Quando channel e None, o caller deve enfileirar em
    pending_webhook_events em vez de processar com canal sintetico
    (default__) que nao casa com selectedThreadId no frontend.
    """
    metadata = value.get("metadata", {})
    phone_number_id = str(metadata.get("phone_number_id", "")).strip()

    if phone_number_id:
        channel = get_channel_by_phone_id(phone_number_id)
        if channel:
            return channel, None
        logger.warning(
            "Webhook: phone_number_id=%s nao bate com nenhum canal cadastrado.",
            phone_number_id,
        )
        # NAO cair no canal default: um phone_number_id que nao bate com nenhum
        # canal (ex.: numero coex desconectado) deve ir pra pending_webhook_events,
        # nao ser processado sob o canal standard/default — senao o coex de um
        # operador vaza pra dentro do canal standard. (Bug 2026-06-05.)
        return None, "no_channel_for_phone"

    logger.warning(
        "Webhook: metadata sem phone_number_id. Payload metadata=%s",
        metadata,
    )
    return None, "no_phone_number_id"


async def _send_bot_reply(wa_id: str, reply, contact_id: int, token: str, phone_id: str,
                          channel_id=None, channel_owner_user_id=None):
    """Envia resposta do bot via WhatsApp Cloud API e salva no banco.

    `reply` pode ser str (texto) ou dict (type="interactive_buttons", ex.:
    consentimento LGPD). A traducao para o payload da Meta e o texto a
    persistir (corpo visivel, nunca o dict cru) vem de bot_transport.

    sender_user_id=None marca a mensagem como originada pelo bot
    automatico (nao por operador humano).
    """
    import httpx
    from config import GRAPH_API_BASE
    from database import save_wa_message

    url = f"{GRAPH_API_BASE}/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload_msg, store_content = build_outbound_payload(reply, wa_id)
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
            content=store_content,
            status="sent" if resp.status_code == 200 else "failed",
            timestamp_wa=datetime.now(timezone.utc).isoformat(),
            operator_id=None,
            channel_id=channel_id,
            channel_owner_user_id=channel_owner_user_id,
            sender_user_id=None,
        )
        if resp.status_code == 200:
            logger.info("[BOT] Resposta enviada para %s | contact=%d", redact_phone(wa_id), contact_id)
        else:
            logger.warning("[BOT] Falha ao enviar resposta | status=%s | erro=%s", resp.status_code, result)
    except Exception as e:
        logger.error("[BOT] Erro ao enviar resposta: %s", e, exc_info=True)


def _normalize_reopen_choice(text):
    """Normaliza texto/payload do botao (sem acento, minusculo) p/ matching
    robusto contra acentuacao e pequenas edicoes no texto do botao."""
    import unicodedata
    s = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii")
    return s.lower().strip()


async def _handle_reopen_button(contact_id, wa_id, channel, button, context,
                                db_id, content, ts_iso, reply_fields, ws_notify_callback=None):
    """Processa a resposta de um botao quick-reply do template de reabertura.

    Resolve a conversation alvo via context.id (mensagem-template original),
    com fallback no id deterministico {channel_id}__{wa_id}. Registra a
    escolha (reopen_response) + mensagem de sistema visivel ao operador.

    - 'Encerrar': fecha o atendimento (fechado_cliente), marca
      client_requested_close (trava p/ reabertura em lote futura) e envia o
      recibo de protocolo (mesma logica do fechamento manual).
    - 'Retomar': reabre o atendimento (aberto) e o Atendimento diario.
    """
    channel_id = channel.get("id") if channel else None

    # Resolve a conversation alvo a partir da mensagem-template citada.
    conversation_id = None
    ctx = context if isinstance(context, dict) else {}
    ctx_id = str(ctx.get("id") or "").strip()
    if ctx_id:
        original = get_wa_message_by_wa_message_id(ctx_id)
        if original:
            conversation_id = original.get("conversation_id")
    if not conversation_id and channel_id and wa_id:
        conversation_id = f"{channel_id}__{wa_id}"

    choice = _normalize_reopen_choice(button.get("payload") or button.get("text"))
    if "encerr" in choice:
        action = "encerrar"
    elif "retom" in choice:
        action = "retomar"
    else:
        action = None
        logger.info("[REOPEN BTN] resposta nao reconhecida | conv=%s txt=%s", conversation_id, choice[:40])

    # Emite a mensagem de botao p/ clientes conectados (paridade com o emit
    # padrao de inbound; em snapshot mode o Firestore tambem propaga).
    if ws_notify_callback:
        await ws_notify_callback({
            "event": "wa_new_message",
            "data": {
                "id": db_id, "contact_id": contact_id, "wa_id": wa_id,
                "msg_type": "button", "content": content, "timestamp": ts_iso,
                **(reply_fields or {}),
            },
        })

    if action is None or not conversation_id:
        return

    conv = get_wa_conversation_by_id(conversation_id)
    contact = get_wa_contact(contact_id)

    # Registra a escolha na conversation (auditavel + trava de reabertura
    # em lote: nao reabrir quem ja pediu encerramento).
    response_fields = {
        "reopen_response": action,
        "reopen_response_at": utcnow().isoformat(),
    }
    if action == "encerrar":
        response_fields["client_requested_close"] = True
    try:
        document("wa_conversations", conversation_id).set(response_fields, merge=True)
    except Exception as exc:
        logger.warning("[REOPEN BTN] falha ao gravar reopen_response conv=%s: %s", conversation_id, exc)

    if action == "encerrar":
        set_attendance_status(conversation_id, "fechado_cliente", clear_takeover=True)
        insert_transfer_system_message(
            contact_id,
            "Cliente encerrou o chamado pelo botao de reabertura.",
            None, conversation_id=conversation_id, channel_id=channel_id,
        )
        # Fecha o Atendimento diario + envia recibo de protocolo (mesma
        # logica do fechamento manual). Import tardio evita ciclo com main.
        try:
            from main import _close_daily_and_send_protocol
            await _close_daily_and_send_protocol(contact, conv, channel, None, "fechado_cliente")
        except Exception as exc:
            logger.warning("[REOPEN BTN] close_daily/protocolo falhou conv=%s: %s", conversation_id, exc)
        log_audit(None, "WA_REOPEN_RESPONSE", f"conv={conversation_id} -> encerrar (cliente)")
        logger.info("[REOPEN BTN] Cliente encerrou | conv=%s", conversation_id)
    else:  # retomar
        set_attendance_status(conversation_id, "aberto")
        # Reabre o Atendimento diario se existir (espelha set-attendance).
        pid = get_current_protocol_id(contact_id)
        if pid:
            try:
                document("attendances_daily", pid).set(
                    {"status": "aberto", "fechado_em": None, "fechado_por_user_id": None}, merge=True,
                )
            except Exception as exc:
                logger.warning("[REOPEN BTN] reabrir daily pid=%s falhou: %s", pid, exc)
        insert_transfer_system_message(
            contact_id,
            "Cliente optou por retomar a solicitacao.",
            None, conversation_id=conversation_id, channel_id=channel_id,
        )
        log_audit(None, "WA_REOPEN_RESPONSE", f"conv={conversation_id} -> retomar (cliente)")
        logger.info("[REOPEN BTN] Cliente retomou | conv=%s", conversation_id)


# Fields que dependem de canal resolvido para escrever mensagem/contato.
# smb_app_state_sync entra aqui porque o upsert_wa_contact agora requer
# channel_id pra gerar conversation_id deterministico. Eventos fora
# dessa lista (statuses, account_update) nao precisam de canal.
_CHANNEL_DEPENDENT_FIELDS = ("smb_message_echoes", "history", "messages", "smb_app_state_sync")

# Fields que auto-atribuem contato ao dono do canal coexistence. Se o
# canal resolve mas owner_user_id ainda nao foi populado (corrida: sync
# de historico comeca na criacao do canal, owner setado logo depois),
# processar agora criaria contato ORFAO (assigned_to_uid="") no pool
# compartilhado — visivel a todo operador (bug isolamento LGPD). Nesses
# casos enfileira pra retry (mesma logica zero-perda de canal ausente).
# smb_app_state_sync fica de fora de proposito: nao atribui (e agenda
# telefonica, nao historico de conversa).
_COEX_OWNER_REQUIRED_FIELDS = ("smb_message_echoes", "history", "messages")


async def process_webhook_payload(payload, ws_notify_callback=None):
    """
    Processa o payload completo do webhook.

    Garantia anti-perda: nunca propaga exception ao caller — qualquer
    erro/canal nao resolvido enfileira em pending_webhook_events e o
    handler HTTP retorna 200 imediato pra Meta. Operadores reprocessam
    via UI admin assim que o canal estiver indexado (ex: depois do
    Embedded Signup completar).
    """
    if payload.get("object") != "whatsapp_business_account":
        return

    # Resolve tenant uma unica vez no inicio do payload — todos os
    # changes deste payload vem do mesmo phone_number_id (mesma WABA).
    first_value = ((payload.get("entry") or [{}])[0].get("changes") or [{}])[0].get("value", {})
    first_phone_id = str((first_value.get("metadata") or {}).get("phone_number_id") or "").strip()
    first_channel, _first_reason = _resolve_webhook_channel(first_value)
    tenant_id = _resolve_webhook_tenant(first_channel, phone_number_id=first_phone_id)
    ctx_token = set_tenant_context(tenant_id)
    try:
        await _process_webhook_payload_inner(payload, ws_notify_callback)
    except Exception as exc:
        # Erro nao tratado durante processamento → enfileira pra retry
        # humano em vez de devolver 5xx pra Meta.
        try:
            enqueue_pending_event(
                payload=payload,
                change_field="exception",
                phone_number_id=first_phone_id,
                reason=f"unhandled_exception:{type(exc).__name__}:{str(exc)[:200]}",
            )
        except Exception as enq_exc:
            logger.error(
                "Falha critica: nao consegui enfileirar payload pendente | erro=%s",
                enq_exc, exc_info=True,
            )
        logger.error("Webhook processing error (enqueued): %s", exc, exc_info=True)
    finally:
        reset_tenant_context(ctx_token)


async def _process_webhook_payload_inner(payload, ws_notify_callback=None):
    """Implementacao do processamento. Tenant_context ja setado pelo wrapper.

    Enfileira changes individuais que dependem de canal nao resolvido
    em vez de processar com canal sintetico (default__) que nao casa
    com selectedThreadId no frontend.
    """
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            field = change.get("field", "")

            # Determina field efetivo para enfileiramento (webhooks padrao
            # da Cloud API entregam 'field=messages' mas o detection abaixo
            # usa 'field=="" with messages key' historicamente).
            effective_field = field if field else ("messages" if "messages" in value else "")

            # Resolve canal para este change
            channel, reason = _resolve_webhook_channel(value)

            # Eventos que dependem de canal pra serem persistidos
            # corretamente. Sem canal, enfileira (zero perda).
            if channel is None and effective_field in _CHANNEL_DEPENDENT_FIELDS:
                phone_id = str((value.get("metadata") or {}).get("phone_number_id") or "").strip()
                # Enfileira o payload INTEIRO (nao so o change) — facilita
                # retry reusando process_webhook_payload e idempotencia
                # via wa_message_id em save_wa_message.
                enqueue_pending_event(
                    payload=payload,
                    change_field=effective_field,
                    phone_number_id=phone_id,
                    reason=reason or "no_channel",
                )
                # Para outros changes deste payload (se houver) seguimos
                # o loop — eles podem ser smb_app_state_sync/etc que nao
                # dependem de canal.
                continue

            # Canal coexistence resolvido mas SEM owner ainda: enfileira
            # em vez de processar (senao cria contato orfao no pool —
            # exatamente o bug que gerou os 3571 orfaos do channel 2).
            # Retry pega o owner ja populado.
            if (
                channel is not None
                and str(channel.get("channel_type", "")) == CHANNEL_TYPE_COEXISTENCE
                and not channel.get("owner_user_id")
                and effective_field in _COEX_OWNER_REQUIRED_FIELDS
            ):
                phone_id = str((value.get("metadata") or {}).get("phone_number_id") or "").strip()
                logger.warning(
                    "Webhook coexistence sem owner_user_id (channel_id=%s) — "
                    "enfileirando %s p/ evitar contato orfao.",
                    channel.get("id"), effective_field,
                )
                enqueue_pending_event(
                    payload=payload,
                    change_field=effective_field,
                    phone_number_id=phone_id,
                    reason="coex_no_owner",
                )
                continue

            if field == "smb_message_echoes":
                await _process_smb_message_echoes(value, ws_notify_callback, channel=channel)

            elif field == "smb_app_state_sync":
                # 100% sincrono e pesado (loop da agenda inteira, ~9000).
                # Roda em threadpool pra NAO congelar o event loop do
                # uvicorn (--workers 1) — outras requests (admin, outros
                # webhooks) seguem servidas durante a onda. Mantem o
                # modelo de durabilidade (ainda dentro da request; erro
                # nao tratado cai no enqueue de process_webhook_payload).
                # anyio copia o contextvar de tenant pra thread.
                await run_in_threadpool(_process_smb_app_state_sync, value, channel)

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
        # Normaliza nono digito BR — Meta entrega numero ora com '9' ora sem
        # (numeros antigos/legados). Sem normalizacao, o mesmo cliente cria
        # contatos e conversations duplicadas.
        wa_id = normalize_br_phone(msg.get("from", ""))
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

        elif msg_type == "button":
            # Resposta a botao quick-reply de template (ex.: template de
            # reabertura 'atualizacao_solicitacao'). Meta entrega o texto do
            # botao em button.text e o payload (se enviado) em button.payload.
            button_obj = msg.get("button", {}) if isinstance(msg.get("button"), dict) else {}
            content = str(button_obj.get("text") or "").strip() or "[button]"

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
                redact_phone(wa_id),
                msg_id[:20],
            )

        elif msg_type == "interactive":
            # Resposta de botao/lista interativa (Cloud API): o cliente tocou
            # num botao (ex.: consentimento LGPD). Extrai o id do botao e
            # normaliza para 'text' para passar pelo gate do bot (~L721), que
            # entao alimenta process_bot_message com o id ("lgpd_aceitar"...).
            content = extract_interactive_inbound(msg)
            effective_msg_type = "text"

        else:
            content = f"[{msg_type}]"
            logger.info("Tipo de mensagem nao tratado: %s", msg_type)

        # Guard de redelivery: a Meta reenvia o payload quando o ACK demora
        # (o motor CX roda DetectIntent inline). save_wa_message ja deduplica
        # o DOC, mas nao sinaliza o caller — sem este check o bot rodaria (e
        # responderia) de novo a cada retry do mesmo msg_id. So consultamos no
        # path que roda o bot (texto): evita 1 leitura Firestore por inbound de
        # midia/status no caminho quente de todos os tenants.
        was_dup = (
            bool(get_wa_message_by_wa_message_id(msg_id))
            if (msg_id and effective_msg_type == "text")
            else False
        )

        # Persistir. sender_user_id=None em inbound (cliente final).
        # channel_owner_user_id captura o dono do numero (relevante p/ coexistence).
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
            channel_owner_user_id=channel_owner_id,
            sender_user_id=None,
            **reply_fields,
        )

        logger.info(
            "[WA IN] %s (%s) | tipo=%s | id=%s",
            redact_name(contact_name), redact_phone(wa_id), effective_msg_type, msg_id[:20]
        )

        # -- Gate de reprocessamento silencioso --
        # Mensagem/contato/conversa ja persistidos acima; se estamos drenando
        # pending antigos, para AQUI: nada de botao/takeover/bot/rating/outbound.
        if _silent_reprocess.get():
            continue

        # -- Resposta de botao quick-reply (template de reabertura) --
        # Registra a escolha do cliente (Retomar/Encerrar), atualiza o
        # atendimento e curto-circuita: NAO roda bot/rating/takeover, que
        # poderiam reatribuir lead ou disparar automacao indevida.
        if effective_msg_type == "button":
            await _handle_reopen_button(
                contact_id=contact_id,
                wa_id=wa_id,
                channel=channel,
                button=msg.get("button", {}) if isinstance(msg.get("button"), dict) else {},
                context=msg.get("context"),
                db_id=db_id,
                content=content,
                ts_iso=ts_iso,
                reply_fields=reply_fields,
                ws_notify_callback=ws_notify_callback,
            )
            continue

        # -- Takeover temporario (coexistence) --
        # A mensagem chegou no canal de channel_owner_id (dono do numero), mas o
        # lead ja pertence a outro operador (contact.assigned_to). Marca a
        # conversa como 'pending' pra UI oferecer "assumir temporariamente" sem
        # roubar o lead. Cliente novo (sem dono previo) nao gera conflito.
        # Leitura unica do contato, reaproveitada pelo takeover e pelo gate
        # do bot (antes eram 3 get_wa_contact por inbound). _contact_fresh
        # abaixo so re-le do banco se o bot rodar — process_bot_message e a
        # unica fonte de mutacao do contato nesta janela.
        contact_row = get_wa_contact(contact_id)
        bot_ran = False

        if channel_type == CHANNEL_TYPE_COEXISTENCE and channel_owner_id:
            _lead_owner = (contact_row or {}).get("assigned_to")
            if _lead_owner and _lead_owner != channel_owner_id:
                flag_conversation_takeover(f"{channel_id}__{wa_id}", _lead_owner, channel_owner_id)

        # -- Bot: processar mensagem se ativo e contato sem operador --
        # Gate: nao dispara se contato ja foi qualificado pelo bot (bot_completed=True)
        # mesmo que ainda nao tenha operador atribuido. O contato esta na fila
        # do departamento e redirigir pro bot reiniciaria o fluxo do zero.
        if effective_msg_type == "text" and content.strip() and not was_dup:
            if (
                contact_row
                and not contact_row.get("assigned_to")
                and not contact_row.get("bot_completed")
            ):
                bot_ran = True
                # Isola falha do bot: a mensagem inbound JA foi salva; um erro
                # aqui NAO deve reenfileirar o payload, porque no retry
                # was_dup=True pularia o bot permanentemente (achado da revisao).
                # Degrada so a resposta do bot; auto-recupera na proxima msg.
                try:
                    bot_reply = await process_bot_message_async(contact_id, content, contact_name)
                    if bot_reply:
                        _bot_token = (channel_token or WHATSAPP_TOKEN or "").strip()
                        _bot_phone_id = channel_phone_id or WHATSAPP_PHONE_NUMBER_ID
                        await _send_bot_reply(
                            wa_id, bot_reply, contact_id, _bot_token, _bot_phone_id,
                            channel_id=channel_id,
                            channel_owner_user_id=channel_owner_id,
                        )
                except Exception:
                    logger.exception(
                        "[BOT] falha ao processar/responder inbound do contato %s",
                        contact_id,
                    )

        # -- Lead convertido: capturar rating ou rerouting --
        # Re-le do banco apenas se o bot rodou (pode ter mudado qualification/
        # bot_completed). Sem bot, contact_row do topo ainda reflete o estado.
        _contact_fresh = get_wa_contact(contact_id) if bot_ran else contact_row
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
        if state == "failed":
            # Meta preenche errors[] apenas em status failed, com
            # code/title/error_data.details. Logamos o motivo para
            # diagnostico (ex.: billing 131009, undeliverable 131026,
            # quality 131049, account-not-registered 133010). Sem PII:
            # code/title/details sao descricoes de erro, nao conteudo.
            errors = status.get("errors") or []
            err = errors[0] if errors and isinstance(errors[0], dict) else {}
            logger.error(
                "[WA STATUS] %s -> failed | code=%s title=%s details=%s",
                msg_id[:20],
                err.get("code"),
                err.get("title"),
                (err.get("error_data") or {}).get("details"),
            )
        else:
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


def _media_already_downloaded(wa_message_id):
    """True se a mensagem ja existe localmente com media_path preenchido.

    Evita re-baixar midia (2 requisicoes Graph + escrita no storage) quando
    o mesmo webhook e reentregue: retry da Meta em non-2xx, retry de
    pending_webhook_events, ou reprocesso do payload inteiro. save_wa_message
    ja e idempotente por wa_message_id, mas o download_media acontece ANTES
    dele — sem este gate, uma unica reentrega de um chunk de history
    re-baixa todas as midias daquele chunk (pressao no rate limit #4 da App).
    """
    if not wa_message_id:
        return False
    existing = get_wa_message_by_wa_message_id(wa_message_id)
    return bool(existing and existing.get("media_path"))


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

    # Em smb_message_echoes, "quem enviou" foi o proprio dono do numero
    # operando o WhatsApp do celular — channel_owner_user_id e sender_user_id
    # apontam pra mesma pessoa.
    channel_id_outer = channel.get("id") if channel else None
    channel_owner_outer = channel.get("owner_user_id") if channel else None
    channel_phone_id_outer = str(channel.get("phone_number_id", "")) if channel else ""
    channel_type_outer = str(channel.get("channel_type", "")) if channel else ""

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

        # Reentrega: se o echo ja foi salvo com midia, nao re-baixar.
        skip_media = _media_already_downloaded(msg_id)

        # Normalizar telefone do cliente e criar/atualizar contato
        normalized_phone = normalize_br_phone(customer_phone)
        contact_id = upsert_wa_contact(
            normalized_phone, "",
            channel_id=channel_id_outer,
            phone_number_id=channel_phone_id_outer,
            source_channel_type=channel_type_outer,
            auto_assign_user_id=channel_owner_outer if channel_type_outer == CHANNEL_TYPE_COEXISTENCE else None,
        )

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
            if media_id_str and not skip_media:
                media_result = await download_media(media_id_str, "image")
                if media_result:
                    media_path = media_result["path"]
                    media_mime = media_result["mime_type"]

        elif msg_type == "audio":
            audio = echo.get("audio", {}) if isinstance(echo.get("audio"), dict) else {}
            media_id_str = audio.get("id", "")
            media_mime = audio.get("mime_type", "")
            if media_id_str and not skip_media:
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
            if media_id_str and not skip_media:
                media_result = await download_media(media_id_str, "video")
                if media_result:
                    media_path = media_result["path"]
                    media_mime = media_result["mime_type"]

        elif msg_type == "sticker":
            sticker = echo.get("sticker", {}) if isinstance(echo.get("sticker"), dict) else {}
            media_id_str = sticker.get("id", "")
            media_mime = sticker.get("mime_type", "image/webp")
            if media_id_str and not skip_media:
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
            if media_id_str and not skip_media:
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

        # Salvar como outbound com source phone_app. operator_id=owner
        # tambem (em smb_echoes o humano dono do numero digitou pelo
        # celular) — sem isso o frontend rotula como "Bot".
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
            operator_id=channel_owner_outer,
            channel_id=channel_id_outer,
            phone_number_id=channel_phone_id_outer,
            channel_owner_user_id=channel_owner_outer,
            sender_user_id=channel_owner_outer,
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

def _process_smb_app_state_sync(value, channel=None):
    """
    Processa sincronizacao de contatos do app WhatsApp Business.
    Recebe add/remove de contatos da lista telefonica do celular.

    Precisa de `channel` resolvido pra propagar `channel_id` no
    upsert_wa_contact. Sem channel_id, upsert_wa_conversation interno
    levanta ConversationIdError (defesa de save_wa_message contra
    ids 'default__'). Caller resolve via _resolve_webhook_channel.
    """
    state_sync = value.get("state_sync", [])
    if not state_sync:
        return

    # Channel context para enriquecer contatos sincronizados (mesma
    # logica de _process_messages e _process_history).
    sync_channel_id = channel.get("id") if channel else None
    sync_channel_owner = channel.get("owner_user_id") if channel else None
    sync_channel_phone = str(channel.get("phone_number_id", "")) if channel else ""
    sync_channel_type = str(channel.get("channel_type", "")) if channel else ""

    # Dedup intra-lote: o state_sync pode trazer o MESMO numero varias
    # vezes no payload. upsert_wa_contact faz find-then-create nao-atomico
    # (query where wa_id== + next_sequence) — em rajada a query nao enxerga
    # o doc recem-criado e nasce duplicata (ids consecutivos pro mesmo
    # numero). Resolver o mesmo numero uma vez por lote elimina a corrida.
    processed_add = {}  # normalized_phone -> contact_id

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
            # Ja sincronizado neste lote — nao re-upsertar (evita a
            # duplicata por corrida find-then-create).
            if normalized_phone in processed_add:
                continue
            # from_message_event=False — contato vem da agenda telefonica
            # do dono, nao de uma conversa real. Nao cria wa_conversation
            # nem popula last_message_at, evitando poluir a sidebar com
            # threads vazias. Quando o operador iniciar conversa ou o
            # cliente mandar mensagem, ai sim a thread nasce.
            contact_id = upsert_wa_contact(
                normalized_phone, display_name,
                channel_id=sync_channel_id,
                phone_number_id=sync_channel_phone,
                source_channel_type=sync_channel_type,
                # Coexistence: a agenda E do dono do numero — pertence ao
                # operador dono do canal, NAO e pool compartilhado (LGPD:
                # senao a agenda pessoal do supervisor vaza p/ todo
                # operador via bucket assigned_to_uid==''). Standard:
                # segue sem atribuicao (modelo diferente). Espelha
                # _process_messages / _process_history.
                auto_assign_user_id=(
                    sync_channel_owner
                    if sync_channel_type == CHANNEL_TYPE_COEXISTENCE
                    else None
                ),
                from_message_event=False,
            )
            processed_add[normalized_phone] = contact_id
            logger.info(
                "[SMB SYNC] Contato sincronizado | phone=%s name=%s id=%s",
                redact_phone(normalized_phone), redact_name(display_name), contact_id,
            )

        elif action == "remove":
            # Nao deletamos contatos, apenas logamos a remocao.
            # O contato pode ter historico de mensagens que precisa ser preservado.
            logger.info(
                "[SMB SYNC] Contato removido no celular (preservado no CRM) | phone=%s name=%s",
                redact_phone(normalized_phone), redact_name(display_name),
            )

        else:
            logger.warning(
                "[SMB SYNC] Acao desconhecida: %s | phone=%s",
                action, redact_phone(normalize_br_phone(phone)),
            )


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

    # Channel context para enriquecer contatos/mensagens importadas.
    hist_channel_id = channel.get("id") if channel else None
    hist_channel_owner = channel.get("owner_user_id") if channel else None
    hist_channel_phone = str(channel.get("phone_number_id", "")) if channel else ""
    hist_channel_type = str(channel.get("channel_type", "")) if channel else ""

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
            contact_id = upsert_wa_contact(
                normalized_thread_phone, "",
                channel_id=hist_channel_id,
                phone_number_id=hist_channel_phone,
                source_channel_type=hist_channel_type,
                auto_assign_user_id=hist_channel_owner if hist_channel_type == CHANNEL_TYPE_COEXISTENCE else None,
            )
            messages = thread.get("messages", [])

            # Normaliza business_phone uma vez (nono digito BR) — comparacao
            # com msg_from/msg_to crus dava direction errada quando empresa
            # cadastrou o numero sem 9 e o webhook entrega com (ou vice-versa).
            business_phone_normalized = normalize_br_phone(business_phone) if business_phone else ""

            for msg in messages:
                msg_from_raw = str(msg.get("from", "")).replace("+", "").replace(" ", "").replace("-", "")
                msg_to_raw = str(msg.get("to", "")).replace("+", "").replace(" ", "").replace("-", "")
                msg_from = normalize_br_phone(msg_from_raw) if msg_from_raw else ""
                msg_to = normalize_br_phone(msg_to_raw) if msg_to_raw else ""
                msg_id = msg.get("id", "")
                msg_type = msg.get("type", "unknown")
                timestamp = msg.get("timestamp", "")
                ts_iso = _parse_unix_timestamp(timestamp)
                history_context = msg.get("history_context", {})
                msg_status = str(history_context.get("status", "")).lower()
                # Reentrega de chunk de history (retry Meta / pending_events):
                # nao re-baixar midia ja persistida.
                skip_media = _media_already_downloaded(msg_id)

                # Determinar direcao: se 'from' e o telefone da empresa, e outbound
                is_outbound = (msg_from == business_phone_normalized) or bool(msg_to)
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
                        operator_id=hist_channel_owner if direction == "outbound" else None,
                        channel_id=hist_channel_id,
                        phone_number_id=hist_channel_phone,
                        channel_owner_user_id=hist_channel_owner,
                        sender_user_id=hist_channel_owner if direction == "outbound" else None,
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
                    if media_id_str and not skip_media:
                        media_result = await download_media(media_id_str, "image")
                        if media_result:
                            media_path = media_result["path"]
                            media_mime = media_result["mime_type"]

                elif msg_type == "audio":
                    audio = msg.get("audio", {}) if isinstance(msg.get("audio"), dict) else {}
                    media_id_str = audio.get("id", "")
                    media_mime = audio.get("mime_type", "")
                    if media_id_str and not skip_media:
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
                    if media_id_str and not skip_media:
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
                    if media_id_str and not skip_media:
                        media_result = await download_media(media_id_str, "document", filename)
                        if media_result:
                            media_path = media_result["path"]
                            media_mime = media_result["mime_type"]

                elif msg_type == "sticker":
                    sticker = msg.get("sticker", {}) if isinstance(msg.get("sticker"), dict) else {}
                    media_id_str = sticker.get("id", "")
                    media_mime = sticker.get("mime_type", "image/webp")
                    if media_id_str and not skip_media:
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
                    operator_id=hist_channel_owner if direction == "outbound" else None,
                    channel_id=hist_channel_id,
                    phone_number_id=hist_channel_phone,
                    channel_owner_user_id=hist_channel_owner,
                    sender_user_id=hist_channel_owner if direction == "outbound" else None,
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
    need_retry = False
    for msg in value.get("messages", []):
        msg_id = msg.get("id", "")
        msg_type = msg.get("type", "unknown")
        timestamp = msg.get("timestamp", "")
        ts_iso = _parse_unix_timestamp(timestamp)

        # Corrida (mais provavel com varias instancias): o asset de midia pode
        # chegar ANTES do placeholder (thread do history) ser salvo. Checa ANTES
        # de baixar — se a mensagem ainda nao existe, NAO baixa (a midia ficaria
        # orfa e o retry com skip_media nao preencheria) e enfileira p/ retry.
        # Zero perda: o retry reprocessa quando o placeholder ja existir.
        if not get_wa_message_by_wa_message_id(msg_id):
            need_retry = True
            logger.warning(
                "[HISTORY MEDIA] placeholder ausente (asset fora de ordem) — "
                "enfileirando retry | id=%s", msg_id[:20],
            )
            continue

        # Reentrega: se o placeholder ja foi preenchido com a midia real,
        # nao re-baixar (evita 2 requisicoes Graph + escrita no storage).
        skip_media = _media_already_downloaded(msg_id)
        if skip_media:
            logger.info("[HISTORY MEDIA] Ja baixada, ignorando reentrega | id=%s", msg_id[:20])
            continue

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
            if media_id_str and not skip_media:
                media_result = await download_media(media_id_str, "image")
                if media_result:
                    media_path = media_result["path"]
                    media_mime = media_result["mime_type"]

        elif msg_type == "audio":
            audio = msg.get("audio", {}) if isinstance(msg.get("audio"), dict) else {}
            media_id_str = audio.get("id", "")
            media_mime = audio.get("mime_type", "")
            if media_id_str and not skip_media:
                media_result = await download_media(media_id_str, "audio")
                if media_result:
                    media_path = media_result["path"]
                    media_mime = media_result["mime_type"]

        elif msg_type == "video":
            video = msg.get("video", {}) if isinstance(msg.get("video"), dict) else {}
            media_id_str = video.get("id", "")
            media_mime = video.get("mime_type", "")
            content = video.get("caption", "")
            if media_id_str and not skip_media:
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
            if media_id_str and not skip_media:
                media_result = await download_media(media_id_str, "document", filename)
                if media_result:
                    media_path = media_result["path"]
                    media_mime = media_result["mime_type"]

        elif msg_type == "sticker":
            sticker = msg.get("sticker", {}) if isinstance(msg.get("sticker"), dict) else {}
            media_id_str = sticker.get("id", "")
            media_mime = sticker.get("mime_type", "image/webp")
            if media_id_str and not skip_media:
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
            # Nao deveria ocorrer (checado no topo do loop), mas por seguranca
            # tambem marca retry em vez de descartar a midia.
            need_retry = True
            logger.warning(
                "[HISTORY MEDIA] Mensagem original nao encontrada para media | wa_msg_id=%s",
                msg_id[:20],
            )

    # Algum asset chegou sem o placeholder (corrida) -> reprocessa o lote depois,
    # quando o thread do history ja tiver criado as mensagens. Idempotente.
    if need_retry:
        try:
            enqueue_pending_event(
                payload={"entry": [{"changes": [{"field": "history", "value": value}]}]},
                change_field="history",
                phone_number_id=str((value.get("metadata") or {}).get("phone_number_id") or "").strip(),
                reason="history_media_no_placeholder",
            )
            logger.info("[HISTORY MEDIA] retry do lote de midia enfileirado")
        except Exception as exc:
            logger.warning("[HISTORY MEDIA] falha ao enfileirar retry da midia: %s", exc)


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

    redacted_phone = redact_phone(phone_number)

    if event == "PARTNER_REMOVED":
        logger.warning(
            "[ACCOUNT] Cliente desconectou da API de Nuvem | phone=%s",
            redacted_phone,
        )
        log_audit(
            user_id=None,
            action="coexistence_partner_removed",
            detail=f"Cliente desconectou o numero {phone_number} da API de Nuvem via WhatsApp Business App",
        )

    elif event == "ACCOUNT_OFFBOARDED":
        logger.warning("[ACCOUNT] Conta removida (offboarded) | phone=%s", redacted_phone)
        log_audit(
            user_id=None,
            action="coexistence_offboarded",
            detail=f"Numero {phone_number} foi removido do coexistence (troca de dispositivo ou reinscricao)",
        )

    elif event == "ACCOUNT_RECONNECTED":
        logger.info("[ACCOUNT] Conta reconectada | phone=%s", redacted_phone)
        log_audit(
            user_id=None,
            action="coexistence_reconnected",
            detail=f"Numero {phone_number} reconectado ao coexistence",
        )

    else:
        logger.info("[ACCOUNT] Evento nao tratado: %s | phone=%s", event, redacted_phone)
