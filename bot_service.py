# -*- coding: utf-8 -*-

"""
Servico de bot para atendimento automatico via WhatsApp.
Fluxo conversacional enxuto: gate LGPD e, apos o aceite, coleta do setor
(departamento) desejado. Opera como state machine: cada mensagem do cliente
avanca o estado.

Fluxo completo:
  (primeiro contato) -> lgpd_awaiting -> ask_sector -> done

A etapa LGPD e gerenciada pelo modulo lgpd_bot.py e atua como gate obrigatorio
antes de qualquer coleta de dados pessoais.

Retorno de process_bot_message:
  - None  -> bot nao deve responder (operador atribuido, bot desligado, ou fluxo concluido)
  - str   -> mensagem de texto simples
  - dict  -> mensagem interativa com botoes (repassada do modulo LGPD)
"""

import re
import logging
import unicodedata
from datetime import datetime, timezone, timedelta
from typing import Optional, Union

from firestore_common import document, utcnow, collection
from database import (
    get_wa_contact, get_system_settings, get_all_departments,
    save_wa_message, log_audit,
)
from lgpd_bot import handle_lgpd

logger = logging.getLogger("castro_crm.bot")

# =========================================================================
# Timezone e expediente
# =========================================================================

EMPRESA_TZ = timezone(timedelta(hours=-3))
HORA_INICIO = 7
HORA_FIM = 17

# =========================================================================
# Vocabularios de classificacao de setor
# =========================================================================
# Obs.: todos os termos abaixo sao comparados atraves de _norm (que remove
# acentos e normaliza espacos), portanto acentuacao aqui e irrelevante para
# o matching — vale a forma normalizada.

TERMOS_PEDIDO = {
    "quero", "preciso", "gostaria", "necessito", "alugar", "locar",
    "locação", "cotar", "orçamento", "valor",
    "preço", "quanto", "reservar",
    # Variantes sem acento
    "locacao", "orcamento", "preco",
}

TERMOS_EQUIPAMENTO = {
    "betoneira", "martelete", "martelo", "martelo demolidor",
    "rompedor", "compactador", "compactador de solo",
    "placa vibratória", "placa vibratoria",
    "andaime", "andaimes",
    "escora", "escoras", "furadeira", "serra", "serra circular",
    "serra mármore", "serra marmore",
    "lavadora", "compressor",
    "gerador", "enceradeira", "vibrador de concreto", "lixadeira",
    "cortadora", "cortadora de piso", "perfurador", "parafusadeira",
    "guincho", "container", "caçamba", "cacamba",
    "rolo compactador", "minicarregadeira", "retroescavadeira",
    "bate estaca", "misturador", "bomba",
    "niveladora", "pá carregadeira", "pa carregadeira",
    "motoniveladora", "escavadeira",
}

PALAVRAS_COMERCIAL = {
    "comercial", "vendas", "locação", "locacao",
    "aluguel", "alugar", "locar",
    "orçamento", "orcamento", "cotação", "cotacao",
    "preço", "preco", "valor", "equipamento",
}

PALAVRAS_FINANCEIRO = {
    "financeiro", "boleto", "boletos", "nota", "nota fiscal",
    "pagamento", "pagamentos", "cobrança", "cobranca",
    "fatura", "faturas", "segunda via", "pix", "depósito",
    "deposito",
}

PALAVRAS_ADMINISTRATIVO = {
    "administrativo", "adm", "cadastro", "documento", "documentos",
    "contrato", "contratos", "fornecedor", "fornecedores", "rh",
}

PALAVRAS_SUPORTE = {
    "sac", "suporte", "atendimento", "reclamação",
    "reclamacao", "problema", "defeito", "quebrado",
    "manutenção", "manutencao",
    "avaria", "atraso", "troca", "trocar", "devolução", "devolucao",
    "devolver", "assistência", "assistencia", "tecnica", "técnica",
    "cancelamento",
}


# =========================================================================
# Utilidades de texto
# =========================================================================

def _norm(texto: str) -> str:
    texto = texto.strip().lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", texto)


def _contem(texto_norm: str, expressao: str) -> bool:
    expressao = _norm(expressao)
    return re.search(
        r"(?<!\w)" + re.escape(expressao) + r"(?!\w)", texto_norm
    ) is not None


def _detectar_equipamento(texto: str) -> Optional[str]:
    """
    Detecta equipamentos conhecidos pelo vocabulario. Usado na
    classificacao de setor para tratar "betoneira" como Comercial.
    """
    texto_norm = _norm(texto)
    if any(_contem(texto_norm, t) for t in TERMOS_EQUIPAMENTO):
        return texto.strip()
    if any(_contem(texto_norm, t) for t in TERMOS_PEDIDO):
        if re.search(
            r"\b\d+\s?(kg|cv|hp|mm|cm|m|pol|polegada|polegadas)\b",
            texto_norm,
        ):
            return texto.strip()
    return None


