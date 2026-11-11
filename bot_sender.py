# -*- coding: utf-8 -*-

"""Envio compartilhado das respostas automaticas do bot pelo WhatsApp."""

import logging
from datetime import datetime, timezone

import httpx
from starlette.concurrency import run_in_threadpool

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
        await run_in_threadpool(save_wa_message,
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


REMINDER_FOOTER = "Para desativar os lembretes, envie PARAR LEMBRETES."


def send_bot_reminder(contact, thread, channel, text, stage, series="B"):
    """POST sem retry. Chamado somente no worker fora do event loop.

    Serie A (lead parado no aviso da LGPD) sai com os botoes do proprio aviso,
    mesmos ids, para o toque entrar no gate que ja existe; a instrucao de
    parada vai no rodape da mensagem interativa. Serie B sai como texto simples.
    """
    from database_firestore import save_wa_message
    if series == "A":
        from lgpd_bot import _BTN_ACEITAR, _BTN_RECUSAR
        reply = {"type": "interactive_buttons", "body": text, "footer": REMINDER_FOOTER,
                 "buttons": [dict(_BTN_ACEITAR), dict(_BTN_RECUSAR)]}
    else:
        reply = text + "\n\n" + REMINDER_FOOTER
    payload, content = build_outbound_payload(reply, str(thread["wa_id"]))
    if series == "A":
        # O chat do CRM mostra o rodape como na serie B (o corpo gravado e so o body).
        content = content + "\n\n" + REMINDER_FOOTER
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(f"{GRAPH_API_BASE}/{channel['phone_number_id']}/messages", json=payload,
                                   headers={"Authorization": f"Bearer {channel['access_token']}"})
        result = response.json()
        if response.status_code != 200:
            code = (result.get("error") or {}).get("code")
            logger.warning("[BOT-REMINDER] envio recusado | status=%s code=%s contact=%s serie=%s etapa=%s",
                           response.status_code, code, contact.get("id"), series, stage)
            return {"ok": False, "code": code}
        message_id = (result.get("messages") or [{}])[0].get("id")
        if not message_id:
            return {"ok": False, "code": "sem_id"}
        save_wa_message(message_id, contact["id"], "outbound", "text", content=content, status="sent",
                        timestamp_wa=datetime.now(timezone.utc).isoformat(), channel_id=thread["channel_id"],
                        conversation_id=thread["id"], sender_user_id=None, operator_id=None,
                        advance_recency=False, reopen_attendance=False, promote_qualification=False,
                        human_outbound=False, sent_by_name="Lembrete automático", contact=contact,
                        automation_kind="bot_reminder", automation_stage=stage, automation_series=series)
        return {"ok": True, "message_id": message_id}
    except Exception as exc:
        # Timeout e persistencia incerta nao autorizam outro POST. So o tipo
        # da excecao no log: a mensagem pode trazer PII do provedor.
        logger.error("[BOT-REMINDER] falha no envio/persistencia | erro=%s contact=%s serie=%s etapa=%s",
                     type(exc).__name__, contact.get("id"), series, stage)
        return {"ok": False, "code": "envio_ou_persistencia"}
