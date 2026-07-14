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


def _record_lgpd_consent(contact_id: int, policy_version: str = ""):
    """Prova de consentimento LGPD: grava no contato (quando + versao da
    politica) E no audit_log. Best-effort: nunca quebra o fluxo do bot.

    policy_version: versao da politica exibida ao titular. Default = a do
    fluxo builtin (Hubloc); o caminho CX passa a versao do tenant
    (settings.ai.lgpd_policy_version).
    """
    version = (policy_version or "").strip() or LGPD_POLICY_VERSION
    now = utcnow().isoformat()
    try:
        document("wa_contacts", contact_id).set({
            "lgpd_consent": True,
            "lgpd_consent_at": now,
            "lgpd_policy_version": version,
        }, merge=True)
    except Exception as exc:
        logger.warning(
            "[LGPD] falha ao gravar consentimento no contato %s: %s",
            contact_id, exc,
        )
    log_audit(
        0, "LGPD_CONSENT_ACCEPTED",
        f"contato {contact_id} | politica {version}",
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


# =========================================================================
# Motor por tenant (dispatcher builtin x Dialogflow CX)
# =========================================================================
#
# tenants/{tid}.settings.ai (gravado pelo super-admin; ver
# docs/PLANO_TENANT_TESTE_VARIZEMED_CX.md) escolhe o motor. Sem config, ou
# com bot_engine != "dialogflow_cx", o builtin roda intacto — tenants
# existentes (Hubloc) nao mudam de comportamento.

_CX_MAX_CONSECUTIVE_FAILURES = 2

_CX_FALLBACK_MSG = (
    "Desculpe, estamos com uma instabilidade momentânea no atendimento "
    "automático. Pode reenviar sua mensagem em instantes?"
)

_CX_HANDOFF_FAIL_MSG = (
    "Desculpe pela instabilidade. Estou te transferindo para a nossa "
    "equipe de atendimento — em breve alguém responde por aqui."
)

# Handoff pedido pelo agente mas sem texto na resposta: nunca transferir em
# silencio (o cliente ficaria sem nenhuma mensagem).
_CX_HANDOFF_DEFAULT_MSG = (
    "Certo! Estou te transferindo para a nossa equipe de atendimento."
)

_CX_MAX_REPLY_CHARS = 4096  # limite de texto da Cloud API do WhatsApp

# Fallback de deteccao de handoff por TEXTO. O agente generativo nem sempre
# seta o parametro handoff_request (validado no staging 2026-07-14: a Val falou
# a mensagem de transferencia mas handoff_request veio False). O sistema antigo
# da Varizemed ja usava 2 sinais (parametro + hints de texto) por isso. Estas
# frases sao trechos das mensagens IMUTAVEIS de transferencia do playbook do
# agente (Step 6). Comparadas via _norm (sem acento, minusculo). Sobrescrevivel
# por tenant em settings.ai.handoff_text_hints.
_DEFAULT_HANDOFF_TEXT_HINTS = (
    "estou transferindo nossa conversa para a equipe de atendimento",
    "deixei sua solicitacao marcada como prioridade",
)


def _cx_is_handoff(result: dict, ai_cfg: dict) -> bool:
    """Handoff se o parametro handoff_request veio true OU o texto da resposta
    casa uma das frases de transferencia (fallback pro agente que nao seta o
    parametro)."""
    if result.get("handoff_request"):
        return True
    hints = ai_cfg.get("handoff_text_hints") or _DEFAULT_HANDOFF_TEXT_HINTS
    reply_norm = _norm(str(result.get("reply_text") or ""))
    if not reply_norm:
        return False
    return any(_norm(str(h)) in reply_norm for h in hints if h)


def _get_tenant_ai_config() -> dict:
    """Config settings.ai do tenant atual (dict vazio se ausente)."""
    from firestore_common import get_tenant_context
    from tenant_service import get_tenant

    tid = get_tenant_context()
    if not tid:
        return {}
    try:
        tenant = get_tenant(tid) or {}
    except Exception as exc:
        logger.warning("[BOT] leitura do tenant %s falhou: %s", tid, exc)
        return {}
    # Guard defensivo nos DOIS niveis: um doc de tenant malformado (settings ou
    # ai como string/lista) nao pode estourar o gate do bot (achado da revisao).
    settings = tenant.get("settings")
    if not isinstance(settings, dict):
        return {}
    ai_cfg = settings.get("ai")
    return ai_cfg if isinstance(ai_cfg, dict) else {}


def _cx_policy_version(ai_cfg: dict) -> str:
    """Versao de politica LGPD do tenant para a prova de consentimento.

    NUNCA cai na constante do builtin (LGPD_POLICY_VERSION = Hubloc): para um
    tenant CX (ex.: clinica, dado sensivel) isso carimbaria o consentimento com
    a politica de OUTRO tenant (achado alta da revisao). Sem versao configurada,
    usa um marcador neutro do proprio tenant e loga aviso.
    """
    from firestore_common import get_tenant_context

    version = str(ai_cfg.get("lgpd_policy_version") or "").strip()
    if version:
        return version
    tid = get_tenant_context() or "tenant"
    logger.warning(
        "[BOT-CX] lgpd_policy_version vazio no tenant %s — configure "
        "settings.ai.lgpd_policy_version (usando marcador neutro)", tid,
    )
    return f"{tid}-sem-versao"


async def process_bot_message_async(
    contact_id: int, text: str, contact_name: str = ""
) -> Optional[Union[str, dict]]:
    """Fachada assincrona do bot: decide o motor pelo tenant atual.

    Mesmo contrato de process_bot_message (None | str | dict). O webhook
    chama esta versao; o builtin continua exposto de forma sincrona para
    tools/sim_bot_flow.py e chamadas legadas.
    """
    from firestore_common import get_tenant_context

    ai_cfg = _get_tenant_ai_config()
    engine = str(ai_cfg.get("bot_engine") or "").strip().lower()
    if not engine:
        # Tenant SEM motor de IA -> bot builtin (Hubloc e afins).
        return process_bot_message(contact_id, text, contact_name)
    # Tenant COM motor de IA configurado NUNCA cai no builtin: o builtin e
    # hardcoded Hubloc (aviso LGPD "Hub Loc", menu de construcao, versao de
    # politica do Hubloc) — cair nele vazaria a marca e carimbaria consentimento
    # do tenant errado (achado alta da revisao). Motor pausado/desconhecido =
    # bot silencioso, nunca builtin.
    if engine == "dialogflow_cx":
        status = str(ai_cfg.get("status") or "active").strip().lower()
        if status == "active":
            return await _process_cx_message(contact_id, text, ai_cfg)
        logger.info("[BOT] motor CX pausado (status=%s) — bot silencioso", status)
        return None
    logger.warning(
        "[BOT] bot_engine desconhecido=%r no tenant %s — bot silencioso "
        "(nao cai no builtin)", engine, get_tenant_context(),
    )
    return None


def _cx_lgpd_notice(ai_cfg: dict) -> str:
    """Aviso LGPD do tenant (settings.ai) com fallback seguro generico."""
    notice = str(ai_cfg.get("lgpd_notice") or "").strip()
    url = str(ai_cfg.get("lgpd_privacy_url") or "").strip()
    if not notice:
        notice = (
            "Olá! Para seguir com o atendimento, precisamos tratar seus "
            "dados pessoais conforme a LGPD."
        )
    if url:
        notice += f"\n(Política de Privacidade: {url})"
    notice += "\n\nPodemos continuar?"
    return notice


async def _process_cx_message(
    contact_id: int, text: str, ai_cfg: dict
) -> Optional[Union[str, dict]]:
    """Turno do motor Dialogflow CX para o contato do tenant atual."""
    import bot_engine_dialogflow
    from firestore_common import get_tenant_context

    if not is_bot_enabled():
        return None

    contact = get_wa_contact(contact_id)
    # bot_completed re-checado aqui (nao so no webhook): reduz o reprocesso
    # quando 2 mensagens do mesmo contato correm durante um DetectIntent lento
    # e a 1a ja transferiu pro humano (achado media da revisao).
    if not contact or contact.get("assigned_to") or contact.get("bot_completed"):
        return None

    state = _get_bot_state(contact_id)

    # ------------------------------------------------------------------
    # Gate LGPD local — SEMPRE antes do motor. A prova de consentimento
    # (contato + audit + versao) fica no CRM; o agente CX recebe
    # lgpd_consent=true e nunca refaz a pergunta (flow neutralizado).
    # ------------------------------------------------------------------
    lgpd_response = handle_lgpd(state, text, aviso_text=_cx_lgpd_notice(ai_cfg))

    first_cx_text = None
    if lgpd_response is not None:
        if state.get("lgpd_status") == "accepted":
            _record_lgpd_consent(
                contact_id,
                policy_version=_cx_policy_version(ai_cfg),
            )
            state["step"] = "cx"
            state.setdefault("started_at", utcnow().isoformat())
            _set_bot_state(contact_id, state)
            # Primeira pergunta do cliente (guardada no gate) vai ao agente
            # neste mesmo turno; a confirmacao do aceite prefixa a resposta.
            first_cx_text = str(state.get("user_first_input") or "").strip()
            if not first_cx_text:
                return lgpd_response
        else:
            if not state.get("step"):
                state["step"] = "lgpd"
                state["started_at"] = utcnow().isoformat()
            _set_bot_state(contact_id, state)
            return lgpd_response

    if state.get("step") != "cx":
        state["step"] = "cx"
        state.setdefault("started_at", utcnow().isoformat())
        _set_bot_state(contact_id, state)

    # ------------------------------------------------------------------
    # DetectIntent
    # ------------------------------------------------------------------
    wa_digits = re.sub(r"\D", "", str(contact.get("wa_id") or ""))
    if not (10 <= len(wa_digits) <= 15):
        logger.warning(
            "[BOT-CX] wa_id do contato %d fora do formato de sessao (%d digitos)",
            contact_id, len(wa_digits),
        )
        return None

    project = str(ai_cfg.get("gcp_project_id") or "").strip()
    agent = str(ai_cfg.get("agent_id") or "").strip()
    if project and agent:
        session_params = {
            "user_id": f"+{wa_digits}",
            "tenant_id": str(get_tenant_context() or ""),
            "lgpd_consent": True,
        }
        turn_text = first_cx_text if first_cx_text is not None else text
        result = await bot_engine_dialogflow.detect_intent_text(
            ai_cfg, wa_digits, turn_text, session_params
        )
    else:
        logger.warning(
            "[BOT-CX] settings.ai incompleto (gcp_project_id/agent_id) "
            "para o contato %d — tratando como falha do motor", contact_id,
        )
        result = {"ok": False}

    # ------------------------------------------------------------------
    # Falha do motor: 1a -> fallback educado; 2a consecutiva -> handoff.
    # ------------------------------------------------------------------
    if not result.get("ok"):
        # cx_fail_count nao e atomico: 2 mensagens concorrentes durante um
        # outage do CX podem subcontar (lost update), atrasando o handoff de 2
        # strikes em ~1 turno. Aceito na v1 (so acontece em outage + entrega
        # concorrente; consequencia = uma msg de desculpa extra). Se virar
        # problema, trocar por firestore.Increment + releitura antes de decidir.
        fails = int(state.get("cx_fail_count") or 0) + 1
        if fails >= _CX_MAX_CONSECUTIVE_FAILURES:
            _finalize_cx_handoff(
                contact_id, ai_cfg,
                summary="Bot IA indisponivel (falhas consecutivas)",
            )
            return _CX_HANDOFF_FAIL_MSG
        _set_bot_state(contact_id, {"cx_fail_count": fails})
        return _CX_FALLBACK_MSG

    if int(state.get("cx_fail_count") or 0):
        _set_bot_state(contact_id, {"cx_fail_count": 0})

    reply = str(result.get("reply_text") or "").strip()
    # No turno do aceite, a confirmacao do consentimento SEMPRE vai ao cliente,
    # mesmo que o agente responda vazio nesse 1o turno — senao o cliente aceita
    # a LGPD e fica no silencio total (achado da revisao). lgpd_response e str
    # (o branch accepted so retorna texto).
    if first_cx_text is not None and isinstance(lgpd_response, str) and lgpd_response:
        reply = f"{lgpd_response}\n\n{reply}".strip() if reply else lgpd_response
    # Trava a invariante 4096 no texto FINAL: o prefixo do aceite e somado
    # DEPOIS da truncagem do conector (achado da revisao).
    if len(reply) > _CX_MAX_REPLY_CHARS:
        reply = reply[:_CX_MAX_REPLY_CHARS]

    # ------------------------------------------------------------------
    # Handoff pedido pelo agente -> pool do setor configurado.
    # Detecta por parametro OU por texto (o agente nem sempre seta o param).
    # ------------------------------------------------------------------
    if _cx_is_handoff(result, ai_cfg):
        _finalize_cx_handoff(
            contact_id, ai_cfg,
            summary=str(result.get("handoff_summary") or "").strip(),
            user_name=str(result.get("user_name") or "").strip(),
        )
        # Nunca transferir em silencio (agente pode pedir handoff sem texto).
        return reply or _CX_HANDOFF_DEFAULT_MSG

    # conversation_complete sem handoff: cliente pode voltar a falar com o
    # bot depois. NAO limpa o estado (preservaria re-pergunta da LGPD) —
    # a sessao do CX expira sozinha no Dialogflow (~30min).
    return reply or None


def _dept_id_by_bot_key(bot_key: str):
    """department_id do tenant atual cujo bot_key casa (None se nao ha)."""
    key = (bot_key or "").strip().lower()
    if not key:
        return None
    for dept in get_all_departments():
        if (dept.get("bot_key") or "").strip().lower() == key:
            return dept.get("id")
    return None


def _finalize_cx_handoff(
    contact_id: int, ai_cfg: dict, summary: str = "", user_name: str = ""
):
    """Encerra o bot CX transferindo o contato para atendimento humano.

    Mesmo modelo do _finalize_bot: bot_completed=True + department_id (pela
    bot_key configurada no tenant), propagacao as conversations (pool do
    setor segmenta por department_id da CONVERSATION), system message com o
    resumo do agente e limpeza do estado. assigned_to fica vazio (pool).
    """
    dept_id = _dept_id_by_bot_key(str(ai_cfg.get("handoff_bot_key") or ""))

    notes = "Bot IA: handoff"
    if user_name:
        notes += f" | Nome={user_name}"

    updates = {
        "bot_completed": True,
        "bot_notes": notes,
    }
    if dept_id:
        updates["department_id"] = dept_id
    document("wa_contacts", contact_id).set(updates, merge=True)

    if dept_id:
        for snap in collection("wa_conversations").where(
            "contact_id", "==", contact_id
        ).stream():
            cd = snap.to_dict() or {}
            if cd.get("is_backup"):
                continue
            snap.reference.set({"department_id": dept_id}, merge=True)

    sys_content = "Bot IA finalizado | Transferido para atendimento humano"
    if summary:
        sys_content += f" | Resumo: {summary}"
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
        "[BOT-CX] Handoff finalizado | contato=%d | dept_id=%s",
        contact_id, dept_id,
    )
