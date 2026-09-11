# -*- coding: utf-8 -*-

"""
Servico de bot para atendimento automatico via WhatsApp.
Fluxo conversacional enxuto: gate LGPD e, apos o aceite, encaminhamento
DIRETO para a fila do setor Comercial (pool "Novos Leads" do frontend),
sem dono. Opera como state machine: cada mensagem do cliente avanca o estado.

Fluxo completo:
  (primeiro contato) -> lgpd_awaiting -> done (fila do Comercial)

O menu de setores foi removido em 2026-07-24 (decisao Hubloc: todo lead novo
entra pelo Comercial; o operador transfere de setor no CRM se preciso).
Estados "ask_sector" ainda em voo no deploy sao honrados: escolha digitada
roteia pro setor correspondente; entrada nao reconhecida cai no Comercial.

A etapa LGPD e gerenciada pelo modulo lgpd_bot.py e atua como gate obrigatorio
antes de qualquer coleta de dados pessoais.

Retorno de process_bot_message:
  - None  -> bot nao deve responder (operador atribuido, bot desligado, ou fluxo concluido)
  - str   -> mensagem de texto simples
  - dict  -> mensagem interativa com botoes (repassada do modulo LGPD)
"""

import re
import logging
import time
import unicodedata
from datetime import datetime, timezone, timedelta
from typing import Optional, Union

from config import CX_DETECT_TIMEOUT_SECONDS
from firestore_common import document, utcnow, collection
from database import (
    get_wa_contact, get_system_settings, get_all_departments,
    save_wa_message, log_audit,
)
from lgpd_bot import handle_lgpd
from lead_temperature import classify_lead_temperature, signal_keys
from business_hours import builtin_expediente_notice, cx_hours_params

logger = logging.getLogger("castro_crm.bot")

# =========================================================================
# Horario comercial: business_hours.py (fonte unica por tenant, frente b).
# As constantes EMPRESA_TZ/HORA_INICIO/HORA_FIM sairam em 2026-08-10 — o 7h
# hardcoded ja divergia do atendimento real da Hubloc (8h) e nao valia por
# tenant.
# =========================================================================

# =========================================================================
# Vocabularios de classificacao de setor (LEGADO)
# =========================================================================
# Usados apenas para honrar estados "ask_sector" em voo no deploy que removeu
# o menu de setores (2026-07-24). Podem ser removidos junto com o handler
# legado quando esses estados drenarem.
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
# conversation). Fluxo atual usa so o 1 (Comercial); 2-4 permanecem pelo
# handler legado de estados "ask_sector" em voo.
# O roteamento e por bot_key, entao renomear o departamento na UI nao quebra.
_BOT_KEY_BY_SETOR = {1: "comercial", 2: "sac", 3: "financeiro", 4: "administrativo"}

# Cache POR TENANT (dict tenant_id -> mapping). Um global unico vazaria os
# department_id do 1o tenant builtin para os demais no mesmo container.
_dept_cache = {}


def _get_dept_map() -> dict:
    """Mapeia setor do bot -> department_id do CRM (cache por tenant).

    Preferencia: campo `bot_key` do departamento (estavel, nao quebra com rename).
    Fallback: substring match com _SETOR_NOMES quando bot_key nao esta definido.
    """
    from firestore_common import get_tenant_context
    tid = get_tenant_context() or ""
    cached = _dept_cache.get(tid)
    if cached is not None:
        return cached
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

    _dept_cache[tid] = mapping
    return mapping


def invalidate_dept_cache():
    # Limpa TODOS os tenants (edicao de setor e rara; rebuild e barato).
    _dept_cache.clear()


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
    document("bot_buffers", contact_id).delete()


SETOR_COMERCIAL = 1

_MSG_FILA_COMERCIAL = (
    "Você já está na fila do nosso time Comercial — em breve um de "
    "nossos atendentes fala com você por aqui."
)


