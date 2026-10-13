# -*- coding: utf-8 -*-
"""Monitor de atendimento: fila de espera, metricas, origem e auditoria.

Porte para o CRM do painel local do Izael ("Monitor Castro Chat v2", entregue
em 13/10/2026). As REGRAS de negocio sao as dele (classificacao de mensagem,
alarme so na fila de espera, palavras mais citadas, origem por texto da 1a
fala, auditoria anonimizada). O que muda e a fonte e o transporte:

- fila de espera: o painel relia TODAS as mensagens das ultimas 12h a cada
  15s (~2.500 docs por consulta no hubloc em 13/10). Aqui o gatilho e o
  `handoff_at` que bot_service._finalize_bot grava em TODAS as threads do
  contato (mesmo marco do aviso de espera na pool) — dezenas de docs por
  consulta; as mensagens so sao lidas para os alertas ja confirmados;
- metricas e auditoria: mensagens por faixa de created_at, sob demanda e com
  cache por tenant (nada de auto-refresh a cada 5 min);
- login/sessao: os do CRM (permissao ver_monitor_atendimento + tenant context
  do middleware). Nenhuma escrita no Firestore alem do log_audit do export.

Modulo PURO nas regras: o acesso a dados vem de database_firestore
(monitor_*) e as rotas ficam em main.py. tools/sim_monitor_flow.py exercita as
regras com dados sinteticos (inclui os cenarios A-I do modo demo do painel).
"""

from __future__ import annotations

import logging
import re
import statistics
import threading
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from config import FEATURE_MONITOR
# Vocabulario e normalizacao do gate LGPD importados (nao copiados) para nao
# divergir do lgpd_bot.
from lgpd_bot import _ACEITE_TERMOS, _RECUSA_TERMOS, _normalizar

logger = logging.getLogger("castro_crm.monitor")

# Fuso fixo -3 (Brasil sem DST desde 2019) — mesma convencao de
# business_hours e do protocolo diario.
BR_TZ = timezone(timedelta(hours=-3))

# ---------------------------------------------------------------------------
# Configuracao por tenant. Tenant fora daqui nao tem monitor (o menu mostra o
# dashboard antigo). Os marcadores de origem e os termos de fluxo sao do
# Hub Loc (texto fixo dos templates de entrada do site e da Meta).
# ---------------------------------------------------------------------------

MONITOR_TENANTS = {
    "hubloc": {
        "rotulo": "Hub Loc",
        # Setores cuja pool alarma, por departments.bot_key (hoje todo
        # handoff do hubloc vai para o Comercial — menu de setores removido).
        "fila_bot_keys": ("comercial",),
        "fila_minutos": 5,
        # Quanto olhar para tras procurando handoff sem resposta. 72h cobre
        # o lead de sexta a tarde que so e visto na segunda de manha.
        "fila_janela_horas": 72,
        "analisar_conteudo": True,
        "origem": True,
        "exportar_auditoria": True,
        "origem_site": ("vim pelo site da hub loc", "pedido de orcamento pelo site da hub loc"),
        "origem_meta": ("ola quero alugar uma ferramenta",
                        "ola posso ter mais informacoes sobre isso",
                        "ola quero alugar andaimes"),
        # Termos do fluxo, nao do cliente: botao LGPD, texto fixo dos
        # templates de entrada e pedido de preco. Sem isto eles lideram o
        # grafico (aparecem em quase toda conversa e nao dizem o equipamento).
        "termos_de_fluxo": ("lgpd aceitar recusar hub loc hubloc site vim pedido orcamento "
                            "locacao alugar ferramenta informacoes valor valores diaria "
                            "diarias preco precos dani"),
    },
}

FILA_TTL_S = 20            # cache da fila por tenant (o frontend consulta a cada 30s)
METRICAS_TTL_S = 600       # cache das metricas por (tenant, dias)
METRICAS_MAX_DIAS = 31
LIMITE_MENSAGENS = 40000   # teto de leitura por consulta (30 dias hubloc ~31k)
AUDITORIA_MAX_DIAS = 31
AUDITORIA_MAX_IDADE_DIAS = 90


def monitor_config(tenant_id) -> dict | None:
    """Config do monitor do tenant, ou None (sem monitor / kill-switch)."""
    if not FEATURE_MONITOR:
        return None
    cfg = MONITOR_TENANTS.get(str(tenant_id or ""))
    return dict(cfg) if cfg else None


# ---------------------------------------------------------------------------
# Texto: uma normalizacao so, reaproveitada por todas as regras
# ---------------------------------------------------------------------------

