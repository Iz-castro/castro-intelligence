# -*- coding: utf-8 -*-

"""
Servico de bot para atendimento automatico via WhatsApp.
Baseado no modelo de fluxo conversacional com coleta de nome, equipamento e setor.
Opera como state machine: cada mensagem do cliente avanca o estado.

Fluxo completo:
  (primeiro contato) -> lgpd_awaiting -> ask_name -> ask_equipment -> ask_sector -> done

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
    "pular", "não quero informar", "não informar",
    "sem nome", "prefiro não informar", "não sei",
    # Variantes sem acento (digitacao comum)
    "nao quero informar", "nao informar",
    "prefiro nao informar", "nao sei",
}

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

TERMOS_INVALIDOS_COMO_NOME = {
    "oi", "olá", "ola", "bom", "boa", "dia", "tarde", "noite",
    "meu", "nome", "cliente", "falar", "quero", "preciso",
    "valor", "preço", "preco", "quanto", "custa", "gostaria",
    "administrativo", "financeiro", "comercial", "sac",
    "sim", "não", "nao", "ok", "aceito", "concordo", "recuso",
    "pular", "obrigado", "obrigada", "vlw", "valeu",
    "locação", "locacao", "alugar", "locar", "equipamento",
    "orçamento", "orcamento", "cotação", "cotacao",
    "boleto",
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

PALAVRAS_SAC = {
    "sac", "suporte", "atendimento", "reclamação",
    "reclamacao", "problema", "defeito", "quebrado",
    "manutenção", "manutencao",
    "avaria", "atraso", "troca", "cancelamento",
}

# -------------------------------------------------------------------------
# Blacklist para aceite livre de equipamento (passo ask_equipment).
# Tokens que sozinhos nao representam um equipamento ou assunto concreto.
# -------------------------------------------------------------------------

_FILTRO_NAO_EQUIPAMENTO = {
    # Artigos, preposicoes, conjuncoes
    "o", "a", "os", "as", "um", "uma", "uns", "umas",
    "de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas",
    "por", "para", "com", "sem", "e", "ou", "que", "se", "me",
    "ao", "aos", "esse", "essa", "este", "esta",
    # Saudacoes
    "oi", "ola", "bom", "boa", "dia", "tarde", "noite",
    "hey", "eai", "opa", "fala",
    # Intencoes genericas
    "quero", "preciso", "gostaria", "necessito",
    "alugar", "locar", "cotar", "ver", "saber",
    # Respostas curtas
    "sim", "nao", "ok", "certo", "beleza",
    "valeu", "vlw", "obrigado", "obrigada",
    # Filler
    "pode", "ser", "favor", "la", "ai", "aqui",
    "tenho", "tem", "teria", "seria", "consigo",
    "voce", "voces", "gente",
}

# Onomatopeias de risada / ruido que nao representam equipamento nem assunto.
# Usado para rejeitar tokens como "kkk", "rsrs", "haha" no aceite livre.
_RISADA_RE = re.compile(r"^(k{2,}|rs(rs)*|(ha){2,}|(he){2,}|hue(hue)*)$")

# Frases inteiras que devem ser rejeitadas mesmo apos filtragem de tokens.
_FRASES_REJEITADAS_EQUIPAMENTO = {
    "quero alugar", "quero locar", "gostaria de alugar",
    "gostaria de locar", "preciso alugar", "preciso locar",
    "bom dia", "boa tarde", "boa noite",
    "oi bom dia", "oi boa tarde", "oi boa noite",
    "ola bom dia", "ola boa tarde", "ola boa noite",
    "quero um orcamento", "quero orcamento",
    "quero cotacao", "quero uma cotacao",
    "quero cotar", "preciso de orcamento",
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
        r"^\s*meu nome (e|eh)\s+",
        r"^\s*me chamo\s+",
        r"^\s*sou o\s+",
        r"^\s*sou a\s+",
        r"^\s*sou\s+",
        r"^\s*pode me chamar de\s+",
        r"^\s*chamo\s+",
        r"^\s*o nome (e|eh)\s*",
        r"^\s*nome:\s*",
        r"^\s*eu sou o\s+",
        r"^\s*eu sou a\s+",
        r"^\s*eu sou\s+",
    ]
    for padrao in padroes:
        texto = re.sub(padrao, "", texto, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", texto).strip()


def _formatar_nome(texto: str) -> str:
    texto = re.sub(r"[^A-Za-zÀ-ɏ'\-\s]", " ", texto)
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
    """
    Detecta equipamentos conhecidos pelo vocabulario.
    Usado no passo ask_name para identificar quando o cliente
    digitou equipamento em vez de nome.
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


