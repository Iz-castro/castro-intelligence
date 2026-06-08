# -*- coding: utf-8 -*-

"""
lgpd.py - Handler de consentimento LGPD
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

Interface:
  handle_lgpd(state, message_text, saudacao) -> Optional[str]
    - Retorna str com resposta ao cliente (interceptou o fluxo)
    - Retorna None quando o consentimento ja existe (pass through)
    - Modifica o dict `state` in place; o chamador persiste no Firestore.
"""

import re
import logging
import unicodedata
from typing import Optional

logger = logging.getLogger("castro_crm.lgpd")

# =========================================================================
# Vocabulario de aceite / recusa
# =========================================================================

_ACEITE_TERMOS = {
    "sim", "aceito", "concordo", "ok", "pode", "autorizo",
    "claro", "com certeza", "aceito os termos", "yes", "s",
    "positivo", "pode sim", "tudo bem", "de acordo",
}

_RECUSA_TERMOS = {
    "nao", "recuso", "discordo", "n", "no", "nope",
    "nao aceito", "nao concordo", "nao autorizo",
    "negativo", "de jeito nenhum", "prefiro nao",
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
# Textos LGPD
# =========================================================================

_AVISO_LGPD = (
    "Antes de prosseguirmos, informamos que esta conversa podera "
    "envolver a coleta de dados pessoais como nome e telefone, "
    "utilizados exclusivamente para fins de atendimento comercial, "
    "elaboracao de orcamentos e gestao de contratos de locacao.\n\n"
    "Seus dados sao tratados com sigilo e em conformidade com a "
    "Lei Geral de Protecao de Dados (LGPD - Lei 13.709/2018).\n\n"
    "Para conhecer nossa politica de privacidade completa, acesse:\n"
    "https://www.centralloc.com.br/politica-de-privacidade-e-protecao-de-dados-pessoais-hub-loc-equipamentos-p-construcao-civil/\n\n"
    "Voce concorda com o uso dos seus dados para fins de atendimento?\n"
    "Responda SIM para aceitar ou NAO para recusar."
)

_ACEITO_RESPOSTA = (
    "Certo, seus dados serao tratados com total seguranca e responsabilidade."
)

_RECUSA_RESPOSTA = (
    "Entendido. Sem o seu consentimento, infelizmente nao podemos "
    "prosseguir com o atendimento por este canal.\n\n"
    "Caso mude de ideia, e so nos enviar uma nova mensagem.\n"
    "A Hub Loc agradece o seu contato!"
)

_RECUSA_LEMBRETE = (
    "Voce optou por nao consentir com o uso dos seus dados.\n"
    "Para iniciar um novo atendimento, responda SIM."
)

_NAO_ENTENDI = (
    "Desculpe, nao entendi sua resposta.\n"
    "Para prosseguir, preciso da sua confirmacao sobre o uso "
    "dos seus dados conforme a LGPD.\n\n"
    "Responda SIM para aceitar ou NAO para recusar."
)


# =========================================================================
# Handler principal
# =========================================================================

def handle_lgpd(
    state: dict,
    message_text: str,
    saudacao: str = "",
) -> Optional[str]:
    """
    Verifica e gerencia o consentimento LGPD.

    Args:
        state: dict do bot_states (sera modificado in place).
        message_text: texto da mensagem recebida do cliente.
        saudacao: saudacao contextual (ex: "Bom dia") gerada pelo bot.

    Returns:
        str com mensagem de resposta ao cliente (fluxo interceptado), ou
        None se o consentimento ja foi dado (pass through para o bot).
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
        return _RECUSA_LEMBRETE

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
        return _NAO_ENTENDI

    # --- Primeiro contato: exibir aviso LGPD ---
    state["lgpd_status"] = "awaiting"
    state["user_first_input"] = message_text

    prefixo = f"{saudacao}! " if saudacao else ""
    texto = (
        f"{prefixo}Bem-vindo a Hub Loc, sua locadora de "
        f"equipamentos para construcao.\n\n{_AVISO_LGPD}"
    )
    logger.info("[LGPD] Aviso enviado ao contato")
    return texto
