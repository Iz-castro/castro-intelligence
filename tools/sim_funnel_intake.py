# -*- coding: utf-8 -*-

"""
Simulador LOCAL da entrada automatica no funil comercial ("intake", ADR 0015)
e das automacoes por evento da emenda de 28/10/2026 (handoff da Val e 1a
resposta humana pelo CRM).

Prova que os campos crm_* entram no MESMO write que o caminho quente ja faz
e SO por mensagem ao vivo DO CLIENTE em canal elegivel, em contato sem etapa,
fora de backup e de revogacao LGPD; que agenda (state_sync), history, eco do
celular, clique de controle, reacao/sistema/desconhecido, canal de outro
tenant e falha na leitura do tenant nao gravam etapa nenhuma (midia que a
Cloud API nao interpreta, unsupported/ephemeral, e request_welcome contam como
entrada em Novo contato); e os caminhos REST (criacao manual entra em Em
atendimento; graduacao de backup em A classificar). Trava as correcoes: o
crm_stage_changed_at da entrada usa o MESMO instante de last_inbound_at
(senao o selo "mensagem nova" de A classificar acendia com a propria mensagem
de entrada); a thread viva de contato ainda backup tambem gradua com
also_lead; e assign_wa_conversation(also_lead) nao le o contato com o funil
desligado nem deixa a graduacao pela metade se essa leitura falha.

Automacoes: o handoff da Val (turno CX REAL pelo webhook, e o builtin) move
Novo contato / A classificar -> Em atendimento no MESMO write do handoff e
grava a Activity depois (set com id deterministico: reentrega/retry nao
duplica), sem tocar qualification e sem regredir as demais etapas; a 1a
resposta humana pelo CRM (kwarg funnel_human_reply dos endpoints de envio
humano de main.py) faz o mesmo; eco, history, lote, recibo e bot nao movem.
Todos os caminhos de handoff do CX (frase de transferencia, motor fora 2x,
settings.ai incompleto, 4 frases de erro, lgpd_by_agent, fora do expediente,
buffer) e todos os estados do builtin sao comparados com o funil desligado:
mesmos writes e leituras, so os crm_* a mais. Endpoints REAIS: texto,
correcao, template manual e reabertura pontual movem; o lote de reabertura
real nao. Sem contexto de tenant nada acontece (sem fallback 'hubloc') e uma
sessao VALIDA de "Ver como" nao passa do middleware em nenhuma rota de envio.
O [Continuar] do template de reabertura devolvido ao agente (develop): o
clique entra por _process_messages (lead antigo vai para A classificar), o
turno sintetico com handoff leva a Em atendimento com Activity, a reentrega
do clique nao repete turno nem Activity e o turno falhando cai na equipe
(mark_contact_bot_done) sem mexer em crm_*.

NAO toca em producao: roda o codigo REAL de webhook.py (_process_messages,
process_webhook_payload, eco, agenda e history), database_firestore.py
(upsert_wa_contact, create_manual_wa_contact, assign_wa_contact,
assign_wa_conversation, save_wa_message), bot_service.py (turno CX com o
conector Dialogflow trocado por roteiro, builtin, handoffs) e main.wa_send
(httpx falso) com o Firestore trocado por um store em memoria separado POR
TENANT (padrao do sim_history_recency.py). O doc do tenant vem de um
tenant_service falso com settings.funnel habilitado (template clinic_v1).
O cliente Firestore real fica travado (AssertionError).

Rodar (Windows, na raiz):
    .venv\\Scripts\\python.exe tools\\sim_funnel_intake.py

Sai com codigo 0 se todos os asserts passarem, 1 caso contrario.
"""

import ast
import asyncio
import copy
import hashlib
import json
import logging
import os
import re
import sys
import types
import warnings
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from google.api_core import exceptions as gcloud_exceptions  # noqa: E402
from google.cloud.firestore_v1.transforms import Increment as _Increment  # noqa: E402

import bot_engine_dialogflow  # noqa: E402  (so detect_intent_text e trocado)
import bot_service  # noqa: E402
import channel_service  # noqa: E402
import config  # noqa: E402
import database  # noqa: E402  (reexporta database_firestore)
import database_firestore as dbf  # noqa: E402
import firestore_common  # noqa: E402
import funnel_catalog as fc  # noqa: E402
import rbac  # noqa: E402
import tenant_service  # noqa: E402
import webhook  # noqa: E402

FAILS = []
CHECKS = 0


def check(cond, label):
    global CHECKS
    CHECKS += 1
    if cond:
        print(f"      ✓ {label}")
    else:
        FAILS.append(label)
        print(f"      ✗ FALHOU: {label}")


def titulo(txt):
    print("\n" + "=" * 70)
    print(txt)
    print("=" * 70)


# =========================================================================
# Store em memoria separado por tenant (padrao do sim_history_recency)
# =========================================================================

STORE = {}       # (tenant, colecao) -> {doc_id: dict}
WRITES = []      # writes do cenario atual: (tenant, colecao, doc_id, campos, merge)
OPS = []         # tipo de cada write do cenario atual: (tenant, colecao, doc_id, "set"|"create")
ALL_WRITES = []  # todos os writes da execucao (varredura de tipos no fim)
READS = []       # leituras do cenario atual: (tenant, colecao, doc_id ou "<query>")
READ_FAILS = set()  # colecoes cujo get() levanta ServiceUnavailable (falha injetada)
WRITE_FAILS = set()  # colecoes cujo set()/create() levanta ServiceUnavailable (falha injetada)
_SEQ = {"n": 1000}
CLOCK = {"now": None}  # relogio controlavel do database_firestore (None = real)


def _space(coll):
    # Mesma regra do firestore_common: globais ficam flat; o resto vai para o
    # tenant do contexto (sem contexto = flat).
    if coll in firestore_common._GLOBAL_COLLECTIONS:
        return ("", coll)
    return (firestore_common.get_tenant_context() or "", coll)


class _Snap:
    def __init__(self, doc_id, data, ref=None):
        self.id = str(doc_id)
        self._data = copy.deepcopy(data) if data is not None else None
        self.reference = ref

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return copy.deepcopy(self._data) if self._data is not None else None


class _DocRef:
    def __init__(self, space, doc_id):
        self.space = space
        self.doc_id = str(doc_id)

    @property
    def id(self):
        return self.doc_id

    def get(self, transaction=None):
        READS.append((self.space[0], self.space[1], self.doc_id))
        if self.space[1] in READ_FAILS:
            raise gcloud_exceptions.ServiceUnavailable("leitura indisponivel (simulado)")
        return _Snap(self.doc_id, STORE.get(self.space, {}).get(self.doc_id), self)

    def _log(self, data, merge, kind="set"):
        if self.space[1] in WRITE_FAILS:
            raise gcloud_exceptions.ServiceUnavailable("escrita indisponivel (simulado)")
        row = (self.space[0], self.space[1], self.doc_id, copy.deepcopy(dict(data)), merge)
        WRITES.append(row)
        ALL_WRITES.append(row)
        OPS.append((self.space[0], self.space[1], self.doc_id, kind))

    def set(self, data, merge=False):
        self._log(data, merge)
        coll = STORE.setdefault(self.space, {})
        data = _apply_increments(coll.get(self.doc_id) if merge else None, data)
        if merge and self.doc_id in coll:
            coll[self.doc_id].update(copy.deepcopy(dict(data)))
        else:
            coll[self.doc_id] = copy.deepcopy(dict(data))

    def create(self, data):
        # Claim atomico (wa_contact_index / wa_message_index): falha se existe.
        coll = STORE.setdefault(self.space, {})
        if self.doc_id in coll:
            raise gcloud_exceptions.AlreadyExists("ja existe")
        self._log(data, False, "create")
        coll[self.doc_id] = copy.deepcopy(dict(data))

    def delete(self):
        STORE.get(self.space, {}).pop(self.doc_id, None)


def _apply_increments(current, data):
    """Sentinela firestore.Increment (cx_fail_count atomico do motor CX):
    soma no valor guardado, como o servidor faria. O resto passa intacto."""
    out = {}
    for key, value in dict(data).items():
        if isinstance(value, _Increment):
            base = (current or {}).get(key)
            base = base if isinstance(base, (int, float)) and not isinstance(base, bool) else 0
            out[key] = base + value.value
        else:
            out[key] = value
    return out