def _aceitar_como_equipamento(texto: str) -> bool:
    """
    Aceita descricao livre como equipamento no passo ask_equipment.
    Rejeita apenas saudacoes, intencoes genericas e respostas vazias.

    Diferente de _detectar_equipamento (whitelist de nomes conhecidos),
    esta funcao usa blacklist: aceita tudo que nao for claramente
    irrelevante. Ainda assim, exige ao menos um token com conteudo
    alfabetico real — rejeita pontuacao pura ("????"), risadas ("kkk",
    "rsrs") e ruido que poluiriam o registro do lead.
    """
    texto_norm = _norm(texto.strip())
    if not texto_norm or len(texto_norm) < 2:
        return False

    # Rejeitar frases inteiras conhecidas como vazias
    if texto_norm in _FRASES_REJEITADAS_EQUIPAMENTO:
        return False

    # Rejeitar termos de pular
    termos_pular_norm = {_norm(x) for x in TERMOS_PULAR}
    if texto_norm in termos_pular_norm:
        return False

    # Tokenizar ignorando pontuacao: pontuacao pura ("????", "!!!") nao
    # gera token. Cada token e alfanumerico (_norm ja removeu acentos).
    tokens = re.findall(r"[0-9a-z]+", texto_norm)
    substantivos = [
        t for t in tokens
        if t not in _FILTRO_NAO_EQUIPAMENTO and len(t) >= 2
    ]

    # Se nenhum token significativo restou, nao e equipamento
    if not substantivos:
        return False

    # Se restaram apenas digitos, tambem nao e equipamento
    if all(t.isdigit() for t in substantivos):
        return False

    # Exigir ao menos um token com conteudo alfabetico real (>=2 letras)
    # que nao seja apenas risada/onomatopeia repetida (kkk, rsrs, haha...).
    def _eh_conteudo(t: str) -> bool:
        if sum(1 for c in t if c.isalpha()) < 2:
            return False
        return _RISADA_RE.match(t) is None

    if not any(_eh_conteudo(t) for t in substantivos):
        return False

    return True


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

    termos_pular_norm = {_norm(x) for x in TERMOS_PULAR}
    if candidato_norm in termos_pular_norm:
        return False

    if any(ch.isdigit() for ch in candidato):
        return False

    if _detectar_equipamento(candidato):
        return False

    tokens = re.findall(r"[A-Za-zÀ-ɏ'\-]+", candidato)
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


def _saudacao_texto() -> str:
    """Retorna a saudacao temporal (Bom dia, Boa tarde, Boa noite)."""
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
            "\n\nNosso expediente funciona de segunda a sexta, das 7h às 17h.\n"
            "Sua mensagem será registrada e o retorno "
            "ocorrerá no próximo horário útil."
        )
    texto += (
        "\n\nPor favor, informe seu nome para iniciarmos o atendimento.\n"
        "(Caso não queira informar, digite PULAR)"
    )
    return texto.strip()