def _msg_pos_aceite(prefixo: str = "") -> str:
    """Mensagem pos-aceite: confirma o encaminhamento pra fila do Comercial,
    anexando o aviso de expediente quando fora do horario de atendimento do
    tenant (business_hours; sem tabela = sem aviso, nunca afirma fechado)."""
    from firestore_common import get_tenant_context
    texto = prefixo + "\n\n" + _MSG_FILA_COMERCIAL
    # Fallback "hubloc" segue o padrao ja documentado do tenant implicito
    # (webhook/middleware/channel_service) — builtin sem contexto e hubloc.
    texto += builtin_expediente_notice(get_tenant_context() or "hubloc")
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
            # Sem menu de setores: o aceite ja finaliza o bot e poe o lead,
            # sem dono, na fila do Comercial (pool "Novos Leads").
            _finalize_bot(contact_id, state, SETOR_COMERCIAL)
            return _msg_pos_aceite(lgpd_response)

        if not step:
            state["step"] = "lgpd"
            state["started_at"] = utcnow().isoformat()
        _set_bot_state(contact_id, state)
        return lgpd_response

    # =================================================================
    # LGPD ja aceita: encaminha direto pra fila do Comercial
    # =================================================================

    if not step or step == "lgpd":
        _finalize_bot(contact_id, state, SETOR_COMERCIAL)
        return _msg_pos_aceite("Olá!")

    # -- Legado: contatos que receberam o menu de setores (pre 2026-07-24) --
    # Honra a escolha em voo; entrada nao reconhecida cai no Comercial.
    if step == "ask_sector":
        setor = _classificar_setor(text.strip())
        if setor is None:
            _finalize_bot(contact_id, state, SETOR_COMERCIAL)
            return _msg_pos_aceite("Certo!")
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
    # handoff_at abre o ciclo de espera por atendimento humano (Modo Recepcao,
    # ver _reception_handoff_unattended) e por isso e gravado mesmo quando o
    # setor nao resolveu — senao a thread ficaria sem marco de ciclo.
    _handoff_at = utcnow()
    for snap in collection("wa_conversations").where(
        "contact_id", "==", contact_id
    ).stream():
        cd = snap.to_dict() or {}
        if cd.get("is_backup"):
            continue
        conv_updates = {"handoff_at": _handoff_at}
        if dept_id:
            conv_updates["department_id"] = dept_id
        snap.reference.set(conv_updates, merge=True)

    if dept_id:
        # Carimba o setor no protocolo do dia (nasceu "GERAL" no 1o inbound).
        # So o CAMPO — o id do protocolo e imutavel. Best-effort.
        try:
            from database import set_attendance_department
            set_attendance_department(contact_id, dept_id)
        except (ImportError, AttributeError):
            pass  # simuladores mockam database sem esta funcao
        except Exception:
            logger.exception(
                "[BOT] carimbo de setor no protocolo falhou | contato=%d", contact_id,
            )

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

# Frases de erro EMBUTIDAS do Dialogflow CX (built-in error event). Chegam
# como turno "ok" (HTTP 200) — o caminho de falha por timeout/5xx nao as
# enxerga, entao sem esta lista o lead recebia o erro EM INGLES e ficava
# preso no funil (incidente varizemed 2026-08-14, pedido de atendimento).
# Comparacao por IGUALDADE do texto normalizado (a frase e a resposta
# inteira do agente) — containment pegaria resposta legitima que cite
# "algo deu errado" no meio de uma frase maior.
_CX_ERROR_REPLY_PHRASES = (
    "sorry something went wrong",
    "desculpe algo deu errado",
)

# Reenvios da MESMA mensagem do lead quando o agente devolve frase de erro
# (transparente pro lead). No 4o erro consecutivo (1 + 3 reenvios), handoff.
_CX_ERROR_RETRY_MAX = 3
# Reenvio so vale a pena se sobrar pelo menos isto do orcamento do turno
# (CX_DETECT_TIMEOUT_SECONDS): menos que isso e timeout certo — vira handoff
# generico direto em vez de mais uma chamada fadada a falhar.
_CX_RESEND_MIN_SECONDS = 5.0
# Relogio monotonico do orcamento do turno (indirecao pra os simuladores
# avancarem o tempo sem dormir).
_monotonic = time.monotonic

_CX_ERROR_HANDOFF_MSG = (
    "Nosso agente virtual está indisponível no momento. "
    "Um operador humano vai continuar o seu atendimento por aqui."
)