def sem_acento(texto: str) -> str:
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def frase_normalizada(texto: str) -> str:
    """minusculo, sem acento, sem pontuacao e emoji, espacos colapsados."""
    return re.sub(r"[^a-z0-9]+", " ", sem_acento(texto)).strip()


# ---------------------------------------------------------------------------
# Classificacao de mensagem (auditoria do Izael de 08/09/2026, conferida em
# database_firestore.save_wa_message)
# ---------------------------------------------------------------------------

DIRECTION_NAO_TURNO = frozenset({"system", "internal"})
MSG_TYPE_NAO_TURNO = frozenset({"reaction", "revoke", "internal"})


def eh_turno(m: dict) -> bool:
    return (m.get("direction") not in DIRECTION_NAO_TURNO
            and m.get("msg_type") not in MSG_TYPE_NAO_TURNO
            and m.get("status") != "failed")


def eh_resposta_humana(m: dict) -> bool:
    """O backend carimba last_human_outbound_at quando ha sender_user_id; o
    operator_id cobre mensagens antigas. Qualquer um dos dois vale."""
    return (eh_turno(m)
            and m.get("direction") == "outbound"
            and (m.get("sender_user_id") is not None or m.get("operator_id") is not None))


def humano_id(m: dict):
    return m.get("sender_user_id") if m.get("sender_user_id") is not None else m.get("operator_id")


def autoria(m: dict) -> str:
    if m.get("direction") == "system":
        return "sistema"
    if m.get("direction") == "internal" or m.get("msg_type") == "internal":
        return "nota interna"
    if m.get("direction") == "inbound":
        return "cliente"
    return "atendente" if eh_resposta_humana(m) else "automatizado"


_RESPOSTAS_LGPD = frozenset(_ACEITE_TERMOS | _RECUSA_TERMOS)


def eh_resposta_lgpd(texto: str) -> bool:
    """Resposta do gate LGPD (botao lgpd_aceitar/lgpd_recusar ou texto)."""
    return _normalizar(texto or "") in _RESPOSTAS_LGPD


# ---------------------------------------------------------------------------
# PII
# ---------------------------------------------------------------------------

RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
RE_DOC_FORMATADO = re.compile(r"\b\d{2,3}\.\d{3}\.\d{3}[/-]\d{2,4}(?:-\d{2})?\b")  # CPF/CNPJ
RE_TELEFONE = re.compile(r"(?:\+?55\s*)?(?:\(?\d{2}\)?[\s.-]*)?9?\d{4}[\s.-]?\d{4}")
RE_DIGITOS = re.compile(r"\d{8,}")


def redigir_pii(texto: str) -> str:
    """Tira e-mail, CPF/CNPJ, telefone e sequencias longas de digitos. A
    sequencia longa vem antes do telefone: senao o padrao de telefone come
    um pedaco de um CPF e deixa o resto exposto."""
    t = RE_EMAIL.sub("[email]", texto or "")
    t = RE_DOC_FORMATADO.sub("[documento]", t)
    t = RE_DIGITOS.sub("[numero]", t)
    return RE_TELEFONE.sub("[telefone]", t)


# ---------------------------------------------------------------------------
# Datas
# ---------------------------------------------------------------------------

def _aware(value):
    """datetime aware ou None (naive/lixo = None)."""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime) or value.tzinfo is None:
        return None
    return value


def _ts(m: dict):
    """Instante REAL da mensagem (timestamp_wa, hora do WhatsApp), com
    created_at (gravacao) de reserva. O recorte do periodo e por created_at
    (indice), mas ordem e tempo de resposta usam a hora real: o historico
    recente importado ao conectar um numero coex chega gravado em rajada
    (0,2 s entre pergunta e resposta) e daria tempo de resposta zero."""
    return _aware(m.get("timestamp_wa")) or _aware(m.get("created_at"))


# Mensagem gravada muito depois de ter acontecido = importacao, nao conversa
# do periodo: historico do WhatsApp Business ao conectar um numero coex (ate
# 180 dias de uma vez, sem marcador proprio — so timestamp_wa antigo) e o
# replay de backup. Em 13/10/2026 eram 39% das mensagens de 7 dias do hubloc
# (canais coex conectados em 09/10 e 13/10) e geravam "midia historico" como
# equipamento mais citado e tempo de resposta 0. Atraso real medido no mesmo
# dia: p99 = 114 s, maximo ~1h35 (fila de pending) — 3h tem folga.
IMPORTADA_APOS = timedelta(hours=3)


def eh_importada(m: dict) -> bool:
    gravada, aconteceu = _aware(m.get("created_at")), _aware(m.get("timestamp_wa"))
    return bool(gravada and aconteceu and gravada - aconteceu > IMPORTADA_APOS)


