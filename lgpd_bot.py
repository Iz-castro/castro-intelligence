# -*- coding: utf-8 -*-

"""
lgpd_bot.py - Handler de consentimento LGPD
Castro Intelligence CRM - Hub Loc

Gerencia o fluxo de consentimento conforme a Lei Geral de Protecao
de Dados (Lei 13.709/2018) antes de iniciar qualquer coleta de
informacoes pessoais no atendimento via WhatsApp.

Opera como gate no inicio da maquina de estados do bot:
  - Se o consentimento ainda nao foi solicitado, exibe o aviso e
    aguarda resposta.
  - Se ja foi dado, retorna None para o bot prosseguir.
  - Se foi recusado, bloqueia o fluxo e permite re-consentimento.

Campos adicionados ao estado do bot (bot_states/{contact_id}):
  lgpd_status  : "awaiting" | "accepted" | "refused" | None
  lgpd_consent : True | False | None

Retorno de handle_lgpd:
  - None                -> consentimento ja existe (pass through)
  - str                 -> mensagem de texto simples
  - dict (type=interactive_buttons) -> mensagem com botoes interativos

  Quando o retorno for dict, o chamador (webhook) deve enviar como
  mensagem interativa via WhatsApp Cloud API. A traducao do dict
  abstrato para o payload da Meta e feita por
  bot_transport.build_outbound_payload() (camada de transporte) -
  este modulo nao conhece o formato da Graph API.

Integracao com webhook.py / bot_transport.py:
  O webhook extrai button_reply.id de respostas interativas (via
  bot_transport.extract_interactive_inbound) e passa como parametro
  `message_text` em handle_lgpd. Os IDs "lgpd_aceitar" e
  "lgpd_recusar" ja fazem parte do vocabulario.
"""

import re
import logging
import unicodedata
from typing import Optional, Union

logger = logging.getLogger("castro_crm.lgpd")

# =========================================================================
# Vocabulario de aceite / recusa
# =========================================================================

_ACEITE_TERMOS = {
    "sim", "aceito", "concordo", "ok", "pode", "autorizo",
    "claro", "com certeza", "aceito os termos", "yes", "s",
    "positivo", "pode sim", "tudo bem", "de acordo",
    "aceitar",
    # IDs dos botoes interativos (recebidos via button_reply)
    "lgpd_aceitar",
}

_RECUSA_TERMOS = {
    "nao", "recuso", "discordo", "n", "no", "nope",
    "nao aceito", "nao concordo", "nao autorizo",
    "negativo", "de jeito nenhum", "prefiro nao",
    "recusar",
    # IDs dos botoes interativos
    "lgpd_recusar",
}


