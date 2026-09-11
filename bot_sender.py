# -*- coding: utf-8 -*-

"""Envio compartilhado das respostas automaticas do bot pelo WhatsApp."""

import logging
from datetime import datetime, timezone

import httpx

from bot_transport import build_outbound_payload
from config import GRAPH_API_BASE
from pii_redaction import redact_phone

logger = logging.getLogger("castro_crm.bot_sender")


async def send_bot_reply(
    wa_id: str,
    reply,
    contact_id: int,
    token: str,
    phone_id: str,
    channel_id=None,
    channel_owner_user_id=None,
):
    """Envia a resposta do bot e persiste o outbound, sem levantar ao caller."""
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
            return True
        logger.warning("[BOT] Falha ao enviar resposta | status=%s | erro=%s", resp.status_code, result)
    except Exception as exc:
        logger.error("[BOT] Erro ao enviar resposta: %s", exc, exc_info=True)
    return False