RE_MARCADOR = re.compile(r"^\s*\[[^\]]*\]\s*$")


def texto_real(m: dict) -> str:
    """Conteudo digitado pelo cliente; "" para marcador de sistema/midia
    ("[Midia do historico - aguardando]", "[errors]", "[unknown]"...)."""
    t = str(m.get("content") or "")
    return "" if RE_MARCADOR.match(t) else t


def _dia(dt: datetime) -> str:
    """Dia no fuso BR, ISO (YYYY-MM-DD): ordena certo na virada do ano."""
    return dt.astimezone(BR_TZ).strftime("%Y-%m-%d")


def _hhmm(dt) -> str:
    dt = _aware(dt)
    return dt.astimezone(BR_TZ).strftime("%H:%M") if dt else ""


def _data_do_protocolo(pid):
    """Protocolo nasce YYYYMMDD-... (dia BR, ensure_daily_attendance)."""
    try:
        return datetime.strptime(str(pid)[:8], "%Y%m%d").replace(tzinfo=BR_TZ)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Fila de espera (alarme)
# ---------------------------------------------------------------------------

def _inicio_do_relogio(tenant_id, handoff_at):
    """O relogio conta do handoff; se o handoff caiu com o expediente fechado,
    conta da abertura seguinte (mesma regra do aviso de espera na pool). Sem
    isso o lead das 7h30 abriria o dia ja com 30 min de atraso."""
    from business_hours import is_open, next_opening
    if is_open(tenant_id, handoff_at) is False:
        return next_opening(tenant_id, handoff_at) or handoff_at
    return handoff_at


def _threads_por_contato(threads):
    por_contato = defaultdict(list)
    for conv in threads or []:
        if conv.get("is_backup") or conv.get("contact_id") is None:
            continue
        if _aware(conv.get("handoff_at")) is None:
            continue
        por_contato[conv["contact_id"]].append(conv)
    return por_contato


def candidatos_da_fila(threads, tenant_id, cfg, now, fila_dept_ids=None) -> list:
    """Contatos que passam nos criterios que dependem SO das threads (sem
    resposta humana apos o handoff, thread aberta, tempo acima do limite,
    setor da fila). So eles tem o cadastro lido — em 13/10 eram 13 handoffs
    em 72h e 0 candidatos."""
    fila_dept_ids = set(fila_dept_ids or ())
    minutos_min = float(cfg.get("fila_minutos") or 5)
    saida = []
    for cid, convs in _threads_por_contato(threads).items():
        handoff = max(_aware(c.get("handoff_at")) for c in convs)
        humanos = [h for h in (_aware(c.get("last_human_outbound_at")) for c in convs) if h]
        if humanos and max(humanos) > handoff:
            continue
        abertas = [c for c in convs if c.get("attendance_status", "aberto") == "aberto"]
        if not abertas:
            continue
        principal = max(abertas, key=lambda c: _aware(c.get("last_inbound_at")) or handoff)
        dept = principal.get("department_id")
        if fila_dept_ids and dept is not None and dept not in fila_dept_ids:
            continue
        if (now - _inicio_do_relogio(tenant_id, handoff)).total_seconds() / 60.0 < minutos_min:
            continue
        saida.append(cid)
    return saida