def _normalizar(texto: str) -> str:
    """Remove acentos, pontuacao final e normaliza espacos."""
    texto = texto.strip().lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = re.sub(r"[.!?,;:]+$", "", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _eh_aceite(texto: str) -> bool:
    return _normalizar(texto) in _ACEITE_TERMOS


def _eh_recusa(texto: str) -> bool:
    return _normalizar(texto) in _RECUSA_TERMOS


# =========================================================================
# Botoes interativos
# =========================================================================

_BTN_ACEITAR = {"id": "lgpd_aceitar", "title": "Aceitar"}
_BTN_RECUSAR = {"id": "lgpd_recusar", "title": "Recusar"}


def _resposta_botoes(
    corpo: str,
    botoes: list,
    rodape: Optional[str] = None,
) -> dict:
    """
    Monta estrutura de resposta com botoes interativos.

    O chamador (webhook) deve converter esse dict em payload
    interactive/button da WhatsApp Cloud API.
    Use montar_payload_interativo() para obter o payload pronto.
    """
    resp = {
        "type": "interactive_buttons",
        "body": corpo,
        "buttons": botoes,
    }
    if rodape:
        resp["footer"] = rodape
    return resp


# =========================================================================
# Textos LGPD (com acentuacao correta)
# =========================================================================

_AVISO_LGPD = (
    "Antes de prosseguirmos, informamos que esta conversa "
    "poderá envolver a coleta de dados pessoais como nome "
    "e telefone, utilizados exclusivamente para fins de "
    "atendimento comercial, elaboração de orçamentos "
    "e gestão de contratos de locação.\n\n"
    "Seus dados são tratados com sigilo e em conformidade "
    "com a Lei Geral de Proteção de Dados "
    "(LGPD - Lei 13.709/2018).\n\n"
    "Para conhecer nossa política de privacidade completa, acesse:\n"
    "https://www.centralloc.com.br/politica-de-privacidade-e-protecao-de-dados-pessoais-hub-loc-equipamentos-p-construcao-civil/\n\n"
    "Você concorda com o uso dos seus dados para fins de atendimento?\n"
    "Toque em um dos botões abaixo ou responda SIM para aceitar ou NÃO para recusar."
)

_ACEITO_RESPOSTA = (
    "Certo, seus dados serão tratados com total "
    "segurança e responsabilidade."
)

_RECUSA_RESPOSTA = (
    "Entendido. Sem o seu consentimento, infelizmente "
    "não podemos prosseguir com o atendimento por este canal.\n\n"
    "Caso mude de ideia, é só nos enviar uma nova mensagem.\n"
    "A Hub Loc agradece o seu contato!"
)

_RECUSA_LEMBRETE_CORPO = (
    "Você optou por não consentir com o uso dos seus dados.\n"
    "Para iniciar um novo atendimento, toque no botão abaixo ou responda SIM."
)

_NAO_ENTENDI_CORPO = (
    "Desculpe, não entendi sua resposta.\n"
    "Para prosseguir, preciso da sua confirmação sobre o uso "
    "dos seus dados conforme a LGPD.\n\n"
    "Toque em um dos botões abaixo ou responda SIM para aceitar ou NÃO para recusar."
)


# =========================================================================
# Handler principal
# =========================================================================

def handle_lgpd(
    state: dict,
    message_text: str,
    saudacao: str = "",
) -> Optional[Union[str, dict]]:
    """
    Verifica e gerencia o consentimento LGPD.

    Args:
        state: dict do bot_states (sera modificado in place).
        message_text: texto da mensagem recebida do cliente,
                      ou o button_reply.id quando vier de botao interativo.
        saudacao: saudacao contextual (ex: "Bom dia") gerada pelo bot.

    Returns:
        None  -> consentimento ja existe (pass through para o bot).
        str   -> mensagem de texto simples.
        dict  -> mensagem interativa com botoes (type="interactive_buttons").
    """
    lgpd_consent = state.get("lgpd_consent")
    lgpd_status = state.get("lgpd_status")

    # --- Consentimento ja dado: pass through ---
    if lgpd_consent is True:
        return None

    # --- Consentimento recusado: permitir re-consentimento ---
    if lgpd_consent is False:
        if _eh_aceite(message_text):
            state["lgpd_consent"] = True
            state["lgpd_status"] = "accepted"
            logger.info("[LGPD] Re-consentimento aceito")
            return _ACEITO_RESPOSTA

        return _resposta_botoes(
            corpo=_RECUSA_LEMBRETE_CORPO,
            botoes=[_BTN_ACEITAR],
        )

    # --- Aguardando resposta do aviso ja enviado ---
    if lgpd_status == "awaiting":
        if _eh_aceite(message_text):
            state["lgpd_consent"] = True
            state["lgpd_status"] = "accepted"
            logger.info("[LGPD] Consentimento aceito")
            return _ACEITO_RESPOSTA

        if _eh_recusa(message_text):
            state["lgpd_consent"] = False
            state["lgpd_status"] = "refused"
            logger.info("[LGPD] Consentimento recusado")
            return _RECUSA_RESPOSTA

        # Resposta nao reconhecida: reenviar botoes
        return _resposta_botoes(
            corpo=_NAO_ENTENDI_CORPO,
            botoes=[_BTN_ACEITAR, _BTN_RECUSAR],
        )

    # --- Primeiro contato: exibir aviso LGPD com botoes ---
    state["lgpd_status"] = "awaiting"
    state["user_first_input"] = message_text

    prefixo = f"{saudacao}! " if saudacao else ""
    corpo = (
        f"{prefixo}Bem-vindo à Hub Loc, sua locadora de "
        f"equipamentos para construção.\n\n{_AVISO_LGPD}"
    )
    logger.info("[LGPD] Aviso enviado ao contato")

    return _resposta_botoes(
        corpo=corpo,
        botoes=[_BTN_ACEITAR, _BTN_RECUSAR],
    )