def _cx_reply_is_error(reply_text, ai_cfg: Optional[dict] = None) -> bool:
    """True se a resposta do agente e uma frase de erro embutida do CX.

    Remove TODA pontuacao antes de comparar ("Desculpe, algo deu errado."
    tem virgula interna que o _norm preserva). Alem das frases builtin,
    aceita frases extras POR TENANT em settings.ai.cx_error_phrases —
    e por ai que a frase de erro customizada que o dev de IA vai definir
    entra SEM deploy (mesmo padrao do override handoff_text_hints)."""
    norm = re.sub(r"[^\w\s]", "", _norm(str(reply_text or "")))
    norm = re.sub(r"\s+", " ", norm).strip()
    if norm in _CX_ERROR_REPLY_PHRASES:
        return True
    extras = (ai_cfg or {}).get("cx_error_phrases") or ()
    if not isinstance(extras, (list, tuple)):
        return False
    for frase in extras:
        f = re.sub(r"[^\w\s]", "", _norm(str(frase or "")))
        if f and re.sub(r"\s+", " ", f).strip() == norm:
            return True
    return False


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
# As duas primeiras sao do val-5.0 (o que a clinica real roda). As duas
# ultimas sao do val-5.0.1 (env 75028a25, 08/08), que reescreveu a mensagem de
# prioridade: "Registrei sua solicitacao como prioridade no sistema. Nossa
# equipe de atendimento humano entrara em contato...". Sem elas o fallback de
# TEXTO nao casava mais e o handoff dependia so do parametro handoff_request —
# que o agente ja esqueceu de setar em producao antes (conferido no
# varizemed-test em 2026-08-09). Lista ADITIVA de proposito: as duas versoes do
# agente convivem enquanto prod e teste apontam pra environments diferentes.
_DEFAULT_HANDOFF_TEXT_HINTS = (
    "estou transferindo nossa conversa para a equipe de atendimento",
    "deixei sua solicitacao marcada como prioridade",
    "registrei sua solicitacao como prioridade",
    "equipe de atendimento humano entrara em contato",
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


def _tenant_is_active() -> bool:
    """False SO quando o doc do tenant diz is_active=False explicitamente.

    Tenant desativado (fim de contrato/inadimplencia) nao pode seguir com o
    bot respondendo cliente e queimando DetectIntent. Falha de leitura ou
    campo ausente = ativo (fail-open): um blip de Firestore nao pode calar o
    bot de quem esta em dia.
    """
    from firestore_common import get_tenant_context
    from tenant_service import get_tenant

    tid = get_tenant_context()
    if not tid:
        return True
    try:
        tenant = get_tenant(tid) or {}
    except Exception:
        return True
    return tenant.get("is_active", True) is not False


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

    if not _tenant_is_active():
        logger.warning(
            "[BOT] tenant %s INATIVO — bot silencioso", get_tenant_context(),
        )
        return None

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
    # Humano conduzindo a THREAD (takeover/supervisor-takeover/picker): esses
    # caminhos assumem so a conversation, nao o Lead, entao o gate por contato
    # acima nao pega. Sem isto o bot responderia por cima do operador.
    if state.get("human_active"):
        return None

    # Hidratacao da prova pelo CONTATO (PLANO_MODELOS Fase 2 item 9): apos o
    # release_lead_to_bot (fechamento devolve ao agente), o bot_states do
    # ciclo anterior ja foi limpo — sem isto o paciente re-toma o aviso LGPD
    # a cada retorno. A prova do contato vale se a policy_version bater com
    # a vigente (ADR 0009 D1: bump de versao re-pergunta); recusa registrada
    # em bot_states tem precedencia (guarda is None); revogado (J-3 D8)
    # nunca hidrata. NAO re-chama _record_lgpd_consent (prova ja existe).
    if state.get("lgpd_consent") is None \
            and contact.get("lgpd_consent") is True \
            and not contact.get("lgpd_revoked") \
            and str(contact.get("lgpd_policy_version") or "").strip() == _cx_policy_version(ai_cfg):
        state["lgpd_consent"] = True
        state["lgpd_status"] = "accepted"

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
        # Horario comercial (frente b): SEMPRE as duas chaves, todo turno —
        # o agente ramifica em fora_do_expediente e interpola retorno_previsto
        # (nunca decide horario sozinho nem escreve hora no texto). Agente que
        # ainda nao usa os params simplesmente os ignora.
        session_params.update(cx_hours_params(get_tenant_context() or ""))
        turn_text = first_cx_text if first_cx_text is not None else text
        # Orcamento do TURNO (CX_DETECT_TIMEOUT_SECONDS, 60s): a 1a chamada
        # tem o teto inteiro; os reenvios por frase de erro abaixo so usam o
        # que sobrou. Sem isto o pior caso era 4 x 60s = 4 min de espera do
        # lead (e ~10 reentregas da Meta). Excecao unica ao teto: a 1a
        # chamada pode reenviar 1x em READ-timeout dentro do conector
        # (CX_READ_TIMEOUT_RETRY, PO 2026-08-20) -> pior caso ~2x o teto;
        # nesse caso o orcamento ja era e os reenvios por frase de erro
        # abaixo simplesmente nao rodam (_restante negativo).
        _turn_deadline = _monotonic() + CX_DETECT_TIMEOUT_SECONDS
        result = await bot_engine_dialogflow.detect_intent_text(
            ai_cfg, wa_digits, turn_text, session_params
        )
        # Frase de erro embutida com HTTP 200 = falha disfarcada. Reenvia a
        # MESMA mensagem do lead ate _CX_ERROR_RETRY_MAX vezes (transparente
        # pro lead; PO 2026-08-14). Se algum reenvio vier limpo, o fluxo segue
        # normal; 4 erros consecutivos caem no handoff logo abaixo. Orcamento
        # esgotado interrompe os reenvios (frase de erro sobrevive -> mesmo
        # handoff generico do 4o erro).
        _erros_seguidos = 0
        while (
            result.get("ok")
            and _cx_reply_is_error(result.get("reply_text"), ai_cfg)
            and _erros_seguidos < _CX_ERROR_RETRY_MAX
        ):
            _restante = _turn_deadline - _monotonic()
            if _restante < _CX_RESEND_MIN_SECONDS:
                logger.warning(
                    "[BOT-CX] frase de erro do agente — orcamento do turno "
                    "esgotado apos %d reenvio(s) | contato=%d",
                    _erros_seguidos, contact_id,
                )
                break
            _erros_seguidos += 1
            logger.warning(
                "[BOT-CX] frase de erro do agente — reenvio %d/%d (%.0fs "
                "restantes) | contato=%d",
                _erros_seguidos, _CX_ERROR_RETRY_MAX, _restante, contact_id,
            )
            result = await bot_engine_dialogflow.detect_intent_text(
                ai_cfg, wa_digits, turn_text, session_params,
                timeout_s=_restante,
            )
        # Re-checa o gate DEPOIS do turno (corrida real: DetectIntent leva ate
        # CX_DETECT_TIMEOUT_SECONDS (60s) por chamada, e os reenvios por frase
        # de erro acima somam; um assume/takeover nesse meio tempo nao pode ser
        # atropelado por resposta/handoff atrasados do bot).
        fresh = get_wa_contact(contact_id)
        if not fresh or fresh.get("assigned_to") or fresh.get("bot_completed"):
            logger.info(
                "[BOT-CX] contato %d assumido/finalizado durante o DetectIntent "
                "— resposta do bot descartada", contact_id,
            )
            return None
        # Takeover no meio do turno assume a THREAD (nao grava no contato):
        # re-le o bot_state pra pegar o human_active marcado nesse intervalo.
        if _get_bot_state(contact_id).get("human_active"):
            logger.info(
                "[BOT-CX] humano assumiu a thread do contato %d durante o "
                "DetectIntent — resposta do bot descartada", contact_id,
            )
            return None
        contact = fresh
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
        # Increment atomico + releitura: 2 mensagens concorrentes durante um
        # outage do CX nao subcontam mais (lost update de read-modify-write).
        # Pode, no pior caso, disparar o handoff em ambas — _finalize e
        # idempotente nos sets; sobra no maximo uma system message repetida.
        from google.cloud import firestore as _gcf
        _state_ref = document("bot_states", contact_id)
        _state_ref.set({"cx_fail_count": _gcf.Increment(1)}, merge=True)
        fails = int((_state_ref.get().to_dict() or {}).get("cx_fail_count") or 0)
        if fails >= _CX_MAX_CONSECUTIVE_FAILURES:
            # Sem params (motor caiu) -> temperatura classifica frio; sem
            # detalhes coletados no sumario. contact vai pro carimbo do
            # protocolo do dia. Falha de persistencia aqui NAO pode calar o
            # cliente: loga e responde mesmo assim (retry na proxima msg).
            try:
                _finalize_cx_handoff(
                    contact_id, ai_cfg,
                    summary="Bot IA indisponivel (falhas consecutivas)",
                    contact=contact,
                )
            except Exception:
                logger.exception(
                    "[BOT-CX] persistencia do handoff-por-falha falhou | "
                    "contato=%d (cliente respondido; re-tenta na proxima msg)",
                    contact_id,
                )
            return _CX_HANDOFF_FAIL_MSG
        return _CX_FALLBACK_MSG

    # ------------------------------------------------------------------
    # Frase de erro SOBREVIVEU aos reenvios (4 erros consecutivos na mesma
    # mensagem) -> handoff com mensagem generica (PO 2026-08-14). A frase
    # de erro NUNCA chega ao lead.
    # ------------------------------------------------------------------
    if _cx_reply_is_error(result.get("reply_text"), ai_cfg):
        logger.warning(
            "[BOT-CX] frase de erro apos %d reenvios — handoff | contato=%d",
            _CX_ERROR_RETRY_MAX, contact_id,
        )
        try:
            _finalize_cx_handoff(
                contact_id, ai_cfg,
                summary="Bot IA com erro interno (4 respostas de erro consecutivas)",
                contact=contact,
            )
        except Exception:
            logger.exception(
                "[BOT-CX] persistencia do handoff-por-erro falhou | "
                "contato=%d (cliente respondido; re-tenta na proxima msg)",
                contact_id,
            )
        return _CX_ERROR_HANDOFF_MSG

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
        # Falha de persistencia NUNCA cala o cliente: a resposta de
        # transferencia sai mesmo se o Firestore falhar aqui. Como
        # bot_completed e o ULTIMO write do handoff (commit-point), uma falha
        # no meio deixa o bot ativo e a proxima mensagem re-tenta o handoff
        # inteiro (sets idempotentes). O snapshot em bot_states tambem
        # sobrevive, entao o resumo ainda sai no assume se preciso.
        try:
            _finalize_cx_handoff(
                contact_id, ai_cfg,
                summary=str(result.get("handoff_summary") or "").strip(),
                user_name=str(result.get("user_name") or "").strip(),
                # Params acumulados da sessao CX: unica fonte da temperatura do
                # lead e do sumario enriquecido (calculo adiado ate aqui — zero
                # writes por turno).
                cx_params=result.get("parameters") or {},
                contact=contact,
            )
        except Exception:
            logger.exception(
                "[BOT-CX] persistencia do handoff falhou | contato=%d "
                "(cliente respondido; re-tenta na proxima msg)", contact_id,
            )
        # Nunca transferir em silencio (agente pode pedir handoff sem texto).
        return reply or _CX_HANDOFF_DEFAULT_MSG

    # Turno SEM handoff: guarda o snapshot minimo dos params coletados em
    # bot_states (doc efemero, SEM listener no frontend e fora do caminho
    # quente) pra que o operador que ASSUMIR um lead self-service tenha
    # temperatura + resumo. Grava so quando a informacao MUDA — nao e write
    # por turno, e nao toca wa_contacts/wa_conversations durante o bot.
    snapshot = _cx_snapshot(result.get("parameters"), ai_cfg.get("temperature_signals"))
    if snapshot and snapshot != (state.get("cx_snapshot") or {}):
        _set_bot_state(contact_id, {"cx_snapshot": snapshot})

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


# Campos do CX usados no SUMARIO (alem dos sinais de temperatura, que vem da
# config). Definem, junto com signal_keys(), o snapshot MINIMO persistido em
# bot_states — minimizacao LGPD: nada do dict cru de params vai pro banco.
_CX_SUMMARY_KEYS = (
    "user_name", "user_symptom", "user_insurance", "user_specialty",
    "wants_appointment", "wants_treatment", "insurance_validated",
)

_CX_HANDOFF_HEADER = "Bot IA finalizado | Transferido para atendimento humano"
_CX_ASSUME_HEADER = "Resumo do bot IA | Atendimento assumido durante a conversa"


def _cx_snapshot(params, signals=None) -> dict:
    """Subconjunto minimo e ESTAVEL dos params (so chaves preenchidas) que
    alimenta temperatura + sumario. Guardado em bot_states pra permitir
    classificar quando o operador ASSUME um lead que nunca pediu handoff
    (self-service) — bot_states nao tem listener no frontend nem e doc quente,
    entao isto NAO reintroduz o write-por-turno vetado nos wa_contacts/
    wa_conversations (so grava quando a informacao coletada muda)."""
    if not isinstance(params, dict):
        return {}
    keys = list(_CX_SUMMARY_KEYS) + [k for k in signal_keys(signals) if k not in _CX_SUMMARY_KEYS]
    snap = {}
    for key in keys:
        value = params.get(key)
        if value is None or value == "":
            continue
        snap[key] = value
    return snap


def _persist_lead_temperature(
    contact_id: int, temperature: str, contact: Optional[dict] = None,
    contact_extra: Optional[dict] = None, dept_id=None, handoff_at=None,
):
    """Grava a temperatura no contato + conversations + protocolo do dia.

    `handoff_at`: so o HANDOFF passa (abre o ciclo de espera por atendimento
    humano na pool — ver _reception_handoff_unattended em database_firestore).
    O caminho de assume sem handoff (apply_cx_snapshot_on_assume) NAO passa:
    la o humano ja esta na conversa, e carimbar abriria um ciclo falso.

    `contact_extra`/`dept_id` entram no MESMO set do contato (o handoff
    aproveita pra gravar bot_completed/notes/department sem write extra).
    O carimbo em attendances_daily e IMUTAVEL por protocolo: engajamento
    novo carimba o protocolo do SEU dia, sem apagar o historico.

    ORDEM IMPORTA (crash-consistency): conversations e protocolo primeiro,
    contato POR ULTIMO — bot_completed (no contact_extra do handoff) e o
    commit-point que silencia o bot. Falha no meio deixa o bot ativo e a
    proxima mensagem re-tenta o handoff inteiro; o inverso (contato primeiro)
    deixava lead com bot_completed=True e threads sem departamento."""
    for snap in collection("wa_conversations").where(
        "contact_id", "==", contact_id
    ).stream():
        cd = snap.to_dict() or {}
        if cd.get("is_backup"):
            continue
        conv_updates = {"lead_temperature": temperature}
        if dept_id:
            conv_updates["department_id"] = dept_id
        if handoff_at is not None:
            conv_updates["handoff_at"] = handoff_at
        snap.reference.set(conv_updates, merge=True)

    protocol_id = str((contact or {}).get("attendance_protocol") or "").strip()
    if protocol_id:
        document("attendances_daily", protocol_id).set(
            {"lead_temperature": temperature}, merge=True,
        )

    updates = dict(contact_extra or {})
    updates["lead_temperature"] = temperature
    updates["lead_temperature_at"] = utcnow()
    if dept_id:
        updates["department_id"] = dept_id
    document("wa_contacts", contact_id).set(updates, merge=True)


def mark_human_active(contact_id: int):
    """Sinaliza que um humano esta conduzindo a conversa NESTA sessao do bot.

    Os caminhos de takeover assumem a THREAD, nao o Lead: nao gravam
    assigned_to no contato, entao o gate do webhook (que olha so o contato)
    deixaria o bot CX continuar respondendo por cima do operador — e ate
    disparar handoff no meio do atendimento humano. bot_states ja e lido a
    cada turno, entao o flag nao custa read extra. Limpo junto com o estado
    no fim do bot (_clear_bot_state)."""
    try:
        _set_bot_state(contact_id, {"human_active": True})
    except Exception:
        logger.exception("[BOT] falha ao marcar human_active | contato=%d", contact_id)


def apply_cx_snapshot_on_assume(
    contact_id: int, contact: Optional[dict] = None,
    conversation_id: Optional[str] = None,
) -> bool:
    """Classifica + emite o resumo quando um operador ASSUME um contato que
    estava em conversa com o bot CX SEM ter chegado a handoff (lead
    self-service: resolveu no proprio bot, ex.: foi agendar online).

    Sem isto o lead ficava invisivel — sem badge e sem resumo — justamente
    quem o operador precisa priorizar (caso real do teste 2026-07-21).
    Idempotente por MARCADOR (snapshot ja emitido + protocolo do dia) em vez
    de zerar o snapshot. Assim os caminhos que NAO silenciam o bot (takeover,
    supervisor-takeover, abrir pelo picker) podem emitir o resumo sem
    descartar dados que o bot ainda esta coletando; se a informacao mudar
    depois, um novo acionamento emite o resumo atualizado.

    O marcador e chaveado pelo PROTOCOLO do dia: sem isso, um engajamento
    NOVO (outro dia, ou lead devolvido ao bot) que recoletasse os mesmos
    params bateria a igualdade e ficaria SEM resumo e SEM carimbo de
    temperatura no protocolo novo (achado da revisao 2026-07-30).

    `conversation_id`: thread onde o resumo deve aparecer. Sem isso o
    save_wa_message deriva a thread de contact.channel_id — que e gravado uma
    unica vez na criacao do contato — e num lead multi-canal (coex) o resumo
    cairia numa thread que o operador nem esta olhando.

    Retorna True se emitiu. Nunca levanta pro caller."""
    ai_cfg = _get_tenant_ai_config()
    if str(ai_cfg.get("bot_engine") or "").strip().lower() != "dialogflow_cx":
        return False
    state = _get_bot_state(contact_id)
    snap = state.get("cx_snapshot") or {}
    if not isinstance(snap, dict) or not snap:
        return False

    if contact is None:
        contact = get_wa_contact(contact_id) or {}
    pid = str((contact or {}).get("attendance_protocol") or "")
    if (snap == (state.get("cx_summary_emitted") or {})
            and pid == str(state.get("cx_summary_emitted_pid") or "")):
        return False

    temperature = classify_lead_temperature(snap, ai_cfg.get("temperature_signals"))
    _persist_lead_temperature(contact_id, temperature, contact)

    sys_content = _cx_handoff_details(
        # user_name sai do proprio snapshot via _s() (que desembrulha struct);
        # str() direto aqui imprimiria o repr de um dict de snapshot antigo.
        summary="", user_name="",
        cx_params=snap, temperature=temperature, header=_CX_ASSUME_HEADER,
    )
    save_wa_message(
        wa_message_id="",
        contact_id=contact_id,
        direction="system",
        msg_type="system",
        content=sys_content,
        status="",
        timestamp_wa=utcnow().isoformat(),
        conversation_id=conversation_id or None,
        # Resumo e ato do sistema, nao do lead/operador: nao pode subir o
        # thread na sidebar (recencia inflada, mesmo padrao do auto-close).
        advance_recency=False,
    )
    _set_bot_state(contact_id, {
        "cx_summary_emitted": snap, "cx_summary_emitted_pid": pid,
    })
    logger.info(
        "[BOT-CX] Resumo emitido no assume | contato=%d | temperatura=%s",
        contact_id, temperature,
    )
    return True


def _cx_handoff_details(
    summary: str, user_name: str, cx_params: dict, temperature: str,
    header: str = _CX_HANDOFF_HEADER,
) -> str:
    """Corpo da system message pro operador (interna ao CRM — cliente nunca
    recebe). Minimizacao LGPD: so linhas com campo PREENCHIDO; os params crus
    NUNCA sao persistidos, so estas linhas derivadas. A 1a linha (header) e
    IMUTAVEL por caminho (tooling/sims dependem dela)."""
    params = cx_params if isinstance(cx_params, dict) else {}

    def _scalar(key):
        # Param em struct {chave: valor} (agente pos-2026-07-29): o conector
        # desembrulha na origem, mas snapshots antigos em bot_states podem
        # carregar o dict cru — sem isto o resumo mostraria o repr do dict.
        v = params.get(key)
        if isinstance(v, dict) and len(v) == 1:
            v = next(iter(v.values()))
        return v

    def _s(key):
        v = _scalar(key)
        v = str(v).strip() if v is not None else ""
        return "" if v.lower() in ("null", "none", "{}") else v

    def _b(key):
        v = _scalar(key)
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("true", "1", "yes", "sim")

    lines = [header]
    if temperature:
        lines.append(f"Temperatura do lead: {temperature.upper()}")
    nome = (user_name or "").strip() or _s("user_name")
    if nome:
        lines.append(f"Nome: {nome}")
    if _s("user_symptom"):
        lines.append(f"Sintoma: {_s('user_symptom')}")
    if _s("user_insurance"):
        convenio = _s("user_insurance")
        if _b("insurance_validated"):
            convenio += " (validado)"
        lines.append(f"Convenio: {convenio}")
    if _s("user_specialty"):
        lines.append(f"Especialidade: {_s('user_specialty')}")
    if _b("wants_appointment"):
        lines.append("Quer agendar: sim")
    if _b("wants_treatment"):
        lines.append("Quer tratamento: sim")
    if summary:
        lines.append(f"Resumo: {summary}")
    return "\n".join(lines)


def _finalize_cx_handoff(
    contact_id: int, ai_cfg: dict, summary: str = "", user_name: str = "",
    cx_params: Optional[dict] = None, contact: Optional[dict] = None,
):
    """Encerra o bot CX transferindo o contato para atendimento humano.

    Mesmo modelo do _finalize_bot: bot_completed=True + department_id (pela
    bot_key configurada no tenant), propagacao as conversations (pool do
    setor segmenta por department_id da CONVERSATION), system message com o
    resumo do agente e limpeza do estado. assigned_to fica vazio (pool).

    Temperatura do lead (execucao adiada — decisao do PO 2026-07-21,
    docs/PLANO_LEAD_TEMPERATURE.md): calculada UMA unica vez AQUI, sobre os
    session params acumulados da sessao CX (`cx_params`), e gravada em batch
    junto dos writes que ja existem: contato (mesmo set), conversations
    (mesmo set do department) e carimbo imutavel no protocolo do dia
    (attendances_daily). NENHUM write por turno. Handoff novo SOBRESCREVE a
    temperatura anterior (semantica por-atendimento: historico nao suja a
    fila do dia). Handoff por falha do motor chega sem params -> frio.
    """
    dept_id = _dept_id_by_bot_key(str(ai_cfg.get("handoff_bot_key") or ""))
    if dept_id is None:
        # bot_key nao resolve (config errada ou setor inativado): fallback pro
        # 1o setor ativo do tenant — lead SEM department_id ficaria fora das
        # pools por setor do frontend. Loga alto: e misconfig a corrigir.
        depts = get_all_departments()
        if depts:
            dept_id = depts[0].get("id")
            logger.error(
                "[BOT-CX] handoff_bot_key=%r nao resolve departamento no tenant "
                "— fallback pro setor %s (%r). Corrija settings.ai.handoff_bot_key.",
                ai_cfg.get("handoff_bot_key"), dept_id, depts[0].get("name"),
            )
        else:
            logger.error(
                "[BOT-CX] handoff sem departamento: tenant sem setor ativo e "
                "handoff_bot_key=%r nao resolve", ai_cfg.get("handoff_bot_key"),
            )
    temperature = classify_lead_temperature(
        cx_params or {}, ai_cfg.get("temperature_signals")
    )

    notes = "Bot IA: handoff"
    if user_name:
        notes += f" | Nome={user_name}"

    # Protocolo do dia nasceu no 1o inbound (fase bot, ainda sem setor ->
    # "GERAL"). Carimba o setor REAL no campo; o ID fica imutavel de proposito
    # (ver docstring de set_attendance_department). Best-effort.
    if dept_id:
        try:
            from database import set_attendance_department
            set_attendance_department(contact_id, dept_id, contact)
        except (ImportError, AttributeError):
            pass  # simuladores mockam database sem esta funcao
        except Exception:
            logger.exception(
                "[BOT-CX] carimbo de setor no protocolo falhou | contato=%d", contact_id,
            )

    # ORDEM: system message ANTES do write do contato. bot_completed=True (no
    # contact_extra) e o que silencia o bot; se ele fosse gravado antes e o
    # save_wa_message falhasse, o lead ficaria finalizado e SEM resumo, sem
    # retry possivel. Assim, uma falha aqui propaga com o bot ainda ativo e a
    # proxima mensagem do cliente re-tenta o handoff inteiro. O custo e uma
    # system message duplicada no retry — visivel e inofensiva.
    sys_content = _cx_handoff_details(summary, user_name, cx_params or {}, temperature)
    save_wa_message(
        wa_message_id="",
        contact_id=contact_id,
        direction="system",
        msg_type="system",
        content=sys_content,
        status="",
        timestamp_wa=utcnow().isoformat(),
        # Ato do sistema: nao sobe o thread na sidebar (o inbound do cliente
        # que causou o handoff ja avancou a recencia ha segundos).
        advance_recency=False,
    )

    _persist_lead_temperature(
        contact_id, temperature, contact,
        contact_extra={"bot_completed": True, "bot_notes": notes},
        dept_id=dept_id,
        # Abre o ciclo de espera da pool: enquanto nenhum operador responder,
        # o auto-close nao devolve este lead ao agente de IA.
        handoff_at=utcnow(),
    )

    _clear_bot_state(contact_id)
    logger.info(
        "[BOT-CX] Handoff finalizado | contato=%d | dept_id=%s | temperatura=%s",
        contact_id, dept_id, temperature,
    )