def calcular_fila(threads, contacts, tenant_id, cfg, now, *, fila_dept_ids=None,
                  dept_names=None, user_names=None) -> list[dict]:
    """Clientes que o bot entregou a pool e seguem sem resposta HUMANA.

    threads: wa_conversations com handoff_at recente (sem backup).
    contacts: {contact_id: doc} dos contatos dessas threads.

    Agrupa por CONTATO: _finalize_bot grava o mesmo handoff_at em todas as
    threads do contato, inclusive a do numero pessoal (coex) da vendedora —
    resposta humana em QUALQUER uma delas para o relogio. Bot, reacao,
    envio falhado e nota interna nao carimbam last_human_outbound_at.

    Fica de fora: quem nao chegou ao handoff (parou no aceite de LGPD ou
    recusou), lead devolvido ao bot, marcado nao qualificado, arquivado,
    com LGPD revogada, thread fechada, ou fila de outro setor.
    """
    dept_names = dept_names or {}
    user_names = user_names or {}
    fila_dept_ids = set(fila_dept_ids or ())
    minutos_min = float(cfg.get("fila_minutos") or 5)

    alertas = []
    for cid, convs in _threads_por_contato(threads).items():
        contact = (contacts or {}).get(cid)
        if not contact or not contact.get("bot_completed"):
            continue
        if (contact.get("lgpd_revoked")
                or contact.get("qualification") == "nao_qualificado"
                or int(contact.get("is_archived") or 0) != 0):
            continue
        handoff = max(_aware(c.get("handoff_at")) for c in convs)
        humanos = [h for h in (_aware(c.get("last_human_outbound_at")) for c in convs) if h]
        if humanos and max(humanos) > handoff:
            continue
        abertas = [c for c in convs if c.get("attendance_status", "aberto") == "aberto"]
        if not abertas:
            continue
        principal = max(abertas, key=lambda c: _aware(c.get("last_inbound_at")) or handoff)
        dept = principal.get("department_id") or contact.get("department_id")
        if fila_dept_ids and dept not in fila_dept_ids:
            continue
        inicio = _inicio_do_relogio(tenant_id, handoff)
        minutos = (now - inicio).total_seconds() / 60.0
        if minutos < minutos_min:
            continue
        dono = principal.get("assigned_to") or contact.get("assigned_to")
        alertas.append({
            "chave": f"{cid}:{handoff.isoformat()}",
            "contato": cid,
            "conversa": principal.get("id"),
            "canal": principal.get("channel_label") or principal.get("channel_id"),
            "fila": dept_names.get(dept) or "",
            "minutos": round(minutos, 1),
            "desde": _hhmm(inicio),
            "handoff_em": _hhmm(handoff),
            "responsavel": user_names.get(dono) if dono is not None else None,
            "protocolo": contact.get("attendance_protocol") or None,
            "mensagens_apos_fila": 0,
            "previa": "",
        })
    alertas.sort(key=lambda a: -a["minutos"])
    return alertas


def resumo_da_espera(mensagens, handoff_at) -> dict:
    """Do historico recente da thread (qualquer ordem): quantas falas o
    cliente mandou depois de entrar na fila e a previa da ultima (redigida)."""
    handoff = _aware(handoff_at)
    falas = []
    for m in mensagens or []:
        if (m.get("direction") == "inbound" and eh_turno(m) and texto_real(m)
                and not eh_resposta_lgpd(texto_real(m))):
            t = _aware(m.get("timestamp_wa")) or _aware(m.get("created_at"))
            if t:
                falas.append((t, m))
    falas.sort(key=lambda x: x[0])
    depois = [m for t, m in falas if handoff and t > handoff]
    ultima = (depois or [m for _, m in falas] or [{}])[-1]
    protocolo = next((m.get("protocol_id") for m in mensagens or [] if m.get("protocol_id")), None)
    return {
        "mensagens_apos_fila": len(depois),
        "previa": redigir_pii(texto_real(ultima))[:90],
        "protocolo": protocolo,
    }


# ---------------------------------------------------------------------------
# Palavras mais citadas — extracao automatica, stdlib pura
# ---------------------------------------------------------------------------

STOPWORDS = frozenset("""a as o os um uma uns umas de do da dos das em no na nos nas por para
com sem sob sobre ate apos entre e ou mas que se ja nao sim eu tu ele ela nos vos eles elas
me te lhe nos vos lhes meu minha seu sua dele dela isso isto aquilo este esta esse essa
aquele aquela ai la aqui bom boa dia tarde noite obrigado obrigada por favor voce voces vc
vcs ok certo tudo bem entao pois porque como quando onde qual quais quanto quantos muito
muita pouco pouca mais menos tem ter tenho temos tinha havia ser sou somos era foi sao esta
estao estou estamos vai vou vamos pode posso podemos quero queria gostaria preciso precisa
precisamos fazer faz feito dar da dou ver vejo sei sabe fica ficou ficar so ainda agora hoje
amanha ontem depois antes vez vezes coisa coisas favor cada todo toda todos todas outro
outra outros outras mesmo mesma qualquer alguem algum alguma nada nenhum ah oi ola opa blz
valeu ta tao pra pro num numa dele nele nela pelo pela pelos pelas
mim tambem mandar manda mando enviar envia envio precisando consegue conseguir contato
""".split())

TOKEN = re.compile(r"[a-z]{3,}")


def normalizar(texto: str, termos_de_fluxo=frozenset()) -> list[str]:
    return [w for w in TOKEN.findall(sem_acento(texto))
            if w not in STOPWORDS and w not in termos_de_fluxo]