def _classificar_setor(texto: str) -> Optional[int]:
    texto_norm = _norm(texto.strip())
    direto = {"1": 1, "2": 2, "3": 3, "4": 4}
    if texto_norm in direto:
        return direto[texto_norm]
    # Assistencia tecnica / troca / devolucao (suporte) tem prioridade sobre
    # comercial: "trocar equipamento" deve ir para suporte, nao vendas.
    if any(_contem(texto_norm, p) for p in PALAVRAS_SUPORTE):
        return 2
    if any(_contem(texto_norm, p) for p in PALAVRAS_FINANCEIRO):
        return 3
    if any(_contem(texto_norm, p) for p in PALAVRAS_COMERCIAL):
        return 1
    if _detectar_equipamento(texto):
        return 1
    if any(_contem(texto_norm, p) for p in PALAVRAS_ADMINISTRATIVO):
        return 4
    return None


# =========================================================================
# Mapeamento setor -> departamento do CRM
# =========================================================================

_SETOR_NOMES = {
    1: "Comercial",
    2: "Assistência Técnica",
    3: "Financeiro",
    4: "Administrativo",
}

# Setor do bot -> bot_key do departamento no CRM. Todos os setores roteiam para
# um departamento real (a pool do frontend segmenta por department_id da
# conversation). A opcao 4 ("Outros assuntos" no menu) cai no Administrativo.
# O roteamento e por bot_key, entao renomear o departamento na UI nao quebra.
_BOT_KEY_BY_SETOR = {1: "comercial", 2: "sac", 3: "financeiro", 4: "administrativo"}

_dept_cache = None


def _get_dept_map() -> dict:
    """Mapeia setor do bot -> department_id do CRM.

    Preferencia: campo `bot_key` do departamento (estavel, nao quebra com rename).
    Fallback: substring match com _SETOR_NOMES quando bot_key nao esta definido.
    """
    global _dept_cache
    if _dept_cache is not None:
        return _dept_cache
    depts = get_all_departments()
    mapping = {}

    by_bot_key = {}
    for dept in depts:
        bk = (dept.get("bot_key") or "").strip().lower()
        if bk:
            by_bot_key[bk] = dept.get("id")
    for setor_id, bot_key in _BOT_KEY_BY_SETOR.items():
        if bot_key in by_bot_key:
            mapping[setor_id] = by_bot_key[bot_key]

    for dept in depts:
        name_norm = _norm(dept.get("name", ""))
        for setor_id, setor_nome in _SETOR_NOMES.items():
            if setor_id in mapping:
                continue
            if _norm(setor_nome) in name_norm or name_norm in _norm(setor_nome):
                mapping[setor_id] = dept.get("id")

    _dept_cache = mapping
    return mapping


def invalidate_dept_cache():
    global _dept_cache
    _dept_cache = None


# =========================================================================
# Bot state machine
# =========================================================================

def _get_bot_state(contact_id: int) -> dict:
    ref = document("bot_states", contact_id)
    snap = ref.get()
    if snap.exists:
        return snap.to_dict() or {}
    return {}


def _set_bot_state(contact_id: int, state: dict):
    document("bot_states", contact_id).set(state, merge=True)


def _clear_bot_state(contact_id: int):
    document("bot_states", contact_id).delete()


def _esta_no_expediente() -> bool:
    agora = datetime.now(timezone.utc).astimezone(EMPRESA_TZ)
    return agora.weekday() < 5 and HORA_INICIO <= agora.hour < HORA_FIM


MENU_SETORES = (
    "Informe o número da opção desejada:\n\n"
    "1 - Comercial\n"
    "2 - Assistência técnica / troca / devolução\n"
    "3 - Financeiro\n"
    "4 - Outros assuntos"
)


def _msg_pedir_setor(prefixo: str = "") -> str:
    """Monta a mensagem do menu de setores, anexando o aviso de expediente
    quando estiver fora do horario de atendimento."""
    texto = prefixo
    if not _esta_no_expediente():
        texto += (
            "\n\nNosso expediente funciona de segunda a sexta, das 7h às 17h.\n"
            "Sua mensagem será registrada e o retorno "
            "ocorrerá no próximo horário útil."
        )
    texto += "\n\n" + MENU_SETORES
    return texto.strip()


def is_bot_enabled() -> bool:
    settings = get_system_settings()
    return bool(settings.get("bot_enabled", False))


LGPD_POLICY_VERSION = "hubloc-2026-06"