MENU_SETORES = (
    "Informe o número da opção desejada:\n\n"
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
    lgpd_response = handle_lgpd(state, text, _saudacao_texto())

    if lgpd_response is not None:
        lgpd_status = state.get("lgpd_status")

        if lgpd_status == "accepted":
            _record_lgpd_consent(contact_id)
            state["step"] = "ask_name"
            state["nome"] = None
            state["equipamento"] = None
            state["setor_sugerido"] = None
            state["started_at"] = utcnow().isoformat()
            _set_bot_state(contact_id, state)
            return _msg_pedir_nome(lgpd_response)

        if not step:
            state["step"] = "lgpd"
            state["started_at"] = utcnow().isoformat()
        _set_bot_state(contact_id, state)
        return lgpd_response

    # =================================================================
    # Fluxo principal do bot (LGPD ja aceita)
    # =================================================================

    if not step or step == "lgpd":
        state["step"] = "ask_name"
        state["nome"] = None
        state["equipamento"] = None
        state["setor_sugerido"] = None
        state["started_at"] = utcnow().isoformat()
        _set_bot_state(contact_id, state)
        return _msg_pedir_nome(
            f"{_saudacao_texto()}! Bem-vindo à Hub Loc."
        )

    text_stripped = text.strip()
    text_norm = _norm(text_stripped)

    termos_pular_norm = {_norm(x) for x in TERMOS_PULAR}

    # -- Etapa: coletar nome --
    if step == "ask_name":
        if text_norm in termos_pular_norm:
            _set_bot_state(contact_id, {
                **state, "step": "ask_equipment", "nome": None,
            })
            return (
                "Sem problemas! Qual equipamento deseja locar?\n"
                "Se não for locação, descreva o "
                "assunto ou digite PULAR."
            )

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
                f"Entendi que você quer falar com o setor: "
                f"{_SETOR_NOMES[setor]}.\n"
                "Agora informe seu nome.\n"
                "(Caso não queira informar, digite PULAR)"
            )

        equipamento = _detectar_equipamento(text_stripped)
        if equipamento:
            _set_bot_state(contact_id, {
                **state, "step": "ask_name_after_equip",
                "equipamento": equipamento, "setor_sugerido": 1,
            })
            return (
                f'Entendi que você se interessa por: "{equipamento}".\n'
                "Agora informe seu nome.\n"
                "(Caso não queira informar, digite PULAR)"
            )

        if _parece_nome(text_stripped):
            nome = _formatar_nome(_limpar_nome(text_stripped))
            _set_bot_state(contact_id, {
                **state, "step": "ask_equipment", "nome": nome,
            })
            document("wa_contacts", contact_id).set(
                {"display_name": nome}, merge=True,
            )
            return (
                f"Obrigado, {nome}! Qual equipamento deseja locar?\n"
                "Se não for locação, descreva o "
                "assunto ou digite PULAR."
            )

        return (
            "Não consegui identificar um nome válido.\n"
            "Digite apenas seu nome.\n"
            "(Caso não queira informar, digite PULAR)"
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
                "Não consegui identificar um nome válido.\n"
                "Digite apenas seu nome ou PULAR."
            )

        _set_bot_state(contact_id, {
            **state, "step": "ask_sector", "nome": nome,
        })

        equip = state.get("equipamento")
        setor_sug = state.get("setor_sugerido")
        msg = MENU_SETORES
        if equip:
            msg += (
                f'\n\nEquipamento informado: "{equip}"\n'
                "Sugestão: 1 - Comercial"
            )
        elif setor_sug:
            msg += (
                f"\n\nSugestão: {setor_sug} - "
                f"{_SETOR_NOMES.get(setor_sug, '?')}"
            )
        return msg

    # -- Etapa: coletar equipamento --
    if step == "ask_equipment":
        if text_norm in termos_pular_norm:
            _set_bot_state(contact_id, {**state, "step": "ask_sector"})
            return MENU_SETORES

        # Primeiro: tentar equipamento conhecido (auto-sugere Comercial)
        equipamento = _detectar_equipamento(text_stripped)
        if equipamento:
            _set_bot_state(contact_id, {
                **state, "step": "ask_sector",
                "equipamento": equipamento, "setor_sugerido": 1,
            })
            return (
                MENU_SETORES
                + f'\n\nEquipamento informado: "{equipamento}"'
                + "\nSugestão: 1 - Comercial"
            )

        # Segundo: verificar se digitou setor direto
        setor = _classificar_setor(text_stripped)
        if setor:
            _set_bot_state(contact_id, {
                **state, "step": "ask_sector", "setor_sugerido": setor,
            })
            return (
                MENU_SETORES
                + f"\n\nSugestão: {setor} - "
                + f"{_SETOR_NOMES.get(setor, '?')}"
            )

        # Terceiro: aceitar descricao livre como equipamento
        if _aceitar_como_equipamento(text_stripped):
            _set_bot_state(contact_id, {
                **state, "step": "ask_sector",
                "equipamento": text_stripped.strip(),
                "setor_sugerido": 1,
            })
            return (
                MENU_SETORES
                + f'\n\nEquipamento informado: "{text_stripped.strip()}"'
                + "\nSugestão: 1 - Comercial"
            )

        # Fallback (so atinge em casos extremos: saudacao pura, ruido, etc.)
        return (
            "Não consegui identificar o equipamento ou assunto.\n"
            "Exemplos: Betoneira, Andaime, Segunda via de boleto.\n"
            "Descreva o que precisa ou digite PULAR."
        )

    # -- Etapa: coletar setor --
    if step == "ask_sector":
        setor = _classificar_setor(text_stripped)
        setor_sug = state.get("setor_sugerido")

        if setor is None:
            if not text_norm and setor_sug:
                setor = setor_sug
            else:
                return (
                    "Opção inválida. Digite 1, 2, 3 ou 4.\n"
                    + MENU_SETORES
                )

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

    nome = state.get("nome") or "Não informado"
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