def mais_citados(textos_por_conversa: dict, termos_de_fluxo=frozenset(), limite: int = 15,
                 minimo_conversas: int = 2) -> list[dict]:
    """Ordena por numero de CONVERSAS distintas: uma conversa repetitiva nao
    domina. Bigrama frequente esconde as palavras soltas que o formam."""
    ocorrencias, conversas = Counter(), defaultdict(set)
    for conv, textos in textos_por_conversa.items():
        for texto in textos:
            if eh_resposta_lgpd(texto):
                continue
            palavras = normalizar(texto, termos_de_fluxo)
            for i, p in enumerate(palavras):
                ocorrencias[p] += 1
                conversas[p].add(conv)
                if i + 1 < len(palavras):
                    bi = f"{p} {palavras[i + 1]}"
                    ocorrencias[bi] += 1
                    conversas[bi].add(conv)
    itens = [{"termo": t, "ocorrencias": ocorrencias[t], "conversas": len(c)}
             for t, c in conversas.items() if len(c) >= minimo_conversas]
    itens.sort(key=lambda x: (-x["conversas"], -x["ocorrencias"], x["termo"]))
    bigrams = [i["termo"] for i in itens[:limite * 3] if " " in i["termo"]]
    partes = {p for b in bigrams for p in b.split()}
    enxuto = [i for i in itens if not (" " not in i["termo"] and i["termo"] in partes)]
    return (enxuto or itens)[:limite]


# ---------------------------------------------------------------------------
# Controle de origem
# ---------------------------------------------------------------------------

REGRA_ORIGEM_VERSAO = "v1 de 29/09/2026 (texto da primeira mensagem)"

ORIGENS = {  # chave -> (rotulo, confianca)
    "site": ("Site", "confirmado"),
    "meta": ("Meta/Instagram", "alta confiança"),
    "indeterminada": ("Indeterminada", "sem marcador"),
}


def classificar_origem(texto: str, cfg: dict) -> tuple[str, str]:
    """(chave, criterio). Site = contem o marcador; Meta = IGUAL a um dos
    templates (maiuscula, acento e pontuacao ignorados). Texto que comeca
    com o template e continua fica Indeterminada (regra ao pe da letra).
    Quando o CRM gravar o referral da Meta / tag do Tag Manager, a tag
    declarada entra aqui e vence o texto (frente de origem de midia)."""
    f = frase_normalizada(texto)
    if any(marca in f for marca in cfg.get("origem_site") or ()):
        return "site", "marcador do site"
    if f in set(cfg.get("origem_meta") or ()):
        return "meta", "template da Meta"
    return "indeterminada", "texto livre"


def metricas_origem(mensagens, cfg, corte) -> dict:
    """Uma linha por protocolo (atendimento do dia): origem pela primeira fala
    do cliente (sem a resposta do aceite), se entrou na fila, se teve
    resposta humana e em quanto tempo."""
    por_protocolo = defaultdict(list)
    for m in mensagens:
        chave = m.get("protocol_id") or f"conv:{m.get('conversation_id')}"
        por_protocolo[chave].append(m)

    linhas, fora, continuacoes = [], 0, 0
    ja_visto = set()
    ordem = sorted(por_protocolo.items(), key=lambda kv: min(_ts(m) for m in kv[1]))
    for pid, msgs in ordem:
        msgs.sort(key=_ts)
        falas = [m for m in msgs if m.get("direction") == "inbound" and eh_turno(m)
                 and texto_real(m) and not eh_resposta_lgpd(texto_real(m))]
        if not falas:
            continue
        inicio = _data_do_protocolo(pid)
        if inicio is not None and inicio.date() < corte.astimezone(BR_TZ).date():
            fora += 1          # protocolo aberto antes da janela: 1a fala ficou fora
            ja_visto.add(falas[0].get("contact_id"))
            continue
        primeira = falas[0]
        contato = primeira.get("contact_id")
        chave, criterio = classificar_origem(texto_real(primeira), cfg)
        # Protocolo e diario: cliente que volta outro dia com "bom dia" abre
        # protocolo novo sem marcador — continuacao, nao lead de origem
        # desconhecida. Retorno COM marcador (clicou em anuncio de novo) conta.
        retorno = contato in ja_visto
        ja_visto.add(contato)
        if retorno and chave == "indeterminada":
            continuacoes += 1
            continue
        humano = next((m for m in msgs if eh_resposta_humana(m) and _ts(m) > _ts(primeira)), None)
        espera = None
        if humano:
            espera = (_ts(humano) - _ts(primeira)).total_seconds() / 60.0
            if espera > 24 * 60:
                espera = None
        linhas.append({"origem": chave, "criterio": criterio,
                       "dia": _dia(_ts(primeira)),
                       "canal": str(primeira.get("channel_id")),
                       "fila": any(_eh_entrada_na_fila(m) for m in msgs),
                       "humano": humano is not None, "espera": espera,
                       "texto": frase_normalizada(texto_real(primeira))})

    resumo = {}
    for chave in list(ORIGENS) + sorted({ln["origem"] for ln in linhas} - set(ORIGENS)):
        grupo = [ln for ln in linhas if ln["origem"] == chave]
        esperas = [ln["espera"] for ln in grupo if ln["espera"] is not None]
        rotulo, confianca = ORIGENS.get(chave, (chave.title(), "tag declarada"))
        resumo[chave] = {
            "rotulo": rotulo, "confianca": confianca, "protocolos": len(grupo),
            "na_fila": sum(1 for ln in grupo if ln["fila"]),
            "com_humano": sum(1 for ln in grupo if ln["humano"]),
            "primeira_resposta_mediana_min": round(statistics.median(esperas), 1) if esperas else None,
        }
    por_dia = defaultdict(Counter)
    por_canal = defaultdict(Counter)
    for ln in linhas:
        por_dia[ln["dia"]][ln["origem"]] += 1
        por_canal[ln["canal"]][ln["origem"]] += 1
    # aberturas recorrentes sem classificacao: candidatas a regra nova
    recorrentes = Counter(ln["texto"][:60] for ln in linhas
                          if ln["origem"] == "indeterminada" and ln["texto"])
    return {
        "versao_regra": REGRA_ORIGEM_VERSAO,
        "total": len(linhas),
        "fora_da_janela": fora,
        "continuacoes": continuacoes,
        "resumo": resumo,
        "por_dia": {d: dict(c) for d, c in sorted(por_dia.items())},
        "por_canal": {k: dict(v) for k, v in sorted(por_canal.items())},
        "indeterminadas_recorrentes": [{"texto": redigir_pii(t), "protocolos": n}
                                       for t, n in recorrentes.most_common(10) if n >= 2],
    }


