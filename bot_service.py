# -*- coding: utf-8 -*-

"""
Servico de bot para atendimento automatico via WhatsApp.
Baseado no modelo de fluxo conversacional com coleta de nome, equipamento e setor.
Opera como state machine: cada mensagem do cliente avanca o estado.

Fluxo completo:
  (primeiro contato) -> lgpd_awaiting -> ask_name -> ask_equipment -> ask_sector -> done

A etapa LGPD e gerenciada pelo modulo lgpd.py e atua como gate obrigatorio
antes de qualquer coleta de dados pessoais.
"""

import re
import logging
import unicodedata
from datetime import datetime, timezone, timedelta
from typing import Optional

from firestore_common import document, utcnow, get_firestore_client
from database import (
    get_wa_contact, get_system_settings, get_all_departments,
    assign_wa_contact, save_wa_message, log_audit,
    get_user_by_id,
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
# Vocabularios
# =========================================================================

CONECTORES_NOME = {"de", "da", "do", "dos", "das", "e"}

TERMOS_PULAR = {
    "pular", "nao quero informar", "nao informar",
    "sem nome", "prefiro nao informar", "nao sei",
}

TERMOS_PEDIDO = {
    "quero", "preciso", "gostaria", "necessito", "alugar", "locar",
    "locacao", "cotar", "orcamento", "valor", "preco", "quanto", "reservar",
}

TERMOS_EQUIPAMENTO = {
    "betoneira", "martelete", "martelo", "martelo demolidor",
    "rompedor", "compactador", "compactador de solo",
    "placa vibratoria", "andaime", "andaimes",
    "escora", "escoras", "furadeira", "serra", "serra circular",
    "serra marmore", "lavadora", "compressor",
    "gerador", "enceradeira", "vibrador de concreto", "lixadeira",
    "cortadora", "cortadora de piso", "perfurador", "parafusadeira",
    "guincho", "container", "cacamba",
}

TERMOS_INVALIDOS_COMO_NOME = {
    "oi", "ola", "bom", "boa", "dia", "tarde", "noite",
    "meu", "nome", "cliente", "falar", "quero", "preciso",
    "valor", "preco", "quanto", "custa", "gostaria",
    "administrativo", "financeiro", "comercial", "sac",
    "sim", "nao", "ok", "aceito", "concordo", "recuso",
    "pular", "obrigado", "obrigada", "vlw", "valeu",
    "locacao", "alugar", "locar", "equipamento",
    "orcamento", "cotacao", "boleto",
}

PALAVRAS_COMERCIAL = {
    "comercial", "vendas", "locacao", "aluguel",
    "alugar", "locar", "orcamento", "cotacao",
    "preco", "valor", "equipamento",
}

PALAVRAS_FINANCEIRO = {
    "financeiro", "boleto", "boletos", "nota", "nota fiscal",
    "pagamento", "pagamentos", "cobranca",
    "fatura", "faturas", "segunda via", "pix", "deposito",
}

PALAVRAS_ADMINISTRATIVO = {
    "administrativo", "adm", "cadastro", "documento", "documentos",
    "contrato", "contratos", "fornecedor", "fornecedores", "rh",
}

PALAVRAS_SAC = {
    "sac", "suporte", "atendimento", "reclamacao",
    "problema", "defeito", "quebrado", "manutencao",
    "avaria", "atraso", "troca", "cancelamento",
}

# =========================================================================
# Utilidades de texto
# =========================================================================

def _norm(texto: str) -> str:
    texto = texto.strip().lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", texto)


def _limpar_nome(texto: str) -> str:
    """Remove prefixos comuns de auto-apresentacao."""
    padroes = [
        r"^\s*meu nome e\s+",
        r"^\s*me chamo\s+",
        r"^\s*sou o\s+",
        r"^\s*sou a\s+",
        r"^\s*sou\s+",
        r"^\s*pode me chamar de\s+",
        r"^\s*chamo\s+",
        r"^\s*o nome e\s+",
        r"^\s*nome:\s*",
        r"^\s*eu sou o\s+",
        r"^\s*eu sou a\s+",
        r"^\s*eu sou\s+",
    ]
    for padrao in padroes:
        texto = re.sub(padrao, "", texto, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", texto).strip()


def _formatar_nome(texto: str) -> str:
    texto = re.sub(r"[^A-Za-z\u00C0-\u024F'\-\s]", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    partes = []
    for token in texto.split():
        if _norm(token) in CONECTORES_NOME:
            partes.append(token.lower())
        else:
            partes.append(token.capitalize())
    return " ".join(partes)


def _contem(texto_norm: str, expressao: str) -> bool:
    expressao = _norm(expressao)
    return re.search(
        r"(?<!\w)" + re.escape(expressao) + r"(?!\w)", texto_norm
    ) is not None


def _detectar_equipamento(texto: str) -> Optional[str]:
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


def _parece_nome(texto: str) -> bool:
    """
    Verifica se o texto se parece com um nome de pessoa.
    Aceita nomes compostos de 1 a 6 tokens, descartando
    palavras que claramente nao sao nomes proprios.
    """
    candidato = _limpar_nome(texto)
    candidato_norm = _norm(candidato)

    if not candidato_norm:
        return False

    # Normalizar termos de pular para comparacao sem acento
    termos_pular_norm = {_norm(x) for x in TERMOS_PULAR}
    if candidato_norm in termos_pular_norm:
        return False

    if any(ch.isdigit() for ch in candidato):
        return False

    if _detectar_equipamento(candidato):
        return False

    tokens = re.findall(r"[A-Za-z\u00C0-\u024F'\-]+", candidato)
    if not tokens or len(tokens) > 6:
        return False

    termos_invalidos_norm = {_norm(x) for x in TERMOS_INVALIDOS_COMO_NOME}
    equipamento_norm = {_norm(x) for x in TERMOS_EQUIPAMENTO}

    for t in tokens:
        tn = _norm(t)
        if tn in CONECTORES_NOME:
            continue
        if tn in termos_invalidos_norm or tn in equipamento_norm:
            return False
        if len(tn) < 2:
            return False

    # Pelo menos um token deve ser um nome proprio (nao conector)
    nomes_reais = [t for t in tokens if _norm(t) not in CONECTORES_NOME]
    if not nomes_reais:
        return False

    return True


def _classificar_setor(texto: str) -> Optional[int]:
    texto_norm = _norm(texto.strip())
    direto = {"1": 1, "2": 2, "3": 3, "4": 4}
    if texto_norm in direto:
        return direto[texto_norm]
    if any(_contem(texto_norm, p) for p in PALAVRAS_FINANCEIRO):
        return 2
    if any(_contem(texto_norm, p) for p in PALAVRAS_ADMINISTRATIVO):
        return 3
    if any(_contem(texto_norm, p) for p in PALAVRAS_SAC):
        return 4
    if any(_contem(texto_norm, p) for p in PALAVRAS_COMERCIAL):
        return 1
    if _detectar_equipamento(texto):
        return 1
    return None


# =========================================================================
# Mapeamento setor -> departamento do CRM
# =========================================================================

_SETOR_NOMES = {1: "Comercial", 2: "Financeiro", 3: "Administrativo", 4: "SAC"}
_BOT_KEY_BY_SETOR = {1: "comercial", 2: "financeiro", 3: "administrativo", 4: "sac"}

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

    # Pass 1: bot_key explicito (prioridade)
    by_bot_key = {}
    for dept in depts:
        bk = (dept.get("bot_key") or "").strip().lower()
        if bk:
            by_bot_key[bk] = dept.get("id")
    for setor_id, bot_key in _BOT_KEY_BY_SETOR.items():
        if bot_key in by_bot_key:
            mapping[setor_id] = by_bot_key[bot_key]

    # Pass 2: substring match para setores que ainda nao tem mapeamento
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

# Fluxo: lgpd -> ask_name -> ask_equipment -> ask_sector -> done
# O estado e dados ficam em Firestore: bot_states/{contact_id}

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


def _saudacao_texto() -> str:
    """Retorna apenas a saudacao temporal (Bom dia, Boa tarde, Boa noite)."""
    agora = datetime.now(timezone.utc).astimezone(EMPRESA_TZ)
    if 5 <= agora.hour < 12:
        return "Bom dia"
    elif 12 <= agora.hour < 18:
        return "Boa tarde"
    return "Boa noite"


def _esta_no_expediente() -> bool:
    agora = datetime.now(timezone.utc).astimezone(EMPRESA_TZ)
    return agora.weekday() < 5 and HORA_INICIO <= agora.hour < HORA_FIM


def _msg_pedir_nome(prefixo: str = "") -> str:
    """Monta a mensagem de solicitacao de nome, com ou sem aviso de expediente."""
    texto = prefixo
    if not _esta_no_expediente():
        texto += (
            "\n\nNosso expediente funciona de segunda a sexta, das 7h as 17h.\n"
            "Sua mensagem sera registrada e o retorno ocorrera no proximo horario util."
        )
    texto += (
        "\n\nPor favor, informe seu nome para iniciarmos o atendimento.\n"
        "(Caso nao queira informar, digite PULAR)"
    )
    return texto.strip()


MENU_SETORES = (
    "Informe o numero da opcao desejada:\n\n"
    "1 - Comercial\n"
    "2 - Financeiro\n"
    "3 - Administrativo\n"
    "4 - SAC"
)


def is_bot_enabled() -> bool:
    settings = get_system_settings()
    return bool(settings.get("bot_enabled", False))


LGPD_POLICY_VERSION = "hubloc-2026-06"


def _record_lgpd_consent(contact_id: int):
    """Prova de consentimento LGPD: grava no contato (quando + versao da
    politica) E no audit_log. Best-effort — nunca quebra o fluxo do bot."""
    now = utcnow().isoformat()
    try:
        document("wa_contacts", contact_id).set({
            "lgpd_consent": True,
            "lgpd_consent_at": now,
            "lgpd_policy_version": LGPD_POLICY_VERSION,
        }, merge=True)
    except Exception as exc:
        logger.warning("[LGPD] falha ao gravar consentimento no contato %s: %s", contact_id, exc)
    log_audit(0, "LGPD_CONSENT_ACCEPTED", f"contato {contact_id} | politica {LGPD_POLICY_VERSION}")


def process_bot_message(
    contact_id: int, text: str, contact_name: str = ""
) -> Optional[str]:
    """
    Processa uma mensagem do cliente pelo bot.
    Retorna a resposta do bot (str) ou None se o bot nao deve responder.
    Se o fluxo terminar, atribui o contato ao departamento correto e retorna None.
    """
    if not is_bot_enabled():
        return None

    contact = get_wa_contact(contact_id)
    if not contact:
        return None

    # Se ja tem operador atribuido, bot nao interfere
    if contact.get("assigned_to"):
        return None

    state = _get_bot_state(contact_id)
    step = state.get("step", "")

    # =================================================================
    # LGPD Gate - executa antes de qualquer coleta de dados
    # =================================================================
    lgpd_response = handle_lgpd(state, text, _saudacao_texto())

    if lgpd_response is not None:
        lgpd_status = state.get("lgpd_status")

        if lgpd_status == "accepted":
            # Consentimento acabou de ser dado: registrar (prova LGPD) + salvar
            # estado e transicionar para ask_name na mesma resposta
            _record_lgpd_consent(contact_id)
            state["step"] = "ask_name"
            state["nome"] = None
            state["equipamento"] = None
            state["setor_sugerido"] = None
            state["started_at"] = utcnow().isoformat()
            _set_bot_state(contact_id, state)
            return _msg_pedir_nome(lgpd_response)

        # Ainda em fluxo LGPD (awaiting, refused, etc.)
        if not step:
            state["step"] = "lgpd"
            state["started_at"] = utcnow().isoformat()
        _set_bot_state(contact_id, state)
        return lgpd_response

    # =================================================================
    # Fluxo principal do bot (LGPD ja aceita)
    # =================================================================

    # Primeira mensagem apos LGPD (caso o estado nao tenha sido
    # inicializado ainda -- ex: migracao de contatos antigos)
    if not step or step == "lgpd":
        state["step"] = "ask_name"
        state["nome"] = None
        state["equipamento"] = None
        state["setor_sugerido"] = None
        state["started_at"] = utcnow().isoformat()
        _set_bot_state(contact_id, state)
        return _msg_pedir_nome(
            f"{_saudacao_texto()}! Bem-vindo a Hub Loc."
        )

    text_stripped = text.strip()
    text_norm = _norm(text_stripped)

    # Normalizar termos de pular para comparacao
    termos_pular_norm = {_norm(x) for x in TERMOS_PULAR}

    # -- Etapa: coletar nome --
    if step == "ask_name":
        # Verificar se pulou
        if text_norm in termos_pular_norm:
            _set_bot_state(contact_id, {
                **state, "step": "ask_equipment", "nome": None,
            })
            return (
                "Sem problemas! Qual equipamento deseja locar?\n"
                "Se nao for locacao, descreva o assunto ou digite PULAR."
            )

        # Verificar se digitou setor direto
        setor = _classificar_setor(text_stripped)
        palavras_setor = (
            PALAVRAS_COMERCIAL | PALAVRAS_FINANCEIRO
            | PALAVRAS_ADMINISTRATIVO | PALAVRAS_SAC
        )
        if setor and (
            text_norm in {"1", "2", "3", "4"}
            or any(_contem(text_norm, p) for p in palavras_setor)
        ):
            _set_bot_state(contact_id, {
                **state, "step": "ask_name_after_sector",
                "setor_sugerido": setor,
            })
            return (
                f"Entendi que voce quer falar com o setor: "
                f"{_SETOR_NOMES[setor]}.\n"
                "Agora informe seu nome.\n"
                "(Caso nao queira informar, digite PULAR)"
            )

        # Verificar se digitou equipamento
        equipamento = _detectar_equipamento(text_stripped)
        if equipamento:
            _set_bot_state(contact_id, {
                **state, "step": "ask_name_after_equip",
                "equipamento": equipamento, "setor_sugerido": 1,
            })
            return (
                f'Entendi que voce se interessa por: "{equipamento}".\n'
                "Agora informe seu nome.\n"
                "(Caso nao queira informar, digite PULAR)"
            )

        # Verificar se e nome valido
        if _parece_nome(text_stripped):
            nome = _formatar_nome(_limpar_nome(text_stripped))
            _set_bot_state(contact_id, {
                **state, "step": "ask_equipment", "nome": nome,
            })
            # Atualizar display_name do contato
            document("wa_contacts", contact_id).set(
                {"display_name": nome}, merge=True,
            )
            return (
                f"Obrigado, {nome}! Qual equipamento deseja locar?\n"
                "Se nao for locacao, descreva o assunto ou digite PULAR."
            )

        return (
            "Nao consegui identificar um nome valido.\n"
            "Digite apenas seu nome.\n"
            "(Caso nao queira informar, digite PULAR)"
        )

    # -- Etapa: nome apos ter dado setor/equipamento primeiro --
    if step in ("ask_name_after_sector", "ask_name_after_equip"):
        if text_norm in termos_pular_norm:
            nome = None
        elif _parece_nome(text_stripped):
            nome = _formatar_nome(_limpar_nome(text_stripped))
            document("wa_contacts", contact_id).set(
                {"display_name": nome}, merge=True,
            )
        else:
            return (
                "Nao consegui identificar um nome valido.\n"
                "Digite apenas seu nome ou PULAR."
            )

        _set_bot_state(contact_id, {
            **state, "step": "ask_sector", "nome": nome,
        })

        equip = state.get("equipamento")
        setor_sug = state.get("setor_sugerido")
        msg = MENU_SETORES
        if equip:
            msg += f'\n\nEquipamento informado: "{equip}"\nSugestao: 1 - Comercial'
        elif setor_sug:
            msg += (
                f"\n\nSugestao: {setor_sug} - "
                f"{_SETOR_NOMES.get(setor_sug, '?')}"
            )
        return msg

    # -- Etapa: coletar equipamento --
    if step == "ask_equipment":
        if text_norm in termos_pular_norm:
            _set_bot_state(contact_id, {**state, "step": "ask_sector"})
            return MENU_SETORES

        equipamento = _detectar_equipamento(text_stripped)
        if equipamento:
            _set_bot_state(contact_id, {
                **state, "step": "ask_sector",
                "equipamento": equipamento, "setor_sugerido": 1,
            })
            msg = (
                MENU_SETORES
                + f'\n\nEquipamento informado: "{equipamento}"'
                + "\nSugestao: 1 - Comercial"
            )
            return msg

        setor = _classificar_setor(text_stripped)
        if setor:
            _set_bot_state(contact_id, {
                **state, "step": "ask_sector", "setor_sugerido": setor,
            })
            msg = (
                MENU_SETORES
                + f"\n\nSugestao: {setor} - "
                + f"{_SETOR_NOMES.get(setor, '?')}"
            )
            return msg

        return (
            "Nao consegui identificar o equipamento ou assunto.\n"
            "Exemplos: Betoneira, Segunda via de boleto, PULAR"
        )

    # -- Etapa: coletar setor --
    if step == "ask_sector":
        setor = _classificar_setor(text_stripped)
        setor_sug = state.get("setor_sugerido")

        if setor is None:
            if not text_norm and setor_sug:
                setor = setor_sug
            else:
                return "Opcao invalida. Digite 1, 2, 3 ou 4.\n" + MENU_SETORES

        # Fluxo concluido -- atribuir ao departamento
        _finalize_bot(contact_id, state, setor)
        return None

    # Estado desconhecido -- resetar
    _clear_bot_state(contact_id)
    return None


def _finalize_bot(contact_id: int, state: dict, setor: int):
    """Finaliza o bot: atribui o contato ao departamento correto."""
    dept_map = _get_dept_map()
    dept_id = dept_map.get(setor)
    setor_nome = _SETOR_NOMES.get(setor, "Desconhecido")

    # Gravar resumo no contato
    nome = state.get("nome") or "Nao informado"
    equipamento = state.get("equipamento") or ""
    notes = f"Bot: Nome={nome}"
    if equipamento:
        notes += f" | Equipamento={equipamento}"
    notes += f" | Setor={setor_nome}"

    updates = {
        "bot_completed": True,
        "bot_setor": setor,
        "bot_setor_nome": setor_nome,
        "bot_notes": notes,
    }
    if dept_id:
        updates["department_id"] = dept_id

    document("wa_contacts", contact_id).set(updates, merge=True)

    # Inserir mensagem de sistema
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
