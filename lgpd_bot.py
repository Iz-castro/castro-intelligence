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
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Union

logger = logging.getLogger("castro_crm.lgpd")

# Brasilia sem horario de verao desde 2019: offset fixo -3 (mesmo de
# database_firestore._BR_TZ e business_hours.BR_TZ).
_BR_TZ = timezone(timedelta(hours=-3))

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


def _maybe_track_first_input(state: dict, message_text: str) -> None:
    """Atualiza user_first_input com a ultima entrada substantiva do cliente
    durante o gate LGPD (usado como replay pelo motor CX no aceite). Ignora
    IDs de botao (aceitar/recusar) — so texto real do cliente conta."""
    norm = _normalizar(message_text)
    if norm and norm not in _ACEITE_TERMOS and norm not in _RECUSA_TERMOS:
        state["user_first_input"] = message_text


def _eh_aceite(texto: str) -> bool:
    return _normalizar(texto) in _ACEITE_TERMOS


def _eh_recusa(texto: str) -> bool:
    return _normalizar(texto) in _RECUSA_TERMOS


# =========================================================================
# Botoes interativos
# =========================================================================

_BTN_ACEITAR = {"id": "lgpd_aceitar", "title": "Sim"}
_BTN_RECUSAR = {"id": "lgpd_recusar", "title": "Não"}


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

_LINK_PRIVACIDADE = (
    "https://hubloc.com.br/politica-de-privacidade/"
)
# Alias publico: o bot_service resolve o link efetivo do builtin (P2b).
LINK_PRIVACIDADE_BUILTIN = _LINK_PRIVACIDADE

# Corpo da mensagem interativa da Cloud API (body.text) — bot_transport
# trunca acima disso, o que cortaria a pergunta final do aviso.
_MAX_CORPO_INTERATIVO = 1024
_PERGUNTA_AVISO = "\n\nPodemos continuar?"
_ROTULO_LINK = "Política de Privacidade"

# Limites do conteudo LGPD editavel na aba Sistema (P2b, plano 3.4). O
# corpo interativo aceita 1024; o CRM anexa a linha do link e a pergunta.
LGPD_NOTICE_MAX_CHARS = 900
LGPD_URL_MAX_CHARS = 500


def montar_aviso_lgpd(
    texto: str, url: str = "", rotulo_link: str = _ROTULO_LINK,
) -> str:
    """Corpo do aviso LGPD: texto + linha do link (se houver) + pergunta.

    Formato unico do CX e do builtin com texto customizado. Rede de
    seguranca: se o conjunto passar do limite do corpo interativo, encurta o
    TEXTO (nunca o link nem a pergunta) — o save da aba Sistema ja impede
    isso; aqui cobre combinacoes com o fallback do settings.ai."""
    texto = (texto or "").strip()
    url = (url or "").strip()
    sufixo = (f"\n({rotulo_link}: {url})" if url else "") + _PERGUNTA_AVISO
    espaco = _MAX_CORPO_INTERATIVO - len(sufixo)
    if espaco > 1 and len(texto) > espaco:
        texto = texto[:espaco - 1].rstrip() + "…"
    return texto + sufixo


# ATENCAO: aviso default com marca da Hub Loc — vale SO porque o unico tenant
# no fluxo builtin e a hubloc (CX sempre passa o aviso do proprio tenant).
# Um 2o tenant builtin exigiria aviso por tenant, como a despedida da recusa
# (_recusa_resposta) ja faz. Desde a P2b o admin pode trocar texto/link pela
# aba Sistema (aviso_lgpd_builtin); este continua sendo o default.
_AVISO_LGPD_TEXTO = (
    "Olá! Que bom ter você na Hub Loc! 👷‍♂️🏗️\n\n"
    "Para falar com nosso atendimento e gerar orçamentos, "
    "precisamos do seu nome e telefone, protegidos pela LGPD."
)
_ROTULO_LINK_BUILTIN = "Nossa Política de Privacidade"

_AVISO_LGPD = montar_aviso_lgpd(
    _AVISO_LGPD_TEXTO, _LINK_PRIVACIDADE, rotulo_link=_ROTULO_LINK_BUILTIN,
)


def aviso_lgpd_builtin(texto: str = "", url: str = "") -> str:
    """Aviso do bot builtin (Hubloc) com o conteudo da aba Sistema.

    Texto customizado segue o formato do CX (texto + link + pergunta). Sem
    texto, mantem o aviso historico, so trocando o link se houver um
    customizado. Sem nada customizado, devolve exatamente _AVISO_LGPD."""
    texto = (texto or "").strip()
    url = (url or "").strip() or _LINK_PRIVACIDADE
    if texto:
        return montar_aviso_lgpd(texto, url)
    return montar_aviso_lgpd(_AVISO_LGPD_TEXTO, url, rotulo_link=_ROTULO_LINK_BUILTIN)