# Entrada na fila nas metricas de origem: a mensagem de sistema que
# _finalize_bot grava ("Bot finalizado | Bot: Setor=X | Encaminhado para X").
RE_FILA = re.compile(r"^bot finalizado\b.*\|\s*encaminhado para\s+(.+?)\s*$")


def _eh_entrada_na_fila(m: dict) -> bool:
    if m.get("direction") != "system":
        return False
    return bool(RE_FILA.match(re.sub(r"\s+", " ", sem_acento(m.get("content") or "")).strip()))


# ---------------------------------------------------------------------------
# Metricas
# ---------------------------------------------------------------------------

def metricas_comercial(mensagens, user_names, cfg, corte) -> dict:
    importadas = sum(1 for m in mensagens if eh_importada(m))
    mensagens = [m for m in mensagens if _ts(m) and not eh_importada(m)]
    turnos = [m for m in mensagens if eh_turno(m)]
    por_conversa = defaultdict(list)
    for m in turnos:
        por_conversa[m.get("conversation_id") or f"c{m.get('contact_id')}"].append(m)

    def nome(uid):
        return user_names.get(uid) or f"operador {uid}"

    atend_por_op = Counter()
    tempos = defaultdict(list)
    primeira = defaultdict(list)
    for msgs in por_conversa.values():
        msgs.sort(key=_ts)
        pendente = None
        primeira_feita = False
        for m in msgs:
            if m.get("direction") == "inbound":
                if pendente is None:
                    pendente = _ts(m)
            elif eh_resposta_humana(m):
                n = nome(humano_id(m))
                if pendente is not None:
                    delta = (_ts(m) - pendente).total_seconds() / 60.0
                    if 0 <= delta <= 24 * 60:
                        tempos[n].append(delta)
                        if not primeira_feita:
                            primeira[n].append(delta)
                            primeira_feita = True
                    pendente = None
        for d in {humano_id(m) for m in msgs if eh_resposta_humana(m)}:
            atend_por_op[nome(d)] += 1

    volume, entrada, canal = Counter(), Counter(), Counter()
    for m in turnos:
        volume[_dia(_ts(m))] += 1
        canal[str(m.get("channel_id"))] += 1
        if m.get("direction") == "inbound":
            entrada[_dia(_ts(m))] += 1

    equipamentos = []
    if cfg.get("analisar_conteudo"):
        # Cliente chama a atendente pelo nome ("oi Aline"): primeiro nome de
        # cada usuario do tenant sai do grafico junto com os termos de fluxo.
        nomes_proprios = {p for n in user_names.values()
                          for p in TOKEN.findall(sem_acento(str(n or "").split(" ")[0].split(".")[0]))}
        fluxo = frozenset(str(cfg.get("termos_de_fluxo") or "").split()) | nomes_proprios
        textos = defaultdict(list)
        for m in turnos:
            if m.get("direction") == "inbound" and texto_real(m):
                textos[m.get("conversation_id") or str(m.get("contact_id"))].append(texto_real(m))
        equipamentos = mais_citados(textos, fluxo)

    def med(d):
        return {k: round(statistics.median(v), 1) for k, v in d.items() if v}

    def mea(d):
        return {k: round(statistics.fmean(v), 1) for k, v in d.items() if v}

    return {
        "importadas_ignoradas": importadas,
        "total_atendimentos": len(por_conversa),
        "total_mensagens": len(turnos),
        "atendimentos_por_operador": dict(atend_por_op.most_common()),
        "resposta_mediana_min": med(tempos),
        "resposta_media_min": mea(tempos),
        "primeira_resposta_mediana_min": med(primeira),
        "volume_por_dia": dict(sorted(volume.items())),
        "entrada_por_dia": dict(sorted(entrada.items())),
        "volume_por_canal": dict(sorted(canal.items())),
        "equipamentos": equipamentos,
        # Origem le as falas E a mensagem de sistema do handoff (fila).
        "origem": metricas_origem(mensagens, cfg, corte) if cfg.get("origem") else None,
    }