def _sort_value(v):
    if isinstance(v, datetime):
        return (0, (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).timestamp())
    if isinstance(v, str):
        try:
            d = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return (0, (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp())
        except ValueError:
            return (1, v)
    if v is None:
        return (-1, 0)
    return (0, v)


def _match(data, field, op, value):
    got = data.get(field)
    if op == "==":
        return got == value
    if op == "in":
        return got in value
    if got is None:
        return False
    try:
        if op == ">=":
            return got >= value
        if op == ">":
            return got > value
        if op == "<=":
            return got <= value
        if op == "<":
            return got < value
    except TypeError:
        return False
    raise AssertionError(f"operador nao suportado no mock: {op}")


class _CollRef:
    def __init__(self, space):
        self.space = space
        self._filters = []
        self._limit = None
        self._order = None

    def where(self, field, op, value):
        self._filters.append((field, op, value))
        return self

    def order_by(self, field, direction="ASCENDING"):
        self._order = (field, str(direction).upper().startswith("DESC"))
        return self

    def limit(self, n):
        self._limit = n
        return self

    def document(self, doc_id=None):
        if doc_id is None:
            _SEQ["n"] += 1
            doc_id = "auto%d" % _SEQ["n"]
        return _DocRef(self.space, doc_id)

    def stream(self):
        READS.append((self.space[0], self.space[1], "<query>"))
        rows = [(doc_id, data) for doc_id, data in list(STORE.get(self.space, {}).items())
                if all(_match(data, f, op, v) for (f, op, v) in self._filters)]
        if self._order:
            field, desc = self._order
            rows.sort(key=lambda r: _sort_value(r[1].get(field)), reverse=desc)
        for i, (doc_id, data) in enumerate(rows):
            if self._limit is not None and i >= self._limit:
                break
            yield _Snap(doc_id, data, _DocRef(self.space, doc_id))


class _Batch:
    def __init__(self):
        self._ops = []

    def set(self, ref, data, merge=False):
        self._ops.append((ref, data, merge))

    def commit(self):
        for ref, data, merge in self._ops:
            ref.set(data, merge=merge)
        self._ops = []


class _BatchOnlyClient:
    """So batch() (graduacao das mensagens do backup); o resto e proibido."""

    def batch(self):
        return _Batch()

    def __getattr__(self, name):
        raise AssertionError("sim tentou usar o cliente Firestore REAL (%s)" % name)


def _no_client(*_a, **_k):
    raise AssertionError("sim tentou abrir cliente Firestore REAL")


# =========================================================================
# Tenants, canais, usuarios e stubs
# =========================================================================

TENANT = "varizemed"
OTHER = "hubloc"
FUNNEL = {"enabled": True, "template": "clinic_v1", "version": 1}
FUNNEL_COEX = dict(FUNNEL, intake_channel_types=["standard", "coexistence"])
TENANT_DOCS = {}
# "funnel" = leituras do doc do tenant feitas PELO funnel_catalog; "other" =
# as do despachante do bot (motor/tenant ativo), que existem com ou sem funil.
LOOKUPS = {"funnel": 0, "webhook": 0, "other": 0}
GET_TENANT_FAILS = {"on": False}
BOT_CALLS = []
PENDING = []

STD_CH = {"id": 4, "tenant_id": TENANT, "is_active": True, "channel_type": "standard",
          "owner_user_id": None, "phone_number_id": "PNID4", "access_token": "tok-4",
          "display_phone_number": "+55 31 3000-0004", "label": "Recepcao"}
COEX_CH = {"id": 8, "tenant_id": TENANT, "is_active": True, "channel_type": "coexistence",
           "owner_user_id": 8, "phone_number_id": "PNID8", "access_token": "tok-8",
           "display_phone_number": "+55 31 90000-0008", "label": "Celular"}
OTHER_CH = {"id": 12, "tenant_id": OTHER, "is_active": True, "channel_type": "standard",
            "owner_user_id": None, "phone_number_id": "PNID12", "access_token": "tok-12",
            "display_phone_number": "+55 11 3000-0012", "label": "Outro tenant"}
LEGACY_CH = {"id": 5, "is_active": True, "channel_type": "standard",  # sem tenant_id
             "owner_user_id": None, "phone_number_id": "PNID5", "access_token": "tok-5",
             "display_phone_number": "+55 31 3000-0005", "label": "Legado"}
CHANNELS = {c["id"]: c for c in (STD_CH, COEX_CH, OTHER_CH, LEGACY_CH)}
CHANNELS_BY_PNID = {c["phone_number_id"]: c for c in CHANNELS.values()}
BUSINESS_COEX = "5531900000008"

USERS = {
    "4": {"id": 4, "display_name": "Operadora", "firebase_uid": "uid-4", "department_id": 2,
          "is_active": 1, "role": "operador", "tenant_id": TENANT},
    "7": {"id": 7, "display_name": "Supervisora", "firebase_uid": "uid-7", "department_id": 2,
          "is_active": 1, "role": "supervisor", "tenant_id": TENANT},
    "8": {"id": 8, "display_name": "Dona do celular", "firebase_uid": "uid-8", "department_id": 3,
          "is_active": 1, "role": "operador", "tenant_id": TENANT},
    "9": {"id": 9, "display_name": "Outra operadora", "firebase_uid": "uid-9", "department_id": 2,
          "is_active": 1, "role": "operador", "tenant_id": TENANT},
}

_REAL_INTAKE_CATALOG = webhook.intake_catalog_for_channel


def _tenant_doc(tid):
    if GET_TENANT_FAILS["on"]:
        raise RuntimeError("tenant_service indisponivel (simulado)")
    doc = TENANT_DOCS.get(str(tid))
    return copy.deepcopy(doc) if doc else None


def _fake_get_tenant_funnel(tid):
    # tenant_service.get_tenant: lido pelo funnel_catalog (import lazy) e pelo
    # despachante do bot (_tenant_is_active/_get_tenant_ai_config). So a
    # leitura do funil conta em LOOKUPS["funnel"] (quem chama decide).
    caller = sys._getframe(1).f_globals.get("__name__", "")
    LOOKUPS["funnel" if caller == "funnel_catalog" else "other"] += 1
    return _tenant_doc(tid)


def _fake_get_tenant_webhook(tid):
    # webhook.get_tenant: janela do buffer / lgpd_by_agent.
    LOOKUPS["webhook"] += 1
    return _tenant_doc(tid)


# Bot: por padrao so registra a chamada. BOT_MODE "cx" roda o turno REAL do
# Dialogflow CX (bot_service._process_cx_message, conector trocado por
# roteiro) e "builtin" o process_bot_message REAL; a resposta nunca e enviada
# (o stub devolve None ao webhook, sem httpx).
BOT_MODE = {"mode": None}
DEPARTMENTS = [{"id": 2, "name": "Recepcao", "bot_key": "atendimento", "is_active": 1},
               {"id": 1, "name": "Comercial", "bot_key": "comercial", "is_active": 1}]
AI_CFG = {"bot_engine": "dialogflow_cx", "status": "active", "gcp_project_id": "proj-sim",
          "agent_id": "agent-sim", "handoff_bot_key": "atendimento",
          "lgpd_policy_version": "varizemed-2026-10"}
CX_SCRIPT = []   # respostas roteirizadas do conector (FIFO)
CX_CALLS = []    # textos enviados ao "agente"
CX_PARAMS = []   # session params de cada chamada ao "agente"
HANDOFF_REPLY = {"ok": True, "reply_text": "Vou te encaminhar para a recepção.", "handoff_request": True,
                 "handoff_summary": "Quer agendar consulta", "conversation_complete": False,
                 "user_name": "", "parameters": {"wants_appointment": True}}
# Demais caminhos de handoff do CX: frase de transferencia sem o parametro,
# frase de erro embutida do agente e motor fora do ar (timeout/5xx).
TEXT_HANDOFF_REPLY = dict(HANDOFF_REPLY, handoff_request=False,
                          reply_text="Certo! Estou transferindo nossa conversa para a equipe de atendimento.")
ERROR_REPLY = {"ok": True, "reply_text": "Desculpe, algo deu errado.", "handoff_request": False,
               "handoff_summary": "", "conversation_complete": False, "user_name": "", "parameters": {}}
DOWN_REPLY = {"ok": False, "reply_text": "", "handoff_request": False, "handoff_summary": "",
              "conversation_complete": False, "user_name": "", "parameters": {}}
NOTES = {}        # fotos intermediarias dos caminhos (ex.: depois da 1a falha do motor)
BUFFER_SENT = []  # respostas do bot enviadas pelo turno do buffer (envio trocado)


async def _fake_detect_intent(cfg, session_id, text, session_params=None, timeout_s=None):
    CX_CALLS.append(text)
    CX_PARAMS.append(copy.deepcopy(session_params or {}))
    if CX_SCRIPT:
        return copy.deepcopy(CX_SCRIPT.pop(0))
    return {"ok": True, "reply_text": "Certo, me conte mais.", "handoff_request": False,
            "handoff_summary": "", "conversation_complete": False, "user_name": "", "parameters": {}}


async def _fake_bot_turn(**kwargs):
    BOT_CALLS.append((kwargs.get("contact_id"), kwargs.get("text")))
    if BOT_MODE["mode"] == "cx":
        await bot_service._process_cx_message(kwargs["contact_id"], kwargs["text"],
                                              copy.deepcopy(BOT_MODE.get("ai") or AI_CFG))
    elif BOT_MODE["mode"] == "builtin":
        bot_service.process_bot_message(kwargs["contact_id"], kwargs["text"])
    return None


async def _fake_download(*_a, **_k):
    return None


def _clock():
    return CLOCK["now"] or datetime.now(timezone.utc)


def _seq(*_a, **_k):
    _SEQ["n"] += 1
    return _SEQ["n"]


def install():
    dbf.document = lambda coll, doc_id: _DocRef(_space(coll), doc_id)
    dbf.collection = lambda coll: _CollRef(_space(coll))
    dbf.next_sequence = _seq
    dbf.utcnow = _clock
    dbf.get_firestore_client = lambda: _BatchOnlyClient()
    firestore_common.get_firestore_client = _no_client
    firestore_common.document = dbf.document
    firestore_common.collection = dbf.collection
    # Tenant EXPLICITO (Activity das automacoes): espaco do tenant pedido,
    # nunca o do contexto.
    firestore_common.tenant_document = lambda tid, coll, doc_id: _DocRef((str(tid), coll), doc_id)
    firestore_common.tenant_collection = lambda tid, coll: _CollRef((str(tid), coll))
    # bot_service importou document/collection/utcnow do firestore_common
    # real; get_wa_contact/save_wa_message ja sao as funcoes do dbf.
    bot_service.document = dbf.document
    bot_service.collection = dbf.collection
    bot_service.utcnow = _clock
    bot_service.get_system_settings = lambda: {"bot_enabled": True}
    bot_service.get_all_departments = lambda: copy.deepcopy(DEPARTMENTS)
    bot_service.log_audit = lambda *a, **k: None
    database.set_attendance_department = lambda *a, **k: None
    bot_engine_dialogflow.detect_intent_text = _fake_detect_intent
    dbf.ensure_daily_attendance = lambda *a, **k: None
    dbf.get_current_protocol_id = lambda *a, **k: None
    dbf.increment_audit_metrics = lambda *a, **k: None
    dbf.increment_usage_metrics = lambda *a, **k: None
    dbf.log_audit = lambda *a, **k: None
    database.is_reception_mode = lambda: False
    channel_service.get_channel = lambda cid: copy.deepcopy(CHANNELS.get(int(cid))) if cid is not None else None
    channel_service.refresh_channels = lambda: None
    channel_service.get_channel_by_phone_id_from_db = lambda pid: None
    tenant_service.get_tenant = _fake_get_tenant_funnel
    rbac._read_perfil_doc = lambda tenant_id, perfil_id: None  # fallback da role
    webhook.get_tenant = _fake_get_tenant_webhook
    webhook.document = dbf.document
    webhook.log_audit = lambda *a, **k: None
    webhook.download_media = _fake_download
    webhook.is_reception_mode = lambda: False
    webhook._buffered_bot_turn = _fake_bot_turn
    webhook.enqueue_pending_event = lambda **kw: PENDING.append(kw)
    webhook.get_channel_by_phone_id = lambda pid: copy.deepcopy(CHANNELS_BY_PNID.get(str(pid)))
    webhook.lookup_phone_routing = lambda pid: (
        {"tenant_id": CHANNELS_BY_PNID[pid]["tenant_id"]}
        if CHANNELS_BY_PNID.get(pid, {}).get("tenant_id") else None)


def reset(feature=True, funnel=FUNNEL, other_funnel=None):
    STORE.clear()
    WRITES.clear()
    OPS.clear()
    READS.clear()
    READ_FAILS.clear()
    WRITE_FAILS.clear()
    BOT_CALLS.clear()
    PENDING.clear()
    BOT_MODE["mode"] = None
    BOT_MODE["ai"] = None
    CX_SCRIPT.clear()
    CX_CALLS.clear()
    CX_PARAMS.clear()
    NOTES.clear()
    BUFFER_SENT.clear()
    bot_service.invalidate_dept_cache()
    LOOKUPS.update(funnel=0, webhook=0, other=0)
    GET_TENANT_FAILS["on"] = False
    CLOCK["now"] = None
    config.FEATURE_FUNNEL = feature
    webhook.intake_catalog_for_channel = _REAL_INTAKE_CATALOG
    TENANT_DOCS.clear()
    TENANT_DOCS[TENANT] = {"id": TENANT, "settings": {"ai": {}}}
    TENANT_DOCS[OTHER] = {"id": OTHER, "settings": {"ai": {}}}
    if funnel:
        TENANT_DOCS[TENANT]["settings"]["funnel"] = copy.deepcopy(funnel)
    if other_funnel:
        TENANT_DOCS[OTHER]["settings"]["funnel"] = copy.deepcopy(other_funnel)
    dbf.invalidate_caches()
    rbac.invalidate_perfil_cache()
    for tid in (TENANT, OTHER, ""):
        STORE[(tid, "users")] = copy.deepcopy(USERS)


# =========================================================================
# Helpers
# =========================================================================

NOW = datetime.now(timezone.utc).replace(microsecond=0)


def unix(dt):
    return str(int(dt.timestamp()))


def seed_contact(cid, wa, tenant=TENANT, **fields):
    doc = {
        "id": cid, "wa_id": wa, "display_name": "Paciente", "declared_name": "",
        "whatsapp_profile_name": "Paciente", "phone_formatted": dbf.format_phone_br(wa),
        "created_source": "webhook", "qualification": "em_atendimento", "notes": "",
        "assigned_to": None, "assigned_to_uid": "", "department_id": None,
        "channel_id": 4, "phone_number_id": "PNID4", "source_channel_type": "standard",
        "is_archived": 0, "is_backup": False, "unread_count": 0,
        "first_seen_at": NOW - timedelta(days=200),
        "last_message_at": NOW - timedelta(days=30),
        "last_inbound_at": NOW - timedelta(days=30),
    }
    doc.update(fields)
    STORE.setdefault((tenant, "wa_contacts"), {})[str(cid)] = doc
    STORE.setdefault((tenant, "wa_contact_index"), {})[wa] = {"contact_id": cid}
    return doc


def contact(cid, tenant=TENANT):
    return STORE.get((tenant, "wa_contacts"), {}).get(str(cid))


def contact_by_wa(wa, tenant=TENANT):
    for d in STORE.get((tenant, "wa_contacts"), {}).values():
        if d.get("wa_id") == wa:
            return d
    return None


def crm(doc):
    return {k: v for k, v in (doc or {}).items() if k.startswith("crm_")}


def contact_writes(cid, tenant=TENANT):
    return [(data, merge) for (t, coll, did, data, merge) in WRITES
            if t == tenant and coll == "wa_contacts" and did == str(cid)]


def writes_in(coll, tenant=TENANT):
    return [w for w in WRITES if w[0] == tenant and w[1] == coll]


def messages_of(cid, tenant=TENANT):
    return [m for m in STORE.get((tenant, "wa_messages"), {}).values() if m.get("contact_id") == cid]


def text_msg(wa, mid, at, body="Oi, quero marcar uma consulta"):
    return {"from": wa, "id": mid, "type": "text", "timestamp": unix(at), "text": {"body": body}}


def value_for(messages, channel, name="Paciente"):
    return {
        "messaging_product": "whatsapp",
        "metadata": {"display_phone_number": channel["display_phone_number"],
                     "phone_number_id": channel["phone_number_id"]},
        "contacts": [{"profile": {"name": name}, "wa_id": (messages[0] or {}).get("from", "")}],
        "messages": messages,
    }


def deliver(messages, channel=STD_CH, tenant=TENANT, name="Paciente"):
    token = firestore_common.set_tenant_context(tenant)
    try:
        asyncio.run(webhook._process_messages(value_for(messages, channel, name), None,
                                              channel=copy.deepcopy(channel)))
    finally:
        firestore_common.reset_tenant_context(token)


def deliver_payload(values):
    """Pipeline inteiro: tenant resolvido pelo phone_number_id da 1a entry."""
    payload = {"object": "whatsapp_business_account",
               "entry": [{"id": "waba", "changes": [{"field": "messages", "value": v}]} for v in values]}
    asyncio.run(webhook.process_webhook_payload(payload))


def in_tenant(fn, tenant=TENANT):
    token = firestore_common.set_tenant_context(tenant)
    try:
        return fn()
    finally:
        firestore_common.reset_tenant_context(token)


def catalog(cfg=FUNNEL):
    return fc.resolve_funnel(copy.deepcopy(cfg))


def is_aware_dt(v):
    return isinstance(v, datetime) and v.tzinfo is not None and v.utcoffset() is not None


# Campos que toda automacao grava (entrada/coorte so quando ausentes).
AUTO_FIELDS = {fc.F_STAGE, fc.F_VERSION, fc.F_CHANGED_AT, fc.F_SOURCE, fc.F_ACTIVITY,
               fc.F_BY_USER, fc.F_BY_UID, fc.F_MAX_ORDER}
# Shape da Activity das automacoes (secao 1 do contrato do funil).
ACTIVITY_KEYS = {"id", "tenant_id", "contact_id", "task_id", "conversation_id", "event_type",
                 "actor_type", "actor_user_id", "actor_uid", "occurred_at", "recorded_at",
                 "operation_id", "from_stage", "to_stage", "stage_reason", "from_reason",
                 "entry_kind", "data"}
_CLINIC_STAGES = {s["key"]: s for s in fc.TEMPLATES["clinic_v1"]["stages"]}


def auto_id(event, cid, from_version, tenant=TENANT):
    """Id esperado da Activity de automacao: deterministico por tenant,
    contato e versao de ORIGEM (reentrega cai no mesmo doc; o evento NAO
    entra: handoff e 1a resposta da mesma versao = 1 Activity)."""
    key = "\x1f".join((tenant, "auto", str(cid), str(from_version)))
    return "stage_auto_" + hashlib.sha256(key.encode("utf-8")).hexdigest()


def seed_stage(cid, wa, stage, version=1, tenant=TENANT, **fields):
    """Contato ja no funil (como a entrada automatica deixaria)."""
    entered = NOW - timedelta(days=3)
    doc = seed_contact(cid, wa, tenant=tenant, **fields)
    sdef = _CLINIC_STAGES.get(stage) or {}
    doc.update({fc.F_STAGE: stage, fc.F_VERSION: version, fc.F_CHANGED_AT: entered,
                fc.F_SOURCE: "intake", fc.F_ACTIVITY: None, fc.F_BY_USER: None, fc.F_BY_UID: "",
                fc.F_ENTERED_AT: entered, fc.F_COHORT: fc.cohort_month(entered),
                fc.F_MAX_ORDER: sdef.get("order", 0) if sdef.get("kind") in fc.PIPELINE_KINDS else 0})
    return doc


def activities(tenant=TENANT):
    return STORE.get((tenant, "crm_activities"), {})


def activities_of(cid, tenant=TENANT):
    return [a for a in activities(tenant).values() if a.get("contact_id") == cid]


class captured:
    """Coleta os WARNING de um logger durante o bloco."""

    def __init__(self, name):
        self.name = name
        self.records = []
        sink = self.records

        class _Handler(logging.Handler):
            def emit(self, record):
                sink.append(record)

        self.handler = _Handler(level=logging.WARNING)

    def __enter__(self):
        logging.getLogger(self.name).addHandler(self.handler)
        return self.records

    def __exit__(self, *_exc):
        logging.getLogger(self.name).removeHandler(self.handler)
        return False


def warnings_of(records):
    return [r.getMessage() for r in records if r.levelno == logging.WARNING]


def no_pii(text, wa, name="Paciente"):
    return not any(p in text for p in (wa, dbf.format_phone_br(wa), name))


def human_send(cid, wa, *, at=None, tenant=TENANT, **kw):
    """save_wa_message REAL como um endpoint de envio humano o chama."""
    args = dict(wa_message_id="", contact_id=cid, direction="outbound", msg_type="text",
                content="Olá! Aqui é a recepção.", status="sent",
                timestamp_wa=(at or NOW).isoformat(), operator_id=4, channel_id=4,
                conversation_id="4__%s" % wa, sender_user_id=4, sent_by_name="Operadora")
    args.update(kw)
    return in_tenant(lambda: dbf.save_wa_message(**args), tenant)


def cx_handoff(cid, **kw):
    """_finalize_cx_handoff REAL com o contato lido como o turno CX le."""
    def _run():
        current = kw.pop("contact", None) or bot_service.get_wa_contact(cid)
        bot_service._finalize_cx_handoff(cid, copy.deepcopy(AI_CFG), summary="Quer agendar",
                                         contact=current, **kw)
    return in_tenant(_run)


def try_call(fn):
    """Nome da excecao que escapou de fn() (None = nenhuma)."""
    try:
        fn()
        return None
    except Exception as exc:  # noqa: BLE001 - o sim registra em vez de abortar
        return type(exc).__name__


# =========================================================================
# Cenarios
# =========================================================================

def cenario_00_ambiente():
    titulo("0. Ambiente: catalogo clinic_v1 e flag global")
    reset()
    check(fc.validate_template("clinic_v1", fc.TEMPLATES["clinic_v1"]) == [], "template clinic_v1 valido")
    check(fc.load_tenant_funnel(TENANT) is not None, "tenant com settings.funnel habilitado resolve o catalogo")
    check(fc.load_tenant_funnel(OTHER) is None, "tenant sem settings.funnel: funil desligado")
    config.FEATURE_FUNNEL = False
    check(fc.load_tenant_funnel(TENANT) is None, "FEATURE_FUNNEL=false: catalogo None mesmo com tenant habilitado")
    config.FEATURE_FUNNEL = True
    check(webhook._FUNNEL_INTAKE_SKIP_TYPES == frozenset({"reaction", "system", "unknown"}),
          "tipos fora da entrada: reacao, sistema, desconhecido (request_welcome, unsupported e ephemeral entram)")
    autos = catalog().get("automations") or {}
    check(all(autos.get(ev) == {"from": ["new", "unclassified"], "to": "in_service"}
              for ev in (fc.AUTO_HANDOFF, fc.AUTO_HUMAN_REPLY)) and set(autos) == set(fc.AUTO_EVENTS),
          "clinic_v1: handoff e 1a resposta humana levam Novo contato / A classificar para Em atendimento")


def cenario_01_flag_desligada():
    titulo("1. FEATURE_FUNNEL=false: nenhum campo crm_* em nenhum caminho")
    reset(feature=False)
    wa_new = "5531911110001"
    deliver([text_msg(wa_new, "w.01a", NOW - timedelta(minutes=2))])
    c = contact_by_wa(wa_new)
    check(c is not None and not crm(c), "inbound ao vivo de contato novo: sem crm_*")
    seed_contact(101, "5531911110002")
    deliver([text_msg("5531911110002", "w.01b", NOW - timedelta(minutes=1))])
    check(not crm(contact(101)), "inbound ao vivo de contato existente: sem crm_*")
    cid, err = in_tenant(lambda: dbf.create_manual_wa_contact(
        "Paciente Manual", "5531911110003", 4, 4, funnel_intake=fc.load_tenant_funnel(TENANT)))
    check(err is None and not crm(contact(cid)), "criacao manual: sem crm_*")
    seed_contact(102, "5531911110004", is_backup=True, assigned_to_uid=dbf.BACKUP_ASSIGNED_UID,
                 last_inbound_at=None)
    in_tenant(lambda: dbf.assign_wa_contact(102, 4, 2, transferred_by=7))
    check(not crm(contact(102)) and contact(102).get("is_backup") is False,
          "graduacao de backup: gradua, mas sem crm_*")
    check(LOOKUPS["funnel"] == 0, "flag desligada: o funil nem le o doc do tenant")


def _payload_writes(feature, legacy=False):
    """Mesmo payload com o funil desligado/ligado: (n writes no contato, n
    writes no total, chaves do 1o write do contato)."""
    reset(feature=feature)
    wa = "5531911110011"
    if legacy:
        seed_contact(111, wa)
    deliver([text_msg(wa, "w.02x", NOW - timedelta(minutes=3))])
    cid = contact_by_wa(wa)["id"]
    ws = contact_writes(cid)
    return len(ws), len(WRITES), set(ws[0][0]) if ws else set()


def cenario_02_contato_novo():
    titulo("2. Inbound ao vivo de contato NOVO -> Novo contato, hora real da mensagem")
    for legacy, label in ((False, "contato novo"), (True, "contato antigo")):
        n_off, total_off, keys_off = _payload_writes(False, legacy)
        n_on, total_on, keys_on = _payload_writes(True, legacy)
        check(n_on == n_off and total_on == total_off,
              f"{label}: zero escrita extra ({n_on} writes no contato, {total_on} no total, com e sem funil)")
        check(keys_on - keys_off == set(fc.CONTACT_STAGE_FIELDS) and not keys_off - keys_on,
              f"{label}: o funil so ACRESCENTA as chaves crm_* ao write que ja existia")

    reset()
    wa = "5531911110012"
    t_msg = NOW - timedelta(minutes=3)
    deliver([text_msg(wa, "w.02a", t_msg)])
    c = contact_by_wa(wa)
    cid = c["id"]
    check(c.get(fc.F_STAGE) == "new", "crm_stage = new")
    check(c.get(fc.F_VERSION) == 1, "crm_stage_version = 1")
    check(c.get(fc.F_SOURCE) == "intake", "crm_stage_source = intake")
    check(fc.F_ACTIVITY in c and c.get(fc.F_ACTIVITY) is None, "crm_stage_activity_id = None (sem Activity no caminho quente)")
    check(c.get(fc.F_BY_USER) is None and c.get(fc.F_BY_UID) == "", "sem autor humano (entrada automatica)")
    check(c.get(fc.F_ENTERED_AT) == t_msg, "crm_funnel_entered_at = hora REAL da mensagem (nao a do processamento)")
    check(c.get(fc.F_COHORT) == fc.cohort_month(t_msg), "crm_cohort_month = mes BR da mensagem")
    check(c.get(fc.F_MAX_ORDER) == 10, "crm_max_reached_order = ordem de Novo contato (10)")
    check(is_aware_dt(c.get(fc.F_CHANGED_AT)) and c.get(fc.F_CHANGED_AT) == c.get("last_inbound_at"),
          "crm_stage_changed_at = instante deste write (o mesmo de last_inbound_at)")
    ws = contact_writes(cid)
    check(ws and ws[0][1] is False and all(k in ws[0][0] for k in fc.CONTACT_STAGE_FIELDS),
          "todos os campos da etapa no write de CRIACAO do contato")
    check(all(not crm(d) for d, _m in ws[1:]), "nenhum write posterior do payload toca crm_*")
    check(len(messages_of(cid)) == 1 and BOT_CALLS == [(cid, "Oi, quero marcar uma consulta")],
          "mensagem persistida e o bot segue sendo chamado")
    check(LOOKUPS["funnel"] == 1, "habilitacao lida 1x no payload")

    titulo("2b. Payload com 3 mensagens de 2 remetentes: catalogo 1x por payload")
    reset()
    wa_a, wa_b = "5531911110013", "5531911110014"
    t_a1, t_a2, t_b = NOW - timedelta(minutes=9), NOW - timedelta(minutes=8), NOW - timedelta(minutes=7)
    deliver([text_msg(wa_a, "w.02b1", t_a1), text_msg(wa_b, "w.02b2", t_b, "Bom dia"),
             text_msg(wa_a, "w.02b3", t_a2, "Ainda tem horario?")])
    ca, cb = contact_by_wa(wa_a), contact_by_wa(wa_b)
    check(LOOKUPS["funnel"] == 1, "3 mensagens -> 1 leitura de habilitacao (nunca por mensagem)")
    check(ca.get(fc.F_STAGE) == "new" and ca.get(fc.F_VERSION) == 1 and ca.get(fc.F_ENTERED_AT) == t_a1,
          "remetente A: entrada pela 1a mensagem; a 2a nao mexe (versao 1)")
    check(cb.get(fc.F_STAGE) == "new" and cb.get(fc.F_ENTERED_AT) == t_b, "remetente B: entrada com a hora dele")


def cenario_03_coorte_fuso():
    titulo("3. Coorte no fuso da clinica e data invalida")
    reset()
    wa = "5531911110021"
    t_msg = datetime(2026, 10, 1, 2, 0, tzinfo=timezone.utc)  # 30/09 23:00 em Sao Paulo
    deliver([text_msg(wa, "w.03a", t_msg)])
    c = contact_by_wa(wa)
    check(c.get(fc.F_ENTERED_AT) == t_msg, "entered_at = 2026-10-01T02:00Z (hora real)")
    check(c.get(fc.F_COHORT) == "2026-09", "coorte = 2026-09 (America/Sao_Paulo), nao 2026-10")
    wa2 = "5531911110022"
    before = datetime.now(timezone.utc)
    msg = text_msg(wa2, "w.03b", NOW)
    msg["timestamp"] = "nao-e-numero"
    deliver([msg])
    c2 = contact_by_wa(wa2)
    entered = c2.get(fc.F_ENTERED_AT)
    check(c2.get(fc.F_STAGE) == "new" and is_aware_dt(entered) and entered >= before - timedelta(seconds=1),
          "timestamp invalido: entrada com a hora do processamento (datetime, nunca string/None)")


def cenario_04_agenda_depois_ao_vivo():
    titulo("4. Contato da agenda (state_sync) sem conversa -> Novo contato na 1a mensagem")
    reset(funnel=FUNNEL_COEX)
    wa = "5531911110031"
    sync = {"state_sync": [{"type": "contact", "action": "add",
                            "contact": {"phone_number": wa, "full_name": "Paciente Agenda"}}]}
    in_tenant(lambda: webhook._process_smb_app_state_sync(sync, channel=copy.deepcopy(COEX_CH)))
    c = contact_by_wa(wa)
    check(c is not None and not crm(c) and c.get("last_inbound_at") is None,
          "agenda cria o contato sem crm_* (mesmo com coexistence elegivel)")
    n_before = len(WRITES)
    in_tenant(lambda: webhook._process_smb_app_state_sync(sync, channel=copy.deepcopy(COEX_CH)))
    check(len(WRITES) == n_before, "state_sync repetido com nada mudado: 0 writes (gate 'if updates')")
    t_msg = NOW - timedelta(minutes=4)
    deliver([text_msg(wa, "w.04a", t_msg)], channel=COEX_CH)
    c = contact_by_wa(wa)
    check(c.get(fc.F_STAGE) == "new" and c.get(fc.F_SOURCE) == "intake",
          "1a mensagem ao vivo do contato da agenda -> new")
    check(c.get(fc.F_ENTERED_AT) == t_msg and c.get(fc.F_ENTERED_AT) != c.get("first_seen_at"),
          "entered_at = hora da mensagem (nao o first_seen_at da agenda)")
    check(c.get("assigned_to") == 8, "posse coexistence preservada (dona do numero)")

    titulo("4b. Contato criado por eco (nunca escreveu) -> Novo contato no canal standard")
    reset()
    seed_contact(141, "5531911110032", last_inbound_at=None, created_source="webhook")
    deliver([text_msg("5531911110032", "w.04b", NOW - timedelta(minutes=1))])
    check(contact(141).get(fc.F_STAGE) == "new", "sem last_inbound_at anterior -> new")


def cenario_05_contato_antigo():
    titulo("5. Contato que JA conversava (last_inbound_at anterior) -> A classificar")
    reset()
    first_seen = datetime(2025, 11, 3, 13, 0, tzinfo=timezone.utc)
    seed_contact(151, "5531911110041", first_seen_at=first_seen.isoformat(),  # legado em string ISO
                 last_inbound_at=NOW - timedelta(days=40))
    t_proc = NOW + timedelta(seconds=1)
    CLOCK["now"] = t_proc
    t_msg = NOW - timedelta(seconds=2)
    deliver([text_msg("5531911110041", "w.05a", t_msg)])
    c = contact(151)
    check(c.get(fc.F_STAGE) == "unclassified" and c.get(fc.F_VERSION) == 1 and c.get(fc.F_SOURCE) == "intake",
          "unclassified, versao 1, source intake")
    check(c.get(fc.F_ENTERED_AT) == first_seen and isinstance(c.get(fc.F_ENTERED_AT), datetime),
          "entered_at = first_seen_at (string ISO coerida para datetime)")
    check(c.get(fc.F_COHORT) == "2025-11", "coorte do first_seen_at (paciente antigo nao conta no mes)")
    check(c.get(fc.F_MAX_ORDER) == 0, "triagem nao conta na maior etapa alcancada")
    check(c.get(fc.F_CHANGED_AT) == t_proc and c.get("last_inbound_at") == t_proc,
          "changed_at = last_inbound_at = instante do write")
    ws = contact_writes(151)
    check(len([d for d, _m in ws if crm(d)]) == 1 and "last_inbound_at" in [d for d, _m in ws if crm(d)][0],
          "etapa no MESMO write que ja grava last_inbound_at")
    cat = catalog()
    sig = fc.derived_signals(cat, c, t_proc + timedelta(minutes=1))
    check(sig["new_activity"] is False,
          "selo 'mensagem nova' NAO acende com a propria mensagem que trouxe o contato")
    first = copy.deepcopy(crm(c))
    CLOCK["now"] = t_proc + timedelta(minutes=5)
    deliver([text_msg("5531911110041", "w.05b", NOW + timedelta(minutes=5), "Voltei")])
    c = contact(151)
    check(crm(c) == first, "mensagem seguinte nao muda a etapa (nem versao, datas ou coorte)")
    sig = fc.derived_signals(cat, c, t_proc + timedelta(minutes=6))
    check(sig["new_activity"] is True, "mensagem POSTERIOR acende o selo 'mensagem nova'")

    titulo("5b. Antigo sem first_seen_at -> entered_at = hora da mensagem")
    reset()
    seed_contact(152, "5531911110042", first_seen_at=None, last_inbound_at=NOW - timedelta(days=3))
    t_msg = NOW - timedelta(seconds=30)
    deliver([text_msg("5531911110042", "w.05c", t_msg)])
    c = contact(152)
    check(c.get(fc.F_STAGE) == "unclassified" and c.get(fc.F_ENTERED_AT) == t_msg,
          "fallback do entered_at = hora real da mensagem")

    titulo("5c. Variante do nono digito: migracao do wa_id e etapa no mesmo write")
    reset()
    seed_contact(153, "553181110043", last_inbound_at=NOW - timedelta(days=5))  # 12 digitos (sem 9)
    deliver([text_msg("5531981110043", "w.05d", NOW - timedelta(seconds=10))])
    c = contact(153)
    ws = [d for d, _m in contact_writes(153) if crm(d)]
    check(c.get(fc.F_STAGE) == "unclassified" and c.get("wa_id") == "5531981110043",
          "achado pela variante: unclassified e wa_id canonizado")
    check(len(ws) == 1 and ws[0].get("wa_id") == "5531981110043", "um write so (wa_id + etapa)")


def cenario_06_etapa_existente():
    titulo("6. Contato COM etapa: nunca sobrescrito")
    reset()
    stage = {fc.F_STAGE: "scheduled", fc.F_VERSION: 3, fc.F_CHANGED_AT: NOW - timedelta(days=2),
             fc.F_SOURCE: "user", fc.F_ACTIVITY: "stage_abc", fc.F_BY_USER: 7, fc.F_BY_UID: "uid-7",
             fc.F_ENTERED_AT: NOW - timedelta(days=20), fc.F_COHORT: "2026-10", fc.F_MAX_ORDER: 40}
    seed_contact(161, "5531911110051", **stage)
    seed_contact(162, "5531911110052", last_inbound_at=None,
                 **dict(stage, **{fc.F_STAGE: "zz_retired", fc.F_VERSION: 1}))
    deliver([text_msg("5531911110051", "w.06a", NOW - timedelta(seconds=5))])
    deliver([text_msg("5531911110052", "w.06b", NOW - timedelta(seconds=4))])
    check(crm(contact(161)) == stage, "etapa manual (scheduled v3) intacta apos mensagem ao vivo")
    check(contact(162).get(fc.F_STAGE) == "zz_retired" and contact(162).get(fc.F_VERSION) == 1,
          "etapa fora do catalogo atual tambem nunca e sobrescrita")
    check(all(not crm(d) for d, _m in contact_writes(161) + contact_writes(162)), "nenhum write com crm_*")


def cenario_07_eco_agenda_history():
    titulo("7. Eco, agenda e history: nada (mesmo com coexistence elegivel)")
    reset(funnel=FUNNEL_COEX)
    cat = fc.load_tenant_funnel(TENANT)
    echo = {"message_echoes": [{"from": BUSINESS_COEX, "to": "5531911110061", "id": "w.07e1",
                                "type": "text", "timestamp": unix(NOW), "text": {"body": "oi"}}],
            "metadata": {"display_phone_number": BUSINESS_COEX, "phone_number_id": "PNID8"}}
    in_tenant(lambda: asyncio.run(webhook._process_smb_message_echoes(echo, channel=copy.deepcopy(COEX_CH))))
    c = contact_by_wa("5531911110061")
    check(c is not None and not crm(c), "eco cria contato sem crm_*")
    seed_contact(171, "5531911110062", last_inbound_at=None, channel_id=8, source_channel_type="coexistence")
    echo2 = copy.deepcopy(echo)
    echo2["message_echoes"][0].update(to="5531911110062", id="w.07e2")
    in_tenant(lambda: asyncio.run(webhook._process_smb_message_echoes(echo2, channel=copy.deepcopy(COEX_CH))))
    check(not crm(contact(171)), "eco em contato existente sem etapa: sem crm_*")
    hist = {"metadata": {"display_phone_number": BUSINESS_COEX, "phone_number_id": "PNID8"},
            "history": [{"metadata": {"phase": 0, "chunk_order": 1, "progress": 100},
                         "threads": [{"id": "5531911110063", "messages": [
                             {"from": "5531911110063", "id": "w.07h1", "type": "text",
                              "timestamp": unix(NOW - timedelta(hours=2)), "text": {"body": "x"},
                              "history_context": {"status": "read"}}]}]}]}
    in_tenant(lambda: asyncio.run(webhook._process_history(hist, channel=copy.deepcopy(COEX_CH))))
    c = contact_by_wa("5531911110063")
    check(c is not None and not crm(c), "history cria contato sem crm_* (inbound real de 2h, mas importado)")
    check(c is not None and c.get("last_inbound_at") is not None, "history ainda abre a janela de 24h (sem regressao)")

    titulo("7b. Gate do upsert_wa_contact com o catalogo passado (defesa em profundidade)")
    for label, kwargs in (("eco (inbound_event=False)", {"inbound_event": False}),
                          ("agenda/history (from_message_event=False)", {"from_message_event": False}),
                          ("clique de controle (control_click=True)", {"control_click": True})):
        reset(funnel=FUNNEL_COEX)
        seed_contact(172, "5531911110064", last_inbound_at=None)
        new_id = in_tenant(lambda: dbf.upsert_wa_contact(
            "5531911110065", "Novo", channel_id=4, phone_number_id="PNID4", source_channel_type="standard",
            skip_conversation_upsert=True, funnel_intake=cat, funnel_intake_at=NOW, **kwargs))
        in_tenant(lambda: dbf.upsert_wa_contact(
            "5531911110064", "Paciente", channel_id=4, phone_number_id="PNID4", source_channel_type="standard",
            skip_conversation_upsert=True, funnel_intake=cat, funnel_intake_at=NOW, **kwargs))
        check(not crm(contact(new_id)) and not crm(contact(172)), f"{label}: contato novo e existente sem crm_*")

    titulo("7c. state_sync repetido com o catalogo passado: continua 0 writes")
    reset(funnel=FUNNEL_COEX)
    seed_contact(173, "5531911110066", whatsapp_profile_name="Agenda", display_name="Agenda")
    n_before = len(WRITES)
    in_tenant(lambda: dbf.upsert_wa_contact(
        "5531911110066", "Agenda", channel_id=4, phone_number_id="PNID4", source_channel_type="standard",
        from_message_event=False, funnel_intake=cat, funnel_intake_at=NOW))
    check(len(WRITES) == n_before and not crm(contact(173)),
          "contato antigo sem etapa + agenda sem mudanca: 0 writes, sem crm_*")


def cenario_08_clique_controle():
    titulo("8. Clique de avaliacao (controle): nunca coloca no funil")
    reset()
    seed_contact(181, "5531911110071", rating_requested_at=(NOW - timedelta(hours=1)).isoformat(),
                 last_inbound_at=NOW - timedelta(hours=2), assigned_to=4, assigned_to_uid="uid-4")
    click = {"from": "5531911110071", "id": "w.08a", "type": "interactive", "timestamp": unix(NOW),
             "interactive": {"type": "button_reply", "button_reply": {"id": "rating_bom", "title": "Bom"}}}
    deliver([click])
    c = contact(181)
    check(not crm(c), "clique valido: sem crm_*")
    check(c.get("rating") == 2, "a avaliacao continua sendo registrada (fluxo intacto)")
    seed_contact(182, "5531911110072", last_inbound_at=None)
    click2 = dict(click, **{"from": "5531911110072", "id": "w.08b"})
    deliver([click2])
    check(not crm(contact(182)), "clique sem pedido pendente (forma de controle): sem crm_*")
    seed_contact(183, "5531911110073", rating_requested_at=(NOW - timedelta(hours=1)).isoformat())
    btn = {"from": "5531911110073", "id": "w.08c", "type": "button", "timestamp": unix(NOW),
           "button": {"payload": "Bom", "text": "Bom"}}
    deliver([btn])
    check(not crm(contact(183)), "botao de template de avaliacao: sem crm_*")


def cenario_09_backup_lgpd():
    titulo("9. Backup e revogacao LGPD: nada")
    reset()
    seed_contact(191, "5531911110081", is_backup=True, assigned_to_uid=dbf.BACKUP_ASSIGNED_UID,
                 last_inbound_at=None, created_source="backup_import")
    seed_contact(192, "5531911110082", lgpd_revoked=True, last_inbound_at=None)
    deliver([text_msg("5531911110081", "w.09a", NOW - timedelta(seconds=3))])
    deliver([text_msg("5531911110082", "w.09b", NOW - timedelta(seconds=2))])
    check(not crm(contact(191)), "contato backup escreve ao vivo: sem crm_* (entra so ao ser graduado)")
    check(not crm(contact(192)), "contato com lgpd_revoked: sem crm_*")
    check(len(messages_of(191)) == 1 and len(messages_of(192)) == 1, "mensagens persistidas normalmente")


def cenario_10_canais():
    titulo("10. Canal coexistence fora de intake_channel_types (default standard): nada")
    reset()
    deliver([text_msg("5531911110091", "w.10a", NOW - timedelta(seconds=9))], channel=COEX_CH)
    c = contact_by_wa("5531911110091")
    check(c is not None and not crm(c) and c.get("assigned_to") == 8,
          "contato novo no coex: sem crm_*, posse da dona do numero preservada")
    seed_contact(1101, "5531911110092", last_inbound_at=None, channel_id=8, source_channel_type="coexistence",
                 assigned_to=8, assigned_to_uid="uid-8")
    deliver([text_msg("5531911110092", "w.10b", NOW - timedelta(seconds=8))], channel=COEX_CH)
    check(not crm(contact(1101)), "contato existente no coex: sem crm_*")

    titulo("10b. Canal de OUTRO tenant: nada")
    reset(other_funnel=FUNNEL)
    deliver([text_msg("5531911110093", "w.10c", NOW - timedelta(seconds=7))], channel=OTHER_CH)
    c = contact_by_wa("5531911110093")
    check(c is not None and not crm(c), "canal hubloc sob contexto varizemed: sem crm_* (tenant do canal != contexto)")
    reset(other_funnel=FUNNEL)
    deliver_payload([value_for([text_msg("5531911110094", "w.10d", NOW - timedelta(seconds=6))], STD_CH),
                     value_for([text_msg("5531911110095", "w.10e", NOW - timedelta(seconds=5))], OTHER_CH)])
    ca, cb = contact_by_wa("5531911110094"), contact_by_wa("5531911110095")
    check(not PENDING, "pipeline completo sem excecao (nada em pending)")
    check(ca is not None and ca.get(fc.F_STAGE) == "new", "1a entry (canal do tenant do contexto): new")
    check(cb is not None and not crm(cb), "2a entry (canal de outro tenant no mesmo payload): sem crm_*")
    reset()
    deliver([text_msg("5531911110096", "w.10f", NOW - timedelta(seconds=4))], channel=OTHER_CH, tenant=OTHER)
    c = contact_by_wa("5531911110096", tenant=OTHER)
    check(c is not None and not crm(c), "tenant sem settings.funnel: sem crm_*")
    reset()
    deliver([text_msg("5531911110097", "w.10g", NOW - timedelta(seconds=3))], channel=LEGACY_CH)
    c = contact_by_wa("5531911110097")
    check(c is not None and c.get(fc.F_STAGE) == "new", "canal legado sem tenant_id segue o tenant do contexto")


def typed_msg(wa, mtype, mid, at):
    msg = {"from": wa, "id": mid, "type": mtype, "timestamp": unix(at)}
    if mtype == "reaction":
        msg["reaction"] = {"message_id": "w.x", "emoji": "\U0001F44D"}
    elif mtype == "system":
        msg["system"] = {"body": "Cliente mudou de numero", "type": "user_changed_number"}
    elif mtype == "unsupported":
        # Midia de visualizacao unica: a Cloud API entrega como unsupported.
        msg["errors"] = [{"code": 131051, "title": "Message type unknown"}]
        msg["unsupported"] = {"type": "view_once"}
    return msg


def cenario_11_tipos():
    titulo("11. unsupported/ephemeral e request_welcome ENTRAM; reacao/sistema/desconhecido nao")
    # request_welcome (o cliente abriu o chat pela 1a vez) conta como entrada
    # em Novo contato desde a decisao do PO de 28/10/2026.
    for i, mtype in enumerate(("unsupported", "ephemeral", "request_welcome")):
        reset()
        wa = "55319111101%02d" % i
        t_msg = NOW - timedelta(seconds=30)
        deliver([typed_msg(wa, mtype, "w.11.%s" % mtype, t_msg)])
        c = contact_by_wa(wa)
        check(c is not None and c.get(fc.F_STAGE) == "new" and c.get(fc.F_VERSION) == 1
              and c.get(fc.F_SOURCE) == "intake" and c.get(fc.F_ENTERED_AT) == t_msg
              and c.get(fc.F_MAX_ORDER) == 10 and len(messages_of(c["id"])) == 1,
              f"{mtype} como 1a mensagem de contato novo: Novo contato (hora real, max_order 10), mensagem gravada")
        first = copy.deepcopy(crm(c))
        deliver([text_msg(wa, "w.11.%s.txt" % mtype, NOW - timedelta(seconds=5))])
        check(crm(contact_by_wa(wa)) == first,
              f"{mtype} e depois texto: segue Novo contato (o texto nao reclassifica para A classificar)")
    for i, mtype in enumerate(("reaction", "system", "unknown")):
        reset()
        wa = "55319111101%02d" % (i + 3)
        deliver([typed_msg(wa, mtype, "w.11.%s" % mtype, NOW)])
        c = contact_by_wa(wa)
        check(c is not None and not crm(c) and len(messages_of(c["id"])) == 1,
              f"{mtype}: contato e mensagem gravados, sem crm_*")

    titulo("11b. Residuo ACEITO: reacao como 1a mensagem e depois texto -> A classificar")
    # Decisao do orquestrador (sem campo novo; docs/funil_crm_varizemed.md
    # secao 2): a reacao nao poe no funil, mas o upsert grava last_inbound_at
    # (janela de 24h da Meta), entao o 1o texto ve "ja conversava" e o contato
    # entra em A classificar (o controle, texto direto, da new no cenario 2).
    # Raro; a equipe move (ou a automacao do handoff/1a resposta leva a Em
    # atendimento). Se um dia existir marcador de inbound contavel, estes
    # asserts passam a esperar new.
    reset()
    wa = "5531911110106"
    deliver([typed_msg(wa, "reaction", "w.11b.r1", NOW - timedelta(seconds=40))])
    c = contact_by_wa(wa)
    check(c is not None and not crm(c) and c.get("last_inbound_at") is not None,
          "reacao cria o contato sem crm_*, mas com last_inbound_at (janela de 24h)")
    deliver([text_msg(wa, "w.11b.t1", NOW - timedelta(seconds=5))])
    c = contact_by_wa(wa)
    check(c.get(fc.F_STAGE) == "unclassified" and c.get(fc.F_MAX_ORDER) == 0 and c.get(fc.F_SOURCE) == "intake",
          "reacao e depois texto: A classificar, max_order 0 (residuo aceito e documentado)")
    # Caminho realista no canal standard: contato sem etapa e sem inbound
    # (agenda ou manual de antes da habilitacao) reage a um template e escreve.
    reset()
    seed_contact(1111, "5531911110108", last_inbound_at=None, last_message_at=None, qualification="novo",
                 first_seen_at=NOW - timedelta(days=3))
    deliver([typed_msg("5531911110108", "reaction", "w.11b.r2", NOW - timedelta(seconds=40))])
    deliver([text_msg("5531911110108", "w.11b.t2", NOW - timedelta(seconds=5))])
    check(contact(1111).get(fc.F_STAGE) == "unclassified",
          "contato sem conversa anterior reage a um template e escreve: A classificar (mesmo residuo)")
    # request_welcome NAO tem mais este residuo (decisao do PO, 28/10): abrir
    # o chat pela 1a vez ja e a entrada em Novo contato, entao o 1o texto
    # encontra a etapa e nao reclassifica. Se a mensagem de boas-vindas da
    # Meta for ligada no WABA, cada lead novo entra assim, em Novo contato.
    reset()
    wa = "5531911110107"
    t_welcome = NOW - timedelta(seconds=40)
    deliver([typed_msg(wa, "request_welcome", "w.11b.w1", t_welcome)])
    c = contact_by_wa(wa)
    check(c.get(fc.F_STAGE) == "new" and c.get(fc.F_ENTERED_AT) == t_welcome,
          "request_welcome sozinho: Novo contato com a hora da abertura do chat")
    deliver([text_msg(wa, "w.11b.t3", NOW - timedelta(seconds=5))])
    c = contact_by_wa(wa)
    check(c.get(fc.F_STAGE) == "new" and c.get(fc.F_VERSION) == 1 and c.get(fc.F_ENTERED_AT) == t_welcome,
          "request_welcome e depois texto: segue Novo contato (sem o residuo de A classificar)")


def cenario_12_falhas():
    titulo("12. get_tenant levantando excecao: mensagem segue, sem etapa")
    reset()
    GET_TENANT_FAILS["on"] = True
    wa = "5531911110121"
    deliver_payload([value_for([text_msg(wa, "w.12a", NOW - timedelta(seconds=5))], STD_CH)])
    c = contact_by_wa(wa)
    check(not PENDING, "nenhuma excecao chegou ao wrapper (nada em pending)")
    check(c is not None and not crm(c), "contato gravado sem crm_*")
    check(c is not None and len(messages_of(c["id"])) == 1 and len(BOT_CALLS) == 1,
          "mensagem persistida e bot chamado normalmente")

    titulo("12b. Falha no proprio bloco do funil do webhook: protegida")
    reset()

    def _boom(*_a, **_k):
        raise RuntimeError("falha simulada no catalogo")

    webhook.intake_catalog_for_channel = _boom
    wa = "5531911110122"
    try:
        deliver([text_msg(wa, "w.12b", NOW - timedelta(seconds=4))])
        raised = False
    except Exception:
        raised = True
    c = contact_by_wa(wa)
    check(not raised, "_process_messages nao propaga a falha")
    check(c is not None and not crm(c) and len(messages_of(c["id"])) == 1 and len(BOT_CALLS) == 1,
          "contato e mensagem gravados, bot chamado, sem crm_*")

    titulo("12c. Catalogo malformado: intake_fields engole, contato segue")
    reset()
    bad = {"stages": "lixo", "intake_channel_types": ["standard"]}
    seed_contact(1123, "5531911110124", last_inbound_at=None)
    try:
        new_id = in_tenant(lambda: dbf.upsert_wa_contact(
            "5531911110123", "Paciente", channel_id=4, phone_number_id="PNID4", source_channel_type="standard",
            skip_conversation_upsert=True, funnel_intake=bad, funnel_intake_at=NOW))
        in_tenant(lambda: dbf.upsert_wa_contact(
            "5531911110124", "Paciente", channel_id=4, phone_number_id="PNID4", source_channel_type="standard",
            skip_conversation_upsert=True, funnel_intake=bad, funnel_intake_at=NOW))
        raised = False
    except Exception:
        raised = True
        new_id = None
    check(not raised and new_id is not None, "upsert nao levanta com catalogo malformado")
    check(not crm(contact(new_id)) and not crm(contact(1123)), "sem crm_* (o script recupera depois)")
    check(contact(1123).get("last_inbound_at") is not None, "o write normal do contato existente aconteceu")


def cenario_13_reentrega():
    titulo("13. Reentrega do MESMO payload (retry da Meta): idempotente")
    reset()
    wa = "5531911110131"
    t_msg = NOW - timedelta(seconds=40)
    payload = [text_msg(wa, "w.13a", t_msg)]
    deliver(payload)
    c1 = copy.deepcopy(crm(contact_by_wa(wa)))
    WRITES.clear()
    deliver(payload)
    c = contact_by_wa(wa)
    check(c1.get(fc.F_STAGE) == "new" and crm(c) == c1, "2a passada nao muda etapa, versao, datas nem coorte")
    check(all(not crm(w[3]) for w in WRITES), "2a passada nao escreve nenhum campo crm_*")
    check(len(messages_of(c["id"])) == 1 and len(BOT_CALLS) == 1, "mensagem nao duplica e o bot nao roda 2x")
    seed_contact(1131, "5531911110132")
    payload2 = [text_msg("5531911110132", "w.13b", NOW - timedelta(seconds=30))]
    deliver(payload2)
    u1 = copy.deepcopy(crm(contact(1131)))
    WRITES.clear()
    deliver(payload2)
    check(u1.get(fc.F_STAGE) == "unclassified" and crm(contact(1131)) == u1
          and all(not crm(w[3]) for w in WRITES), "contato antigo: idem")

    titulo("13b. Reprocessamento silencioso de pending: entrada com a hora REAL")
    reset()
    wa = "5531911110133"
    t_old = NOW - timedelta(days=3)
    tok = webhook._silent_reprocess.set(True)
    try:
        deliver([text_msg(wa, "w.13c", t_old)])
    finally:
        webhook._silent_reprocess.reset(tok)
    c = contact_by_wa(wa)
    check(c.get(fc.F_STAGE) == "new" and c.get(fc.F_ENTERED_AT) == t_old and c.get(fc.F_COHORT) == fc.cohort_month(t_old),
          "entrada/coorte = data da mensagem antiga (nao conta como entrada de hoje)")
    check(not BOT_CALLS, "reprocessamento silencioso continua sem bot")

    titulo("13c. Corrida perdida no claim do indice: o vencedor recebe a entrada")
    reset()
    wa = "5531911110134"
    STORE[(TENANT, "wa_contacts")] = {"1134": {"id": 1134, "wa_id": "outro-formato", "is_backup": False,
                                               "first_seen_at": NOW, "last_inbound_at": None,
                                               "whatsapp_profile_name": "Paciente"}}
    STORE[(TENANT, "wa_contact_index")] = {wa: {"contact_id": 1134}}
    t_msg = NOW - timedelta(seconds=20)
    deliver([text_msg(wa, "w.13d", t_msg)])
    check(contact(1134).get(fc.F_STAGE) == "new" and contact(1134).get(fc.F_ENTERED_AT) == t_msg,
          "fallback _update_existing_wa_contact(vencedor) aplica a entrada")
    check(len(STORE[(TENANT, "wa_contacts")]) == 1, "nenhum contato duplicado")


def cenario_14_manual():
    titulo("14. Criacao manual pelo operador -> Em atendimento (a equipe iniciou a conversa)")
    reset()
    cat = fc.load_tenant_funnel(TENANT)
    before = datetime.now(timezone.utc) - timedelta(seconds=1)
    cid, err = in_tenant(lambda: dbf.create_manual_wa_contact(
        "Paciente Manual", "5531911110141", 4, 4, funnel_intake=cat))
    c = contact(cid)
    check(err is None and c.get(fc.F_STAGE) == "in_service" and c.get(fc.F_VERSION) == 1
          and c.get(fc.F_SOURCE) == "intake" and c.get(fc.F_MAX_ORDER) == 20,
          "contato novo -> in_service, versao 1, max_order 20 (decisao do PO, 28/10)")
    check(c.get(fc.F_BY_USER) == 4 and c.get(fc.F_BY_UID) == "uid-4", "changed_by = operador que criou")
    check(is_aware_dt(c.get(fc.F_ENTERED_AT)) and c.get(fc.F_ENTERED_AT) >= before
          and c.get(fc.F_COHORT) == fc.cohort_month(c.get(fc.F_ENTERED_AT)), "entrada agora, coorte do mes")
    ws = contact_writes(cid)
    check(ws and ws[0][1] is False and crm(ws[0][0]), "etapa no write de criacao")
    check(not writes_in("crm_activities") and c.get(fc.F_ACTIVITY) is None,
          "entrada manual nao grava Activity (so os campos no write de criacao)")

    seed_contact(1142, "5531911110142", first_seen_at=datetime(2025, 6, 1, 12, tzinfo=timezone.utc),
                 last_inbound_at=NOW - timedelta(days=60), is_archived=1, declared_name="")
    cid2, err2 = in_tenant(lambda: dbf.create_manual_wa_contact(
        "Paciente Antigo", "5531911110142", 4, 4, funnel_intake=cat))
    c2 = contact(1142)
    check(err2 is None and cid2 == 1142 and c2.get(fc.F_STAGE) == "in_service"
          and c2.get(fc.F_ENTERED_AT) == datetime(2025, 6, 1, 12, tzinfo=timezone.utc)
          and c2.get(fc.F_COHORT) == "2025-06" and c2.get(fc.F_BY_USER) == 4,
          "reabertura de contato legado -> in_service, entered_at/coorte = first_seen_at (nao conta no mes)")
    seed_contact(1143, "5531911110143", last_inbound_at=None)
    in_tenant(lambda: dbf.create_manual_wa_contact("Agenda", "5531911110143", 4, 4, funnel_intake=cat))
    check(contact(1143).get(fc.F_STAGE) == "in_service", "reabertura de contato que nunca escreveu -> in_service")
    seed_contact(1144, "5531911110144", **{fc.F_STAGE: "awaiting_followup", fc.F_VERSION: 2})
    in_tenant(lambda: dbf.create_manual_wa_contact("Com etapa", "5531911110144", 4, 4, funnel_intake=cat))
    check(contact(1144).get(fc.F_STAGE) == "awaiting_followup" and contact(1144).get(fc.F_VERSION) == 2,
          "contato com etapa: intacto")
    cat_off = fc.resolve_funnel(dict(FUNNEL, inactive_stages=["in_service"]))
    cid9, _e9 = in_tenant(lambda: dbf.create_manual_wa_contact(
        "Destino inativo", "5531911110149", 4, 4, funnel_intake=cat_off))
    check(contact(cid9).get(fc.F_STAGE) == "new",
          "Em atendimento inativa no tenant: a criacao manual cai na regra da 1a mensagem (new)")

    titulo("14b. Ramo admin-override e dono alheio")
    seed_contact(1145, "5531911110145", assigned_to=9, assigned_to_uid="uid-9", declared_name="",
                 last_inbound_at=None)
    WRITES.clear()
    cid5, err5 = in_tenant(lambda: dbf.create_manual_wa_contact(
        "Nome Declarado", "5531911110145", 4, 7, allow_admin_override=True, funnel_intake=cat))
    ws5 = contact_writes(1145)
    check(err5 is None and cid5 == 1145 and ws5 and all(not crm(d) for d, _m in ws5),
          "admin-override completa o nome mas NAO escreve etapa")
    check(contact(1145).get("assigned_to") == 9, "dono original preservado")
    WRITES.clear()
    _cid6, err6 = in_tenant(lambda: dbf.create_manual_wa_contact(
        "Outro", "5531911110145", 4, 4, funnel_intake=cat))
    check(err6 and not contact_writes(1145), "dono alheio sem override: erro e nenhum write")
    cid7, _e7 = in_tenant(lambda: dbf.create_manual_wa_contact("Sem funil", "5531911110146", 4, 4,
                                                               funnel_intake=None))
    check(not crm(contact(cid7)), "funnel_intake=None: sem crm_*")

    titulo("14c. Endpoint: catalogo do tenant EXPLICITO do usuario, so se == contexto")
    try:
        import main as _main
    except Exception as exc:  # outro agente pode estar editando main.py
        check(False, f"main.py importavel ({type(exc).__name__})")
        return
    _main.log_audit = lambda *a, **k: None
    for label, user_tid, expect in (("usuario do tenant do contexto", TENANT, "in_service"),
                                    ("claim de outro tenant", OTHER, None),
                                    ("usuario sem tenant_id", "", None)):
        reset()
        user = dict(USERS["4"], tenant_id=user_tid)
        body = _main.ManualContactRequest(declared_name="Paciente API", phone="31911110147", channel_id=4)
        token = firestore_common.set_tenant_context(TENANT)
        try:
            out = asyncio.run(_main.create_contact_manual(body, current_user=user))
        finally:
            firestore_common.reset_tenant_context(token)
        c = contact_by_wa("5531911110147")
        got = (c or {}).get(fc.F_STAGE)
        check(out.get("contact") is not None and got == expect, f"{label}: etapa {expect}")


def cenario_15_graduacao():
    titulo("15. Graduacao de backup (REST) -> A classificar, source graduation")
    reset()
    first_seen = datetime(2025, 3, 10, 15, tzinfo=timezone.utc)
    wa = "5531911110151"

    def seed_backup(cid, wa_id, **extra):
        doc = seed_contact(cid, wa_id, is_backup=True, assigned_to_uid=dbf.BACKUP_ASSIGNED_UID,
                           first_seen_at=first_seen, last_inbound_at=None, created_source="backup_import",
                           **extra)
        conv_id = f"4__{wa_id}"
        STORE.setdefault((TENANT, "wa_conversations"), {})[conv_id] = {
            "id": conv_id, "contact_id": cid, "wa_id": wa_id, "channel_id": 4, "is_backup": True,
            "assigned_to": None, "assigned_to_uid": dbf.BACKUP_ASSIGNED_UID, "unread_count": 0}
        STORE.setdefault((TENANT, "wa_messages"), {})["m%d" % cid] = {
            "id": "m%d" % cid, "contact_id": cid, "conversation_id": conv_id, "is_backup": True}
        return doc, conv_id

    seed_backup(1151, wa)
    t0 = datetime.now(timezone.utc) - timedelta(seconds=1)
    in_tenant(lambda: dbf.assign_wa_contact(1151, 4, 2, transferred_by=7))
    c = contact(1151)
    check(c.get(fc.F_STAGE) == "unclassified" and c.get(fc.F_SOURCE) == "graduation" and c.get(fc.F_VERSION) == 1,
          "assign_wa_contact em backup: unclassified, source graduation, versao 1")
    check(c.get(fc.F_ENTERED_AT) == first_seen and c.get(fc.F_COHORT) == "2025-03",
          "entered_at/coorte = first_seen_at (paciente antigo)")
    check(is_aware_dt(c.get(fc.F_CHANGED_AT)) and c.get(fc.F_CHANGED_AT) >= t0 and c.get(fc.F_MAX_ORDER) == 0
          and c.get(fc.F_BY_USER) is None and c.get(fc.F_BY_UID) == "",
          "changed_at = agora; sem autor; triagem fora da maior etapa")
    grad = [d for d, _m in contact_writes(1151) if crm(d)]
    check(len(grad) == 1 and grad[0].get("is_backup") is False, "etapa no MESMO write que gradua (is_backup=False)")
    check(STORE[(TENANT, "wa_conversations")][f"4__{wa}"].get("is_backup") is False
          and STORE[(TENANT, "wa_messages")]["m1151"].get("is_backup") is False,
          "threads e mensagens do backup graduadas (sem regressao)")

    seed_contact(1152, "5531911110152", last_inbound_at=None)
    in_tenant(lambda: dbf.assign_wa_contact(1152, 4, 2, transferred_by=7))
    check(not crm(contact(1152)), "assign_wa_contact em contato vivo (nao backup): sem crm_*")
    seed_backup(1153, "5531911110153", lgpd_revoked=True)
    in_tenant(lambda: dbf.assign_wa_contact(1153, 4, 2, transferred_by=7))
    check(not crm(contact(1153)) and contact(1153).get("is_backup") is False, "backup com lgpd_revoked: gradua sem crm_*")
    seed_backup(1154, "5531911110154", **{fc.F_STAGE: "disqualified", fc.F_VERSION: 4})
    in_tenant(lambda: dbf.assign_wa_contact(1154, 4, 2, transferred_by=7))
    check(contact(1154).get(fc.F_STAGE) == "disqualified" and contact(1154).get(fc.F_VERSION) == 4,
          "backup que ja tinha etapa: intacto")

    titulo("15b. assign_wa_conversation(also_lead)")
    _d, conv = seed_backup(1155, "5531911110155")
    in_tenant(lambda: dbf.assign_wa_conversation(conv, 4, 2, 7, also_lead=True))
    c = contact(1155)
    check(c.get(fc.F_STAGE) == "unclassified" and c.get(fc.F_SOURCE) == "graduation"
          and c.get(fc.F_ENTERED_AT) == first_seen, "thread backup + also_lead: unclassified graduation")
    _d, conv = seed_backup(1156, "5531911110156")
    in_tenant(lambda: dbf.assign_wa_conversation(conv, 4, 2, 7, also_lead=False))
    check(not crm(contact(1156)) and contact(1156).get("is_backup") is True,
          "thread backup SEM also_lead: contato nao muda (segue backup, sem crm_*)")
    seed_contact(1157, "5531911110157", is_backup=True, assigned_to_uid=dbf.BACKUP_ASSIGNED_UID,
                 first_seen_at=first_seen, last_inbound_at=NOW - timedelta(hours=1))
    live_conv = "4__5531911110157"
    STORE[(TENANT, "wa_conversations")][live_conv] = {
        "id": live_conv, "contact_id": 1157, "wa_id": "5531911110157", "channel_id": 4,
        "assigned_to": None, "assigned_to_uid": "", "unread_count": 1}
    in_tenant(lambda: dbf.assign_wa_conversation(live_conv, 4, 2, 7, also_lead=True))
    c = contact(1157)
    check(c.get("is_backup") is False and c.get(fc.F_STAGE) == "unclassified" and c.get(fc.F_SOURCE) == "graduation",
          "thread VIVA de contato ainda backup + also_lead: o write gradua o contato -> unclassified")
    seed_contact(1158, "5531911110158", last_inbound_at=None)
    conv8 = "4__5531911110158"
    STORE[(TENANT, "wa_conversations")][conv8] = {
        "id": conv8, "contact_id": 1158, "wa_id": "5531911110158", "channel_id": 4,
        "assigned_to": None, "assigned_to_uid": "", "unread_count": 0}
    in_tenant(lambda: dbf.assign_wa_conversation(conv8, 4, 2, 7, also_lead=True))
    check(not crm(contact(1158)), "thread e contato vivos + also_lead: sem crm_* (nao e graduacao)")

    titulo("15c. Sem tenant no contexto: nenhum fallback implicito")
    reset(other_funnel=FUNNEL)
    seed_contact(1159, "5531911110159", tenant="", is_backup=True, assigned_to_uid=dbf.BACKUP_ASSIGNED_UID,
                 last_inbound_at=None)
    dbf.assign_wa_contact(1159, 4, 2, transferred_by=7)
    c = contact(1159, tenant="")
    check(c.get("is_backup") is False and not crm(c), "graduacao sem contexto: sem crm_*")
    check(LOOKUPS["funnel"] == 0, "nenhuma leitura de tenant (nem 'hubloc') sem contexto")

    titulo("15d. Funil desligado no tenant: graduacao sem etapa")
    reset(funnel=None)
    seed_backup(1160, "5531911110160")
    in_tenant(lambda: dbf.assign_wa_contact(1160, 4, 2, transferred_by=7))
    check(not crm(contact(1160)) and contact(1160).get("is_backup") is False, "tenant sem settings.funnel: sem crm_*")

    titulo("15e. assign_wa_conversation(also_lead) com o funil desligado: zero leitura de wa_contacts")
    # Ordem ORIGINAL dos writes (antes do funil): thread, contato (dono do
    # lead), sale_owner, mensagens do backup, log de transferencia.
    original_order = ["wa_conversations", "wa_contacts", "wa_contacts", "wa_messages", "wa_transfer_log"]
    for label, kwargs in (("FEATURE_FUNNEL=false", {"feature": False}),
                          ("tenant sem settings.funnel", {"funnel": None})):
        reset(**kwargs)
        _d, conv = seed_backup(1161, "5531911110161")
        READS.clear()
        WRITES.clear()
        out = in_tenant(lambda: dbf.assign_wa_conversation(conv, 4, 2, 7, also_lead=True))
        c = contact(1161)
        check(not [r for r in READS if r[1] == "wa_contacts"],
              f"{label}: thread backup + also_lead sem nenhuma leitura de wa_contacts")
        check(out and out.get("contact_id") == 1161 and c.get("is_backup") is False and c.get("assigned_to") == 4
              and c.get("sale_owner_user_id") == 4 and not crm(c)
              and STORE[(TENANT, "wa_messages")]["m1161"].get("is_backup") is False,
              f"{label}: graduacao completa (dono, sale_owner, mensagens), sem crm_*")
        check([w[1] for w in WRITES] == original_order,
              f"{label}: ordem original dos writes (thread, contato, sale_owner, mensagens, log)")
    reset(feature=False)
    seed_contact(1164, "5531911110164", is_backup=True, assigned_to_uid=dbf.BACKUP_ASSIGNED_UID,
                 first_seen_at=first_seen, last_inbound_at=NOW - timedelta(hours=1))
    live_conv = "4__5531911110164"
    STORE.setdefault((TENANT, "wa_conversations"), {})[live_conv] = {
        "id": live_conv, "contact_id": 1164, "wa_id": "5531911110164", "channel_id": 4,
        "assigned_to": None, "assigned_to_uid": "", "unread_count": 1}
    READS.clear()
    in_tenant(lambda: dbf.assign_wa_conversation(live_conv, 4, 2, 7, also_lead=True))
    check(not [r for r in READS if r[1] == "wa_contacts"] and contact(1164).get("is_backup") is False
          and not crm(contact(1164)),
          "thread VIVA de contato backup, FEATURE_FUNNEL=false: gradua sem ler wa_contacts")

    titulo("15f. Leitura do contato falhando na graduacao: segue sem etapa, nunca pela metade")
    records = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Capture(level=logging.WARNING)
    db_logger = logging.getLogger("castro_crm.database")
    db_logger.addHandler(handler)
    try:
        for label, live in (("thread backup", False), ("thread VIVA de contato backup", True)):
            reset()
            if live:
                cid, wa_f = 1163, "5531911110163"
                seed_contact(cid, wa_f, is_backup=True, assigned_to_uid=dbf.BACKUP_ASSIGNED_UID,
                             first_seen_at=first_seen, last_inbound_at=NOW - timedelta(hours=1))
                conv = "4__%s" % wa_f
                STORE.setdefault((TENANT, "wa_conversations"), {})[conv] = {
                    "id": conv, "contact_id": cid, "wa_id": wa_f, "channel_id": 4,
                    "assigned_to": None, "assigned_to_uid": "", "unread_count": 1}
            else:
                cid, wa_f = 1162, "5531911110162"
                _d, conv = seed_backup(cid, wa_f)
            READS.clear()
            records.clear()
            READ_FAILS.add("wa_contacts")
            try:
                out = in_tenant(lambda: dbf.assign_wa_conversation(conv, 4, 2, 7, also_lead=True))
                raised = None
            except Exception as exc:  # noqa: BLE001 - o sim registra a falha em vez de abortar
                out, raised = None, type(exc).__name__
            finally:
                READ_FAILS.clear()
            c = contact(cid)
            thread = STORE[(TENANT, "wa_conversations")][conv]
            check(any(r[1] == "wa_contacts" for r in READS),
                  f"{label}: com o funil ligado a leitura do contato foi tentada (e falhou)")
            check(raised is None and out and out.get("contact_id") == cid,
                  f"{label}: ServiceUnavailable na leitura do contato nao propaga (got {raised})")
            check(thread.get("is_backup") is False and thread.get("assigned_to") == 4
                  and c.get("is_backup") is False and c.get("assigned_to") == 4
                  and c.get("assigned_to_uid") == "uid-4" and not crm(c),
                  f"{label}: thread e contato com o novo dono, contato graduado sem crm_*")
            if not live:
                check(c.get("sale_owner_user_id") == 4
                      and STORE[(TENANT, "wa_messages")]["m%d" % cid].get("is_backup") is False,
                      f"{label}: sale_owner gravado e mensagens historicas graduadas")
            check(len(STORE.get((TENANT, "wa_transfer_log"), {})) == 1, f"{label}: log de transferencia gravado")
            warns = [r.getMessage() for r in records if r.levelno == logging.WARNING]
            pii = (wa_f, dbf.format_phone_br(wa_f), "Paciente")
            check(len(warns) == 1 and "funil" in warns[0] and not any(p in warns[0] for p in pii),
                  f"{label}: 1 aviso no log, sem telefone nem nome")
    finally:
        db_logger.removeHandler(handler)


def _conversa_val(wa, mode="cx", handoff=True):
    """Conversa REAL pelo webhook: 1a mensagem (entrada no funil + aviso LGPD
    do turno real) e o aceite "Sim" (CX: turno com handoff roteirizado sobre
    a 1a pergunta; builtin: o aceite ja finaliza no Comercial). WRITES/OPS/
    READS ficam so com o aceite. Devolve (contact_id, hora da 1a mensagem,
    payload do aceite para reentregar)."""
    BOT_MODE["mode"] = mode
    t1 = NOW - timedelta(minutes=2)
    deliver([text_msg(wa, "w.val.%s.1" % wa[-4:], t1)])
    cid = contact_by_wa(wa)["id"]
    WRITES.clear()
    OPS.clear()
    READS.clear()
    if handoff and mode == "cx":
        CX_SCRIPT.append(HANDOFF_REPLY)
    accept = [text_msg(wa, "w.val.%s.2" % wa[-4:], NOW - timedelta(minutes=1), "Sim")]
    deliver(accept)
    return cid, t1, accept


def _handoff_write(cid):
    """(indice em WRITES, campos) dos writes do contato com bot_completed=True."""
    return [(i, d) for i, (_t, coll, did, d, _m) in enumerate(WRITES)
            if coll == "wa_contacts" and did == str(cid) and d.get("bot_completed") is True]


def cenario_16_handoff():
    titulo("16. Handoff da Val (turno CX REAL pelo webhook): Novo contato -> Em atendimento no MESMO write")
    reset()
    wa = "5531911110171"
    cid, t1, accept = _conversa_val(wa)
    c = contact(cid)
    hand = _handoff_write(cid)
    check(len(hand) == 1 and CX_CALLS == ["Oi, quero marcar uma consulta"],
          "aceite da LGPD -> turno CX com a 1a pergunta -> handoff (1 write do contato com bot_completed)")
    idx, hw = hand[0] if hand else (-1, {})
    aid = auto_id(fc.AUTO_HANDOFF, cid, 1)
    check(c.get(fc.F_STAGE) == "in_service" and c.get(fc.F_VERSION) == 2
          and c.get(fc.F_SOURCE) == "rule:handoff" and c.get(fc.F_ACTIVITY) == aid,
          "in_service, versao 2, source rule:handoff, activity_id deterministico (stage_auto_*)")
    check(set(crm(hw)) == AUTO_FIELDS and bool(hw.get("lead_temperature")) and hw.get("department_id") == 2,
          "etapa no MESMO write do handoff (bot_completed + temperatura + setor); entrada/coorte nao reescritas")
    check(c.get(fc.F_BY_USER) is None and c.get(fc.F_BY_UID) == "" and c.get(fc.F_MAX_ORDER) == 20,
          "sem autor humano; max_order 10 -> 20 (Em atendimento)")
    check(c.get(fc.F_ENTERED_AT) == t1 and c.get(fc.F_COHORT) == fc.cohort_month(t1),
          "entrada e coorte da 1a mensagem preservadas (write-once)")
    check(is_aware_dt(c.get(fc.F_CHANGED_AT)) and c.get(fc.F_CHANGED_AT) >= c.get("last_inbound_at"),
          "changed_at = instante do handoff (datetime com fuso)")
    check(not [d for (_t, coll, _d, d, _m) in WRITES if coll == "wa_contacts" and "qualification" in d]
          and c.get("qualification") == "novo",
          "handoff NAO escreve qualification (o lead segue 'novo' na caixa da recepcao)")
    act = activities().get(aid) or {}
    check(set(act) == ACTIVITY_KEYS and act.get("event_type") == fc.EVENT_CHANGED
          and act.get("actor_type") == "system" and act.get("actor_user_id") is None and act.get("actor_uid") == ""
          and act.get("from_stage") == "new" and act.get("to_stage") == "in_service"
          and act.get("entry_kind") == fc.ENTRY_KIND_MOVE and act.get("stage_reason") is None
          and act.get("from_reason") is None,
          "Activity crm_stage_changed: system, new -> in_service, entry_kind move, sem motivo")
    check(act.get("contact_id") == cid and act.get("tenant_id") == TENANT and act.get("task_id") is None
          and act.get("conversation_id") is None and act.get("occurred_at") == c.get(fc.F_CHANGED_AT)
          and act.get("data") == {"stage_version": 2, "source": "rule:handoff", "rule": "handoff"}
          and act.get("operation_id") == "auto:%s:1" % cid,
          "Activity: contato/tenant certos, occurred_at = changed_at, data {stage_version, source, rule}")
    _same = dict(c, id=cid, **{fc.F_STAGE: "new", fc.F_VERSION: 1})
    _cat = fc.load_tenant_funnel(TENANT)
    _h = fc.auto_transition(_same, NOW, _cat, fc.AUTO_HANDOFF, TENANT)
    _r = fc.auto_transition(_same, NOW, _cat, fc.AUTO_HUMAN_REPLY, TENANT)
    check(_h[1] and _r[1] and _h[1]["id"] == _r[1]["id"] == _h[0][fc.F_ACTIVITY] == _r[0][fc.F_ACTIVITY]
          and _h[1]["data"]["rule"] == "handoff" and _r[1]["data"]["rule"] == "human_reply",
          "handoff e 1a resposta humana da MESMA versao = mesmo id de Activity (1 movimento, nao 2)")
    pos = [i for i, w in enumerate(WRITES) if w[1] == "crm_activities"]
    check(pos == [idx + 1] and [k for (_t, coll, _d, k) in OPS if coll == "crm_activities"] == ["set"]
          and all(w[4] is False and w[0] == TENANT for w in WRITES if w[1] == "crm_activities"),
          "Activity com set (sem merge), no tenant explicito, LOGO DEPOIS do write do contato")
    check(not STORE.get((TENANT, "bot_states"), {}).get(str(cid))
          and any(str(m.get("content", "")).startswith("Bot IA finalizado") for m in messages_of(cid)),
          "resto do handoff intacto: resumo do bot gravado e estado do bot limpo")

    titulo("16b. Reentrega do aceite (retry da Meta): o bot nao roda de novo e nada muda")
    before = copy.deepcopy(crm(contact(cid)))
    WRITES.clear()
    deliver(accept)
    check(CX_CALLS == ["Oi, quero marcar uma consulta"] and crm(contact(cid)) == before,
          "was_dup segura o turno: etapa, versao e datas intactas")
    check(not writes_in("crm_activities") and len(activities_of(cid)) == 1
          and all(not crm(w[3]) for w in WRITES), "nenhum write com crm_* e 1 Activity so")

    titulo("16c. Paciente antigo: A classificar (entrada) -> Em atendimento no handoff")
    reset()
    first_seen = datetime(2025, 8, 4, 12, tzinfo=timezone.utc)
    seed_contact(1172, "5531911110172", first_seen_at=first_seen, last_inbound_at=NOW - timedelta(days=30),
                 qualification="novo")
    cid, _t1, _acc = _conversa_val("5531911110172")
    c = contact(1172)
    act = activities().get(auto_id(fc.AUTO_HANDOFF, 1172, 1)) or {}
    check(cid == 1172 and c.get(fc.F_STAGE) == "in_service" and c.get(fc.F_VERSION) == 2
          and c.get(fc.F_MAX_ORDER) == 20, "unclassified -> in_service, versao 2, max_order 0 -> 20")
    check(c.get(fc.F_ENTERED_AT) == first_seen and c.get(fc.F_COHORT) == "2025-08",
          "entrada/coorte do paciente antigo preservadas")
    check(act.get("from_stage") == "unclassified" and act.get("entry_kind") == fc.ENTRY_KIND_MOVE,
          "Activity from unclassified, entry_kind move (fato do periodo, nao triagem)")

    titulo("16d. O handoff nunca regride nem poe no funil quem esta fora dele")
    for i, stage in enumerate(("in_service", "awaiting_followup", "scheduled", "loyal",
                               "non_converted", "disqualified", "zz_retired")):
        reset()
        cid = 11730 + i
        seed_stage(cid, "55319111173%02d" % i, stage, version=3, qualification="novo")
        before = copy.deepcopy(crm(contact(cid)))
        WRITES.clear()
        cx_handoff(cid)
        c = contact(cid)
        check(crm(c) == before and c.get("bot_completed") is True and not activities()
              and all(not crm(w[3]) for w in WRITES),
              f"{stage}: handoff acontece, etapa/versao intactas, sem Activity")
    reset()
    seed_contact(1180, "5531911110180", last_inbound_at=NOW - timedelta(minutes=5))
    cx_handoff(1180)
    check(not crm(contact(1180)) and contact(1180).get("bot_completed") is True and not activities(),
          "contato sem etapa: o handoff nao o coloca no funil")
    reset(funnel=dict(FUNNEL, inactive_stages=["in_service"]))
    seed_stage(1186, "5531911110186", "new")
    cx_handoff(1186)
    check(contact(1186).get(fc.F_STAGE) == "new" and not activities(),
          "Em atendimento inativa no tenant: o handoff nao move")

    titulo("16e. FEATURE_FUNNEL=false ou tenant sem funil: o handoff e o de sempre")
    runs = {}
    for label, kwargs in (("ligado", {}), ("FEATURE_FUNNEL=false", {"feature": False}),
                          ("tenant sem settings.funnel", {"funnel": None})):
        reset(**kwargs)
        cid, _t, _a = _conversa_val("5531911110181")
        hw = _handoff_write(cid)
        runs[label] = ([w[1] for w in WRITES], set(hw[0][1]) if len(hw) == 1 else None,
                       LOOKUPS["funnel"], contact(cid))
    on_seq, on_keys, _l, _c = runs["ligado"]
    for label in ("FEATURE_FUNNEL=false", "tenant sem settings.funnel"):
        seq, keys, _lookups, c = runs[label]
        check(seq == [coll for coll in on_seq if coll != "crm_activities"] and "crm_activities" in on_seq,
              f"{label}: mesma sequencia de writes do aceite + handoff, so sem a Activity")
        check(keys is not None and on_keys is not None and on_keys - keys == AUTO_FIELDS and not keys - on_keys
              and not crm(c) and c.get("bot_completed") is True,
              f"{label}: write do handoff identico; o funil so ACRESCENTA os crm_*")
    check(runs["FEATURE_FUNNEL=false"][2] == 0, "flag desligada: o handoff nem le o doc do tenant")

    titulo("16f. Falhas: Activity, leitura do tenant e write do contato (commit-point)")
    reset()
    seed_stage(1182, "5531911110182", "new", qualification="novo")
    WRITE_FAILS.add("crm_activities")
    with captured("castro_crm.database") as recs:
        raised = try_call(lambda: cx_handoff(1182))
    WRITE_FAILS.clear()
    c = contact(1182)
    warns = warnings_of(recs)
    check(raised is None and c.get("bot_completed") is True and c.get(fc.F_STAGE) == "in_service"
          and not STORE.get((TENANT, "bot_states"), {}).get("1182"),
          "falha ao gravar a Activity nao quebra o handoff (bot finalizado, etapa movida, estado limpo)")
    check(not activities() and len(warns) == 1 and "activity" in warns[0] and no_pii(warns[0], "5531911110182"),
          "sem Activity e 1 aviso no log, sem telefone nem nome")
    reset()
    seed_stage(1183, "5531911110183", "new")
    GET_TENANT_FAILS["on"] = True
    raised = try_call(lambda: cx_handoff(1183))
    GET_TENANT_FAILS["on"] = False
    check(raised is None and contact(1183).get("bot_completed") is True and contact(1183).get(fc.F_STAGE) == "new"
          and not activities(), "leitura do tenant falhando: handoff completo, etapa intacta, sem Activity")
    reset()
    seed_stage(1184, "5531911110184", "new")
    WRITE_FAILS.add("wa_contacts")
    raised = try_call(lambda: cx_handoff(1184))
    WRITE_FAILS.clear()
    check(raised == "ServiceUnavailable" and contact(1184).get(fc.F_STAGE) == "new"
          and not contact(1184).get("bot_completed") and not activities(),
          "write do contato falhando: a excecao sobe como hoje (retry na proxima msg) e NENHUMA Activity")
    cx_handoff(1184)
    check(contact(1184).get(fc.F_STAGE) == "in_service"
          and list(activities()) == [auto_id(fc.AUTO_HANDOFF, 1184, 1)],
          "retry do handoff: move e grava a Activity com o MESMO id deterministico")

    titulo("16g. Dois handoffs do mesmo estado (corrida/reentrega): 1 Activity, versao 2")
    reset()
    seed_stage(1185, "5531911110185", "new")
    stale = in_tenant(lambda: bot_service.get_wa_contact(1185))
    for _ in range(2):
        cx_handoff(1185, contact=copy.deepcopy(stale))
    check(contact(1185).get(fc.F_VERSION) == 2 and len(activities_of(1185)) == 1
          and len(writes_in("crm_activities")) == 2,
          "mesmo id regravado com set: um doc so, versao 2 (nunca 3)")

    titulo("16h. Bot builtin (o aceite da LGPD finaliza no Comercial): mesma automacao, sem leitura extra")
    reads = {}
    for label, kwargs in (("ligado", {}), ("desligado", {"feature": False})):
        reset(**kwargs)
        cid, _t, _a = _conversa_val("5531911110187", mode="builtin")
        reads[label] = len([r for r in READS if r[1] == "wa_contacts"])
        if label != "ligado":
            check(not crm(contact(cid)) and contact(cid).get("bot_completed") is True,
                  "builtin com a flag desligada: finaliza sem crm_*")
            continue
        c = contact(cid)
        hw = _handoff_write(cid)
        pos = [i for i, w in enumerate(WRITES) if w[1] == "crm_activities"]
        check(c.get(fc.F_STAGE) == "in_service" and c.get(fc.F_SOURCE) == "rule:handoff" and len(hw) == 1
              and set(crm(hw[0][1])) == AUTO_FIELDS and hw[0][1].get("bot_setor") == 1,
              "builtin: Em atendimento no MESMO write do bot_completed/setor")
        check(len(hw) == 1 and pos == [hw[0][0] + 1] and c.get(fc.F_ACTIVITY) == auto_id(fc.AUTO_HANDOFF, cid, 1)
              and (activities().get(c.get(fc.F_ACTIVITY)) or {}).get("to_stage") == "in_service",
              "builtin: Activity logo depois do write do contato")
        check(c.get("qualification") == "novo", "builtin: qualification intacta")
    check(reads["ligado"] == reads["desligado"],
          "builtin: o contato do turno e reaproveitado (%s x %s leituras de wa_contacts)"
          % (reads["ligado"], reads["desligado"]))
    extra = {}
    for label, kwargs in (("ligado", {}), ("desligado", {"feature": False})):
        reset(**kwargs)
        seed_stage(1188, "5531911110188", "new")
        READS.clear()
        in_tenant(lambda: bot_service._finalize_bot(1188, {}, bot_service.SETOR_COMERCIAL))
        extra[label] = (len([r for r in READS if r[1] == "wa_contacts"]), contact(1188).get(fc.F_STAGE))
    check(extra["ligado"][0] == extra["desligado"][0] + 1 and extra["ligado"][1] == "in_service"
          and extra["desligado"][1] == "new",
          "chamador sem o contato: le 1x SO com o catalogo do tenant (%s x %s)"
          % (extra["ligado"][0], extra["desligado"][0]))


def _clear_turn():
    WRITES.clear()
    OPS.clear()
    READS.clear()


def _lgpd_then(wa, tag, script, accept_text="Sim"):
    """1a mensagem pelo webhook (entrada no funil + aviso LGPD do turno CX
    REAL) e o aceite com o roteiro do conector. WRITES/OPS/READS ficam so com
    o aceite. Devolve o contact_id."""
    deliver([text_msg(wa, "w.%s.1" % tag, NOW - timedelta(minutes=4))])
    cid = contact_by_wa(wa)["id"]
    _clear_turn()
    CX_SCRIPT.extend(copy.deepcopy(script))
    deliver([text_msg(wa, "w.%s.2" % tag, NOW - timedelta(minutes=3), accept_text)])
    return cid


def _note(tag, cid):
    NOTES[tag] = (copy.deepcopy(crm(contact(cid))), bool(contact(cid).get("bot_completed")),
                  len(activities_of(cid)))


def _path_text_hint(wa):
    # O agente fala a frase de transferencia mas nao seta handoff_request.
    return _lgpd_then(wa, "txt", [TEXT_HANDOFF_REPLY])


def _path_down_twice(wa):
    # 1a falha do DetectIntent (timeout/5xx) responde o fallback educado; a
    # 2a seguida transfere ("Bot IA indisponivel").
    cid = _lgpd_then(wa, "down", [DOWN_REPLY])
    _note("1a falha", cid)
    _clear_turn()
    CX_SCRIPT.append(copy.deepcopy(DOWN_REPLY))
    deliver([text_msg(wa, "w.down.3", NOW - timedelta(minutes=2), "Alô? Alguém aí?")])
    return cid


def _path_incomplete_ai(wa):
    # settings.ai sem agent_id: o turno nem chama o agente e cai no mesmo
    # contador de falhas (o contato do turno e o lido no inicio, sem releitura).
    BOT_MODE["ai"] = dict(AI_CFG, agent_id="")
    cid = _lgpd_then(wa, "noagent", [])
    _note("1a falha", cid)
    _clear_turn()
    deliver([text_msg(wa, "w.noagent.3", NOW - timedelta(minutes=2), "Alô? Alguém aí?")])
    return cid


def _path_errors(wa):
    # Frase de erro embutida do CX em 1 + 3 reenvios: handoff generico.
    return _lgpd_then(wa, "err", [ERROR_REPLY] * 4)


def _path_lgpd_by_agent(wa):
    # settings.ai.lgpd_by_agent: sem gate local, o 1o turno ja pode transferir
    # (entrada e handoff no MESMO payload).
    BOT_MODE["ai"] = dict(AI_CFG, lgpd_by_agent=True)
    _clear_turn()
    CX_SCRIPT.append(copy.deepcopy(HANDOFF_REPLY))
    deliver([text_msg(wa, "w.agentlgpd.1", NOW - timedelta(minutes=2))])
    return contact_by_wa(wa)["id"]


def _path_after_hours(wa):
    # Fora do expediente o CRM so informa o agente (fora_do_expediente e
    # retorno_previsto); o handoff e o mesmo caminho.
    saved = bot_service.cx_hours_params
    bot_service.cx_hours_params = lambda _tid: {"fora_do_expediente": True, "retorno_previsto": "amanhã às 8h"}
    try:
        return _lgpd_then(wa, "hrs", [HANDOFF_REPLY])
    finally:
        bot_service.cx_hours_params = saved


def _path_buffer(wa):
    """Lote ja claimado do debounce persistido (bot_buffers): o turno roda pelo
    dispatcher REAL (process_bot_message_async -> CX) com o texto juntado,
    como no handler do debounce e no cron do buffer."""
    cid = 1290
    seed_stage(cid, wa, "new", qualification="novo", last_inbound_at=NOW - timedelta(minutes=1))
    STORE.setdefault((TENANT, "bot_states"), {})[str(cid)] = {
        "lgpd_consent": True, "lgpd_status": "accepted", "step": "cx"}
    TENANT_DOCS[TENANT]["settings"]["ai"] = dict(AI_CFG, buffer_seconds=3)
    CX_SCRIPT.append(copy.deepcopy(HANDOFF_REPLY))
    items = [{"text": "Quero agendar", "ts": (NOW - timedelta(seconds=9)).isoformat(), "n": 1},
             {"text": "amanhã cedo", "ts": (NOW - timedelta(seconds=5)).isoformat(), "n": 2}]
    saved = (webhook.release_bot_buffer_claim, webhook.drain_claimed_bot_buffer, webhook._send_bot_reply)

    async def _sent(_wa, reply, *_a, **_k):
        BUFFER_SENT.append(reply)
        return True

    webhook.release_bot_buffer_claim = lambda *_a, **_k: None
    webhook.drain_claimed_bot_buffer = lambda *_a, **_k: {"status": "empty", "items": []}
    webhook._send_bot_reply = _sent
    _clear_turn()
    try:
        in_tenant(lambda: asyncio.run(webhook.process_claimed_bot_buffer(
            cid, "claim-sim", items, "Paciente", wa, "tok-4", "PNID4", channel_id=4)))
    finally:
        webhook.release_bot_buffer_claim, webhook.drain_claimed_bot_buffer, webhook._send_bot_reply = saved
    return cid


def _handoff_run(path, wa, **reset_kw):
    """Roda um caminho de handoff pelo codigo REAL e fotografa o turno."""
    reset(**reset_kw)
    BOT_MODE["mode"] = "cx"
    cid = path(wa)
    hand = _handoff_write(cid)
    return {"cid": cid, "seq": [w[1] for w in WRITES], "hand": hand,
            "keys": set(hand[0][1]) if len(hand) == 1 else None,
            "reads": len([r for r in READS if r[1] == "wa_contacts"]),
            "contact": copy.deepcopy(contact(cid)), "acts": copy.deepcopy(activities_of(cid)),
            "ops": [k for (_t, coll, _d, k) in OPS if coll == "crm_activities"],
            "act_pos": [i for i, w in enumerate(WRITES) if w[1] == "crm_activities"],
            "crm_writes": [w[1] for w in WRITES if crm(w[3])],
            # So merge: a criacao do contato (set sem merge, qualification
            # 'novo') nao e o handoff; o handoff nunca grava qualification.
            "qual_writes": [w for w in WRITES if w[1] == "wa_contacts" and w[4] and "qualification" in w[3]],
            "lgpd_writes": [w for w in WRITES if w[1] == "wa_contacts" and "lgpd_consent" in w[3]],
            "bot_state": copy.deepcopy(STORE.get((TENANT, "bot_states"), {}).get(str(cid))),
            "calls": list(CX_CALLS), "params": copy.deepcopy(CX_PARAMS), "sent": list(BUFFER_SENT),
            "notes": copy.deepcopy(NOTES), "lookups": LOOKUPS["funnel"]}


CX_PATHS = (
    ("frase de transferencia (handoff_request falso)", _path_text_hint, "5531911110211"),
    ("motor fora do ar 2x seguidas (timeout/5xx)", _path_down_twice, "5531911110212"),
    ("settings.ai incompleto (sem agent_id)", _path_incomplete_ai, "5531911110213"),
    ("4 frases de erro do agente", _path_errors, "5531911110214"),
    ("settings.ai.lgpd_by_agent (sem gate local)", _path_lgpd_by_agent, "5531911110215"),
    ("fora do expediente", _path_after_hours, "5531911110216"),
    ("buffer CX (lote do debounce)", _path_buffer, "5531911110217"),
)


def cenario_16i_caminhos_cx():
    titulo("16i. TODOS os caminhos de handoff do CX: Em atendimento no MESMO write, Activity logo depois")
    for label, path, wa in CX_PATHS:
        on = _handoff_run(path, wa)
        c = on["contact"]
        aid = auto_id(fc.AUTO_HANDOFF, on["cid"], 1)
        idx = on["hand"][0][0] if len(on["hand"]) == 1 else -1
        check(len(on["hand"]) == 1 and c.get(fc.F_STAGE) == "in_service" and c.get(fc.F_VERSION) == 2
              and c.get(fc.F_SOURCE) == "rule:handoff" and c.get(fc.F_ACTIVITY) == aid
              and set(crm(on["hand"][0][1])) == AUTO_FIELDS and c.get(fc.F_MAX_ORDER) == 20,
              f"{label}: Em atendimento v2 no MESMO write do bot_completed (so os crm_* da automacao)")
        check(on["act_pos"] == [idx + 1] and on["ops"] == ["set"] and [a.get("id") for a in on["acts"]] == [aid]
              and on["acts"][0].get("from_stage") == "new" and on["acts"][0].get("data", {}).get("rule") == "handoff",
              f"{label}: 1 Activity (set, id deterministico) LOGO DEPOIS do write do contato")
        check(c.get("bot_completed") is True and not on["bot_state"] and not on["qual_writes"]
              and c.get("qualification") == "novo",
              f"{label}: handoff completo (estado do bot limpo) e qualification intacta")
        for tag, kwargs in (("FEATURE_FUNNEL=false", {"feature": False}),
                            ("tenant sem settings.funnel", {"funnel": None})):
            run = _handoff_run(path, wa, **kwargs)
            check(run["seq"] == [coll for coll in on["seq"] if coll != "crm_activities"]
                  and run["keys"] is not None and on["keys"] is not None
                  and on["keys"] - run["keys"] == AUTO_FIELDS and not run["keys"] - on["keys"]
                  and run["reads"] == on["reads"] and not run["acts"] and not run["crm_writes"]
                  and run["contact"].get("bot_completed") is True,
                  f"{label}, {tag}: mesmos writes e as mesmas {run['reads']} leituras de wa_contacts; "
                  f"o funil so ACRESCENTA os crm_*")
            if tag == "FEATURE_FUNNEL=false":
                check(run["lookups"] == 0, f"{label}, {tag}: o doc do tenant nem e lido pelo funil")
        if path is _path_text_hint:
            check(on["calls"] == ["Oi, quero marcar uma consulta"],
                  f"{label}: detectado pela frase (1 chamada ao agente, com a 1a pergunta)")
        elif path in (_path_down_twice, _path_incomplete_ai):
            first = on["notes"].get("1a falha") or ({}, True, -1)
            check(first[0].get(fc.F_STAGE) == "new" and first[0].get(fc.F_VERSION) == 1
                  and first[1] is False and first[2] == 0,
                  f"{label}: a 1a falha so responde o fallback (Novo contato v1, bot ativo, sem Activity)")
            # Motor fora: 1 chamada no turno do aceite (a 1a pergunta) e 1 na
            # mensagem seguinte; sem agent_id o agente nunca e chamado.
            check(len(on["calls"]) == (0 if path is _path_incomplete_ai else 2),
                  f"{label}: {'o agente nunca e chamado' if path is _path_incomplete_ai else '1 chamada por turno (aceite e mensagem seguinte)'}")
        elif path is _path_errors:
            check(len(on["calls"]) == 4, f"{label}: 1 chamada + 3 reenvios antes do handoff")
        elif path is _path_lgpd_by_agent:
            check(on["crm_writes"].count("wa_contacts") == 2 and c.get(fc.F_ENTERED_AT) == NOW - timedelta(minutes=2)
                  and not on["lgpd_writes"] and on["params"] and "lgpd_consent" not in on["params"][0],
                  f"{label}: entrada (v1) e handoff (v2) no mesmo payload; o CRM nao grava nem afirma aceite")
        elif path is _path_after_hours:
            check(on["params"] and on["params"][-1].get("fora_do_expediente") is True
                  and on["params"][-1].get("retorno_previsto") == "amanhã às 8h",
                  f"{label}: o agente recebeu fora_do_expediente=True no turno do handoff")
        elif path is _path_buffer:
            check(on["calls"] == ["Quero agendar\namanhã cedo"] and on["sent"] == [HANDOFF_REPLY["reply_text"]],
                  f"{label}: 1 turno com a rajada juntada e 1 resposta enviada")


BUILTIN_STATES = (
    ("LGPD ja aceita, sem step", {"lgpd_consent": True, "lgpd_status": "accepted"}, "Oi, tudo bem?", 1),
    ("step cx (tenant voltou do CX para o builtin)",
     {"lgpd_consent": True, "lgpd_status": "accepted", "step": "cx"}, "Oi", 1),
    ("step lgpd com aceite", {"lgpd_consent": True, "lgpd_status": "accepted", "step": "lgpd"}, "Oi", 1),
    ("menu legado: setor reconhecido", {"lgpd_consent": True, "lgpd_status": "accepted", "step": "ask_sector"},
     "2", 2),
    ("menu legado: texto nao reconhecido", {"lgpd_consent": True, "lgpd_status": "accepted",
                                            "step": "ask_sector"}, "talvez", 1),
)


def _builtin_run(state, text, wa, cid, **reset_kw):
    reset(**reset_kw)
    seed_stage(cid, wa, "new", qualification="novo", last_inbound_at=NOW - timedelta(minutes=1))
    STORE.setdefault((TENANT, "bot_states"), {})[str(cid)] = copy.deepcopy(state)
    before = copy.deepcopy(crm(contact(cid)))
    _clear_turn()
    reply = in_tenant(lambda: bot_service.process_bot_message(cid, text))
    hand = _handoff_write(cid)
    return {"reply": reply, "hand": hand, "keys": set(hand[0][1]) if len(hand) == 1 else None,
            "seq": [w[1] for w in WRITES], "reads": len([r for r in READS if r[1] == "wa_contacts"]),
            "contact": copy.deepcopy(contact(cid)), "acts": copy.deepcopy(activities_of(cid)),
            "act_pos": [i for i, w in enumerate(WRITES) if w[1] == "crm_activities"], "before": before,
            "bot_state": copy.deepcopy(STORE.get((TENANT, "bot_states"), {}).get(str(cid)))}


def cenario_16j_caminhos_builtin():
    titulo("16j. Bot builtin: todos os estados que finalizam no Comercial/setor movem no MESMO write")
    for i, (label, state, text, setor) in enumerate(BUILTIN_STATES):
        cid, wa = 1295 + i, "55319111102%02d" % (30 + i)
        on = _builtin_run(state, text, wa, cid)
        c = on["contact"]
        idx = on["hand"][0][0] if len(on["hand"]) == 1 else -1
        check(len(on["hand"]) == 1 and on["hand"][0][1].get("bot_setor") == setor
              and set(crm(on["hand"][0][1])) == AUTO_FIELDS and c.get(fc.F_STAGE) == "in_service"
              and c.get(fc.F_VERSION) == 2 and c.get(fc.F_ACTIVITY) == auto_id(fc.AUTO_HANDOFF, cid, 1)
              and on["act_pos"] == [idx + 1] and not on["bot_state"] and c.get("qualification") == "novo",
              f"builtin, {label}: Em atendimento no write do bot_completed (setor {setor}), Activity logo depois")
        for tag, kwargs in (("FEATURE_FUNNEL=false", {"feature": False}),
                            ("tenant sem settings.funnel", {"funnel": None})):
            run = _builtin_run(state, text, wa, cid, **kwargs)
            check(run["seq"] == [coll for coll in on["seq"] if coll != "crm_activities"]
                  and run["keys"] is not None and on["keys"] is not None
                  and on["keys"] - run["keys"] == AUTO_FIELDS and not run["keys"] - on["keys"]
                  and run["reads"] == on["reads"] and crm(run["contact"]) == run["before"] and not run["acts"]
                  and run["reply"] == on["reply"],
                  f"builtin, {label}, {tag}: mesmos writes, leituras e resposta; etapa intacta")
    saved = bot_service.builtin_expediente_notice
    bot_service.builtin_expediente_notice = lambda _tid: "\n\nEstamos fora do horário de atendimento."
    try:
        out = _builtin_run(BUILTIN_STATES[0][1], "Oi", "5531911110239", 1299)
    finally:
        bot_service.builtin_expediente_notice = saved
    check("fora do horário" in str(out["reply"]) and out["contact"].get(fc.F_STAGE) == "in_service"
          and len(out["hand"]) == 1 and set(crm(out["hand"][0][1])) == AUTO_FIELDS,
          "builtin fora do expediente: aviso no texto e o mesmo handoff com a etapa no mesmo write")


def _raise_unavailable(*_a, **_k):
    raise gcloud_exceptions.ServiceUnavailable("leitura indisponivel (simulado)")


def cenario_16k_handoff_robustez():
    titulo("16k. Handoff: leitura do contato falhando, sem contexto de tenant e Activity do builtin falhando")
    # Chamador que nao traz o contato: o funil le 1x (so com catalogo); se a
    # leitura falha, o handoff segue inteiro e a etapa fica como estava.
    reset()
    seed_stage(1240, "5531911110240", "new", qualification="novo")
    saved = bot_service.get_wa_contact
    bot_service.get_wa_contact = _raise_unavailable
    try:
        with captured("castro_crm.bot") as recs:
            raised = try_call(lambda: in_tenant(
                lambda: bot_service._finalize_bot(1240, {}, bot_service.SETOR_COMERCIAL)))
    finally:
        bot_service.get_wa_contact = saved
    c = contact(1240)
    warns = [w for w in warnings_of(recs) if "funil" in w]
    check(raised is None and c.get("bot_completed") is True and c.get(fc.F_STAGE) == "new"
          and c.get(fc.F_VERSION) == 1 and not activities()
          and any(str(m.get("content", "")).startswith("Bot finalizado") for m in messages_of(1240)),
          "leitura do contato pelo funil falhando: handoff completo (bot finalizado, resumo gravado), etapa intacta")
    check(len(warns) == 1 and no_pii(warns[0], "5531911110240"), "1 aviso do funil no log, sem telefone nem nome")

    # Sem contexto de tenant: nenhum fallback implicito ('hubloc' tambem tem
    # funil aqui, entao um fallback apareceria) e nenhuma leitura do funil.
    reset(other_funnel=FUNNEL)
    seed_stage(1241, "5531911110241", "new", tenant="", qualification="novo")
    raised = try_call(lambda: bot_service._finalize_bot(
        1241, {}, bot_service.SETOR_COMERCIAL, contact=bot_service.get_wa_contact(1241)))
    c = contact(1241, tenant="")
    check(raised is None and c.get("bot_completed") is True and c.get(fc.F_STAGE) == "new"
          and not any(activities(t) for t in (TENANT, OTHER, "")) and LOOKUPS["funnel"] == 0,
          "sem contexto de tenant: handoff de sempre, etapa intacta, nenhuma leitura do funil (nem 'hubloc')")
    reset(other_funnel=FUNNEL)
    seed_stage(1246, "5531911110246", "new", tenant="", qualification="novo")
    raised = try_call(lambda: bot_service._finalize_cx_handoff(
        1246, copy.deepcopy(AI_CFG), summary="Quer agendar", contact=bot_service.get_wa_contact(1246)))
    c = contact(1246, tenant="")
    check(raised is None and c.get("bot_completed") is True and c.get(fc.F_STAGE) == "new"
          and not any(activities(t) for t in (TENANT, OTHER, "")) and LOOKUPS["funnel"] == 0,
          "CX sem contexto de tenant: idem (o tenant vem SO do contexto, nunca de fallback)")

    # Activity do builtin falhando: best-effort, o handoff nao percebe.
    reset()
    seed_stage(1243, "5531911110243", "new", qualification="novo")
    WRITE_FAILS.add("crm_activities")
    try:
        with captured("castro_crm.database") as recs:
            raised = try_call(lambda: in_tenant(lambda: bot_service._finalize_bot(
                1243, {}, bot_service.SETOR_COMERCIAL, contact=bot_service.get_wa_contact(1243))))
    finally:
        WRITE_FAILS.clear()
    c = contact(1243)
    warns = warnings_of(recs)
    check(raised is None and c.get("bot_completed") is True and c.get(fc.F_STAGE) == "in_service"
          and not activities() and not STORE.get((TENANT, "bot_states"), {}).get("1243")
          and any(str(m.get("content", "")).startswith("Bot finalizado") for m in messages_of(1243)),
          "builtin com a Activity falhando: handoff completo, etapa movida, estado do bot limpo")
    check(len(warns) == 1 and "activity" in warns[0] and no_pii(warns[0], "5531911110243"),
          "builtin: 1 aviso no log, sem telefone nem nome")


def cenario_17_resposta_humana():
    titulo("17. 1a resposta humana pelo CRM (funnel_human_reply=True): Novo contato -> Em atendimento")
    keys = {}
    wa = "5531911110191"
    for label, feature in (("ligado", True), ("desligado", False)):
        reset(feature=feature)
        seed_stage(1191, wa, "new", qualification="novo", last_inbound_at=NOW - timedelta(minutes=10))
        WRITES.clear()
        OPS.clear()
        t_reply = NOW - timedelta(minutes=1)
        human_send(1191, wa, at=t_reply, funnel_human_reply=True)
        ws = contact_writes(1191)
        keys[label] = set(ws[0][0]) if len(ws) == 1 else None
        if not feature:
            check(contact(1191).get(fc.F_STAGE) == "new" and not activities() and LOOKUPS["funnel"] == 0,
                  "FEATURE_FUNNEL=false: nada muda e o tenant nem e lido")
            continue
        c = contact(1191)
        aid = auto_id(fc.AUTO_HUMAN_REPLY, 1191, 1)
        check(c.get(fc.F_STAGE) == "in_service" and c.get(fc.F_VERSION) == 2
              and c.get(fc.F_SOURCE) == "rule:human_reply" and c.get(fc.F_ACTIVITY) == aid
              and c.get(fc.F_CHANGED_AT) == t_reply and c.get(fc.F_MAX_ORDER) == 20,
              "in_service v2, source rule:human_reply, changed_at = hora da mensagem, max_order 20")
        check(len(ws) == 1 and "last_message_at" in ws[0][0] and set(crm(ws[0][0])) == AUTO_FIELDS,
              "campos no MESMO write do contato que a mensagem ja fazia")
        check(c.get("qualification") == "em_atendimento" and c.get("first_human_contact_at") == t_reply,
              "promocao legada novo -> em_atendimento intacta (regra de 2026-09, nao do funil)")
        act = activities().get(aid) or {}
        check(set(act) == ACTIVITY_KEYS and act.get("from_stage") == "new" and act.get("to_stage") == "in_service"
              and act.get("actor_type") == "system" and act.get("occurred_at") == t_reply
              and act.get("data") == {"stage_version": 2, "source": "rule:human_reply", "rule": "human_reply"}
              and act.get("operation_id") == "auto:1191:1",
              "Activity da 1a resposta: system, new -> in_service, occurred_at = hora da mensagem")
        ci = [i for i, w in enumerate(WRITES) if w[1] == "wa_contacts"]
        ai = [i for i, w in enumerate(WRITES) if w[1] == "crm_activities"]
        check(len(ai) == 1 and ci and ai[0] > ci[0]
              and [k for (_t, coll, _d, k) in OPS if coll == "crm_activities"] == ["set"],
              "Activity com set, depois do write do contato")
        snap = copy.deepcopy(crm(c))
        WRITES.clear()
        human_send(1191, wa, at=NOW, funnel_human_reply=True)
        check(crm(contact(1191)) == snap and not writes_in("crm_activities") and len(activities()) == 1,
              "2a resposta: nada muda (ja em Em atendimento)")
    check(keys["ligado"] is not None and keys["desligado"] is not None
          and keys["ligado"] - keys["desligado"] == AUTO_FIELDS and not keys["desligado"] - keys["ligado"],
          "o funil so ACRESCENTA os crm_* ao write do contato (qualification segue so a regra legada)")
    reset()
    seed_stage(1192, "5531911110192", "unclassified")
    human_send(1192, "5531911110192", funnel_human_reply=True)
    act = activities().get(auto_id(fc.AUTO_HUMAN_REPLY, 1192, 1)) or {}
    check(contact(1192).get(fc.F_STAGE) == "in_service" and act.get("from_stage") == "unclassified",
          "A classificar -> Em atendimento na 1a resposta humana")

    titulo("17b. Sem o kwarg, bot, lote, recibo e sistema: nada muda")
    for label, kw in (("sem o kwarg (eco/history usam o default False)", {}),
                      ("bot (sender_user_id None)", {"funnel_human_reply": True, "sender_user_id": None,
                                                    "operator_id": None}),
                      ("lote de reabertura (human_outbound=False)", {"funnel_human_reply": True,
                                                                     "human_outbound": False}),
                      ("recibo de fechamento (promote_qualification=False)", {"funnel_human_reply": True,
                                                                             "promote_qualification": False}),
                      ("mensagem de sistema", {"funnel_human_reply": True, "direction": "system",
                                               "msg_type": "system"})):
        reset()
        seed_stage(1193, "5531911110193", "new")
        before = copy.deepcopy(crm(contact(1193)))
        WRITES.clear()
        human_send(1193, "5531911110193", **kw)
        check(crm(contact(1193)) == before and not activities() and all(not crm(w[3]) for w in WRITES),
              f"{label}: etapa intacta, sem Activity")
    for i, stage in enumerate(("in_service", "awaiting_followup", "scheduled", "loyal",
                               "non_converted", "disqualified")):
        reset()
        cid, wa_i = 11940 + i, "55319111194%02d" % i
        seed_stage(cid, wa_i, stage, version=4)
        before = copy.deepcopy(crm(contact(cid)))
        human_send(cid, wa_i, funnel_human_reply=True)
        check(crm(contact(cid)) == before and not activities(), f"{stage}: a resposta humana nao regride")
    reset()
    seed_contact(1195, "5531911110195")
    human_send(1195, "5531911110195", funnel_human_reply=True)
    check(not crm(contact(1195)) and not activities(), "contato sem etapa: a resposta nao o coloca no funil")
    reset(funnel=None)
    seed_stage(1197, "5531911110197", "new")
    human_send(1197, "5531911110197", funnel_human_reply=True)
    check(contact(1197).get(fc.F_STAGE) == "new" and not activities(), "tenant sem settings.funnel: nada")

    titulo("17c. Falha da Activity, envios simultaneos e mesmo wamid")
    reset()
    seed_stage(1198, "5531911110198", "new")
    WRITE_FAILS.add("crm_activities")
    with captured("castro_crm.database") as recs:
        raised = try_call(lambda: human_send(1198, "5531911110198", funnel_human_reply=True))
    WRITE_FAILS.clear()
    warns = warnings_of(recs)
    check(raised is None and contact(1198).get(fc.F_STAGE) == "in_service" and len(messages_of(1198)) == 1
          and not activities(), "falha da Activity: mensagem gravada e etapa movida, sem excecao")
    check(len(warns) == 1 and "activity" in warns[0] and no_pii(warns[0], "5531911110198"),
          "1 aviso no log, sem telefone nem nome")
    reset()
    seed_stage(1199, "5531911110199", "new")
    stale = copy.deepcopy(contact(1199))
    for _ in range(2):
        human_send(1199, "5531911110199", funnel_human_reply=True, contact=copy.deepcopy(stale))
    check(contact(1199).get(fc.F_VERSION) == 2 and len(activities_of(1199)) == 1,
          "dois envios simultaneos do mesmo estado: 1 Activity (mesmo id), versao 2")
    reset()
    seed_stage(1200, "5531911110200", "new")
    m1 = human_send(1200, "5531911110200", wa_message_id="wamid.HUMAN.1", funnel_human_reply=True)
    snap = copy.deepcopy(crm(contact(1200)))
    WRITES.clear()
    m2 = human_send(1200, "5531911110200", wa_message_id="wamid.HUMAN.1", funnel_human_reply=True)
    check(m1 == m2 and snap.get(fc.F_STAGE) == "in_service" and crm(contact(1200)) == snap
          and not writes_in("crm_activities"), "mesmo wamid (dedup): devolve a mensagem existente, nada muda")

    titulo("17d. Eco do celular e history (outbound da dona do numero) nao movem")
    reset(funnel=FUNNEL_COEX)
    wa_c = "5531911110201"
    seed_stage(1201, wa_c, "new", channel_id=8, phone_number_id="PNID8", source_channel_type="coexistence",
               assigned_to=8, assigned_to_uid="uid-8")
    before = copy.deepcopy(crm(contact(1201)))
    echo = {"message_echoes": [{"from": BUSINESS_COEX, "to": wa_c, "id": "w.18.echo", "type": "text",
                                "timestamp": unix(NOW - timedelta(minutes=2)), "text": {"body": "Oi, tudo bem?"}}],
            "metadata": {"display_phone_number": BUSINESS_COEX, "phone_number_id": "PNID8"}}
    in_tenant(lambda: asyncio.run(webhook._process_smb_message_echoes(echo, channel=copy.deepcopy(COEX_CH))))
    out = [m for m in messages_of(1201) if m.get("direction") == "outbound"]
    check(len(out) == 1 and out[0].get("sender_user_id") == 8 and crm(contact(1201)) == before and not activities(),
          "eco (outbound humano da dona, sender_user_id=8): etapa intacta, sem Activity")
    hist = {"metadata": {"display_phone_number": BUSINESS_COEX, "phone_number_id": "PNID8"},
            "history": [{"metadata": {"phase": 0, "chunk_order": 1, "progress": 100},
                         "threads": [{"id": wa_c, "messages": [
                             {"from": BUSINESS_COEX, "to": wa_c, "id": "w.18.hist", "type": "text",
                              "timestamp": unix(NOW - timedelta(minutes=1)), "text": {"body": "Retorno"},
                              "history_context": {"status": "read"}}]}]}]}
    in_tenant(lambda: asyncio.run(webhook._process_history(hist, channel=copy.deepcopy(COEX_CH))))
    out = [m for m in messages_of(1201) if m.get("direction") == "outbound"]
    check(len(out) == 2 and crm(contact(1201)) == before and not activities(),
          "history (outbound importado da dona): etapa intacta, sem Activity")

    titulo("17e. Endpoint REAL POST /api/wa/send (main.wa_send): a 1a resposta move")
    try:
        import main as _main
    except Exception as exc:  # outro agente pode estar editando main.py
        check(False, f"main.py importavel ({type(exc).__name__})")
        return
    reset()
    wa_s = "5531911110202"
    seed_stage(1202, wa_s, "new", qualification="novo", last_inbound_at=NOW - timedelta(minutes=5))
    conv_id = "4__%s" % wa_s
    STORE.setdefault((TENANT, "wa_conversations"), {})[conv_id] = {
        "id": conv_id, "contact_id": 1202, "wa_id": wa_s, "channel_id": 4,
        "assigned_to": None, "assigned_to_uid": "", "unread_count": 0}
    sent = []

    class _Resp:
        status_code = 200

        def json(self):
            return {"messages": [{"id": "wamid.SEND.1202"}]}

    class _Client:
        def __init__(self, *_a, **_k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

        async def post(self, url, json=None, headers=None):
            sent.append(json)
            return _Resp()

    saved = (_main.httpx, _main.log_audit, channel_service.get_send_credentials)
    _main.httpx = types.SimpleNamespace(AsyncClient=_Client)
    _main.log_audit = lambda *a, **k: None
    channel_service.get_send_credentials = lambda cid: ("tok-4", "PNID4", "https://mock.invalid")
    try:
        body = _main.WaSendRequest(conversation_id=conv_id, content="Olá! Aqui é a recepção.")
        out = in_tenant(lambda: asyncio.run(_main.wa_send(body, current_user=dict(USERS["7"]))))
        raised = None
    except Exception as exc:  # noqa: BLE001
        out, raised = {}, type(exc).__name__
    finally:
        _main.httpx, _main.log_audit, channel_service.get_send_credentials = saved
    c = contact(1202)
    check(raised is None and (out or {}).get("status") == "sent" and len(sent) == 1
          and c.get(fc.F_STAGE) == "in_service" and c.get(fc.F_SOURCE) == "rule:human_reply",
          "supervisora responde pelo CRM: Em atendimento (o endpoint passa funnel_human_reply=True)"
          + (f" [{raised}]" if raised else ""))
    check(set(activities()) == {auto_id(fc.AUTO_HUMAN_REPLY, 1202, 1)}, "Activity da 1a resposta gravada")


def cenario_17f_resposta_falhas():
    titulo("17f. 1a resposta: write do contato falhando, tenant indisponivel e leituras de sempre")
    reset()
    seed_stage(1203, "5531911110203", "new")
    WRITE_FAILS.add("wa_contacts")
    raised = try_call(lambda: human_send(1203, "5531911110203", funnel_human_reply=True))
    WRITE_FAILS.clear()
    check(raised == "ServiceUnavailable" and contact(1203).get(fc.F_STAGE) == "new" and not activities(),
          "write do contato falhando: a excecao sobe como antes (sem o funil tambem) e NENHUMA Activity")
    reset()
    seed_stage(1204, "5531911110204", "new")
    GET_TENANT_FAILS["on"] = True
    with captured("castro_crm.funnel_catalog") as recs:
        raised = try_call(lambda: human_send(1204, "5531911110204", funnel_human_reply=True))
    GET_TENANT_FAILS["on"] = False
    warns = warnings_of(recs)
    check(raised is None and contact(1204).get(fc.F_STAGE) == "new" and len(messages_of(1204)) == 1
          and not activities(), "leitura do tenant falhando: mensagem gravada, etapa intacta, sem excecao")
    check(warns and all(no_pii(w, "5531911110204") for w in warns), "aviso no log sem telefone nem nome")
    runs = {}
    for label, kwargs in (("ligado", {}), ("FEATURE_FUNNEL=false", {"feature": False}),
                          ("tenant sem settings.funnel", {"funnel": None})):
        reset(**kwargs)
        seed_stage(1205, "5531911110205", "new", qualification="novo")
        _clear_turn()
        human_send(1205, "5531911110205", funnel_human_reply=True)
        runs[label] = ([w[1] for w in WRITES], len([r for r in READS if r[1] == "wa_contacts"]),
                       copy.deepcopy(crm(contact(1205))), LOOKUPS["funnel"])
    on_seq, on_reads, on_stage, _l = runs["ligado"]
    check(on_stage.get(fc.F_STAGE) == "in_service" and on_seq.count("crm_activities") == 1,
          "ligado: Em atendimento e 1 Activity")
    for label in ("FEATURE_FUNNEL=false", "tenant sem settings.funnel"):
        seq, reads, stage, lookups = runs[label]
        check(seq == [coll for coll in on_seq if coll != "crm_activities"] and reads == on_reads
              and stage.get(fc.F_STAGE) == "new" and stage.get(fc.F_VERSION) == 1,
              f"{label}: mesmos writes (so sem a Activity) e as mesmas {reads} leituras de wa_contacts")
    check(runs["FEATURE_FUNNEL=false"][3] == 0, "FEATURE_FUNNEL=false: o doc do tenant nem e lido no envio")


def _fake_graph(main_mod, wamid):
    """httpx falso da Graph API + credenciais do canal; devolve (sent, restore)."""
    sent = []

    class _Resp:
        status_code = 200

        def json(self):
            return {"messages": [{"id": wamid}]}

    class _Client:
        def __init__(self, *_a, **_k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

        async def post(self, url, json=None, headers=None):
            sent.append(json)
            return _Resp()

    saved = (main_mod.httpx, main_mod.log_audit, channel_service.get_send_credentials)
    main_mod.httpx = types.SimpleNamespace(AsyncClient=_Client)
    main_mod.log_audit = lambda *a, **k: None
    channel_service.get_send_credentials = lambda cid: ("tok-4", "PNID4", "https://mock.invalid")

    def restore():
        main_mod.httpx, main_mod.log_audit, channel_service.get_send_credentials = saved

    return sent, restore


def cenario_17g_correcao():
    titulo("17g. Endpoint REAL de correcao (main.correct_message): correcao e envio humano novo ao paciente")
    try:
        import main as _main
    except Exception as exc:  # outro agente pode estar editando main.py
        check(False, f"main.py importavel ({type(exc).__name__})")
        return
    # Supervisora corrige uma mensagem da Val (contato ainda em Novo contato):
    # a correcao sai pelo CRM, com autoria humana, e conta como a 1a resposta.
    reset()
    wa_k = "5531911110206"
    seed_stage(1206, wa_k, "new", qualification="novo", last_inbound_at=NOW - timedelta(minutes=5))
    conv_k = "4__%s" % wa_k
    STORE.setdefault((TENANT, "wa_conversations"), {})[conv_k] = {
        "id": conv_k, "contact_id": 1206, "wa_id": wa_k, "channel_id": 4,
        "assigned_to": None, "assigned_to_uid": "", "unread_count": 0}
    STORE.setdefault((TENANT, "wa_messages"), {})["9001"] = {
        "id": 9001, "wa_message_id": "wamid.VAL.9001", "contact_id": 1206, "conversation_id": conv_k,
        "direction": "outbound", "msg_type": "text", "content": "Nosso endereço é Rua A, 10.",
        "sender_user_id": None, "operator_id": None, "channel_id": 4}
    sent, restore = _fake_graph(_main, "wamid.FIX.1206")
    try:
        body = _main.CorrectMessageRequest(message_id=9001, new_content="Correção: o endereço é Rua B, 20.")
        out = in_tenant(lambda: asyncio.run(_main.correct_message(body, current_user=dict(USERS["7"]))))
        raised = None
    except Exception as exc:  # noqa: BLE001
        out, raised = {}, type(exc).__name__
    finally:
        restore()
    c = contact(1206)
    new_msg = [m for m in messages_of(1206) if m.get("wa_message_id") == "wamid.FIX.1206"]
    check(raised is None and (out or {}).get("status") == "sent" and len(sent) == 1 and len(new_msg) == 1
          and new_msg[0].get("sender_user_id") == 7
          and STORE[(TENANT, "wa_messages")]["9001"].get("is_corrected") is True,
          "correcao enviada pelo CRM com autoria da supervisora; original marcada como corrigida"
          + (f" [{raised}]" if raised else ""))
    check(c.get(fc.F_STAGE) == "in_service" and c.get(fc.F_SOURCE) == "rule:human_reply"
          and set(activities()) == {auto_id(fc.AUTO_HUMAN_REPLY, 1206, 1)}
          and c.get("first_human_contact_at") is not None,
          "Em atendimento pela 1a resposta humana (mesmo sinal do first_human_contact_at legado)")


def cenario_17h_resposta_contexto_backup():
    titulo("17h. 1a resposta: sem contexto de tenant (sem fallback) e contato backup: nada")
    reset(other_funnel=FUNNEL)
    seed_stage(1244, "5531911110244", "new", tenant="")
    raised = try_call(lambda: dbf.save_wa_message(
        wa_message_id="", contact_id=1244, direction="outbound", msg_type="text", content="Olá!",
        status="sent", timestamp_wa=NOW.isoformat(), operator_id=4, channel_id=4,
        conversation_id="4__5531911110244", sender_user_id=4, sent_by_name="Operadora",
        funnel_human_reply=True))
    check(raised is None and contact(1244, tenant="").get(fc.F_STAGE) == "new"
          and len(messages_of(1244, tenant="")) == 1
          and not any(activities(t) for t in (TENANT, OTHER, "")) and LOOKUPS["funnel"] == 0,
          "sem contexto de tenant: mensagem gravada, etapa intacta, nenhuma leitura do funil (nem 'hubloc')")
    reset()
    seed_stage(1245, "5531911110245", "new", is_backup=True)
    human_send(1245, "5531911110245", funnel_human_reply=True)
    check(contact(1245).get(fc.F_STAGE) == "new" and not activities(),
          "contato backup: a resposta nao move a etapa")


def _templates_stub(main_mod, templates):
    """_load_approved_templates_for_channel falso (WABA do canal); devolve o restore."""
    saved = main_mod._load_approved_templates_for_channel

    async def _load(_channel):
        return {"templates": copy.deepcopy(templates), "waba_id": "waba-sim"}

    main_mod._load_approved_templates_for_channel = _load

    def restore():
        main_mod._load_approved_templates_for_channel = saved

    return restore


def _seed_thread(cid, wa, stage, **fields):
    seed_stage(cid, wa, stage, qualification="novo", **fields)
    conv_id = "4__%s" % wa
    STORE.setdefault((TENANT, "wa_conversations"), {})[conv_id] = {
        "id": conv_id, "contact_id": cid, "wa_id": wa, "channel_id": 4,
        "assigned_to": None, "assigned_to_uid": "", "unread_count": 0,
        "last_message_at": NOW - timedelta(days=10)}
    return conv_id


def cenario_17i_templates():
    titulo("17i. Template manual e reabertura pontual (envio de uma pessoa) movem; o lote REAL nao")
    try:
        import main as _main
    except Exception as exc:  # outro agente pode estar editando main.py
        check(False, f"main.py importavel ({type(exc).__name__})")
        return
    reopen_tpl = {"name": _main.REOPEN_TEMPLATE_NAME, "language": _main.REOPEN_TEMPLATE_LANG,
                  "category": "UTILITY", "components": [
                      {"type": "BODY", "text": "Olá {{1}}, retomando a conversa de {{2}}."},
                      {"type": "BUTTONS", "buttons": [{"text": "Retomar"}, {"text": "Encerrar"}]}]}
    service_tpl = {"name": "confirmacao_sim", "language": "pt_BR", "category": "UTILITY",
                   "components": [{"type": "BODY", "text": "Seu horário está confirmado."}]}
    user = dict(USERS["7"])

    # Template manual escolhido pela equipe (finalidade servico).
    reset()
    conv_id = _seed_thread(1250, "5531911110250", "new")
    sent, restore = _fake_graph(_main, "wamid.TPL.1250")
    restore_tpl = _templates_stub(_main, [service_tpl])
    try:
        body = _main.WaSendTemplateRequest(conversation_id=conv_id, template_name="confirmacao_sim",
                                           language="pt_BR", contact_purpose="service")
        raised = try_call(lambda: in_tenant(lambda: asyncio.run(_main.wa_send_template(body, current_user=user))))
    finally:
        restore_tpl()
        restore()
    c = contact(1250)
    check(raised is None and len(sent) == 1 and c.get(fc.F_STAGE) == "in_service"
          and c.get(fc.F_SOURCE) == "rule:human_reply"
          and set(activities()) == {auto_id(fc.AUTO_HUMAN_REPLY, 1250, 1)},
          "template manual pelo CRM (main.wa_send_template REAL): Em atendimento + Activity"
          + (f" [{raised}]" if raised else ""))

    # Reabertura PONTUAL: a pessoa da equipe reabre UM contato (reusa o
    # wa_send_template); conta como a equipe iniciando a conversa.
    for cid, wa, stage, moves in ((1251, "5531911110251", "unclassified", True),
                                  (1252, "5531911110252", "non_converted", False)):
        reset()
        conv_id = _seed_thread(cid, wa, stage)
        before = copy.deepcopy(crm(contact(cid)))
        sent, restore = _fake_graph(_main, "wamid.REOPEN.%d" % cid)
        restore_tpl = _templates_stub(_main, [reopen_tpl])
        try:
            raised = try_call(lambda: in_tenant(lambda: asyncio.run(
                _main.wa_reopen_conversation(conv_id, body=None, current_user=user))))
        finally:
            restore_tpl()
            restore()
        c = contact(cid)
        if moves:
            check(raised is None and len(sent) == 1 and c.get(fc.F_STAGE) == "in_service"
                  and c.get(fc.F_SOURCE) == "rule:human_reply" and c.get("last_reopen_template_at")
                  and (activities().get(auto_id(fc.AUTO_HUMAN_REPLY, cid, 1)) or {}).get("from_stage") == stage,
                  "reabertura pontual (main.wa_reopen_conversation REAL) de A classificar: Em atendimento"
                  + (f" [{raised}]" if raised else ""))
        else:
            check(raised is None and len(sent) == 1 and crm(c) == before and not activities(),
                  "reabertura pontual de Não convertido: template sai, etapa intacta (so a partir de Novo/A classificar)"
                  + (f" [{raised}]" if raised else ""))

    # Lote de reabertura REAL (_run_reopen_batch): o template sai com o
    # operador que disparou como autor, mas nao e atencao humana -> nada.
    reset()
    conv_id = _seed_thread(1253, "5531911110253", "new")
    plan = [dict(contact(1253), _reopen_target={"channel_id": 4, "conversation_id": conv_id,
                                                "last_message_at": NOW - timedelta(days=10)})]
    before = copy.deepcopy(crm(contact(1253)))
    sent, restore = _fake_graph(_main, "wamid.BATCH.1253")
    saved_asyncio = _main.asyncio

    async def _no_sleep(_seconds):
        return None

    _main.asyncio = types.SimpleNamespace(sleep=_no_sleep)
    try:
        raised = try_call(lambda: asyncio.run(_main._run_reopen_batch(
            TENANT, "batch-sim", plan, [], {4: copy.deepcopy(STD_CH)}, {4: copy.deepcopy(reopen_tpl)}, 7)))
    finally:
        _main.asyncio = saved_asyncio
        restore()
    batch_msgs = [m for m in messages_of(1253) if m.get("wa_message_id") == "wamid.BATCH.1253"]
    check(raised is None and len(sent) == 1 and len(batch_msgs) == 1 and batch_msgs[0].get("sender_user_id") == 7
          and crm(contact(1253)) == before and not activities()
          and (STORE.get((TENANT, "reopen_batches"), {}).get("batch-sim") or {}).get("enviados") == 1,
          "lote REAL: template enviado e gravado (autor = quem disparou), etapa intacta, sem Activity"
          + (f" [{raised}]" if raised else ""))


# Endpoints REST de envio HUMANO (main.py) que passam funnel_human_reply=True.
HUMAN_SEND_ENDPOINTS = {"wa_send", "wa_send_media", "wa_send_audio", "wa_send_location",
                        "wa_send_template", "correct_message"}


class _SaveCalls(ast.NodeVisitor):
    """(funcao mais interna, linha, valor de funnel_human_reply|None) de cada
    chamada save_wa_message(...) do arquivo."""

    def __init__(self):
        self.stack = []
        self.calls = []

    def visit_FunctionDef(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node):
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if name == "save_wa_message":
            kw = next((k for k in node.keywords if k.arg == "funnel_human_reply"), None)
            self.calls.append((self.stack[-1] if self.stack else "<modulo>", node.lineno,
                               ast.unparse(kw.value) if kw is not None else None))
        self.generic_visit(node)


def _save_calls(path):
    visitor = _SaveCalls()
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    with warnings.catch_warnings():
        # Docstring alheia com escape invalido (SyntaxWarning) nao e assunto do gate.
        warnings.simplefilter("ignore", SyntaxWarning)
        visitor.visit(ast.parse(source, filename=path))
    return visitor.calls


def cenario_18_chamadas_de_envio():
    titulo("18. Gate estatico: SO os endpoints de envio humano passam funnel_human_reply=True")
    try:
        main_calls = _save_calls(os.path.join(ROOT, "main.py"))
    except (OSError, SyntaxError) as exc:  # outro agente pode estar editando main.py
        check(False, f"main.py legivel ({type(exc).__name__})")
        return
    human = [c for c in main_calls if c[0] in HUMAN_SEND_ENDPOINTS]
    others = [c for c in main_calls if c[0] not in HUMAN_SEND_ENDPOINTS]
    check({c[0] for c in human} == HUMAN_SEND_ENDPOINTS and all(c[2] == "True" for c in human),
          "texto, midia, audio, localizacao, template manual e correcao passam True (%d chamadas)" % len(human))
    check(others and all(c[2] in (None, "False") for c in others),
          "lote, recibo, aviso do takeover e demais envios de main.py nao passam (%s)"
          % ", ".join(sorted({c[0] for c in others})))
    files = [os.path.join(ROOT, f) for f in os.listdir(ROOT) if f.endswith(".py") and f != "main.py"]
    scripts = os.path.join(ROOT, "scripts")
    files += [os.path.join(scripts, f) for f in os.listdir(scripts) if f.endswith(".py")]
    bad = []
    for path in files:
        try:
            calls = _save_calls(path)
        except (OSError, SyntaxError):
            continue  # arquivo em edicao por outro agente; main.py e o alvo
        bad += ["%s:%d" % (os.path.basename(path), line) for (_f, line, val) in calls if val not in (None, "False")]
    check(not bad, "webhook (eco/history), bot, bot_sender, database e scripts nunca passam o kwarg (%s)"
          % (", ".join(bad) or "nenhum"))
    # Ninguem reaproveita um endpoint de envio humano por dentro (cron, lote,
    # follow-up automatico, webhook): o unico chamador interno e a reabertura
    # PONTUAL, que tambem e um POST de uma pessoa da equipe.
    callers = []
    for path in [os.path.join(ROOT, "main.py")] + files:
        try:
            callers += [(os.path.basename(path), caller, callee)
                        for caller, callee in _endpoint_calls(path, HUMAN_SEND_ENDPOINTS)]
        except (OSError, SyntaxError):
            continue
    check(callers == [("main.py", "wa_reopen_conversation", "wa_send_template")],
          "chamador interno dos endpoints de envio humano: so a reabertura pontual (%s)"
          % ", ".join("%s:%s->%s" % c for c in callers))


def _endpoint_calls(path, names):
    """(funcao chamadora, endpoint chamado) para cada chamada a um dos `names`."""
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        tree = ast.parse(source, filename=path)
    found = []

    class _V(ast.NodeVisitor):
        def __init__(self):
            self.stack = []

        def visit_FunctionDef(self, node):
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Call(self, node):
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name in names:
                found.append((self.stack[-1] if self.stack else "<modulo>", name))
            self.generic_visit(node)

    _V().visit(tree)
    return found


def cenario_20_ver_como():
    titulo("20. Ver como (sessao VALIDA de visualizacao): nenhuma rota de envio humano passa do middleware")
    try:
        import main as _main
        import firebase_admin_client as _fac
        from starlette.requests import Request
        from starlette.responses import StreamingResponse
    except Exception as exc:  # outro agente pode estar editando main.py
        check(False, f"main.py importavel ({type(exc).__name__})")
        return
    names = HUMAN_SEND_ENDPOINTS | {"wa_reopen_conversation"}
    routes = {}
    for route in _main.app.routes:
        name = getattr(getattr(route, "endpoint", None), "__name__", "")
        if name in names:
            routes[name] = (route.path, set(getattr(route, "methods", None) or ()))
    check(set(routes) == names and all(methods == {"POST"} for _p, methods in routes.values()),
          "envio humano = %d rotas POST (%s)" % (len(routes), ", ".join(sorted(p for p, _m in routes.values()))))
    check(not {p for p, _m in routes.values()} & set(_main._IMPERSONATE_READ_POSTS),
          "nenhuma rota de envio na allowlist de POSTs de leitura do Ver como")

    reset()
    wa = "5531911110260"
    conv_id = _seed_thread(1260, wa, "new")
    before = copy.deepcopy(contact(1260))
    imp = {"uid": "imp_ro_" + "a" * 32, "imp": True, "tenant_id": TENANT, "imp_sid": "a" * 32,
           "perfil_acesso_id": "perfil_sim"}
    normal = {"uid": "uid-7", "tenant_id": TENANT}
    token = {"decoded": None}
    executed = []

    async def _endpoint(_request):
        # Como o call_next real: corpo em stream (o middleware o consome na
        # revalidacao final de uma sessao de visualizacao).
        executed.append(firestore_common.get_tenant_context())
        return StreamingResponse(iter([b'{"reached":true}']), media_type="application/json")

    def _request(path):
        return Request({"type": "http", "method": "POST", "path": path,
                        "headers": [(b"authorization", b"Bearer sim-token")], "query_string": b"",
                        "scheme": "http", "server": ("sim.local", 80), "client": ("127.0.0.1", 1)})

    keys = ("FEATURE_IMPERSONATE", "is_impersonation_token", "valid_impersonation_subject",
            "validate_impersonation_claims", "validate_session", "read_impersonation_toggles")
    saved = {k: getattr(_main, k) for k in keys}
    saved_verify = _fac.verify_firebase_id_token
    # Sessao de visualizacao VALIDA (flag ligada, registro ativo, claims ok):
    # o pior caso; so a trava de metodo/rota do middleware fica de pe.
    _main.FEATURE_IMPERSONATE = True
    _main.is_impersonation_token = lambda d: bool((d or {}).get("imp"))
    _main.valid_impersonation_subject = lambda d: True
    _main.validate_impersonation_claims = lambda d: True
    _main.validate_session = lambda d: {"sid": (d or {}).get("imp_sid"), "status": "active"}
    _main.read_impersonation_toggles = lambda tid, pid: {}
    _fac.verify_firebase_id_token = lambda _tok: copy.deepcopy(token["decoded"])
    blocked, passed = [], []
    try:
        for name, (path, _m) in sorted(routes.items()):
            real_path = path.replace("{conversation_id}", conv_id)
            for decoded, sink in ((imp, blocked), (normal, passed)):
                token["decoded"] = decoded
                executed.clear()
                WRITES.clear()
                try:
                    resp = asyncio.run(_main.tenant_context_middleware(_request(real_path), _endpoint))
                    code = resp.status_code
                except Exception as exc:  # noqa: BLE001 - falha do middleware vira check, nao traceback
                    code = type(exc).__name__
                sink.append((name, code, list(executed), len(WRITES)))
    finally:
        for k, v in saved.items():
            setattr(_main, k, v)
        _fac.verify_firebase_id_token = saved_verify
    check(len(blocked) == len(routes) and all(code == 403 and not ran and not nw for _n, code, ran, nw in blocked),
          "Ver como: 403 nas %d rotas de envio humano, endpoint nunca executado e nenhum write" % len(blocked))
    check(contact(1260) == before and not activities() and not messages_of(1260),
          "Ver como: contato, etapa, mensagens e Activities intactos")
    check(len(passed) == len(routes) and all(ran == [TENANT] for _n, _c, ran, _w in passed),
          "controle: o mesmo middleware com token normal chega ao endpoint no tenant do usuario")


def _reopen_click(wa, mid):
    """Clique no botao [Continuar] do template de reabertura (quick-reply)."""
    return {"from": wa, "id": mid, "type": "button", "timestamp": unix(NOW - timedelta(seconds=5)),
            "button": {"payload": "Continuar", "text": "Continuar"}}


def _seed_reopen_lead(cid, wa):
    """Lead antigo em fase de bot (sem dono, bot_completed False, LGPD ja
    aceita), sem etapa, com a thread fechada por inatividade que recebeu o
    template de reabertura."""
    seed_contact(cid, wa, qualification="novo", bot_completed=False, assigned_to=None,
                 last_reopen_template_at=NOW - timedelta(hours=1))
    conv_id = "4__%s" % wa
    STORE.setdefault((TENANT, "wa_conversations"), {})[conv_id] = {
        "id": conv_id, "contact_id": cid, "channel_id": 4, "wa_id": wa,
        "attendance_status": "fechado_inatividade", "assigned_to": None, "assigned_to_uid": "",
        "source_channel_type": "standard", "is_backup": False}
    STORE.setdefault((TENANT, "bot_states"), {})[str(cid)] = {
        "step": "cx", "lgpd_consent": True, "lgpd_status": "accepted"}
    return conv_id


def _continuar_run(cid, wa, feature=True, fail_turn=False, sent=None):
    """Um clique [Continuar] pelo _process_messages REAL com o motor CX ativo
    no tenant (settings.ai) e o despachante real do bot; so o envio da
    resposta e trocado. fail_turn = o turno sintetico do agente levanta."""
    reset(feature=feature)
    TENANT_DOCS[TENANT]["settings"]["ai"] = copy.deepcopy(AI_CFG)
    conv_id = _seed_reopen_lead(cid, wa)
    if fail_turn:
        async def _boom(*_a, **_k):
            raise RuntimeError("motor CX fora (simulado)")
        webhook.process_bot_message_async = _boom
    else:
        webhook.process_bot_message_async = bot_service.process_bot_message_async
        CX_SCRIPT.append(copy.deepcopy(HANDOFF_REPLY))
    if sent is not None:
        sent.clear()
    deliver([_reopen_click(wa, "w.21.%d" % cid)])
    return conv_id


def cenario_21_continuar_agente():
    titulo("21. [Continuar] da reabertura devolvido ao agente (develop) com o funil ligado")
    saved = {name: getattr(webhook, name) for name in ("process_bot_message_async", "_send_bot_reply")}
    sent = []

    async def _send(*args, **kwargs):
        sent.append(args[1] if len(args) > 1 else kwargs.get("reply"))

    webhook._send_bot_reply = _send
    try:
        wa = "5531911110301"
        conv_id = _continuar_run(9101, wa, sent=sent)
        c = contact(9101)
        acts = activities_of(9101)
        stage_writes = [d for d, _m in contact_writes(9101) if crm(d)]
        check(in_tenant(webhook._tenant_bot_engine_is_cx) and STORE[(TENANT, "wa_conversations")][conv_id]
              ["attendance_status"] == "aberto", "motor CX ativo no tenant e a thread reaberta pelo clique")
        check(len(stage_writes) == 2 and stage_writes[0][fc.F_STAGE] == "unclassified"
              and stage_writes[0][fc.F_SOURCE] == "intake" and stage_writes[0][fc.F_VERSION] == 1
              and set(crm(stage_writes[0])) == set(fc.CONTACT_STAGE_FIELDS),
              "o clique entra por _process_messages: lead antigo sem etapa vai para A classificar (intake)")
        check(CX_CALLS == [config.REOPEN_RESUME_BOT_TEXT] and CX_PARAMS[0].get("origem") == "retomada_lote"
              and sent == [HANDOFF_REPLY["reply_text"]],
              "turno sintetico do agente (origem=retomada_lote) e a resposta enviada")
        check(c[fc.F_STAGE] == "in_service" and c[fc.F_VERSION] == 2 and c[fc.F_SOURCE] == "rule:handoff"
              and c.get("bot_completed") is True and c.get("qualification") == "novo",
              "handoff no turno do Continuar: A classificar -> Em atendimento (qualification intocada)")
        check(len(acts) == 1 and acts[0]["id"] == auto_id("handoff", 9101, 1) == c[fc.F_ACTIVITY]
              and (acts[0]["from_stage"], acts[0]["to_stage"]) == ("unclassified", "in_service")
              and acts[0]["data"].get("rule") == "handoff",
              "1 Activity da automacao (handoff) apontada pelo contato")
        before, calls, n_acts, n_msgs = copy.deepcopy(crm(c)), len(CX_CALLS), len(acts), len(messages_of(9101))
        WRITES.clear()
        deliver([_reopen_click(wa, "w.21.9101")])
        check(crm(contact(9101)) == before and len(CX_CALLS) == calls and len(activities_of(9101)) == n_acts
              and len(sent) == 1 and not [d for d, _m in contact_writes(9101) if crm(d)],
              "reentrega do MESMO clique (was_dup): nenhum turno, Activity, envio ou crm_* a mais")
        check(not writes_in("wa_conversations") and len(messages_of(9101)) == n_msgs,
              "reentrega nao reprocessa o botao: thread nao regravada e nenhum aviso de sistema novo")
        # Controle: funil desligado = o mesmo fluxo do develop, sem crm_* nem Activity.
        _continuar_run(9102, "5531911110302", feature=False, sent=sent)
        off = contact(9102)
        check(not crm(off) and not activities_of(9102) and off.get("bot_completed") is True
              and CX_CALLS == [config.REOPEN_RESUME_BOT_TEXT] and len(sent) == 1,
              "funil desligado: mesmo Continuar (turno + handoff), sem crm_* e sem Activity")
        # Turno do agente falhando: cai na equipe (mark_contact_bot_done) e a
        # etapa da entrada fica; o carimbo nao escreve crm_*.
        _continuar_run(9103, "5531911110303", fail_turn=True, sent=sent)
        failed = contact(9103)
        done = [d for d, m in contact_writes(9103) if m and d.get("bot_completed") is True]
        check(failed[fc.F_STAGE] == "unclassified" and failed[fc.F_VERSION] == 1 and failed[fc.F_SOURCE] == "intake"
              and failed.get("bot_completed") is True and not activities_of(9103) and not CX_CALLS and not sent,
              "turno falhando: lead fica em A classificar, cai na equipe, sem Activity nem envio")
        check(done == [{"bot_completed": True}], "mark_contact_bot_done grava so bot_completed (nada de crm_*)")
    finally:
        for name, value in saved.items():
            setattr(webhook, name, value)


_SENTINEL_MODULE = "google.cloud.firestore"
_COHORT_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_INTAKE_SOURCES = {"intake", "graduation"}
_AUTO_SOURCES = {fc.SOURCE_RULE_PREFIX + ev for ev in fc.AUTO_EVENTS}


def _sentinels(value):
    if isinstance(value, dict):
        return [s for v in value.values() for s in _sentinels(v)]
    return [value] if type(value).__module__.startswith(_SENTINEL_MODULE) else []


def cenario_19_tipos():
    titulo("19. Varredura de TODOS os writes da execucao: tipos dos crm_* e das Activities")
    rows = [(t, coll, did, data) for (t, coll, did, data, _m) in ALL_WRITES if crm(data)]
    intake = [r for r in rows if r[3].get(fc.F_SOURCE) in _INTAKE_SOURCES]
    autos = [r for r in rows if r[3].get(fc.F_SOURCE) in _AUTO_SOURCES]
    check(len(intake) >= 20 and len(autos) >= 10,
          f"varredura nao vazia ({len(intake)} entradas, {len(autos)} automacoes)")
    check(len(intake) + len(autos) == len(rows),
          "todo write com crm_* e entrada automatica ou automacao (source no vocabulario)")
    check(not [s for _t, _c, _d, data in rows for s in _sentinels(crm(data))],
          "nenhum sentinela (SERVER_TIMESTAMP/Increment/DELETE_FIELD/ArrayUnion) em crm_*")
    bad_dates = [k for _t, _c, _d, data in rows for k, v in crm(data).items()
                 if k.endswith("_at") and not is_aware_dt(v)]
    check(not bad_dates, "crm_*_at sempre datetime com fuso (nunca string/None/ingenuo)")
    check(all(set(crm(data)) == set(fc.CONTACT_STAGE_FIELDS) for _t, _c, _d, data in intake),
          "entrada grava o conjunto completo de campos da etapa (secao 1)")
    check(all(AUTO_FIELDS <= set(crm(data)) <= set(fc.CONTACT_STAGE_FIELDS)
              and (fc.F_ENTERED_AT in data) == (fc.F_COHORT in data) for _t, _c, _d, data in autos),
          "automacao: campos da etapa; entrada e coorte so juntas (e so quando ausentes)")
    check(all(isinstance(data[fc.F_VERSION], int) and not isinstance(data[fc.F_VERSION], bool)
              and data[fc.F_VERSION] >= 1 for _t, _c, _d, data in rows), "versao int >= 1")
    check(all(isinstance(data[fc.F_MAX_ORDER], int) and not isinstance(data[fc.F_MAX_ORDER], bool)
              for _t, _c, _d, data in rows), "crm_max_reached_order int")
    check(all(_COHORT_RE.match(str(data[fc.F_COHORT])) for _t, _c, _d, data in rows if fc.F_COHORT in data),
          "coorte 'AAAA-MM'")
    check(all((data[fc.F_BY_USER] is None or (isinstance(data[fc.F_BY_USER], int)
                                              and not isinstance(data[fc.F_BY_USER], bool)))
              and isinstance(data[fc.F_BY_UID], str) and data[fc.F_ACTIVITY] is None
              for _t, _c, _d, data in intake),
          "entrada: autor user_id int|None e uid str; sem Activity (activity_id None)")
    check(all(data[fc.F_BY_USER] is None and data[fc.F_BY_UID] == ""
              and str(data[fc.F_ACTIVITY]).startswith("stage_auto_") for _t, _c, _d, data in autos),
          "automacao: sem autor humano e activity_id stage_auto_*")
    check(all(coll == "wa_contacts" for _t, coll, _d, _data in rows), "crm_* so em wa_contacts")
    acts = [(t, did, data, m) for (t, coll, did, data, m) in ALL_WRITES if coll == "crm_activities"]
    check(len(acts) >= 10 and all(did == data.get("id") and did.startswith("stage_auto_") and m is False
                                  and t == data.get("tenant_id") and set(data) == ACTIVITY_KEYS
                                  for t, did, data, m in acts),
          f"Activities ({len(acts)}): id = doc, stage_auto_*, set sem merge, no tenant do proprio doc, so as chaves do contrato")
    check(all(is_aware_dt(data["occurred_at"]) and is_aware_dt(data["recorded_at"])
              and isinstance(data["contact_id"], int) and not isinstance(data["contact_id"], bool)
              and not _sentinels(data) and data["event_type"] == fc.EVENT_CHANGED
              and data["actor_type"] == "system" and data["data"].get("source") in _AUTO_SOURCES
              for _t, _did, data, _m in acts),
          "Activities: datas com fuso, contact_id int, sem sentinela, crm_stage_changed de sistema")


def main():
    install()
    cenario_00_ambiente()
    cenario_01_flag_desligada()
    cenario_02_contato_novo()
    cenario_03_coorte_fuso()
    cenario_04_agenda_depois_ao_vivo()
    cenario_05_contato_antigo()
    cenario_06_etapa_existente()
    cenario_07_eco_agenda_history()
    cenario_08_clique_controle()
    cenario_09_backup_lgpd()
    cenario_10_canais()
    cenario_11_tipos()
    cenario_12_falhas()
    cenario_13_reentrega()
    cenario_14_manual()
    cenario_15_graduacao()
    cenario_16_handoff()
    cenario_16i_caminhos_cx()
    cenario_16j_caminhos_builtin()
    cenario_16k_handoff_robustez()
    cenario_17_resposta_humana()
    cenario_17f_resposta_falhas()
    cenario_17g_correcao()
    cenario_17h_resposta_contexto_backup()
    cenario_17i_templates()
    cenario_18_chamadas_de_envio()
    cenario_20_ver_como()
    cenario_21_continuar_agente()
    cenario_19_tipos()  # por ultimo: varre os writes de TODOS os cenarios
    print("\n" + "=" * 70)
    if FAILS:
        print(f"FALHOU: {len(FAILS)} de {CHECKS} asserts")
        for f in FAILS:
            print(f"  - {f}")
        sys.exit(1)
    print(f"OK: {CHECKS} asserts")
    sys.exit(0)


if __name__ == "__main__":
    main()