def _record_lgpd_consent(contact_id: int):
    """Prova de consentimento LGPD: grava no contato (quando + versao da
    politica) E no audit_log. Best-effort: nunca quebra o fluxo do bot."""
    now = utcnow().isoformat()
    try:
        document("wa_contacts", contact_id).set({
            "lgpd_consent": True,
            "lgpd_consent_at": now,
            "lgpd_policy_version": LGPD_POLICY_VERSION,
        }, merge=True)
    except Exception as exc:
        logger.warning(
            "[LGPD] falha ao gravar consentimento no contato %s: %s",
            contact_id, exc,
        )
    log_audit(
        0, "LGPD_CONSENT_ACCEPTED",
        f"contato {contact_id} | politica {LGPD_POLICY_VERSION}",
    )


def process_bot_message(
    contact_id: int, text: str, contact_name: str = ""
) -> Optional[Union[str, dict]]:
    """
    Processa uma mensagem do cliente pelo bot.

    Returns:
        None  -> bot nao deve responder.
        str   -> mensagem de texto simples.
        dict  -> mensagem interativa (botoes LGPD); o webhook deve
                 enviar como interactive/button via WhatsApp Cloud API.
    """
    if not is_bot_enabled():
        return None

    contact = get_wa_contact(contact_id)
    if not contact:
        return None

    if contact.get("assigned_to"):
        return None

    state = _get_bot_state(contact_id)
    step = state.get("step", "")

    # =================================================================
    # LGPD Gate - executa antes de qualquer coleta de dados
    # =================================================================
    lgpd_response = handle_lgpd(state, text)

    if lgpd_response is not None:
        lgpd_status = state.get("lgpd_status")

        if lgpd_status == "accepted":
            _record_lgpd_consent(contact_id)
            state["step"] = "ask_sector"
            state["started_at"] = utcnow().isoformat()
            _set_bot_state(contact_id, state)
            return _msg_pedir_setor(lgpd_response)

        if not step:
            state["step"] = "lgpd"
            state["started_at"] = utcnow().isoformat()
        _set_bot_state(contact_id, state)
        return lgpd_response

    # =================================================================
    # Fluxo principal (LGPD ja aceita): coleta direto o setor
    # =================================================================

    if not step or step == "lgpd":
        state["step"] = "ask_sector"
        state["started_at"] = utcnow().isoformat()
        _set_bot_state(contact_id, state)
        return _msg_pedir_setor("Olá! Como podemos te ajudar hoje?")

    # -- Etapa: coletar setor --
    if step == "ask_sector":
        setor = _classificar_setor(text.strip())
        if setor is None:
            return "Opção inválida. Digite 1, 2, 3 ou 4.\n\n" + MENU_SETORES

        _finalize_bot(contact_id, state, setor)
        return None

    # Estado desconhecido: resetar (observabilidade — sem PII, so step/contato)
    logger.warning(
        "[BOT] step desconhecido=%r contato=%d — resetando estado",
        step, contact_id,
    )
    _clear_bot_state(contact_id)
    return None


def _finalize_bot(contact_id: int, state: dict, setor: int):
    """Finaliza o bot: atribui o contato ao departamento correto."""
    dept_map = _get_dept_map()
    dept_id = dept_map.get(setor)
    setor_nome = _SETOR_NOMES.get(setor, "Desconhecido")

    notes = f"Bot: Setor={setor_nome}"

    updates = {
        "bot_completed": True,
        "bot_setor": setor,
        "bot_setor_nome": setor_nome,
        "bot_notes": notes,
    }
    if dept_id:
        updates["department_id"] = dept_id

    document("wa_contacts", contact_id).set(updates, merge=True)

    # Propaga o setor para as threads do contato: a pool ("novos") do frontend
    # segmenta por department_id da CONVERSATION, nao do contato. Mantem
    # assigned_to vazio — o lead segue sem dono, na pool do setor. Pula backup.
    if dept_id:
        for snap in collection("wa_conversations").where(
            "contact_id", "==", contact_id
        ).stream():
            cd = snap.to_dict() or {}
            if cd.get("is_backup"):
                continue
            snap.reference.set({"department_id": dept_id}, merge=True)

    sys_content = (
        f"Bot finalizado | {notes} | Encaminhado para {setor_nome}"
    )
    save_wa_message(
        wa_message_id="",
        contact_id=contact_id,
        direction="system",
        msg_type="system",
        content=sys_content,
        status="",
        timestamp_wa=utcnow().isoformat(),
    )

    _clear_bot_state(contact_id)
    logger.info(
        "[BOT] Fluxo finalizado | contato=%d | setor=%s | dept_id=%s",
        contact_id, setor_nome, dept_id,
    )