# ---------------------------------------------------------------------------
# Auditoria por atendente
# ---------------------------------------------------------------------------

def slug(texto: str) -> str:
    """Nome de arquivo seguro (sem acento, sem barra)."""
    t = re.sub(r"[^a-z0-9]+", "-", sem_acento(texto)).strip("-")
    return t or "operador"


def gerar_auditoria(mensagens, user_names, operador_id: int, inicio: datetime,
                    fim: datetime, rotulo: str) -> tuple[str, int]:
    """Texto da auditoria: toda conversa (protocolo) em que o atendente
    respondeu no periodo, com o cliente anonimizado (sem nome nem telefone;
    contato pelo id interno) e PII redigida no corpo."""
    nome = user_names.get(operador_id) or f"operador {operador_id}"
    no_periodo = [m for m in mensagens if _ts(m) and inicio <= _ts(m) < fim and not eh_importada(m)]
    convs_do_op = {m.get("conversation_id") for m in no_periodo
                   if eh_resposta_humana(m) and humano_id(m) == operador_id}
    selecionadas = defaultdict(list)
    for m in no_periodo:
        if m.get("conversation_id") in convs_do_op:
            selecionadas[m.get("protocol_id") or m.get("conversation_id")].append(m)

    linhas = [
        f"AUDITORIA DE ATENDIMENTO — {rotulo}",
        f"Atendente: {nome} (id {operador_id})",
        f"Periodo: {inicio.astimezone(BR_TZ):%d/%m/%Y %H:%M} a "
        f"{(fim - timedelta(seconds=1)).astimezone(BR_TZ):%d/%m/%Y %H:%M}",
        f"Extraido em: {datetime.now(BR_TZ):%d/%m/%Y %H:%M} (horario de Brasilia)",
        f"Conversas: {len(selecionadas)}",
        "",
        "Cliente anonimizado: nome e telefone removidos; protocolo preservado.",
        "Autoria 'automatizado' e inferencia por ausencia de operador na mensagem.",
        "Historico importado do WhatsApp (conexao de numero) fica de fora.",
        "=" * 78, "",
    ]
    for protocolo, msgs in sorted(selecionadas.items(), key=lambda kv: str(kv[0])):
        msgs.sort(key=_ts)
        linhas.append(f"--- PROTOCOLO {protocolo} | Cliente {msgs[0].get('contact_id')} "
                      f"| canal {msgs[0].get('channel_id')} ---")
        for m in msgs:
            quem = autoria(m)
            if quem == "atendente":
                quem = user_names.get(humano_id(m)) or f"operador {humano_id(m)}"
            hora = _ts(m).astimezone(BR_TZ).strftime("%d/%m %H:%M")
            corpo = redigir_pii(m.get("content") or f"[{m.get('msg_type')}]")
            linhas.append(f"[{hora}] {quem}: {corpo}")
        linhas.append("")
    return "\n".join(linhas), len(selecionadas)


# ---------------------------------------------------------------------------
# Servico (cache + orquestracao). Chamado em threadpool com o tenant setado.
# ---------------------------------------------------------------------------

_cache: dict = {}
_cache_lock = threading.Lock()


def _cacheado(chave, ttl, produtor, refresh=False):
    agora = time.monotonic()
    if not refresh:
        with _cache_lock:
            achado = _cache.get(chave)
            if achado and agora - achado[0] < ttl:
                return achado[1]
    valor = produtor()
    with _cache_lock:
        _cache[chave] = (agora, valor)
    return valor


def _nomes_usuarios():
    from database import get_all_users
    return {u.get("id"): (u.get("display_name") or u.get("email") or f"operador {u.get('id')}")
            for u in get_all_users() if u.get("id") is not None}