_ACEITO_RESPOSTA = (
    "Certo, seus dados serão tratados com total "
    "segurança e responsabilidade."
)

def _nome_tenant() -> str:
    """Nome de exibicao do tenant atual (tenant.name — mesmo dado do topbar).
    Vazio se indisponivel; nunca levanta. get_tenant e cacheado em memoria,
    entao nao custa read por recusa."""
    try:
        from firestore_common import get_tenant_context
        from tenant_service import get_tenant
        tid = get_tenant_context()
        if not tid:
            return ""
        return str((get_tenant(tid) or {}).get("name") or "").strip()
    except Exception:
        return ""


def _recusa_resposta() -> str:
    """Despedida da recusa com a marca do TENANT ATUAL, data-driven.

    Era uma constante com "A Hub Loc agradece o seu contato!" hardcoded —
    compartilhada por todos os tenants. Em 2026-08-10, 2 leads da varizemed
    (clinica) recusaram o LGPD e receberam a despedida assinada pela Hub Loc
    (locadora). Sem nome resolvido, degrada pra despedida neutra — nunca
    assina com a marca de outro cliente. Sem artigo antes do nome de
    proposito ("Hub Loc agradece", nao "A Hub Loc agradece"): artigo tem
    genero e quebraria com tenants futuros."""
    nome = _nome_tenant()
    agradece = f"{nome} agradece o seu contato!" if nome else "Agradecemos o seu contato!"
    return (
        "Entendido. Sem o seu consentimento, infelizmente "
        "não podemos prosseguir com o atendimento por este canal.\n\n"
        "Caso mude de ideia, é só nos enviar uma nova mensagem.\n"
        + agradece
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
# Politica LGPD por DATA (P2b, docs/PLANO_REABERTURA_LOTE_BOT_RECEPCAO.md 3.4)
# =========================================================================
#
# A "versao" da politica passa a ser a data de publicacao da politica vigente
# (system_settings.lgpd_policy_date, editada pelo admin na aba Sistema). Um
# aceite vale se nao for ANTERIOR a essa data (comparacao pela data do aceite
# em Brasilia), nunca por igualdade de texto — igualdade reperguntaria a base
# inteira na primeira edicao. Funcoes puras: sem Firestore, testaveis nos sims.

_DATA_POLITICA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_data_politica(valor) -> Optional[date]:
    """'AAAA-MM-DD' estrito -> date. Vazio ou invalido -> None."""
    texto = str(valor or "").strip()
    if not texto or not _DATA_POLITICA_RE.match(texto):
        return None
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date()
    except ValueError:
        return None


def hoje_br(agora: Optional[datetime] = None) -> date:
    """Data de hoje em Brasilia (agora naive = UTC)."""
    agora = agora or datetime.now(timezone.utc)
    if agora.tzinfo is None:
        agora = agora.replace(tzinfo=timezone.utc)
    return agora.astimezone(_BR_TZ).date()


def data_aceite_br(valor) -> Optional[date]:
    """lgpd_consent_at (ISO em UTC ou datetime) -> data em Brasilia.
    None se ausente ou ilegivel."""
    if not valor:
        return None
    if isinstance(valor, datetime):
        momento = valor
    elif isinstance(valor, str):
        try:
            momento = datetime.fromisoformat(valor.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(_BR_TZ).date()


def aceite_cobre_data(contato: dict, data_politica: date) -> bool:
    """Parte DATA da regra: o contato guarda aceite (lgpd_consent=True) que
    nao e anterior a politica vigente. Aceite legado sem lgpd_consent_at vale;
    carimbo ilegivel e tratado como legado (vale) e logado. NAO olha
    revogacao — o portao de revogacao e outro (ver aceite_vigente)."""
    contato = contato if isinstance(contato, dict) else {}
    if contato.get("lgpd_consent") is not True:
        return False
    bruto = contato.get("lgpd_consent_at")
    if not bruto:
        return True
    data_aceite = data_aceite_br(bruto)
    if data_aceite is None:
        logger.warning(
            "[LGPD] lgpd_consent_at ilegivel no contato %s — tratado como aceite legado",
            contato.get("id"),
        )
        return True
    return data_aceite >= data_politica


def aceite_vigente(contato: dict, data_politica: date) -> bool:
    """Regra completa com data configurada: consentiu, nao revogou e o aceite
    nao e anterior a politica vigente (hidratacao da prova pelo contato)."""
    contato = contato if isinstance(contato, dict) else {}
    if contato.get("lgpd_revoked"):
        return False
    return aceite_cobre_data(contato, data_politica)


def validar_config_lgpd(campos: dict, hoje: date, atual: Optional[dict] = None) -> dict:
    """Valida e normaliza os campos LGPD presentes em `campos` (save da aba
    Sistema). Devolve so as chaves presentes, normalizadas; levanta
    ValueError com mensagem legivel (o endpoint responde 400).

    - lgpd_policy_date: vazia ou AAAA-MM-DD valida e NAO futura em relacao a
      `hoje` (Brasilia). Data futura deixaria todo aceite "anterior" a
      politica — inclusive o que o paciente acabou de dar —, um loop de
      reconsentimento.
    - lgpd_privacy_url: vazia ou https://..., sem espacos.
    - lgpd_notice: no maximo LGPD_NOTICE_MAX_CHARS caracteres.
    `atual` (settings gravados) entra so na checagem do corpo composto, para
    PUT parcial que traz texto OU link."""
    campos = campos if isinstance(campos, dict) else {}
    limpo = {}
    if "lgpd_policy_date" in campos:
        bruto = str(campos.get("lgpd_policy_date") or "").strip()
        if bruto:
            data_pol = parse_data_politica(bruto)
            if data_pol is None:
                raise ValueError("Data da politica invalida: use uma data valida no formato AAAA-MM-DD")
            if data_pol > hoje:
                raise ValueError(
                    f"A data da politica nao pode ser futura (hoje e {hoje:%d/%m/%Y}). "
                    "Use a data de publicacao da politica que ja esta no ar.")
            bruto = data_pol.isoformat()
        limpo["lgpd_policy_date"] = bruto
    if "lgpd_privacy_url" in campos:
        url = str(campos.get("lgpd_privacy_url") or "").strip()
        if url:
            if (not url.lower().startswith("https://") or len(url) <= len("https://")
                    or any(c.isspace() for c in url)):
                raise ValueError("Link da politica invalido: deve comecar com https:// e nao ter espacos")
            if len(url) > LGPD_URL_MAX_CHARS:
                raise ValueError(f"Link da politica longo demais (maximo {LGPD_URL_MAX_CHARS} caracteres)")
        limpo["lgpd_privacy_url"] = url
    if "lgpd_notice" in campos:
        texto = str(campos.get("lgpd_notice") or "").replace("\r\n", "\n").strip()
        if len(texto) > LGPD_NOTICE_MAX_CHARS:
            raise ValueError(
                f"Texto do aviso longo demais (maximo {LGPD_NOTICE_MAX_CHARS} caracteres; "
                f"tem {len(texto)})")
        limpo["lgpd_notice"] = texto
    atual = atual if isinstance(atual, dict) else {}
    texto_ef = limpo.get("lgpd_notice", str(atual.get("lgpd_notice") or "").strip())
    url_ef = limpo.get("lgpd_privacy_url", str(atual.get("lgpd_privacy_url") or "").strip())
    if texto_ef and url_ef:
        composto = len(texto_ef) + len(f"\n({_ROTULO_LINK}: {url_ef})") + len(_PERGUNTA_AVISO)
        if composto > _MAX_CORPO_INTERATIVO:
            raise ValueError(
                f"Aviso + link passam do limite de {_MAX_CORPO_INTERATIVO} caracteres da "
                f"mensagem do WhatsApp ({composto}); encurte o texto ou o link")
    return limpo


# =========================================================================
# Handler principal
# =========================================================================

def handle_lgpd(
    state: dict,
    message_text: str,
    aviso_text: Optional[str] = None,
) -> Optional[Union[str, dict]]:
    """
    Verifica e gerencia o consentimento LGPD.

    Args:
        state: dict do bot_states (sera modificado in place).
        message_text: texto da mensagem recebida do cliente,
                      ou o button_reply.id quando vier de botao interativo.
        aviso_text: texto do aviso de consentimento exibido no primeiro
                    contato. Default = aviso historico do builtin (Hubloc);
                    o bot_service passa o aviso resolvido do tenant (aba
                    Sistema > settings.ai > default, lgpd_policy_config).

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

        # Captura a intencao real digitada durante o re-prompt (ex.: "quero
        # agendar") — o motor CX faz replay de user_first_input no aceite; sem
        # isso a 1a mensagem antiga seria reenviada ao agente (achado da revisao).
        _maybe_track_first_input(state, message_text)
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
            return _recusa_resposta()

        # Resposta nao reconhecida: reenviar botoes (e atualizar o replay do CX
        # com a intencao real, se o cliente digitou algo em vez de tocar botao).
        _maybe_track_first_input(state, message_text)
        return _resposta_botoes(
            corpo=_NAO_ENTENDI_CORPO,
            botoes=[_BTN_ACEITAR, _BTN_RECUSAR],
        )

    # --- Primeiro contato: exibir aviso LGPD com botoes ---
    state["lgpd_status"] = "awaiting"
    state["user_first_input"] = message_text

    logger.info("[LGPD] Aviso enviado ao contato")

    return _resposta_botoes(
        corpo=aviso_text or _AVISO_LGPD,
        botoes=[_BTN_ACEITAR, _BTN_RECUSAR],
    )
