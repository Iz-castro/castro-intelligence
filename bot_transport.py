# -*- coding: utf-8 -*-

"""
bot_transport.py - Camada de transporte entre o bot e a WhatsApp Cloud API.

Responsabilidade unica: traduzir as respostas ABSTRATAS do bot
(str ou dict type="interactive_buttons", produzidas por
lgpd_bot/bot_service) para o formato concreto da Meta Graph API,
e extrair o conteudo util de mensagens interativas recebidas (button_reply
/ list_reply). Os modulos de dominio (bot/LGPD) nao conhecem o formato da
Meta; este modulo e o unico ponto que conhece.

E proposital que este modulo seja leve (apenas stdlib) para ser importavel
em testes/simuladores sem puxar FastAPI, Firestore ou config.

Limites da Cloud API v22 (interactive type=button) aplicados defensivamente:
  - body.text   <= 1024 chars
  - footer.text <= 60 chars
  - no maximo 3 botoes (reply)
  - button.reply.title <= 20 chars
  - button.reply.id    <= 256 chars
"""

import logging
from typing import Tuple, Union

logger = logging.getLogger("castro_crm.bot_transport")

_MAX_BODY = 1024
_MAX_FOOTER = 60
_MAX_BUTTONS = 3
_MAX_TITLE = 20
_MAX_ID = 256


def _so_digitos(valor) -> str:
    return "".join(ch for ch in str(valor or "") if ch.isdigit())


def build_outbound_payload(
    reply: Union[str, dict],
    to,
) -> Tuple[dict, str]:
    """
    Constroi o payload de envio para POST /{phone_id}/messages.

    Args:
        reply: str  -> mensagem de texto simples; ou
               dict -> {"type": "interactive_buttons", "body": str,
                        "buttons": [{"id","title"}, ...], "footer"?: str}
               (formato abstrato retornado por handle_lgpd / process_bot_message).
        to:    numero do destinatario (qualquer formato; sera reduzido a digitos).

    Returns:
        (payload, store_content)
          payload       -> dict pronto para json= no httpx/requests.
          store_content -> texto a persistir em wa_messages.content (o corpo
                           visivel da mensagem, nunca o dict cru).
    """
    wa_target = _so_digitos(to)

    # --- Mensagem interativa com botoes ---
    if isinstance(reply, dict) and reply.get("type") == "interactive_buttons":
        body = str(reply.get("body") or "")
        if len(body) > _MAX_BODY:
            logger.warning(
                "[TRANSPORT] body interativo excede %d chars (%d) — truncando",
                _MAX_BODY, len(body),
            )
            body = body[:_MAX_BODY]

        botoes = reply.get("buttons") or []
        if len(botoes) > _MAX_BUTTONS:
            logger.warning(
                "[TRANSPORT] %d botoes excede o limite de %d — usando os 3 primeiros",
                len(botoes), _MAX_BUTTONS,
            )
            botoes = botoes[:_MAX_BUTTONS]

        buttons_payload = []
        for btn in botoes:
            btn_id = str(btn.get("id") or "")[:_MAX_ID]
            btn_title = str(btn.get("title") or "")
            if len(btn_title) > _MAX_TITLE:
                logger.warning(
                    "[TRANSPORT] title de botao excede %d chars (%r) — truncando",
                    _MAX_TITLE, btn_title,
                )
                btn_title = btn_title[:_MAX_TITLE]
            buttons_payload.append(
                {"type": "reply", "reply": {"id": btn_id, "title": btn_title}}
            )

        interactive = {
            "type": "button",
            "body": {"text": body},
            "action": {"buttons": buttons_payload},
        }
        footer = reply.get("footer")
        if footer:
            interactive["footer"] = {"text": str(footer)[:_MAX_FOOTER]}

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": wa_target,
            "type": "interactive",
            "interactive": interactive,
        }
        return payload, body

    # --- Mensagem de texto simples (str ou fallback defensivo) ---
    text = reply if isinstance(reply, str) else str(reply)
    payload = {
        "messaging_product": "whatsapp",
        "to": wa_target,
        "type": "text",
        "text": {"body": text},
    }
    return payload, text


def extract_interactive_inbound(msg: dict) -> str:
    """
    Extrai o conteudo util de uma mensagem inbound type="interactive".

    A Meta entrega a resposta de um botao interativo em
    msg["interactive"]["button_reply"] = {"id","title"} (ou "list_reply").
    Retorna o id do botao (contrato estavel; o vocabulario do bot reconhece
    "lgpd_aceitar"/"lgpd_recusar"), com fallback no title. String vazia se
    nao houver nada extraivel.
    """
    inter = msg.get("interactive") if isinstance(msg.get("interactive"), dict) else {}
    reply = inter.get("button_reply") or inter.get("list_reply") or {}
    if not isinstance(reply, dict):
        return ""
    return str(reply.get("id") or reply.get("title") or "").strip()