def fila_de_espera(tenant_id, cfg, now=None) -> dict:
    """Payload do alarme. Fora do expediente devolve a lista vazia."""
    from business_hours import is_open, schedule_summary
    now = now or datetime.now(timezone.utc)
    aberto = is_open(tenant_id, now) is not False
    base = {
        "dentro_do_expediente": aberto,
        "expediente": schedule_summary(tenant_id) or "",
        "limite_min": cfg.get("fila_minutos") or 5,
        "agora": now.astimezone(BR_TZ).strftime("%H:%M:%S"),
        "alertas": [],
    }
    if not aberto:
        return base

    def produzir():
        from database import (
            get_all_departments, monitor_get_contacts, monitor_queue_threads,
            monitor_thread_messages,
        )
        agora = now
        janela = timedelta(hours=float(cfg.get("fila_janela_horas") or 72))
        threads = monitor_queue_threads(agora - janela)
        depts = get_all_departments(include_inactive=True)
        dept_names = {d.get("id"): d.get("name") or "" for d in depts}
        keys = {str(k).lower() for k in cfg.get("fila_bot_keys") or ()}
        fila_ids = {d.get("id") for d in depts
                    if keys and str(d.get("bot_key") or "").lower() in keys and d.get("is_active", 1)}
        if keys and not fila_ids:
            logger.warning("[MONITOR] nenhum setor ativo casa fila_bot_keys=%s | tenant=%s",
                           sorted(keys), tenant_id)
        candidatos = candidatos_da_fila(threads, tenant_id, cfg, agora, fila_ids)
        contacts = monitor_get_contacts(candidatos) if candidatos else {}
        alertas = calcular_fila(threads, contacts, tenant_id, cfg, agora,
                                fila_dept_ids=fila_ids, dept_names=dept_names,
                                user_names=_nomes_usuarios() if threads else {})
        handoffs = {}
        for t in threads:
            h = _aware(t.get("handoff_at"))
            if h and (t.get("contact_id") not in handoffs or h > handoffs[t.get("contact_id")]):
                handoffs[t.get("contact_id")] = h
        for a in alertas:
            try:
                msgs = monitor_thread_messages(a["contato"], a["conversa"])
            except Exception:
                logger.exception("[MONITOR] historico da fila falhou | contato=%s", a["contato"])
                continue
            r = resumo_da_espera(msgs, handoffs.get(a["contato"]))
            a["mensagens_apos_fila"] = r["mensagens_apos_fila"]
            a["previa"] = r["previa"]
            a["protocolo"] = a["protocolo"] or r["protocolo"]
        return alertas

    base["alertas"] = _cacheado(("fila", tenant_id), FILA_TTL_S, produzir)
    return base


def metricas(tenant_id, cfg, dias: int, refresh=False) -> dict:
    """Metricas do periodo (sob demanda, cache de 10 min por tenant+periodo)."""
    dias = max(1, min(int(dias), METRICAS_MAX_DIAS))

    def produzir():
        from database import monitor_messages_between
        agora = datetime.now(timezone.utc)
        corte = agora - timedelta(days=dias)
        msgs, truncado = monitor_messages_between(corte, agora + timedelta(minutes=1), LIMITE_MENSAGENS)
        dados = metricas_comercial(msgs, _nomes_usuarios(), cfg, corte)
        return {"dias": dias, "truncado": truncado, "dados": dados, "mensagens_lidas": len(msgs),
                "extraido_em": agora.astimezone(BR_TZ).strftime("%d/%m/%Y %H:%M:%S")}

    return _cacheado(("metricas", tenant_id, dias), METRICAS_TTL_S, produzir, refresh=refresh)


def auditoria_atendente(tenant_id, cfg, operador_id: int, inicio_dia, fim_dia) -> dict:
    """Texto da auditoria de um atendente entre dois dias BR (inclusivos)."""
    from database import monitor_messages_between
    inicio = datetime.combine(inicio_dia, datetime.min.time(), tzinfo=BR_TZ)
    fim = datetime.combine(fim_dia, datetime.min.time(), tzinfo=BR_TZ) + timedelta(days=1)
    msgs, truncado = monitor_messages_between(inicio.astimezone(timezone.utc),
                                              fim.astimezone(timezone.utc), LIMITE_MENSAGENS)
    nomes = _nomes_usuarios()
    texto, n = gerar_auditoria(msgs, nomes, operador_id, inicio, fim, cfg.get("rotulo") or tenant_id)
    if truncado:
        texto = ("ATENCAO: o periodo bateu no teto de leitura e esta incompleto. "
                 "Reduza o periodo.\n\n" + texto)
    return {"texto": texto, "conversas": n, "truncado": truncado,
            "nome": nomes.get(operador_id) or f"operador {operador_id}"}
