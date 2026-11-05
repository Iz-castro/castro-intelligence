# -*- coding: utf-8 -*-
"""Exercita repository e service REAIS do funil com Firestore em memoria.

Sem ADC, rede, agente CX ou WhatsApp. Reais: funnel_repository,
funnel_service, funnel_catalog, followup_access.build_authorizer, RBAC e o
predicado main._require_contact_access. Cobre tambem as decisoes do PO de
28/10: etapas do clinic_v1, coluna Novo contato so com
ver_contatos_agente_funil, desfecho legado gravado junto da mudanca manual
("uma classificacao so"), os nomes/textos que a clinica edita (tela
"Etapas") e o desfecho do "Encerrar atendimento" pela funcao compartilhada
funnel_service.close_attendance_outcome (o endpoint main.wa_set_attendance
inteiro, com notas, tags e mensagens, roda no sim_funnel_api pelo main.app).
O fake (deste simulador e do sim_funnel_api) imita as restricoes do
Firestore que importam aqui: tipos
distintos nao se igualam (0 != False), campo ausente nao casa filtro nem
ordem, 'in' (1..30 valores), count() agregado, range num campo so,
order_by multiplo com __name__ implicito, start_after por dict de valores,
set com merge, create duplicado = erro, leitura apos escrita na transacao =
erro e contencao (leitura mudou antes do commit) = Aborted com retry.

Rodar na raiz do worktree:
    C:\\Rafael\\castro-intelligence\\.venv\\Scripts\\python.exe tools\\sim_funnel_flow.py
Sai 0 quando todos os checks passam; 1 caso contrario.
"""

import copy
import functools
import hashlib
import json
import math
import os
import sys
import threading
import traceback
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from fastapi import HTTPException  # noqa: E402
from google.api_core import exceptions as google_exceptions  # noqa: E402

import config  # noqa: E402
import firestore_common as common  # noqa: E402
import followup_access as access  # noqa: E402
import funnel_catalog as fc  # noqa: E402
import funnel_repository as repository_module  # noqa: E402
import funnel_service as service_module  # noqa: E402
import rbac  # noqa: E402
import tenant_service  # noqa: E402
import main  # noqa: E402  (predicado real _require_contact_access)
from funnel_repository import FunnelRepository  # noqa: E402
from funnel_routes import parse_stage_body  # noqa: E402
from funnel_service import FunnelService  # noqa: E402


TENANT = "clinic_test"
OTHER_TENANT = "other_tenant"
GLOBAL = "__global__"
BASE_NOW = datetime(2026, 10, 19, 15, 0, tzinfo=timezone.utc)  # segunda, 12h em Sao Paulo
NOW = [BASE_NOW]

DATA = {}
REVISIONS = {}
LOCK = threading.RLock()
QUERY_LOG = []
WRITES = []
BEFORE_TRANSACTION = []
BEFORE_COMMIT = []
FORCE_ABORT = [0]
PROFILES = {}
TENANTS = {}
AUDIT = []
MAX_ATTEMPTS = 5
CHECKS = [0]

ALICE = {"id": 1, "firebase_uid": "alice", "tenant_id": TENANT, "role": "operador",
         "perfil_acesso_id": "op_move", "display_name": "Operadora Alice"}
BOB = {"id": 2, "firebase_uid": "bob", "tenant_id": TENANT, "role": "operador",
       "display_name": "Operador Bob"}
MANAGER = {"id": 3, "firebase_uid": "manager", "tenant_id": TENANT, "role": "supervisor",
           "display_name": "Supervisora Sintetica"}
CAROL = {"id": 5, "firebase_uid": "carol", "tenant_id": TENANT, "role": "operador",
         "perfil_acesso_id": "op_no_followup", "display_name": "Operadora Carol"}
NODASH = {"id": 6, "firebase_uid": "nodash", "tenant_id": TENANT, "role": "supervisor",
          "perfil_acesso_id": "sup_no_dash", "display_name": "Supervisor sem painel"}
# Operadora com a coluna do agente de IA liberada (e follow-up), sem mover.
EVE = {"id": 4, "firebase_uid": "eve", "tenant_id": TENANT, "role": "operador",
       "perfil_acesso_id": "op_agent", "display_name": "Operadora Eve"}
# Supervisao com a coluna do agente de IA desligada no perfil.
SUPNOAGENT = {"id": 10, "firebase_uid": "sup-no-agent", "tenant_id": TENANT, "role": "supervisor",
              "perfil_acesso_id": "sup_no_agent", "display_name": "Supervisora sem Val"}
# Admin (perfil de sistema): unico com gerenciar_config_sistema no seed.
ADMIN = {"id": 9, "firebase_uid": "admin", "tenant_id": TENANT, "role": "admin",
         "display_name": "Admin Sintetica"}
USERS = (ALICE, BOB, MANAGER, EVE, CAROL, NODASH, SUPNOAGENT, ADMIN)
TENANT_DOC = {"id": TENANT, "settings": {"funnel": {"enabled": True, "template": "clinic_v1", "version": 3},
                                         "ai": {}}}
CATALOG = fc.funnel_for_tenant(TENANT_DOC)
CARD_KEYS = {"contact_id", "display_name", "lead_temperature", "lead_temperature_at", "stage", "stage_version",
             "stage_changed_at", "stage_source", "owner", "last_inbound_at", "last_activity_at", "signals",
             "badges", "reason", "next_task", "tasks_visible"}
CONFIG_STAGE_KEYS = {"key", "label", "kind", "order", "requires_reason", "manual_target", "milestone",
                     "appointment_kind", "stale", "description", "active", "close_outcome",
                     "legacy_qualification", "visibility_permission", "visible", "default_label",
                     "default_description"}
# Escrita da etapa no contato: crm_* + o desfecho legado equivalente.
CONTACT_WRITE_FIELDS = set(fc.CONTACT_STAGE_FIELDS) | set(repository_module.LEGACY_FIELDS)
LEGACY_BY_STAGE = {"in_service": "em_atendimento", "awaiting_followup": "nao_convertido",
                   "scheduled": "convertido", "loyal": "convertido", "non_converted": "nao_convertido",
                   "disqualified": "nao_qualificado"}


# ---------------------------------------------------------------------------
# Firestore em memoria
# ---------------------------------------------------------------------------

def _ftype(value):
    # Ordem de tipos do Firestore: null < bool < numero < timestamp < texto < ref.
    if value is None:
        return 0
    if isinstance(value, bool):
        return 1
    if isinstance(value, (int, float)):
        return 2
    if isinstance(value, datetime):
        return 3
    if isinstance(value, str):
        return 4
    if isinstance(value, Reference):
        return 5
    return 9


def _norm(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    if isinstance(value, Reference):
        return value.id
    return value


def _sort_key(value):
    return (_ftype(value), _norm(value))


def _same(actual, expected):
    return _ftype(actual) == _ftype(expected) and _norm(actual) == _norm(expected)


def _compare(actual, operator, expected):
    if operator == "==":
        return _same(actual, expected)
    if operator == "in":
        return any(_same(actual, item) for item in expected)
    if _ftype(actual) != _ftype(expected) or _ftype(actual) not in (2, 3, 4):
        return False
    left, right = _norm(actual), _norm(expected)
    return {"<": left < right, "<=": left <= right, ">": left > right, ">=": left >= right}[operator]


class Snapshot:
    def __init__(self, reference, value):
        self.reference = reference
        self.id = reference.id
        self.exists = value is not None
        self._value = copy.deepcopy(value)

    def to_dict(self):
        return copy.deepcopy(self._value)


class Reference:
    def __init__(self, tenant, name, doc_id):
        self.tenant, self.name = tenant, name
        self.id = str(doc_id)
        self.key = (tenant, name, self.id)

    def get(self, transaction=None):
        with LOCK:
            if transaction is not None:
                if transaction.writes:
                    raise AssertionError("Firestore nao permite leitura depois de escrita na transacao")
                transaction.reads[self.key] = REVISIONS.get(self.key, 0)
            else:
                QUERY_LOG.append({"collection": self.name, "kind": "get"})
            return Snapshot(self, DATA.get(self.key))


class AggregateQuery:
    def __init__(self, query):
        self.query = query

    def get(self, transaction=None):
        QUERY_LOG.append({"collection": self.query.name, "kind": "count",
                          "filters": [(f, o) for f, o, _ in self.query.filters]})
        return [[SimpleNamespace(alias="n", value=len(self.query._rows()))]]


class Query:
    def __init__(self, tenant, name):
        self.tenant, self.name = tenant, name
        self.filters, self.orders = [], []
        self.cap, self.after = None, None

    def _copy(self, **changes):
        clone = copy.copy(self)
        for key, value in changes.items():
            setattr(clone, key, value)
        return clone

    def where(self, field, operator, value):
        assert operator in ("==", "in", "<", "<=", ">", ">="), "operador nao suportado: %s" % operator
        if operator == "in":
            assert isinstance(value, list) and 0 < len(value) <= 30, "'in' exige lista de 1 a 30 valores"
        return self._copy(filters=self.filters + [(field, operator, value)])

    def order_by(self, field, direction=None):
        return self._copy(orders=self.orders + [(field, direction == "DESCENDING")])

    def limit(self, value):
        return self._copy(cap=value)

    def start_after(self, values):
        assert isinstance(values, dict), "start_after por valores (dict)"
        return self._copy(after=dict(values))

    def count(self, alias=None):
        return AggregateQuery(self)

    def _effective_orders(self):
        ranges = [field for field, operator, _ in self.filters if operator in ("<", "<=", ">", ">=")]
        assert len(set(ranges)) <= 1, "range em mais de um campo"
        orders = list(self.orders)
        if ranges and orders:
            assert orders[0][0] == ranges[0], "1o order_by precisa ser o campo do range"
        if ranges and not orders:
            orders = [(ranges[0], False)]
        if not any(field == "__name__" for field, _ in orders):
            orders.append(("__name__", orders[-1][1] if orders else False))
        return orders

    def _rows(self):
        orders = self._effective_orders()
        with LOCK:
            items = [(key[2], copy.deepcopy(value)) for key, value in DATA.items()
                     if key[0] == self.tenant and key[1] == self.name]
        rows = []
        for doc_id, value in items:
            if not all(field in value and _compare(value[field], operator, expected)
                       for field, operator, expected in self.filters):
                continue
            if not all(field == "__name__" or field in value for field, _ in orders):
                continue
            rows.append((doc_id, value))

        def key_for(row, field):
            return (5, row[0]) if field == "__name__" else _sort_key(row[1][field])

        for field, descending in reversed(orders):
            rows.sort(key=lambda row: key_for(row, field), reverse=descending)
        if self.after is not None:
            def beyond(row):
                for field, descending in orders:
                    assert field in self.after, "start_after sem o campo %s" % field
                    expected = self.after[field]
                    wanted = ((5, expected.id if isinstance(expected, Reference) else str(expected))
                              if field == "__name__" else _sort_key(expected))
                    actual = key_for(row, field)
                    if actual != wanted:
                        return actual < wanted if descending else actual > wanted
                return False
            rows = [row for row in rows if beyond(row)]
        return rows

    def stream(self, transaction=None):
        assert self.cap is not None, "Query sem limite"
        if transaction is not None and transaction.writes:
            raise AssertionError("Firestore nao permite leitura depois de escrita na transacao")
        QUERY_LOG.append({"collection": self.name, "kind": "stream", "limit": self.cap,
                          "filters": [(f, o) for f, o, _ in self.filters]})
        rows = self._rows()[:self.cap]
        return iter([Snapshot(Reference(self.tenant, self.name, doc_id), value) for doc_id, value in rows])


def firestore_compat(value, path="doc", in_array=False):
    """Tipos que o Firestore grava (sem Sentinel/Increment, datetime com fuso)."""
    if value is None or isinstance(value, (bool, int, float, str, bytes)):
        return
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise AssertionError("Firestore fake: datetime sem fuso em %s" % path)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise AssertionError("Firestore fake: chave invalida em %s: %r" % (path, key))
            firestore_compat(item, "%s.%s" % (path, key))
        return
    if isinstance(value, (list, tuple)):
        if in_array:
            raise AssertionError("Firestore fake: lista dentro de lista em %s" % path)
        for index, item in enumerate(value):
            firestore_compat(item, "%s[%d]" % (path, index), in_array=True)
        return
    raise AssertionError("Firestore fake: tipo %s nao gravavel em %s" % (type(value).__name__, path))


def _deep_merge(base, update):
    result = copy.deepcopy(base)
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


class Transaction:
    def __init__(self):
        self.reads = {}
        self.writes = []

    def set(self, reference, value, merge=False):
        firestore_compat(value, "/".join(reference.key))
        self.writes.append(("set", reference.key, copy.deepcopy(value), bool(merge)))

    def create(self, reference, value):
        firestore_compat(value, "/".join(reference.key))
        self.writes.append(("create", reference.key, copy.deepcopy(value), False))


def _commit(transaction):
    with LOCK:
        if FORCE_ABORT[0] > 0:
            FORCE_ABORT[0] -= 1
            raise google_exceptions.Aborted("contencao simulada")
        for key, revision in transaction.reads.items():
            if REVISIONS.get(key, 0) != revision:
                raise google_exceptions.Aborted("documento lido mudou antes do commit")
        for kind, key, _, _ in transaction.writes:
            if kind == "create" and key in DATA:
                raise google_exceptions.AlreadyExists("create duplicado")
        for kind, key, value, merge in transaction.writes:
            DATA[key] = _deep_merge(DATA.get(key) or {}, value) if merge else copy.deepcopy(value)
            REVISIONS[key] = REVISIONS.get(key, 0) + 1
            WRITES.append({"key": key, "kind": kind, "merge": merge, "fields": sorted(value)})


def transactional(fn):
    """Mesmo contrato do google.cloud.firestore.transactional: re-executa em
    Aborted ate MAX_ATTEMPTS e entao ValueError(...) from Aborted."""
    @functools.wraps(fn)
    def wrapped(transaction, *args, **kwargs):
        while BEFORE_TRANSACTION:
            BEFORE_TRANSACTION.pop(0)()
        last = None
        for attempt in range(MAX_ATTEMPTS):
            current = transaction if attempt == 0 else Transaction()
            current.reads, current.writes = {}, []
            result = fn(current, *args, **kwargs)
            while BEFORE_COMMIT:
                BEFORE_COMMIT.pop(0)()
            try:
                _commit(current)
                return result
            except google_exceptions.Aborted as exc:
                last = exc
        raise ValueError("Failed to commit transaction in %d attempts." % MAX_ATTEMPTS) from last
    wrapped.to_wrap = fn
    return wrapped


class Client:
    def transaction(self):
        return Transaction()

    def get_all(self, references, transaction=None):
        refs = list(references)
        QUERY_LOG.append({"collection": refs[0].name if refs else "", "kind": "get_all", "size": len(refs)})
        with LOCK:
            return iter([Snapshot(ref, DATA.get(ref.key)) for ref in refs])


CLIENT = Client()


def put(name, doc_id, value, tenant=TENANT):
    key = (tenant, name, str(doc_id))
    with LOCK:
        DATA[key] = copy.deepcopy(value)
        REVISIONS[key] = REVISIONS.get(key, 0) + 1


def doc(name, doc_id, tenant=TENANT):
    return copy.deepcopy(DATA.get((tenant, name, str(doc_id))))


def bump(name, doc_id, tenant=TENANT, **fields):
    """Escrita de 'outro processo' fora da transacao em teste."""
    key = (tenant, name, str(doc_id))
    with LOCK:
        DATA[key] = {**(DATA.get(key) or {}), **copy.deepcopy(fields)}
        REVISIONS[key] = REVISIONS.get(key, 0) + 1


# Lookups implicitos do CRM (o autorizador roda sob tenant_context).
def enriched_contact(contact_id):
    tenant = common.get_tenant_context()
    row = copy.deepcopy(DATA.get((tenant, "wa_contacts", str(contact_id))))
    if row is None:
        return None
    row.setdefault("id", int(contact_id))
    owner = DATA.get((tenant, "users", str(row.get("assigned_to")))) if row.get("assigned_to") is not None else None
    row["assigned_name"] = (owner or {}).get("display_name", "")
    row["assigned_to_uid"] = row.get("assigned_to_uid", "") or (owner or {}).get("firebase_uid", "")
    return common.normalize_record(row)


def conversation_by_id(conversation_id):
    row = copy.deepcopy(DATA.get((common.get_tenant_context(), "wa_conversations", str(conversation_id))))
    if row is None:
        return None
    row.setdefault("id", str(conversation_id))
    return common.normalize_record(row)


def channel_by_id(channel_id):
    QUERY_LOG.append({"collection": "channels", "kind": "channel"})
    row = DATA.get((GLOBAL, "channels", str(channel_id)))
    return common.normalize_record(copy.deepcopy(row)) if row else None


def thread_messages(contact_id, limit=50, offset=0, conversation_id=None):
    tenant = common.get_tenant_context()
    rows = [copy.deepcopy(row) for key, row in DATA.items()
            if key[0] == tenant and key[1] == "wa_messages" and row.get("contact_id") == contact_id
            and (not conversation_id or row.get("conversation_id") == conversation_id)]
    rows.sort(key=lambda row: row["timestamp_wa"], reverse=True)
    return [common.normalize_record(row) for row in reversed(rows[:limit])]


def install():
    repository_module.tenant_collection = lambda tenant, name: Query(tenant, name)
    repository_module.tenant_document = lambda tenant, name, doc_id: Reference(tenant, name, doc_id)
    repository_module.get_firestore_client = lambda: CLIENT
    repository_module.firestore = SimpleNamespace(transactional=transactional)
    repository_module.RECORD_SHAPES = True
    access.tenant_collection = lambda tenant, name: Query(tenant, name)
    access.get_wa_contact = enriched_contact
    access.get_wa_conversation_by_id = conversation_by_id
    access.get_channel = channel_by_id
    access.get_wa_conversation = thread_messages
    # _require_contact_access (main.py) importa collection na chamada.
    common.collection = lambda name: Query(common.get_tenant_context() or "", name)
    # Qualquer caminho fora dos fakes acima nao pode criar cliente com ADC.
    common.get_firestore_client = lambda: (_ for _ in ()).throw(AssertionError("cliente Firestore real proibido"))
    rbac._read_perfil_doc = lambda tenant_id, perfil_id: copy.deepcopy(PROFILES.get((tenant_id, perfil_id)))
    rbac.invalidate_perfil_cache()
    tenant_service.get_tenant = lambda tenant_id: copy.deepcopy(TENANTS.get(str(tenant_id)))
    # Auditoria do servico (log_audit real usa o contexto implicito): registra.
    service_module._default_audit = lambda tenant, user_id, action, detail: AUDIT.append(
        (tenant, user_id, action, detail))
    config.FEATURE_FUNNEL = True
    config.FEATURE_FOLLOWUP = True


install()


# ---------------------------------------------------------------------------
# Fixtures (todas sinteticas)
# ---------------------------------------------------------------------------

def stage_fields(stage, changed, source="intake", version=1, entered=None, activity=None, max_order=None):
    entered = entered or changed
    return {fc.F_STAGE: stage, fc.F_VERSION: version, fc.F_CHANGED_AT: changed, fc.F_SOURCE: source,
            fc.F_ACTIVITY: activity, fc.F_BY_USER: None, fc.F_BY_UID: "", fc.F_ENTERED_AT: entered,
            fc.F_COHORT: fc.cohort_month(entered),
            fc.F_MAX_ORDER: fc.next_max_order(CATALOG, 0, stage) if max_order is None else max_order}


def contact(cid, stage=None, changed=None, tenant=TENANT, drop=(), max_order=None, **fields):
    now = NOW[0]
    row = {"id": cid, "wa_id": "5531990000%03d" % cid, "phone_formatted": "+55 31 99000-0%03d" % cid,
           "display_name": "Paciente sintético %d" % cid, "assigned_to": None, "assigned_to_uid": "",
           "is_archived": 0, "is_backup": False, "bot_completed": True, "lgpd_consent": True,
           "qualification": "em_atendimento", "first_seen_at": now - timedelta(days=40),
           "last_inbound_at": now - timedelta(hours=2), "last_message_at": now - timedelta(hours=1),
           "notes": "nota privada sintética", "tags": ["etiqueta-sintetica"], "human_active": False,
           "sale_owner": None, "reopen_attempts": 0}
    if stage:
        row.update(stage_fields(stage, changed or now - timedelta(days=1), max_order=max_order))
    row.update(fields)
    for key in drop:
        row.pop(key, None)
    put("wa_contacts", cid, row, tenant=tenant)
    return row


def put_task(task_id, contact_id, due, status="pending", conversation_id=None, assignee=None, tenant=TENANT):
    put("crm_tasks", task_id, {"id": task_id, "tenant_id": tenant, "contact_id": contact_id,
                               "conversation_id": conversation_id, "status": status, "due_at": due,
                               "title": "Tarefa sintética %s" % task_id, "queue_key": "reception",
                               "assignment_mode": "user" if assignee else "queue",
                               "assignee_user_id": (assignee or {}).get("id"),
                               "assignee_uid": (assignee or {}).get("firebase_uid", ""),
                               "type": "retorno", "contact_purpose": "commercial"}, tenant=tenant)


def activity(act_id, contact_id, event_type, occurred, from_stage=None, to_stage=None, entry_kind=None,
             reason=None, from_reason=None, actor=ALICE, note=None, corrects=None):
    row = {"id": act_id, "tenant_id": TENANT, "contact_id": contact_id, "task_id": None, "conversation_id": None,
           "event_type": event_type, "actor_type": "user", "actor_user_id": actor["id"],
           "actor_uid": actor["firebase_uid"], "occurred_at": occurred, "recorded_at": occurred,
           "operation_id": act_id, "from_stage": from_stage, "to_stage": to_stage, "stage_reason": reason,
           "from_reason": from_reason,
           "data": {"reason_note": note, "appointment_kind": None, "source": "user", "suggested_by": None}}
    if event_type == fc.EVENT_CHANGED:
        row["entry_kind"] = entry_kind
    if corrects:
        row["corrects_entry_id"], row["corrects_month"] = corrects
    put("crm_activities", act_id, row)
    return row


def seed():
    NOW[0] = BASE_NOW
    now = NOW[0]
    with LOCK:
        DATA.clear()
        REVISIONS.clear()
    WRITES.clear()
    QUERY_LOG.clear()
    BEFORE_TRANSACTION.clear()
    BEFORE_COMMIT.clear()
    FORCE_ABORT[0] = 0
    service_module.reset_rate_limits()
    service_module.reset_dashboard_cache()
    service_module.reset_overrides_cache()
    AUDIT.clear()
    config.FEATURE_FUNNEL = True
    config.FEATURE_FOLLOWUP = True
    PROFILES.clear()
    PROFILES[(TENANT, "op_move")] = {"toggles": {"ver_funil": True, "mover_etapa_funil": True,
                                                 "gerenciar_followup": True}}
    PROFILES[(TENANT, "op_no_followup")] = {"toggles": {"ver_funil": True, "mover_etapa_funil": True,
                                                        "gerenciar_followup": False}}
    PROFILES[(TENANT, "op_agent")] = {"toggles": {"ver_funil": True, "ver_contatos_agente_funil": True,
                                                  "gerenciar_followup": True}}
    PROFILES[(TENANT, "sup_no_dash")] = {"toggles": {"ver_dashboard_funil": False}}
    PROFILES[(TENANT, "sup_no_agent")] = {"toggles": {"ver_contatos_agente_funil": False}}
    rbac.invalidate_perfil_cache()
    TENANTS.clear()
    TENANTS[TENANT] = copy.deepcopy(TENANT_DOC)
    TENANTS[OTHER_TENANT] = {"id": OTHER_TENANT, "settings": {}}
    for user in USERS:
        put("users", user["id"], {**user, "is_active": 1})
    put("channels", 4, {"id": 4, "tenant_id": TENANT, "channel_type": "standard"}, tenant=GLOBAL)
    put("channels", 6, {"id": 6, "tenant_id": TENANT, "channel_type": "coexistence"}, tenant=GLOBAL)

    contact(10, "new", now - timedelta(days=3), last_inbound_at=now - timedelta(days=3), bot_completed=False,
            lead_temperature="quente", lead_temperature_at=now - timedelta(days=1), bot_outcome="agendado")
    contact(11, "in_service", assigned_to=1, assigned_to_uid="alice", last_inbound_at=now - timedelta(days=5))
    contact(12, "in_service", assigned_to=2, assigned_to_uid="bob")
    contact(13, "awaiting_followup", assigned_to=1, drop=("assigned_to_uid",))       # UID legado
    contact(14, "scheduled", now - timedelta(days=20), assigned_to=2, assigned_to_uid="bob")
    contact(15, "in_service", is_backup=True)
    contact(16, "in_service", is_archived=1)
    contact(17, first_seen_at=datetime(2026, 9, 9, 15, 0, tzinfo=timezone.utc))      # sem etapa
    contact(18, "unclassified", **{fc.F_SOURCE: fc.SOURCE_GRADUATION})
    contact(19, "in_service", assigned_to=2, drop=("assigned_to_uid",))               # legado do Bob
    contact(21, "new", now - timedelta(hours=2), lgpd_consent=None,
            commercial_contact_block={"active": True, "version": 1})
    contact(22, drop=("last_inbound_at",))                                             # nunca escreveu
    contact(24, "non_converted", datetime(2026, 10, 5, 15, 0, tzinfo=timezone.utc), max_order=20)
    contact(25, "non_converted", datetime(2026, 10, 6, 15, 0, tzinfo=timezone.utc), max_order=40)
    contact(26, "new", datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc), is_backup=True)
    tie = now - timedelta(days=2)
    for index, cid in enumerate(range(30, 60)):
        # 12 empates exatos de crm_stage_changed_at (paginacao por valor + __name__).
        changed = tie if index < 12 else tie - timedelta(hours=index)
        extra = {}
        if index in (20, 25, 29):
            # Parados: paciente sem escrever ha mais de 2 dias (regra de Em atendimento).
            changed = now - timedelta(days=40 + index)
            extra["last_inbound_at"] = changed
        contact(cid, "in_service", changed, **extra)
    contact(60, "legacy_stage")                                                        # fora do catalogo
    for cid in (61, 62, 63):
        contact(cid, "disqualified")
    contact(99, "new", tenant=OTHER_TENANT)

    for conv_id, row in {
        "4__10": {"contact_id": 10, "channel_id": 4, "assigned_to": None, "assigned_to_uid": ""},
        "6__coex10": {"contact_id": 10, "channel_id": 6, "assigned_to": 2, "assigned_to_uid": "bob"},
        "6__coex14": {"contact_id": 14, "channel_id": 6, "assigned_to": 1, "assigned_to_uid": "alice"},
        "4__11": {"contact_id": 11, "channel_id": 4, "assigned_to": 1, "assigned_to_uid": "alice"},
    }.items():
        put("wa_conversations", conv_id, {**row, "id": conv_id, "attendance_status": "fechado_manual",
                                          "unread_count": 0})

    put_task("T1", 10, now + timedelta(hours=1))
    put_task("T2", 10, now - timedelta(minutes=30), conversation_id="6__coex10")       # coex do Bob
    put_task("T3", 11, now - timedelta(hours=1), assignee=ALICE)
    put_task("T4", 11, now + timedelta(days=2))
    put_task("T5", 11, now - timedelta(days=3), status="completed")
    put_task("T7", 99, now - timedelta(days=1), tenant=OTHER_TENANT)

    for msg_id, extras in (("m-normal", {}), ("m-admin", {"visibility": "admin_only"}),
                           ("m-backup", {"is_backup": True}), ("m-flag-admin", {"admin_only": True})):
        put("wa_messages", msg_id, {"id": msg_id, "contact_id": 10, "conversation_id": "4__10",
                                    "direction": "inbound", "msg_type": "text", "status": "received",
                                    "timestamp_wa": now - timedelta(hours=1), "content": "Mensagem sintética",
                                    **extras})


# ---------------------------------------------------------------------------
# Helpers de teste
# ---------------------------------------------------------------------------

def check(condition, label):
    CHECKS[0] += 1
    if not condition:
        raise AssertionError(label)
    print("  OK " + label)


def title(text):
    print("\n== " + text)


def expect(status, code, fn, label):
    try:
        fn()
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        actual = detail.get("code") if detail else exc.detail
        check(exc.status_code == status and (code is None or actual == code),
              "%s (HTTP %s %s)" % (label, exc.status_code, actual))
        return exc
    raise AssertionError(label + ": nao falhou")


def svc(user=None, catalog=None):
    user = copy.deepcopy(user or ALICE)
    authorize = access.build_authorizer(TENANT, main._require_contact_access, permission="ver_funil")
    return FunnelService(FunnelRepository(TENANT), user, authorize, catalog or CATALOG,
                         require_contact_access=main._require_contact_access, clock=lambda: NOW[0])


def payload(to_stage, version, op, **extra):
    return parse_stage_body({"to_stage": to_stage, "expected_version": version, "operation_id": op, **extra})


def move(user, contact_id, to_stage, version, op, **extra):
    result = svc(user).change_stage(contact_id, payload(to_stage, version, op, **extra))
    NOW[0] += timedelta(minutes=1)   # cronologia real entre eventos
    return result


def receipt(uid, contact_id, op):
    value = "\x1f".join([TENANT, "stage", uid, str(contact_id), op])
    return "stage_" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def fingerprint(contact_id, body):
    text = json.dumps({"contact_id": contact_id, "payload": body}, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def columns(board):
    return {column["stage"]: column for column in board["columns"]}


def card_ids(board, stage=None):
    cols = columns(board)
    selected = [cols[stage]] if stage else list(cols.values())
    return {card["contact_id"] for column in selected if column for card in column["cards"]}


def all_cards(board):
    return [card for column in board["columns"] for card in column["cards"]]


def live_contacts(owner_filter=None):
    """Referencia independente das igualdades do quadro (tipos do Firestore)."""
    rows = []
    for key, row in DATA.items():
        if key[0] != TENANT or key[1] != "wa_contacts":
            continue
        archived = row.get("is_archived")
        if not (isinstance(archived, int) and not isinstance(archived, bool) and archived == 0):
            continue
        if row.get("is_backup") is not False or not isinstance(row.get(fc.F_STAGE), str):
            continue
        if owner_filter is not None and not owner_filter(row):
            continue
        rows.append(row)
    return rows


def contact_values(row):
    found = []

    def walk(value):
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)
        else:
            found.append(value)
    walk(row)
    return found


# ---------------------------------------------------------------------------
# Cenarios
# ---------------------------------------------------------------------------

def scenario_fake():
    title("Fake do Firestore: restricoes reais")
    seed()
    tx = Transaction()
    tx.set(Reference(TENANT, "x", "1"), {"a": 1})
    try:
        Reference(TENANT, "x", "1").get(transaction=tx)
        check(False, "leitura apos escrita deveria falhar")
    except AssertionError as exc:
        check("depois de escrita" in str(exc), "leitura apos escrita na transacao e proibida")
    put("x", "dup", {"a": 1})
    tx = Transaction()
    tx.create(Reference(TENANT, "x", "dup"), {"a": 2})
    try:
        _commit(tx)
        check(False, "create duplicado deveria falhar")
    except google_exceptions.AlreadyExists:
        check(doc("x", "dup") == {"a": 1}, "create duplicado = erro, nada gravado")
    try:
        Query(TENANT, "wa_contacts").where("crm_stage", "==", "new").stream()
        check(False, "query sem limite deveria falhar")
    except AssertionError:
        check(True, "query sem limite e recusada")
    rows = list(Query(TENANT, "wa_contacts").where("is_archived", "==", False).limit(500).stream())
    check(not rows, "0 != False (tipos distintos nao se igualam)")
    rows = list(Query(TENANT, "wa_contacts").where("assigned_to_uid", "==", "").limit(500).stream())
    check(13 not in {int(s.id) for s in rows}, "campo ausente nao casa igualdade (UID legado)")
    try:
        Query(TENANT, "wa_contacts").where("id", "in", list(range(31)))
        check(False, "in com 31 valores deveria falhar")
    except AssertionError:
        check(True, "'in' limitado a 30 valores")
    tx = Transaction()
    try:
        tx.set(Reference(TENANT, "x", "2"), {"a": datetime(2026, 1, 1)})
        check(False, "datetime ingenuo deveria falhar")
    except AssertionError:
        check(True, "datetime sem fuso nao e gravavel")


def scenario_catalog():
    title("Catalogo, capacidades e identidade")
    seed()
    catalog = fc.load_tenant_funnel(TENANT)
    check(catalog and catalog["template"] == "clinic_v1"
          and [s["key"] for s in catalog["stages"]] == ["new", "in_service", "awaiting_followup", "scheduled", "loyal",
                                                        "non_converted", "disqualified", "unclassified"]
          and catalog["kpis"]["booked_stage"] == "scheduled" and catalog["legacy_qualification_sync"],
          "catalogo resolvido do tenant (clinic_v1, 8 etapas em ordem, legado sincronizado)")
    check(fc.load_tenant_funnel(OTHER_TENANT) is None and service_module.load_catalog(OTHER_TENANT) is None,
          "tenant sem settings.funnel = funil desligado (webhook e telas)")
    config.FEATURE_FUNNEL = False
    check(fc.load_tenant_funnel(TENANT) is None and service_module.load_catalog(TENANT) is None,
          "FEATURE_FUNNEL desligada = sem catalogo")
    config.FEATURE_FUNNEL = True
    alice = svc(ALICE).get_config()
    check(alice["capabilities"] == {"can_move": True, "can_dashboard": False, "privileged": False, "followup": True,
                                    "can_configure": False, "can_see_agent_contacts": False},
          "capacidades da operadora com mover (sem a coluna do agente de IA)")
    manager = svc(MANAGER).get_config()
    check(manager["capabilities"] == {"can_move": True, "can_dashboard": True, "privileged": True, "followup": True,
                                      "can_configure": False, "can_see_agent_contacts": True},
          "capacidades da supervisao (seed): ve a coluna do agente, nao edita os textos")
    admin = svc(ADMIN).get_config()["capabilities"]
    check(admin["can_configure"] and admin["can_see_agent_contacts"] and admin["can_dashboard"],
          "admin edita os textos (gerenciar_config_sistema) e ve tudo")
    bob = svc(BOB).get_config()
    check(not bob["capabilities"]["can_move"] and not bob["capabilities"]["can_see_agent_contacts"]
          and "can_confirm_conversion" not in bob["capabilities"],
          "operador seed so ve; conversao sem permissao propria (saiu confirmar_conversao_funil)")
    check("confirmar_conversao_funil" not in rbac.PERMISSION_KEYS and "ver_contatos_agente_funil" in rbac.PERMISSION_KEYS
          and rbac.SEED_PERFIS["perfil_supervisor"]["toggles"]["ver_contatos_agente_funil"]
          and not rbac.SEED_PERFIS["perfil_operador"]["toggles"]["ver_contatos_agente_funil"]
          and rbac.SEED_PERFIS["perfil_admin"]["toggles"]["ver_contatos_agente_funil"],
          "RBAC: ver_contatos_agente_funil no catalogo (seed supervisao sim, operador nao, admin todos)")
    stage = next(s for s in manager["catalog"]["stages"] if s["key"] == "non_converted")
    check(set(stage) == CONFIG_STAGE_KEYS and stage["requires_reason"] and stage["close_outcome"]
          and stage["legacy_qualification"] == "nao_convertido", "shape das etapas do /config (sem restricted)")
    check([s["key"] for s in alice["catalog"]["stages"]] == [s["key"] for s in CATALOG["stages"]]
          and [s["key"] for s in alice["catalog"]["stages"] if not s["visible"]] == ["new"]
          and next(s for s in alice["catalog"]["stages"] if s["key"] == "new")["visibility_permission"]
          == "ver_contatos_agente_funil" and all(s["visible"] for s in manager["catalog"]["stages"]),
          "/config lista TODAS as etapas; Novo contato invisivel so para quem nao tem a permissao")
    check({s["key"] for s in manager["catalog"]["stages"] if s["close_outcome"]}
          == {"awaiting_followup", "scheduled", "loyal", "non_converted", "disqualified"}
          and {s["key"]: s["legacy_qualification"] for s in manager["catalog"]["stages"]
               if s["legacy_qualification"]} == LEGACY_BY_STAGE,
          "desfechos do encerramento e legado equivalente por etapa")
    labels = {s["key"]: s["label"] for s in manager["catalog"]["stages"]}
    check(labels["new"] == "Novo contato" and labels["in_service"] == "Em atendimento"
          and labels["scheduled"] == "Cliente Agendado" and labels["loyal"] == "Paciente em acompanhamento"
          and labels["disqualified"] == "Não qualificado", "rotulos do PO (28/10)")
    check(all(s["description"] and s["default_label"] == s["label"] and s["default_description"] == s["description"]
              for s in manager["catalog"]["stages"]) and manager["catalog"]["overrides_version"] == 0,
          "texto explicativo em toda etapa; padrao = rotulo atual sem textos da clinica")
    reasons = {r["key"]: r for r in manager["catalog"]["reasons"]}
    check(reasons["other"]["allows_note"] and reasons["other"]["hint"] and reasons["not_informed"]["selectable"] is False
          and reasons["proposal_declined"]["label"] == "Não aceitou a proposta"
          and reasons["no_show"]["label"] == "Não compareceu"
          and all(r["default_label"] == r["label"] for r in reasons.values()),
          "motivos: nota so em Outro, 'nao registrado' fora da escolha, novos motivos do PO")
    expect(403, "tenant_mismatch", lambda: FunnelRepository("bad/tenant"), "tenant invalido no repositorio")
    expect(403, "tenant_mismatch", lambda: svc({**ALICE, "tenant_id": OTHER_TENANT}), "sessao de outro tenant")
    for flag in ("read_only", "impersonating"):
        expect(403, "read_only_session", lambda f=flag: svc({**ALICE, f: True}).get_config(), "%s negado" % flag)
    expect(403, "read_only_session",
           lambda: svc({**ALICE, "impersonation": {"sid": "a" * 32, "by": 3}}).get_config(),
           "sessao Ver como (user['impersonation']) negada no servico")
    bump("users", 1, is_active=0)
    expect(403, "user_inactive", lambda: svc(ALICE).get_config(), "usuario desativado relido e negado")
    bump("users", 1, is_active=1, role="supervisor")
    expect(403, "user_inactive", lambda: svc(ALICE).get_config(), "perfil alterado revoga a sessao antiga")
    bump("users", 1, role="operador")
    expect(404, "funnel_disabled", lambda: FunnelService(FunnelRepository(TENANT), ALICE, None, None),
           "servico sem catalogo = funil desligado")


def scenario_board():
    title("Quadro: escopo, contagens, selos e whitelist")
    seed()
    before = copy.deepcopy(DATA)
    board = svc(ALICE).board()
    cols = columns(board)
    check([column["stage"] for column in board["columns"]] == [s["key"] for s in CATALOG["stages"] if s["key"] != "new"],
          "etapas visiveis do catalogo, em ordem (sem Novo contato para a operadora)")
    check(card_ids(board) == {11, 18, 24, 25, 61, 62, 63} | set(range(30, 49)),
          "operador ve proprios + pool (20 primeiros de Em atendimento)")
    check(not card_ids(board) & {10, 12, 13, 14, 15, 16, 19, 21, 26, 60, 99},
          "nada de lead com a Val, colega, UID legado, backup, arquivado, fora do catalogo ou outro tenant")
    scope = lambda row: row.get("assigned_to_uid") in ("alice", "")
    for key, column in cols.items():
        expected = [row for row in live_contacts(scope) if row[fc.F_STAGE] == key]
        cut = fc.stale_cutoff(fc.stage_def(CATALOG, key), NOW[0])
        stale = None if not cut else sum(1 for row in expected if cut[0] in row and row[cut[0]] < cut[1])
        check(column["count"] == len(expected) and column["stale_count"] == stale,
              "%s: count=%d stale=%s batem com a referencia" % (key, column["count"], column["stale_count"]))
        if column["count"] <= service_module.CARD_LIMIT:
            check(len(column["cards"]) == column["count"]
                  and (stale is None or stale == sum(1 for c in column["cards"] if c["signals"]["stale"])),
                  "%s: cards e selos 'parado' coerentes com o cabecalho" % key)
    check(cols["in_service"]["next_cursor"] and len(cols["in_service"]["cards"]) == 20
          and cols["in_service"]["count"] == 31 and cols["in_service"]["stale_count"] == 4,
          "coluna grande pagina em 20 com cursor (31 contatos, 4 parados)")
    check(cols["loyal"]["count"] == 0 and cols["loyal"]["stale_count"] is None
          and cols["scheduled"]["stale_count"] is None, "etapa sem regra de parado devolve stale_count nulo")
    cards = {card["contact_id"]: card for card in all_cards(board)}
    check(all(set(card) == CARD_KEYS for card in cards.values()), "card com whitelist EXPLICITA de campos")
    dump = json.dumps(board, ensure_ascii=False)
    check(not any(text in dump for text in ("5531990000", "99000-0", "nota privada", "etiqueta-sintetica",
                                             "lgpd_consent", "qualification", "em_atendimento", "wa_id")),
          "card sem telefone, notas, tags, LGPD ou qualificacao")
    c11 = cards[11]
    check(c11["owner"] == {"user_id": 1, "name": "Operadora Alice"} and c11["signals"]["stale"],
          "dono do lead pelo lookup em lote e 'parado' por silencio do paciente")
    check(c11["stage_changed_at"].endswith("+00:00") and c11["stage_version"] == 1 and c11["stage_source"] == "intake",
          "datas ISO com fuso, versao e origem da etapa")
    manager = svc(MANAGER).board()
    mcards = {card["contact_id"]: card for card in all_cards(manager)}
    c10, c21 = mcards[10], mcards[21]
    check(c10["badges"] == {"with_bot": True, "lgpd_pending": False, "commercial_blocked": False,
                            "bot_outcome": "agendado"} and c10["owner"] is None and c10["lead_temperature"] == "quente",
          "selos do card da pool com a Val (sugestao do bot so como selo)")
    check(c21["badges"]["lgpd_pending"] and c21["badges"]["commercial_blocked"] and not c21["signals"]["stale"],
          "sem aceite LGPD e recusa comercial viram selo; mensagem recente nao e 'parado'")
    TENANTS[TENANT]["settings"]["ai"]["lgpd_by_agent"] = True
    agent_cards = {card["contact_id"]: card for card in all_cards(svc(MANAGER).board())}
    check(not agent_cards[21]["badges"]["lgpd_pending"], "lgpd_by_agent: o CRM nao cobra aceite LGPD no selo")
    TENANTS[TENANT]["settings"]["ai"].pop("lgpd_by_agent")
    check({11, 12, 19} <= card_ids(manager, "in_service") and card_ids(manager, "awaiting_followup") == {13}
          and card_ids(manager, "scheduled") == {14} and card_ids(manager, "new") == {10, 21},
          "privilegiado ve o tenant (inclusive UID legado) e a coluna do agente de IA")
    check(not card_ids(manager) & {15, 16, 26}, "privilegiado tambem nao ve backup/arquivado no quadro")
    check(columns(manager)["in_service"]["stale_count"] == 4 and columns(manager)["new"]["stale_count"] == 1
          and mcards[10]["signals"]["stale"] and columns(manager)["scheduled"]["stale_count"] is None,
          "parado por silencio do paciente (Novo contato 1 dia, Em atendimento 2); Cliente Agendado sem regra")
    mine = svc(ALICE).board(mine=True)
    check(card_ids(mine) == {11}, "mine=1: so os proprios, sem a pool")
    check(card_ids(svc(MANAGER).board(mine=True)) == set(), "mine=1 vale para qualquer usuario")
    owner = svc(MANAGER).board(owner_id=2)
    check(card_ids(owner) == {12, 14} and owner["scope"]["owner_id"] == 2,
          "owner_id resolve o uid do usuario (legado so com assigned_to fica de fora)")
    expect(403, "owner_filter_forbidden", lambda: svc(ALICE).board(owner_id=2), "owner_id por operador")
    expect(422, "filter_invalid", lambda: svc(MANAGER).board(owner_id=2, mine=True), "owner_id e mine juntos")
    expect(422, "owner_invalid", lambda: svc(MANAGER).board(owner_id=404), "owner_id inexistente")
    expect(422, "filter_invalid", lambda: svc(ALICE).board(order="sideways"), "ordem invalida")
    asc = svc(ALICE).board(order="asc")
    check(columns(asc)["in_service"]["cards"][0]["contact_id"] == 59 and asc["scope"]["order"] == "asc",
          "ordem asc traz o mais antigo na etapa primeiro")
    TENANTS[TENANT]["settings"]["funnel"]["inactive_stages"] = ["disqualified", "loyal"]
    inactive_catalog = fc.funnel_for_tenant(TENANTS[TENANT])
    stages = [column["stage"] for column in svc(ALICE, inactive_catalog).board()["columns"]]
    check("disqualified" in stages and "loyal" not in stages
          and not columns(svc(ALICE, inactive_catalog).board())["disqualified"]["active"],
          "etapa inativa so aparece com contatos (active=false)")
    TENANTS[TENANT]["settings"]["funnel"].pop("inactive_stages")
    check(DATA == before and not WRITES, "GET do quadro nao grava nada")


def scenario_visibility():
    title("Coluna Novo contato (lead com o agente de IA) so com ver_contatos_agente_funil")
    seed()
    asked = []
    count_stage, stage_page = FunnelRepository.count_stage, FunnelRepository.stage_page

    def count_spy(self, stage, owner=None, stale=None):
        asked.append(stage)
        return count_stage(self, stage, owner, stale)

    def page_spy(self, stage, owner, descending=True, after=None, limit=21):
        asked.append(stage)
        return stage_page(self, stage, owner, descending, after, limit)

    FunnelRepository.count_stage, FunnelRepository.stage_page = count_spy, page_spy
    try:
        svc(ALICE).board()
        check("new" not in asked and "in_service" in asked,
              "operadora sem a permissao: Novo contato nem e consultada (total, parados e cards)")
        asked.clear()
        eve = svc(EVE).board()
        check(asked.count("new") == 3 and eve["columns"][0]["stage"] == "new",
              "operadora COM a permissao: coluna consultada (total, parados e pagina) e exibida")
    finally:
        FunnelRepository.count_stage, FunnelRepository.stage_page = count_stage, stage_page
    new = columns(eve)["new"]
    check(card_ids(eve, "new") == {10, 21} and new["count"] == 2 and new["stale_count"] == 1,
          "Novo contato da operadora = so a pool (backup fora), com parados")
    for user in (ALICE, BOB, SUPNOAGENT):
        expect(404, "unknown_stage", lambda u=user: svc(u).stage_cards("new"),
               "coluna invisivel responde como inexistente (%s)" % user["firebase_uid"])
    check({card["contact_id"] for card in svc(EVE).stage_cards("new")["cards"]} == {10, 21}
          and {card["contact_id"] for card in svc(MANAGER).stage_cards("new")["cards"]} == {10, 21},
          "quem tem a permissao pagina a coluna")
    check("new" not in [column["stage"] for column in svc(SUPNOAGENT).board()["columns"]]
          and not svc(SUPNOAGENT).get_config()["capabilities"]["can_see_agent_contacts"],
          "supervisao com o toggle desligado tambem perde a coluna")
    drawer = svc(ALICE).contact_drawer(10)
    check(drawer["stage"]["key"] == "new" and drawer["capabilities"] == {"can_move": True, "write_scope": True}
          and svc(ALICE).contact_stage(21)["stage"]["key"] == "new",
          "drawer e revalidacao leve do contato com a Val continuam (acesso do CRM, nao do quadro)")
    check(next(row for row in svc(MANAGER).dashboard()["current"]["stages"] if row["stage"] == "new")["count"] == 2,
          "painel gerencial conta Novo contato (contagem do tenant, sem cards)")


def scenario_pagination():
    title("Paginacao por cursor de valores")
    seed()
    for order in ("desc", "asc"):
        board = svc(ALICE).board(order=order)
        column = columns(board)["in_service"]
        seen = [card["contact_id"] for card in column["cards"]]
        stale = sum(1 for card in column["cards"] if card["signals"]["stale"])
        cursor = column["next_cursor"]
        pages = 0
        while cursor:
            page = svc(ALICE).stage_cards("in_service", cursor=cursor, order=order, limit=7)
            seen.extend(card["contact_id"] for card in page["cards"])
            stale += sum(1 for card in page["cards"] if card["signals"]["stale"])
            cursor = page["next_cursor"]
            pages += 1
        check(len(seen) == len(set(seen)) == column["count"] == 31 and set(seen) == {11} | set(range(30, 60)),
              "%s: %d paginas sem duplicar nem pular (12 empates de crm_stage_changed_at)" % (order, pages))
        check(stale == column["stale_count"] == 4, "%s: parados somados nas paginas = cabecalho" % order)
        moments = [doc("wa_contacts", cid)[fc.F_CHANGED_AT] for cid in seen]
        check(moments == sorted(moments, reverse=(order == "desc")), "%s: ordem por tempo na etapa" % order)
    cursor = columns(svc(ALICE).board())["in_service"]["next_cursor"]
    tampered = cursor[:-1] + ("0" if cursor[-1] != "0" else "1")
    expect(400, "cursor_invalid", lambda: svc(ALICE).stage_cards("in_service", cursor=tampered), "cursor adulterado")
    expect(400, "cursor_invalid", lambda: svc(BOB).stage_cards("in_service", cursor=cursor), "cursor de outra identidade")
    expect(400, "cursor_invalid", lambda: svc(ALICE).stage_cards("in_service", cursor=cursor, order="asc"),
           "cursor de outra ordenacao")
    expect(400, "cursor_invalid", lambda: svc(ALICE).stage_cards("awaiting_followup", cursor=cursor),
           "cursor de outra etapa")
    expect(400, "cursor_invalid", lambda: svc(ALICE).stage_cards("in_service", cursor=cursor, mine=True),
           "cursor de outro filtro")
    expect(400, "cursor_invalid", lambda: svc(ALICE).stage_cards("in_service", cursor="forjado.abc"), "cursor forjado")
    NOW[0] += timedelta(minutes=61)
    expect(400, "cursor_invalid", lambda: svc(ALICE).stage_cards("in_service", cursor=cursor), "cursor vencido (1 h)")
    NOW[0] = BASE_NOW
    expect(404, "unknown_stage", lambda: svc(ALICE).stage_cards("nao_existe"), "etapa inexistente na coluna")
    expect(422, "filter_invalid", lambda: svc(ALICE).stage_cards("in_service", limit=51), "limite acima de 50")


def scenario_tasks():
    title("Proxima tarefa em lote, visibilidade e flags")
    seed()
    # 31o card do quadro da supervisao (UID legado do Bob: fora do filtro por
    # dono e do escopo das operadoras): o lote de tarefas passa de 30.
    contact(20, "loyal", assigned_to=2, drop=("assigned_to_uid",))
    QUERY_LOG.clear()
    manager = svc(MANAGER).board()
    cards = {card["contact_id"]: card for card in all_cards(manager)}
    task_queries = [q for q in QUERY_LOG if q["collection"] == "crm_tasks"]
    check(len(cards) > 30 and len(task_queries) == math.ceil(len(cards) / 30),
          "%d cards -> %d consultas de tarefas (lote de 30, sem N+1)" % (len(cards), len(task_queries)))
    check(all(q["kind"] == "stream" and q["limit"] == 200 and ("contact_id", "in") in q["filters"] for q in task_queries),
          "tarefas por 'contact_id in' com limite 200")
    gets = [q for q in QUERY_LOG if q["kind"] == "get"]
    check(len(gets) == 1 and gets[0]["collection"] == "users", "nenhum get por card (so a releitura do usuario)")
    check(sum(1 for q in QUERY_LOG if q["kind"] == "get_all" and q["collection"] == "users") == 1,
          "1 lookup de usuarios por pagina")
    check(cards[10]["next_task"]["id"] == "T2" and cards[10]["next_task"]["overdue"],
          "privilegiado: primeira por due_at inclusive tarefa de thread coex")
    check(cards[11]["next_task"] == {"id": "T3", "title": "Tarefa sintética T3", "due_at": (BASE_NOW - timedelta(hours=1)).isoformat(),
                                     "overdue": True, "queue_key": "reception", "assignee_name": "Operadora Alice"}
          and cards[11]["signals"]["task_overdue"], "tarefa concluida ignorada; atrasada sinalizada com responsavel")
    check(cards[13]["next_task"] is None and cards[13]["signals"]["no_next_action"],
          "Aguardando retorno sem tarefa = 'sem proxima acao'")
    QUERY_LOG.clear()
    eve = {card["contact_id"]: card for card in all_cards(svc(EVE).board())}
    check(eve[10]["next_task"]["id"] == "T1" and not eve[10]["next_task"]["overdue"],
          "tarefa de thread coex alheia oculta para operador")
    check(sum(1 for q in QUERY_LOG if q["kind"] == "get_all" and q["collection"] == "wa_conversations") == 1
          and sum(1 for q in QUERY_LOG if q["kind"] == "channel") == 1,
          "threads em lote e tipo do canal em cache por request")
    config.FEATURE_FOLLOWUP = False
    QUERY_LOG.clear()
    off = {card["contact_id"]: card for card in all_cards(svc(MANAGER).board())}
    check(not [q for q in QUERY_LOG if q["collection"] == "crm_tasks"]
          and all(card["next_task"] is None and not card["tasks_visible"] for card in off.values())
          and not off[13]["signals"]["no_next_action"] and not off[11]["signals"]["task_overdue"],
          "FEATURE_FOLLOWUP=false: nenhuma tarefa, consulta ou selo de tarefa")
    check(not svc(MANAGER).get_config()["capabilities"]["followup"], "capability followup desligada")
    config.FEATURE_FOLLOWUP = True
    carol = {card["contact_id"]: card for card in all_cards(svc(CAROL).board())}
    check(all(card["next_task"] is None and not card["tasks_visible"] for card in carol.values()),
          "sem gerenciar_followup: nenhuma tarefa nem selo")
    drawer = svc(MANAGER).contact_drawer(11)
    check([task["id"] for task in drawer["tasks"]] == ["T3", "T4"], "drawer lista pendentes acessiveis (ate 5)")
    check([task["id"] for task in svc(ALICE).contact_drawer(10)["tasks"]] == ["T1"], "drawer do operador oculta coex alheia")
    check(svc(CAROL).contact_drawer(10)["tasks"] is None, "drawer sem follow-up: tasks=null")


def scenario_task_truncation():
    title("Lote de tarefas cortado no limite (200): sem 'sem proxima acao' falso")
    seed()
    now = NOW[0]
    crowd = list(range(100, 119))                       # 19 contatos de Aguardando retorno
    for index, cid in enumerate(crowd):
        contact(cid, "awaiting_followup", now - timedelta(days=2, minutes=index))
    contact(119, "awaiting_followup", now - timedelta(hours=1))
    base = now - timedelta(days=30)
    for k in range(11):                                 # 19 x 11 = 209 pendentes antes da do 119
        for index, cid in enumerate(crowd):
            put_task("TB%03d_%02d" % (cid, k), cid, base + timedelta(minutes=k * len(crowd) + index))
    put_task("TT119", 119, now + timedelta(days=10))
    calls = []
    original = FunnelRepository.pending_tasks

    def spy(self, contact_ids, limit=200, after=None):
        calls.append((sorted(contact_ids), after))
        return original(self, contact_ids, limit=limit, after=after)

    FunnelRepository.pending_tasks = spy
    try:
        cards = {card["contact_id"]: card for card in svc(MANAGER).stage_cards("awaiting_followup", limit=50)["cards"]}
        check(len(cards) == 21 and len(calls) == 2 and calls[0][1] is None
              and calls[1][0] == [13, 119] and calls[1][1] == (base + timedelta(minutes=199), "TB109_10"),
              "lote cheio: 2a consulta so com quem ficou sem tarefa, a partir da ultima linha vista")
        c119 = cards[119]
        check(c119["next_task"]["id"] == "TT119" and c119["tasks_visible"]
              and not c119["signals"]["no_next_action"] and not c119["signals"]["task_overdue"],
              "209 tarefas antes da unica do 119 nao apagam a proxima tarefa dele")
        check(cards[13]["next_task"] is None and cards[13]["tasks_visible"] and cards[13]["signals"]["no_next_action"],
              "sem tarefa nenhuma (com certeza) continua 'sem proxima acao'")
        check(all(cards[cid]["next_task"]["id"] == "TB%03d_00" % cid for cid in crowd),
              "quem apareceu no lote cortado tem a 1a tarefa certa (prefixo da ordem por due_at)")
        for user in (MANAGER, EVE):
            board = {card["contact_id"]: card for card in all_cards(svc(user).board())}
            check(board[119]["next_task"]["id"] == "TT119" and not board[119]["signals"]["no_next_action"]
                  and board[10]["next_task"]["id"] == ("T2" if user is MANAGER else "T1"),
                  "quadro de %s: proxima tarefa certa mesmo com lote cheio" % user["display_name"])
        service_module.TASK_ROUNDS, rounds = 1, service_module.TASK_ROUNDS
        try:
            calls.clear()
            capped = {card["contact_id"]: card for card in svc(MANAGER).stage_cards("awaiting_followup", limit=50)["cards"]}
            check(len(calls) == 1 and capped[119]["next_task"] is None and not capped[119]["tasks_visible"]
                  and not capped[119]["signals"]["no_next_action"] and not capped[119]["signals"]["task_overdue"],
                  "teto de rodadas: contato incerto sai sem tarefa e sem selo de tarefa")
            check(not capped[13]["tasks_visible"] and not capped[13]["signals"]["no_next_action"],
                  "sem certeza: nada de 'sem proxima acao' nem para quem nao tem tarefa")
            check(capped[100]["next_task"]["id"] == "TB100_00" and capped[100]["tasks_visible"],
                  "quem apareceu no lote cortado mantem a tarefa e o selo")
        finally:
            service_module.TASK_ROUNDS = rounds
    finally:
        FunnelRepository.pending_tasks = original

    # Operadora: tarefas de thread coex oculta tambem consomem o limite.
    seed()
    for index in range(service_module.TASK_LIMIT):
        put_task("TH%03d" % index, 10, now - timedelta(days=10) + timedelta(minutes=index),
                 conversation_id="6__coex10")
    drawer = svc(ALICE).contact_drawer(10)
    check([task["id"] for task in drawer["tasks"]] == ["T1"] and not drawer["signals"]["task_overdue"],
          "operadora: 200 tarefas de thread oculta nao escondem a tarefa visivel (drawer)")
    eve = {card["contact_id"]: card for card in all_cards(svc(EVE).board())}
    alice = {card["contact_id"]: card for card in all_cards(svc(ALICE).board())}
    check(eve[10]["next_task"]["id"] == "T1" and alice[11]["next_task"]["id"] == "T3",
          "operadoras: idem no quadro (lote inteiro reconsultado)")
    check(svc(MANAGER).contact_drawer(10)["tasks"][0]["id"] == "TH000", "privilegiado ve as tarefas da thread coex")
    service_module.TASK_ROUNDS, rounds = 1, service_module.TASK_ROUNDS
    try:
        drawer = svc(ALICE).contact_drawer(10)
        check(drawer["tasks"] is None and not drawer["signals"]["task_overdue"]
              and not drawer["signals"]["no_next_action"], "drawer incerto: tasks=null e nenhum selo de tarefa")
        eve = {card["contact_id"]: card for card in all_cards(svc(EVE).board())}
        check(not eve[10]["tasks_visible"] and eve[10]["next_task"] is None,
              "card incerto da operadora sem tarefa visivel")
    finally:
        service_module.TASK_ROUNDS = rounds


def scenario_display_names():
    title("Nome exibido nunca e o telefone (card, drawer e contexto)")
    seed()
    contact(70, "new", display_name="+55 31 99000-0070", declared_name="", whatsapp_profile_name="")
    contact(71, "new", display_name="+55 31 99000-0071", declared_name="", whatsapp_profile_name="Maria Sintética")
    contact(72, "new", display_name="5531990000072", declared_name="Nome Declarado Sintético")
    contact(73, "new", display_name="", declared_name="", whatsapp_profile_name="+55 (31) 99000-0073")
    contact(74, "new", display_name="Paciente 2026")
    contact(76, "new", display_name="", drop=("wa_id", "phone_formatted"))
    # Novo contato: coluna visivel a quem tem ver_contatos_agente_funil.
    board = svc(EVE).board()
    cards = {card["contact_id"]: card for card in all_cards(board)}
    expected = {70: "Contato sem nome (final 0070)", 71: "Maria Sintética", 72: "Nome Declarado Sintético",
                73: "Contato sem nome (final 0073)", 74: "Paciente 2026", 76: "Contato sem nome"}
    check({cid: cards[cid]["display_name"] for cid in expected} == expected,
          "card: telefone vira nome declarado/de perfil ou 'Contato sem nome (final NNNN)'")
    dump = json.dumps(board, ensure_ascii=False)
    check("99000-0" not in dump and "5531990000" not in dump, "quadro sem telefone mesmo sem nome")
    drawer = svc(ALICE).contact_drawer(70)
    context = svc(ALICE).contact_context(70)
    check(drawer["contact"]["display_name"] == context["contact"]["display_name"] == expected[70]
          and "99000-0" not in json.dumps([drawer, context], ensure_ascii=False),
          "drawer e contexto com o mesmo nome, sem telefone")
    check(svc(ALICE).contact_context(71)["contact"]["display_name"] == "Maria Sintética",
          "contexto usa o nome de perfil quando o nome gravado e o telefone")


def scenario_stage_check():
    title("Revalidacao leve do drawer: etapa, versao e acesso")
    seed()
    move(ALICE, 10, "non_converted", 1, "op-chk-0001", reason="other", reason_note="Prefere outra clinica")
    move(ALICE, 11, "scheduled", 1, "op-chk-0002", appointment_kind="consultation")
    before = copy.deepcopy(DATA)
    writes = len(WRITES)
    for user, cid in ((ALICE, 10), (BOB, 10), (MANAGER, 10), (ALICE, 11), (ALICE, 14), (ALICE, 17),
                      (MANAGER, 16), (ALICE, 21)):
        drawer = svc(user).contact_drawer(cid)
        light = svc(user).contact_stage(cid)
        check(set(light) == {"stage", "version", "can_move", "write_scope"} and light["stage"] == drawer["stage"]
              and light["version"] == (drawer["stage"] or {}).get("version", 0)
              and light["can_move"] == drawer["capabilities"]["can_move"]
              and light["write_scope"] == drawer["capabilities"]["write_scope"],
              "%s/%d: etapa igual a do drawer, versao %d, can_move=%s" % (
                  user["firebase_uid"], cid, light["version"], light["can_move"]))
    light = svc(ALICE).contact_stage(10)
    check(light["stage"]["reason"]["key"] == "other" and light["stage"]["reason_note"] == "Prefere outra clinica"
          and svc(BOB).contact_stage(10)["stage"]["reason_note"] is None,
          "motivo da Activity apontada; nota so para autora/privilegiado")
    check(svc(ALICE).contact_stage(11)["stage"]["appointment_kind"] == "consultation", "tipo de compromisso do Agendado")
    empty = svc(ALICE).contact_stage(17)
    check(empty == {"stage": None, "version": 0, "can_move": True, "write_scope": True},
          "contato sem etapa: stage nulo e versao 0")
    thread_only = svc(ALICE).contact_stage(14)
    check(not thread_only["write_scope"] and not thread_only["can_move"] and thread_only["stage"]["key"] == "scheduled",
          "so-thread: etapa atual sem escrita")
    QUERY_LOG.clear()
    svc(ALICE).contact_stage(21)
    check([q["collection"] for q in QUERY_LOG] == ["users"], "etapa sem motivo: so a releitura do usuario (o contato vem do autorizador)")
    QUERY_LOG.clear()
    svc(ALICE).contact_stage(10)
    check([(q["collection"], q["kind"]) for q in QUERY_LOG] == [("users", "get"), ("crm_activities", "get")],
          "etapa com motivo: + 1 leitura da Activity apontada; sem historico nem tarefas")
    check(DATA == before and len(WRITES) == writes, "revalidacao leve nao grava nada")
    bump("wa_contacts", 21, assigned_to=2, assigned_to_uid="bob")
    expect(404, "out_of_scope", lambda: svc(ALICE).contact_stage(21), "perdeu o acesso (lead transferido) = 404")
    expect(404, "out_of_scope", lambda: svc(ALICE).contact_stage(15), "backup para operador = 404")
    expect(404, "out_of_scope", lambda: svc(ALICE).contact_stage(99), "contato de outro tenant = 404")
    archived = svc(MANAGER).contact_stage(16)
    check(archived["stage"]["key"] == "in_service" and not archived["can_move"], "privilegiado: arquivado sem mover")


def scenario_moves():
    title("Mudanca de etapa: transacao, recibo, regras e whitelist de escrita")
    seed()
    start = copy.deepcopy(DATA)
    body = payload("in_service", 1, "op-happy-0001")
    result = move(ALICE, 10, "in_service", 1, "op-happy-0001")
    receipt_id = receipt("alice", 10, "op-happy-0001")
    check(result["activity_id"] == receipt_id and not result["replayed"] and result["contact_id"] == 10
          and result["stage"]["key"] == "in_service" and result["stage"]["version"] == 2,
          "mudanca feliz: recibo = id deterministico, versao +1")
    check(len(WRITES) == 2 and WRITES[0]["key"] == (TENANT, "wa_contacts", "10") and WRITES[0]["merge"]
          and WRITES[1] == {"key": (TENANT, "crm_activities", receipt_id), "kind": "create", "merge": False,
                            "fields": sorted(doc("crm_activities", receipt_id))},
          "exatamente 2 escritas: contato (merge) + 1 Activity (create)")
    after = doc("wa_contacts", 10)
    changed = {key for key in set(after) | set(start[(TENANT, "wa_contacts", "10")])
               if after.get(key) != start[(TENANT, "wa_contacts", "10")].get(key)}
    check(changed <= set(fc.CONTACT_STAGE_FIELDS) and set(WRITES[0]["fields"]) <= set(fc.CONTACT_STAGE_FIELDS),
          "legado ja equivalente (em_atendimento): contato recebe so campos crm_* (%s)" % ",".join(sorted(changed)))
    check(after[fc.F_CHANGED_AT] == BASE_NOW and after[fc.F_MAX_ORDER] == 20 and after[fc.F_SOURCE] == "user"
          and after[fc.F_BY_USER] == 1 and after[fc.F_BY_UID] == "alice" and after[fc.F_ACTIVITY] == receipt_id
          and after[fc.F_ENTERED_AT] == start[(TENANT, "wa_contacts", "10")][fc.F_ENTERED_AT],
          "changed_at datetime, maior etapa monotonica, autor e entrada write-once")
    event = doc("crm_activities", receipt_id)
    check(event["event_type"] == fc.EVENT_CHANGED and event["entry_kind"] == "move" and event["from_stage"] == "new"
          and event["to_stage"] == "in_service" and event["task_id"] is None and event["conversation_id"] is None
          and event["actor_type"] == "user" and event["actor_uid"] == "alice" and event["result_version"] == 2
          and event["request_fingerprint"] == fingerprint(10, body) and event["operation_id"] == "op-happy-0001"
          and event["data"] == {"reason_note": None, "appointment_kind": None, "stage_version": 2, "source": "user",
                                "suggested_by": None, "legacy_qualification": None}
          and "corrects_entry_id" not in event and "via" not in event["data"],
          "Activity no shape do contrato (recibo no proprio doc; legado nao tocado = None)")
    writes = len(WRITES)
    replay = svc(ALICE).change_stage(10, body)
    check(replay["replayed"] and replay["activity_id"] == receipt_id and replay["stage"]["version"] == 2
          and len(WRITES) == writes, "replay idempotente: mesmo operation_id e contato, nada gravado")
    expect(409, "operation_reused", lambda: svc(ALICE).change_stage(11, payload("awaiting_followup", 1, "op-happy-0001")),
           "mesmo operation_id em OUTRO contato")
    expect(409, "operation_reused", lambda: svc(ALICE).change_stage(10, payload("awaiting_followup", 2, "op-happy-0001")),
           "mesmo operation_id com outro payload")
    stale = expect(409, "stale_version", lambda: move(ALICE, 10, "awaiting_followup", 1, "op-stale-0001"),
                   "versao antiga")
    check(stale.detail["current"] == {"stage": "in_service", "version": 2, "changed_at": BASE_NOW.isoformat(),
                                      "changed_by_user_id": 1, "changed_by_name": "Operadora Alice"},
          "409 stale_version traz quem moveu, para onde e quando")
    expect(422, "same_stage", lambda: move(ALICE, 10, "in_service", 2, "op-same-0001"), "mesma etapa")
    expect(422, "reason_required", lambda: move(ALICE, 10, "non_converted", 2, "op-rule-0001"),
           "Nao convertido sem motivo")
    expect(422, "note_not_allowed", lambda: move(ALICE, 10, "non_converted", 2, "op-rule-0002", reason="price",
                                                 reason_note="texto"), "nota so no motivo Outro")
    secret = "DADO-CLINICO-" + "x" * 120
    exc = expect(422, "note_invalid", lambda: move(ALICE, 10, "non_converted", 2, "op-rule-0003", reason="other",
                                                   reason_note=secret), "nota acima de 120 caracteres")
    check("DADO-CLINICO" not in json.dumps(exc.detail, ensure_ascii=False), "422 da nota nao ecoa o texto")
    expect(422, "note_invalid", lambda: move(ALICE, 10, "non_converted", 2, "op-rule-0004", reason="other",
                                             reason_note="linha\nquebrada"), "nota com quebra de linha")
    expect(422, "reason_not_allowed", lambda: move(ALICE, 10, "non_converted", 2, "op-rule-0005",
                                                   reason="not_informed"), "motivo so de migracao nao e escolhivel")
    expect(422, "reason_not_allowed", lambda: move(ALICE, 10, "awaiting_followup", 2, "op-rule-0006", reason="price"),
           "etapa sem motivo recusa motivo")
    expect(422, "unknown_stage", lambda: move(ALICE, 10, "lost_forever", 2, "op-rule-0007"), "etapa inexistente")
    expect(422, "stage_not_allowed", lambda: move(ALICE, 10, "unclassified", 2, "op-rule-0008"),
           "A classificar nao e destino manual")
    expect(422, "appointment_kind_invalid", lambda: move(ALICE, 10, "awaiting_followup", 2, "op-rule-0009",
                                                         appointment_kind="consultation"),
           "tipo de compromisso so em Agendado")
    check(len(WRITES) == writes, "nenhuma regra violada grava algo")

    entry = move(ALICE, 10, "non_converted", 2, "op-lost-0001", reason="price")
    entry_doc = doc("crm_activities", entry["activity_id"])
    check(entry["stage"]["reason"] == {"key": "price", "label": "Preço"} and entry_doc["stage_reason"] == "price"
          and entry_doc["entry_kind"] == "move" and entry_doc["from_reason"] is None, "Nao convertido com motivo")
    check("price" not in contact_values(doc("wa_contacts", 10))
          and not [key for key in doc("wa_contacts", 10) if "reason" in key],
          "motivo NUNCA vai para o contato (so na Activity)")
    card = {c["contact_id"]: c for c in all_cards(svc(ALICE).board())}[10]
    check(card["reason"] == {"key": "price", "label": "Preço"}, "card le o motivo da Activity apontada")
    bump("crm_activities", entry["activity_id"], stage_reason="financial")
    card = {c["contact_id"]: c for c in all_cards(svc(ALICE).board())}[10]
    check(card["reason"]["key"] == "financial", "motivo do card vem da Activity (nao de copia no contato)")
    bump("crm_activities", entry["activity_id"], stage_reason="price")
    fix = move(ALICE, 10, "non_converted", 3, "op-fix-0001", reason="distance")
    fix_doc = doc("crm_activities", fix["activity_id"])
    entry_month = fc.cohort_month(entry_doc["occurred_at"])
    check(fix_doc["event_type"] == fc.EVENT_REASON_CHANGED and fix_doc["corrects_entry_id"] == entry["activity_id"]
          and fix_doc["corrects_month"] == entry_month == "2026-10" and fix_doc["from_reason"] == "price"
          and fix_doc["stage_reason"] == "distance" and "entry_kind" not in fix_doc,
          "correcao de motivo = crm_stage_reason_changed com corrects_entry_id/corrects_month")
    check(doc("wa_contacts", 10)[fc.F_CHANGED_AT] == entry_doc["occurred_at"] and doc("wa_contacts", 10)[fc.F_VERSION] == 4,
          "correcao nao muda o tempo na etapa (so a versao)")
    fix2 = move(ALICE, 10, "non_converted", 4, "op-fix-0002", reason="other", reason_note="Mudou de cidade")
    fix2_doc = doc("crm_activities", fix2["activity_id"])
    check(fix2_doc["corrects_entry_id"] == entry["activity_id"] and fix2_doc["corrects_month"] == entry_month
          and fix2_doc["from_reason"] == "distance" and fix2_doc["data"]["reason_note"] == "Mudou de cidade",
          "correcao da correcao copia o alvo original")
    drawer = svc(ALICE).contact_drawer(10)
    check(drawer["stage"]["reason"]["key"] == "other" and drawer["stage"]["reason_note"] == "Mudou de cidade",
          "drawer: autora ve a nota livre")
    check(drawer["suggestions"] == [{"to_stage": "scheduled", "source": "bot_outcome", "label": "Cliente Agendado"}],
          "sugestao de um clique a partir do desfecho da Val")
    bob = svc(BOB).contact_drawer(10)
    check(bob["stage"]["reason"]["key"] == "other" and bob["stage"]["reason_note"] is None
          and all(item["reason_note"] is None for item in bob["history"]["items"]),
          "nota livre so para privilegiado ou autor (drawer e historico)")
    check(svc(MANAGER).contact_drawer(10)["stage"]["reason_note"] == "Mudou de cidade", "privilegiado ve a nota")
    react = move(ALICE, 10, "in_service", 5, "op-react-0001")
    react_doc = doc("crm_activities", react["activity_id"])
    check(react_doc["entry_kind"] == "reactivation" and react_doc["from_stage"] == "non_converted"
          and react_doc["from_reason"] == "other" and react["stage"]["reason"] is None,
          "reativacao preserva from_reason; etapa aberta sem motivo")
    # Conversao (kind won) sem permissao propria: mover_etapa_funil basta
    # (saiu confirmar_conversao_funil/restricted, decisao do PO de 28/10).
    loyal = move(ALICE, 10, "loyal", 6, "op-loyal-0001")
    check(loyal["stage"]["key"] == "loyal" and doc("wa_contacts", 10)[fc.F_MAX_ORDER] == 50
          and doc("wa_contacts", 10)["converted_by_user_id"] == 1,
          "Paciente em acompanhamento (ganho) pela operadora com mover, sem permissao de conversao")
    scheduled = move(MANAGER, 10, "scheduled", 7, "op-sched-0001", appointment_kind="procedure")
    check(scheduled["stage"]["appointment_kind"] == "procedure"
          and doc("crm_activities", scheduled["activity_id"])["data"]["appointment_kind"] == "procedure"
          and doc("wa_contacts", 10)[fc.F_MAX_ORDER] == 50 and doc("wa_contacts", 10)["assigned_to"] is None,
          "Cliente Agendado com tipo; maior etapa nao regride; dono intocado")
    check(doc("wa_contacts", 10)["converted_by_user_id"] == 1
          and doc("crm_activities", scheduled["activity_id"])["data"]["legacy_qualification"] is None,
          "legado ja 'convertido': nada regravado, quem converteu continua o mesmo")
    check(svc(ALICE).contact_drawer(10)["suggestions"] == [], "sem sugestao quando ja esta na etapa sugerida")

    triage = move(ALICE, 17, "new", 0, "op-triage-0001")
    c17 = doc("wa_contacts", 17)
    check(doc("crm_activities", triage["activity_id"])["entry_kind"] == "triage" and c17[fc.F_VERSION] == 1
          and c17[fc.F_ENTERED_AT] == c17["first_seen_at"] and c17[fc.F_COHORT] == "2026-09"
          and c17[fc.F_MAX_ORDER] == 10 and doc("crm_activities", triage["activity_id"])["from_stage"] is None,
          "incluir no funil: triagem, entrada = first_seen_at (ja conversava) e coorte dela")
    move(ALICE, 22, "new", 0, "op-triage-0002")
    check(doc("wa_contacts", 22)[fc.F_ENTERED_AT] == NOW[0] - timedelta(minutes=1)
          and doc("wa_contacts", 22)[fc.F_COHORT] == "2026-10", "contato que nunca escreveu entra agora")
    triage2 = move(ALICE, 18, "in_service", 1, "op-triage-0003")
    check(doc("crm_activities", triage2["activity_id"])["entry_kind"] == "triage", "saida de A classificar = triagem")

    expect(403, "out_of_scope_write", lambda: move(ALICE, 14, "awaiting_followup", 1, "op-thread-0001"),
           "acesso so por thread propria (coex) nao move")
    activity("hist14", 14, fc.EVENT_CHANGED, BASE_NOW - timedelta(days=20), "in_service", "scheduled", "move",
             actor=BOB)
    thread_only = svc(ALICE).contact_drawer(14)
    check(thread_only["capabilities"] == {"can_move": False, "write_scope": False}
          and thread_only["stage"]["key"] == "scheduled" and thread_only["history"] == {"items": [], "next_cursor": None},
          "so-thread: etapa atual sem historico/nota e sem mover")
    legacy = move(ALICE, 13, "in_service", 1, "op-legacy-0001")
    check(legacy["stage"]["key"] == "in_service" and "assigned_to_uid" not in doc("wa_contacts", 13),
          "guard de UID legado derivado nao da 409 falso nem faz backfill")
    expect(409, "contact_unavailable", lambda: move(MANAGER, 15, "awaiting_followup", 1, "op-backup-0001"),
           "backup nao muda")
    expect(409, "contact_unavailable", lambda: move(MANAGER, 16, "awaiting_followup", 1, "op-arch-0001"),
           "arquivado nao muda")
    expect(404, "out_of_scope", lambda: move(ALICE, 15, "awaiting_followup", 1, "op-backup-0002"),
           "backup nem aparece para o operador")
    expect(404, "out_of_scope", lambda: svc(ALICE).contact_drawer(15), "drawer de backup para operador = 404")
    expect(404, "out_of_scope", lambda: svc(ALICE).contact_drawer(16), "drawer de arquivado para operador = 404")
    archived = svc(MANAGER).contact_drawer(16)
    check(archived["contact"]["is_archived"] and not archived["capabilities"]["can_move"],
          "privilegiado ve arquivado com can_move=false")
    expect(404, "out_of_scope", lambda: svc(ALICE).contact_drawer(12), "IDOR: drawer de lead do colega")
    expect(404, "out_of_scope", lambda: move(ALICE, 12, "awaiting_followup", 1, "op-idor-0001"),
           "IDOR: mover lead do colega")
    expect(404, "out_of_scope", lambda: svc(ALICE).contact_drawer(99), "contato de outro tenant nao resolve")
    expect(403, "permission_denied", lambda: move(BOB, 10, "awaiting_followup", 8, "op-bob-0001"),
           "sem mover_etapa_funil = 403")

    for write in WRITES:
        tenant, name, _ = write["key"]
        check(tenant == TENANT and ((name == "wa_contacts" and write["merge"] and set(write["fields"]) <= CONTACT_WRITE_FIELDS)
                                    or (name == "crm_activities" and write["kind"] == "create")),
              "escrita permitida: %s/%s (%s)" % (name, write["key"][2][:16], write["kind"]))
    written = {write["key"] for write in WRITES}
    untouched = [key for key in start if key not in written and key[1] != "crm_activities" and DATA.get(key) != start[key]]
    check(untouched == [], "nenhum outro doc (threads, mensagens, tarefas, usuarios) mudou")
    for key in written:
        if key[1] == "wa_contacts":
            before = {k: v for k, v in start[key].items() if k not in CONTACT_WRITE_FIELDS}
            now_doc = {k: v for k, v in DATA[key].items() if k not in CONTACT_WRITE_FIELDS}
            final = DATA[key]
            legacy = LEGACY_BY_STAGE.get(final.get(fc.F_STAGE))
            check(before == now_doc and final.get("qualification") == (legacy or start[key].get("qualification"))
                  and ("converted_by_user_id" in final) == (final.get("qualification") == "convertido"),
                  "contato %s: bot/dono/LGPD/tags intocados; legado = equivalente da etapa (%s)"
                  % (key[2], final.get("qualification")))

    history = svc(ALICE).contact_drawer(10)["history"]
    items = history["items"]
    check(history["next_cursor"] is None and len(items) == 8 and items[-1]["synthetic"]
          and items[-1]["event_type"] == "crm_funnel_entered" and items[-1]["to_stage"] == "new"
          and items[-1]["occurred_at"] == start[(TENANT, "wa_contacts", "10")][fc.F_ENTERED_AT].isoformat(),
          "historico + item sintetico de entrada (intake) na ultima pagina")
    real = [item for item in items if not item["synthetic"]]
    check([item["occurred_at"] for item in real] == sorted((item["occurred_at"] for item in real), reverse=True)
          and real[-1]["from_stage"] == "new" and real[0]["to_stage"] == "scheduled"
          and real[0]["actor"] == {"type": "user", "user_id": 3, "name": "Supervisora Sintetica"},
          "historico em ordem decrescente com autor resolvido")
    check({item["event_type"] for item in real} == {fc.EVENT_CHANGED, fc.EVENT_REASON_CHANGED}
          and any(item["from_reason"] == {"key": "other", "label": "Outro"} for item in real),
          "historico mostra correcoes e motivo anterior")
    check(all(item["via"] is None for item in items), "mudanca pelo quadro/cartao: via=None no historico")
    triage_items = svc(ALICE).contact_drawer(17)["history"]["items"]
    check(len(triage_items) == 1 and not triage_items[0]["synthetic"],
          "entrada por Activity (triagem manual) nao duplica item sintetico")

    contact(23, "new", BASE_NOW - timedelta(days=30))
    stage = "new"
    for index in range(24):
        target = "in_service" if stage != "in_service" else "awaiting_followup"
        activity("h23_%02d" % index, 23, fc.EVENT_CHANGED, BASE_NOW - timedelta(days=29) + timedelta(hours=index),
                 stage, target, "move")
        stage = target
    bump("wa_contacts", 23, **{fc.F_STAGE: stage, fc.F_VERSION: 25, fc.F_ACTIVITY: "h23_23"})
    first = svc(ALICE).contact_history(23)
    second = svc(ALICE).contact_history(23, first["next_cursor"])
    ids = [item["id"] for item in first["items"] + second["items"] if not item["synthetic"]]
    check(len(first["items"]) == 20 and first["next_cursor"] and len(second["items"]) == 5
          and second["items"][-1]["synthetic"] and second["items"][-1]["to_stage"] == "new"
          and second["next_cursor"] is None and len(ids) == len(set(ids)) == 24,
          "historico pagina 20 + resto, sintetico so na ultima pagina")
    expect(400, "cursor_invalid", lambda: svc(ALICE).contact_history(23, first["next_cursor"] + "x"),
           "cursor do historico adulterado")
    expect(400, "cursor_invalid", lambda: svc(ALICE).contact_history(10, first["next_cursor"]),
           "cursor do historico de outro contato")


def scenario_concurrency():
    title("Concorrencia: guards, contencao e replay concorrente")
    seed()
    BEFORE_TRANSACTION.append(lambda: bump("wa_contacts", 21, assigned_to=2, assigned_to_uid="bob"))
    expect(409, "context_changed", lambda: move(ALICE, 21, "in_service", 1, "op-race-0001"),
           "transferencia entre autorizacao e commit")
    check(doc("wa_contacts", 21)[fc.F_STAGE] == "new" and not WRITES, "conflito atomico nao grava")
    bump("wa_contacts", 21, assigned_to=None, assigned_to_uid="")
    BEFORE_TRANSACTION.append(lambda: bump("users", 1, role="supervisor"))
    expect(409, "context_changed", lambda: move(ALICE, 21, "in_service", 1, "op-race-0002"),
           "perfil alterado durante a transacao")
    bump("users", 1, role="operador")
    BEFORE_COMMIT.append(lambda: bump("wa_contacts", 21, **{fc.F_STAGE: "awaiting_followup", fc.F_VERSION: 2,
                                                            fc.F_BY_USER: 3}))
    exc = expect(409, "stale_version", lambda: move(ALICE, 21, "in_service", 1, "op-race-0003"),
                 "escrita concorrente antes do commit: retry relê e acusa versao")
    check(exc.detail["current"]["stage"] == "awaiting_followup" and exc.detail["current"]["changed_by_name"] == "Supervisora Sintetica"
          and not WRITES, "retry nao grava a tentativa abortada")
    FORCE_ABORT[0] = MAX_ATTEMPTS
    expect(409, "try_again", lambda: move(ALICE, 21, "in_service", 2, "op-race-0004"), "contencao persistente")
    check(not WRITES and FORCE_ABORT[0] == 0, "Aborted apos retries = 409 try_again sem escrita")
    body = payload("in_service", 2, "op-race-0005")
    rid = receipt("alice", 21, "op-race-0005")

    def concurrent_twin():
        put("crm_activities", rid, {"id": rid, "tenant_id": TENANT, "contact_id": 21, "event_type": fc.EVENT_CHANGED,
                                    "request_fingerprint": fingerprint(21, body), "result_version": 3,
                                    "to_stage": "in_service", "from_stage": "awaiting_followup",
                                    "occurred_at": NOW[0], "actor_uid": "alice", "data": {}})
        bump("wa_contacts", 21, **{fc.F_STAGE: "in_service", fc.F_VERSION: 3, fc.F_ACTIVITY: rid})
    BEFORE_COMMIT.append(concurrent_twin)
    twin = svc(ALICE).change_stage(21, body)
    check(twin["replayed"] and twin["stage"]["version"] == 3 and not WRITES,
          "requisicao gemea confirmada antes: retry vira replay sem duplicar")


def scenario_context():
    title("Contexto e mensagens so-leitura (mesmo contrato do follow-up)")
    seed()
    before = copy.deepcopy(DATA)
    context = svc(ALICE).contact_context(10)
    check({row["id"] for row in context["conversations"]} == {"4__10"}, "operador ve so threads autorizadas")
    check(set(context["contact"]) == {"id", "display_name", "lead_temperature", "bot_completed", "is_archived"},
          "contexto devolve contato em whitelist (nunca o doc cru)")
    check({row["id"] for row in svc(MANAGER).contact_context(10)["conversations"]} == {"4__10", "6__coex10"},
          "privilegiado ve todas as threads do contato")
    expect(404, "out_of_scope", lambda: svc(ALICE).contact_context(10, "6__coex10"), "thread coex alheia")
    expect(404, "out_of_scope", lambda: svc(ALICE).contact_context(10, "4__11"), "thread de outro contato")
    expect(422, "invalid_conversation", lambda: svc(ALICE).contact_context(10, "bad/path"), "id de conversa invalido")
    rows = svc(ALICE).contact_messages(10, "4__10")["messages"]
    check([row["id"] for row in rows] == ["m-normal"], "admin_only/backup/visibilidade filtrados no servidor")
    check(len(svc(MANAGER).contact_messages(10, "4__10")["messages"]) == 4, "privilegiado recebe tudo")
    expect(404, "out_of_scope", lambda: svc(ALICE).contact_messages(10, "6__coex10"), "mensagens de thread alheia")
    expect(422, "invalid_conversation", lambda: svc(ALICE).contact_messages(10, ""), "mensagens exigem conversation_id")
    expect(404, "out_of_scope", lambda: svc(ALICE).contact_messages(12, "4__11"), "mensagens de lead do colega")
    check(DATA == before and not WRITES, "contexto/mensagens nao gravam, nao assumem e nao marcam lida")


def check_writes_whitelist(start, label):
    """Toda escrita do teste: contato (merge, crm_* + legado) ou Activity
    (create); nenhum outro doc mudou; no contato, fora do whitelist nada mudou."""
    for write in WRITES:
        tenant, name, _ = write["key"]
        if not (tenant == TENANT and ((name == "wa_contacts" and write["merge"]
                                       and set(write["fields"]) <= CONTACT_WRITE_FIELDS)
                                      or (name == "crm_activities" and write["kind"] == "create"))):
            raise AssertionError("%s: escrita fora do whitelist %r" % (label, write))
    written = {write["key"] for write in WRITES}
    for key, value in start.items():
        if key[1] == "wa_contacts":
            # Contatos (escritos ou nao): fora do whitelist nada mudou. Os
            # bumps do proprio teste (/qualify concorrente) so tocam o legado.
            before = {k: v for k, v in value.items() if k not in CONTACT_WRITE_FIELDS}
            after = {k: v for k, v in (DATA.get(key) or {}).items() if k not in CONTACT_WRITE_FIELDS}
            if before != after:
                raise AssertionError("%s: contato %s mudou fora do whitelist" % (label, key[2]))
        elif key[1] != "crm_activities" and key not in written and DATA.get(key) != value:
            raise AssertionError("%s: doc %s mudou sem escrita do funil" % (label, "/".join(key)))
    check(True, "%s: escritas so em wa_contacts (crm_* + qualification + converted_by_user_id) e crm_activities"
          % label)


def scenario_legacy_sync():
    title("Uma classificacao so: desfecho legado gravado junto da mudanca manual")
    seed()
    start = copy.deepcopy(DATA)
    result = move(ALICE, 11, "scheduled", 1, "op-sync-0001", appointment_kind="consultation")
    c11 = doc("wa_contacts", 11)
    event = doc("crm_activities", result["activity_id"])
    check(len(WRITES) == 2 and WRITES[0]["key"] == (TENANT, "wa_contacts", "11") and WRITES[0]["merge"]
          and set(WRITES[0]["fields"]) - set(fc.CONTACT_STAGE_FIELDS) == {"qualification", "converted_by_user_id"}
          and WRITES[1] == {"key": (TENANT, "crm_activities", result["activity_id"]), "kind": "create",
                            "merge": False, "fields": sorted(event)},
          "legado no MESMO merge da transacao (crm_* + qualification + converted_by_user_id) + 1 Activity")
    check(c11["qualification"] == "convertido" and c11["converted_by_user_id"] == 1
          and event["data"]["legacy_qualification"] == "convertido" and "via" not in event["data"],
          "Cliente Agendado grava 'convertido' e quem converteu; a Activity registra o legado gravado")
    check(AUDIT == [(TENANT, 1, "CONTACT_QUALIFY", "Contato 11: convertido (via funil)")],
          "auditoria CONTACT_QUALIFY '(via funil)' depois do commit")
    replay = svc(ALICE).change_stage(11, payload("scheduled", 1, "op-sync-0001", appointment_kind="consultation"))
    check(replay["replayed"] and len(WRITES) == 2 and len(AUDIT) == 1, "replay nao regrava o legado nem audita de novo")
    AUDIT.clear()
    loyal = move(MANAGER, 11, "loyal", 2, "op-sync-0002")
    check(set(WRITES[2]["fields"]) <= set(fc.CONTACT_STAGE_FIELDS) and doc("wa_contacts", 11)["converted_by_user_id"] == 1
          and doc("crm_activities", loyal["activity_id"])["data"]["legacy_qualification"] is None and not AUDIT,
          "legado ja equivalente (Agendado -> Paciente em acompanhamento): so crm_*, sem auditoria")
    move(MANAGER, 11, "non_converted", 3, "op-sync-0003", reason="price")
    check(doc("wa_contacts", 11)["qualification"] == "nao_convertido"
          and set(WRITES[4]["fields"]) - set(fc.CONTACT_STAGE_FIELDS) == {"qualification"}
          and AUDIT == [(TENANT, 3, "CONTACT_QUALIFY", "Contato 11: nao_convertido (via funil)")],
          "Nao convertido grava 'nao_convertido'; converted_by_user_id so e gravado em 'convertido'")
    AUDIT.clear()
    fix = move(MANAGER, 11, "non_converted", 4, "op-sync-0004", reason="distance")
    check(doc("crm_activities", fix["activity_id"])["event_type"] == fc.EVENT_REASON_CHANGED and not AUDIT
          and set(WRITES[6]["fields"]) <= set(fc.CONTACT_STAGE_FIELDS),
          "correcao de motivo com o legado ja igual: nada de legado nem auditoria")
    bump("wa_contacts", 11, qualification="qualificado")                      # /qualify no meio
    move(MANAGER, 11, "non_converted", 5, "op-sync-0005", reason="financial")
    check(doc("wa_contacts", 11)["qualification"] == "nao_convertido"
          and AUDIT == [(TENANT, 3, "CONTACT_QUALIFY", "Contato 11: nao_convertido (via funil)")],
          "correcao manual de motivo tambem ressincroniza um legado divergente")
    AUDIT.clear()
    for version, (stage, legacy) in enumerate((("in_service", "em_atendimento"),
                                               ("awaiting_followup", "nao_convertido"),
                                               ("disqualified", "nao_qualificado")), start=6):
        moved = move(MANAGER, 11, stage, version, "op-sync-%04d" % (10 + version))
        check(doc("wa_contacts", 11)["qualification"] == legacy
              and doc("crm_activities", moved["activity_id"])["data"]["legacy_qualification"] == legacy
              and AUDIT[-1] == (TENANT, 3, "CONTACT_QUALIFY", "Contato 11: %s (via funil)" % legacy),
              "%s grava o legado '%s' e audita" % (stage, legacy))
    check(fc.legacy_qualification_for(CATALOG, "new") is None and fc.legacy_qualification_for(CATALOG, "unclassified") is None,
          "Novo contato e A classificar nao tem legado equivalente")
    mark = len(WRITES)
    move(ALICE, 17, "new", 0, "op-sync-0020")
    check(set(WRITES[mark]["fields"]) <= set(fc.CONTACT_STAGE_FIELDS)
          and doc("wa_contacts", 17)["qualification"] == "em_atendimento",
          "incluir em Novo contato nunca escreve qualification")
    # Legado decidido sobre o doc lido NA transacao: /qualify concorrente que
    # ja deixou 'convertido' (de outra pessoa) nao e regravado.
    BEFORE_TRANSACTION.append(lambda: bump("wa_contacts", 19, qualification="convertido", converted_by_user_id=2))
    AUDIT.clear()
    mark = len(WRITES)
    move(MANAGER, 19, "scheduled", 1, "op-sync-0021")
    check(set(WRITES[mark]["fields"]) <= set(fc.CONTACT_STAGE_FIELDS) and doc("wa_contacts", 19)["converted_by_user_id"] == 2
          and not AUDIT, "legado ja igual no doc da transacao: nada regravado (quem converteu continua)")
    check_writes_whitelist(start, "sync legado")
    # Template sem legacy_qualification_sync (outro cliente): a etapa nunca
    # toca o legado, nem no encerramento.
    fc.TEMPLATES["nosync_test"] = {key: copy.deepcopy(value) for key, value in fc.TEMPLATES["clinic_v1"].items()
                                   if key != "legacy_qualification_sync"}
    try:
        nosync = fc.resolve_funnel({"enabled": True, "template": "nosync_test"})
        check(not nosync["legacy_qualification_sync"] and all(s["legacy_qualification"] is None for s in nosync["stages"]),
              "template sem sync resolve sem legado equivalente")
        AUDIT.clear()
        mark = len(WRITES)
        result = svc(MANAGER, nosync).change_stage(12, payload("scheduled", 1, "op-sync-0022"))
        check(set(WRITES[mark]["fields"]) <= set(fc.CONTACT_STAGE_FIELDS)
              and doc("wa_contacts", 12)["qualification"] == "em_atendimento" and not AUDIT
              and doc("crm_activities", result["activity_id"])["data"]["legacy_qualification"] is None,
              "template sem sync: mudanca manual so grava crm_*")
    finally:
        fc.TEMPLATES.pop("nosync_test", None)


def scenario_settings():
    title("Textos da clinica (tela Etapas): GET/PUT, versao, validacao e cache")
    seed()
    for user in (ALICE, MANAGER, EVE):
        expect(403, "permission_denied", lambda u=user: svc(u).get_settings(),
               "GET /settings sem gerenciar_config_sistema (%s)" % user["firebase_uid"])
        expect(403, "permission_denied",
               lambda u=user: svc(u).save_settings({"version": 0, "stage_labels": {"new": "X"}}),
               "PUT /settings sem gerenciar_config_sistema (%s)" % user["firebase_uid"])
    check(not WRITES and doc("system_settings", "funnel") is None, "403 nao grava nada")
    view = svc(ADMIN).get_settings()
    check(set(view) == {"version", "template", "stage_labels", "stage_descriptions", "reason_labels", "stages", "reasons"}
          and view["version"] == 0 and view["template"] == "clinic_v1"
          and view["stage_labels"] == view["stage_descriptions"] == view["reason_labels"] == {}
          and [s["key"] for s in view["stages"]] == [s["key"] for s in CATALOG["stages"]]
          and all(set(s) == {"key", "default_label", "default_description"} for s in view["stages"])
          and [r["key"] for r in view["reasons"]] == [r["key"] for r in CATALOG["reasons"]]
          and all(set(r) == {"key", "default_label"} for r in view["reasons"]),
          "GET /settings no shape do contrato (sem doc = versao 0 e mapas vazios)")
    check(next(s for s in view["stages"] if s["key"] == "loyal")["default_label"] == "Paciente em acompanhamento",
          "padrao = rotulo do template")
    # Cache aquecido ANTES do PUT (rotulo padrao) e painel calculado com ele.
    check(fc.stage_label(service_module.load_catalog(TENANT), "scheduled") == "Cliente Agendado", "catalogo das telas aquecido")
    dash_before = svc(MANAGER, service_module.load_catalog(TENANT)).dashboard()
    check(not dash_before["cached"], "painel calculado com os rotulos padrao")
    body = {"version": 0, "stage_labels": {"scheduled": "Consulta marcada", "loyal": "Em tratamento"},
            "stage_descriptions": {"scheduled": "Marcou a primeira consulta."},
            "reason_labels": {"price": "Valor"}}
    saved = svc(ADMIN).save_settings(copy.deepcopy(body))
    stored = doc("system_settings", "funnel")
    check(saved["version"] == 1 and stored["version"] == 1 and stored["template"] == "clinic_v1"
          and stored["updated_by_user_id"] == 9 and stored["updated_by_uid"] == "admin" and stored["updated_at"] == NOW[0]
          and stored["stage_labels"] == body["stage_labels"] and stored["stage_descriptions"] == body["stage_descriptions"]
          and stored["reason_labels"] == body["reason_labels"] and saved["stage_labels"] == body["stage_labels"],
          "PUT grava versao+1, autor (id e uid), updated_at e os mapas")
    check(len(WRITES) == 1 and WRITES[0]["key"] == (TENANT, "system_settings", "funnel") and not WRITES[0]["merge"],
          "1 escrita: doc tenant-scoped system_settings/funnel (inteiro, sem merge)")
    check(AUDIT and AUDIT[-1][:3] == (TENANT, 9, "FUNNEL_SETTINGS_UPDATE")
          and "Consulta" not in AUDIT[-1][3] and "Valor" not in AUDIT[-1][3],
          "auditoria FUNNEL_SETTINGS_UPDATE sem o texto editado")
    catalog = service_module.load_catalog(TENANT)
    check(catalog["overrides_version"] == 1 and fc.stage_label(catalog, "scheduled") == "Consulta marcada"
          and fc.reason_label(catalog, "price") == "Valor", "cache invalidado no PUT: catalogo das telas com os textos novos")
    check(fc.stage_label(fc.load_tenant_funnel(TENANT), "scheduled") == "Cliente Agendado",
          "webhook/intake (load_tenant_funnel) nao usa os textos da clinica")
    stages = {s["key"]: s for s in svc(MANAGER, catalog).get_config()["catalog"]["stages"]}
    check(stages["scheduled"]["label"] == "Consulta marcada" and stages["scheduled"]["default_label"] == "Cliente Agendado"
          and stages["scheduled"]["description"] == "Marcou a primeira consulta."
          and stages["scheduled"]["default_description"] == fc.stage_def(CATALOG, "scheduled")["description"]
          and stages["loyal"]["label"] == "Em tratamento" and stages["new"]["label"] == "Novo contato",
          "/config: rotulo e texto da clinica, padrao preservado para 'restaurar padrao'")
    check(columns(svc(MANAGER, catalog).board())["scheduled"]["label"] == "Consulta marcada", "/board com o rotulo novo")
    lost = move(MANAGER, 12, "non_converted", 1, "op-text-0001", reason="price")
    check(lost["stage"]["reason"] == {"key": "price", "label": "Preço"}, "catalogo antigo da request (sem textos): rotulo padrao")
    card = {c["contact_id"]: c for c in svc(MANAGER, catalog).stage_cards("non_converted")["cards"]}[12]
    check(card["reason"] == {"key": "price", "label": "Valor"}, "/stages/{s}/cards: motivo com o rotulo da clinica")
    drawer = svc(MANAGER, catalog).contact_drawer(14)
    check(drawer["stage"]["label"] == "Consulta marcada"
          and svc(MANAGER, catalog).contact_drawer(12)["history"]["items"][0]["reason"]["label"] == "Valor",
          "drawer e historico com os rotulos da clinica")
    dash = svc(MANAGER, catalog).dashboard()
    check(not dash["cached"] and {row["stage"]: row["label"] for row in dash["current"]["stages"]}["scheduled"] == "Consulta marcada"
          and {row["stage"]: row["label"] for row in dash["cohort"]["month"]["levels"]}["loyal"] == "Em tratamento"
          and {row["stage"]: row["label"] for row in dash["movements"]}["scheduled"] == "Consulta marcada",
          "painel: versao dos textos na chave do cache (nada de rotulo velho) e rotulos novos")
    writes = len(WRITES)
    stale = expect(409, "stale_version", lambda: svc(ADMIN).save_settings({"version": 0, "stage_labels": {}}),
                   "PUT com versao antiga")
    check(stale.detail["current"] == {"version": 1} and doc("system_settings", "funnel")["version"] == 1
          and len(WRITES) == writes, "409 stale_version traz a versao atual e nao grava")
    secret = "TEXTO-SECRETO-" + "x" * 40
    for label, bad in (("chave de etapa desconhecida", {"stage_labels": {"attended": "Atendido"}}),
                       ("rotulo com 41 caracteres", {"stage_labels": {"new": secret[:41]}}),
                       ("texto com 201 caracteres", {"stage_descriptions": {"new": (secret * 5)[:201]}}),
                       ("quebra de linha", {"reason_labels": {"price": "Valor\n" + secret}}),
                       ("valor que nao e texto", {"stage_labels": {"new": 5}}),
                       ("mapa que nao e objeto", {"stage_descriptions": [secret]}),
                       ("motivo usado como etapa", {"reason_labels": {"scheduled": "Agendou"}})):
        exc = expect(422, "overrides_invalid", lambda b=bad: svc(ADMIN).save_settings(dict(b, version=1)),
                     "422 overrides_invalid: %s" % label)
        check("SECRETO" not in json.dumps(exc.detail, ensure_ascii=False), "422 sem eco do texto (%s)" % label)
    for bad_version in (-1, "1", True, None):
        expect(422, "invalid_payload", lambda v=bad_version: svc(ADMIN).save_settings({"version": v}),
               "versao invalida %r" % (bad_version,))
    check(len(WRITES) == writes and doc("system_settings", "funnel")["version"] == 1, "nenhum 422 grava")
    saved = svc(ADMIN).save_settings({"version": 1, "reason_labels": {"price": "Preço alto"}})
    check(saved["stage_labels"] == body["stage_labels"] and saved["stage_descriptions"] == body["stage_descriptions"]
          and saved["reason_labels"] == {"price": "Preço alto"} and saved["version"] == 2,
          "mapa ausente fica como esta; mapa enviado substitui o salvo")
    saved = svc(ADMIN).save_settings({"version": 2, "stage_labels": {"scheduled": "", "loyal": "  Em tratamento  "},
                                      "stage_descriptions": {"scheduled": None}})
    catalog = service_module.load_catalog(TENANT)
    check(saved["stage_labels"] == {"loyal": "Em tratamento"} and saved["stage_descriptions"] == {}
          and fc.stage_label(catalog, "scheduled") == "Cliente Agendado"
          and fc.stage_def(catalog, "scheduled")["description"] == fc.stage_def(CATALOG, "scheduled")["description"],
          "texto vazio/nulo volta ao padrao; espacos nas pontas aparados")
    TENANTS[TENANT]["settings"]["funnel"]["stage_labels"] = {"loyal": "Fidelizado", "awaiting_followup": "Retorno"}
    view = svc(ADMIN).get_settings()
    catalog = service_module.load_catalog(TENANT)
    defaults = {s["key"]: s["default_label"] for s in view["stages"]}
    check(defaults["loyal"] == "Fidelizado" and fc.stage_label(catalog, "loyal") == "Em tratamento"
          and fc.stage_label(catalog, "awaiting_followup") == "Retorno",
          "padrao = settings.funnel da Castro sobre o template; texto da clinica vence")
    TENANTS[TENANT]["settings"]["funnel"].pop("stage_labels")
    # Outra instancia gravou: esta so ve depois do TTL (30 s) do cache.
    service_module.load_catalog(TENANT)
    put("system_settings", "funnel", dict(doc("system_settings", "funnel"), version=4,
                                          stage_labels={"new": "Chegou agora"}))
    check(fc.stage_label(service_module.load_catalog(TENANT), "new") == "Novo contato",
          "cache por tenant (30 s): escrita de outra instancia aparece so no TTL")
    real_time = service_module.time
    later = real_time.monotonic() + service_module.OVERRIDES_TTL_SECONDS + 1
    service_module.time = SimpleNamespace(monotonic=lambda: later)
    try:
        check(fc.stage_label(service_module.load_catalog(TENANT), "new") == "Chegou agora",
              "TTL (%d s) vencido: rele o doc" % service_module.OVERRIDES_TTL_SECONDS)
    finally:
        service_module.time = real_time
    service_module.reset_overrides_cache()
    put("system_settings", "funnel", {"version": 5, "template": "clinic_v1",
                                      "stage_labels": {"new": "z" * 60, "scheduled": "Agendou", "ghost": "X"},
                                      "stage_descriptions": "lixo", "reason_labels": {"price": 7}})
    service_module.reset_overrides_cache()
    view = svc(ADMIN).get_settings()
    catalog = service_module.load_catalog(TENANT)
    check(view["version"] == 5 and view["stage_labels"] == {"scheduled": "Agendou"} and view["stage_descriptions"] == {}
          and view["reason_labels"] == {} and fc.stage_label(catalog, "new") == "Novo contato"
          and fc.stage_label(catalog, "scheduled") == "Agendou" and fc.reason_label(catalog, "price") == "Preço",
          "doc editado a mao com entradas invalidas: ignoradas chave a chave (tela e quadro nao quebram)")
    original = FunnelRepository.overrides
    FunnelRepository.overrides = lambda self: (_ for _ in ()).throw(RuntimeError("indisponivel"))
    service_module.reset_overrides_cache()
    try:
        catalog = service_module.load_catalog(TENANT)
        check(catalog and fc.stage_label(catalog, "scheduled") == "Cliente Agendado",
              "leitura dos textos falhou: rotulos padrao e o funil continua")
    finally:
        FunnelRepository.overrides = original
    check(fc.stage_label(service_module.load_catalog(TENANT), "scheduled") == "Agendou", "a falha nao fica em cache")
    check(all(write["key"] == (TENANT, "system_settings", "funnel") or write["key"][1] in ("wa_contacts", "crm_activities")
              for write in WRITES), "textos: nenhuma escrita fora de system_settings/funnel (alem da mudanca de etapa)")


def close_body(to_stage, version, op, **extra):
    return {"to_stage": to_stage, "expected_version": version, "operation_id": op, "reason": None,
            "reason_note": None, "appointment_kind": None, **extra}


def close(user, contact_id, body, conversation=None):
    """main.wa_set_attendance: contato lido pelo endpoint (get_wa_contact) e a
    funcao compartilhada do funil, antes de qualquer escrita do fechamento."""
    row = enriched_contact(contact_id)
    thread = conversation if conversation is not None else {"id": "4__%s" % contact_id, "contact_id": contact_id,
                                                              "is_backup": False}
    result = service_module.close_attendance_outcome(copy.deepcopy(user), thread, row, copy.deepcopy(body),
                                                     clock=lambda: NOW[0])
    NOW[0] += timedelta(minutes=1)
    return result


def scenario_close():
    title("Encerrar atendimento: desfecho = etapa (close_attendance_outcome)")
    seed()
    start = copy.deepcopy(DATA)
    # Gate (legado em_atendimento, etapa que nao e desfecho): o toggle de
    # fechar cobre; Bob (operador seed) nao tem mover_etapa_funil.
    check(not rbac.has_permission(BOB, "mover_etapa_funil"), "Bob nao tem mover_etapa_funil")
    body = close_body("scheduled", 1, "op-close-0001", appointment_kind="consultation")
    result = close(BOB, 12, body)
    c12 = doc("wa_contacts", 12)
    event = doc("crm_activities", receipt("bob", 12, "op-close-0001"))
    check(result["applied"] and not result["replayed"] and result["activity_id"] == event["id"]
          and result["stage"]["key"] == "scheduled" and result["stage"]["version"] == 2
          and result["stage"]["appointment_kind"] == "consultation" and result["qualification"] == "convertido",
          "gate sem mover_etapa_funil: etapa gravada e resposta com stage + legado")
    check(c12[fc.F_STAGE] == "scheduled" and c12["qualification"] == "convertido" and c12["converted_by_user_id"] == 2
          and c12[fc.F_BY_USER] == 2 and c12[fc.F_SOURCE] == "user",
          "contato: etapa + legado 'convertido' + quem converteu no mesmo merge")
    check(event["data"]["via"] == "close" and event["data"]["legacy_qualification"] == "convertido"
          and event["entry_kind"] == "move" and event["from_stage"] == "in_service" and event["actor_uid"] == "bob"
          and event["data"]["appointment_kind"] == "consultation",
          "Activity do encerramento: data.via='close', legado e tipo de compromisso")
    check(len(WRITES) == 2 and AUDIT == [(TENANT, 2, "CONTACT_QUALIFY", "Contato 12: convertido (no encerramento, via funil)")],
          "2 escritas (contato + Activity) e auditoria do legado '(no encerramento, via funil)'")
    history = svc(MANAGER).contact_history(12)["items"]
    check(history[0]["via"] == "close" and history[0]["to_stage"] == "scheduled" and history[-1]["via"] is None,
          "historico marca o desfecho escolhido no encerramento (via='close')")
    replay = close(BOB, 12, body)
    check(replay["applied"] and replay["replayed"] and replay["activity_id"] == event["id"]
          and replay["stage"]["key"] == "scheduled" and replay["qualification"] == "convertido"
          and len(WRITES) == 2 and len(AUDIT) == 1,
          "replay do mesmo operation_id (retry do fechamento): nada regravado, o fechamento segue")
    expect(409, "operation_reused", lambda: close(BOB, 12, dict(body, appointment_kind="procedure")),
           "mesmo operation_id com outro corpo")
    # Fora do gate (etapa de desfecho + legado terminal): trocar exige mover.
    bump("wa_contacts", 14, qualification="convertido")
    writes = len(WRITES)
    expect(403, "permission_denied", lambda: close(BOB, 14, close_body("non_converted", 1, "op-close-0002", reason="price")),
           "fora do gate: trocar desfecho sem mover_etapa_funil = 403")
    check(len(WRITES) == writes and doc("wa_contacts", 14)[fc.F_STAGE] == "scheduled", "403 nao grava nada")
    same = close(BOB, 14, close_body("scheduled", 1, "op-close-0003"))
    check(same["applied"] and same["activity_id"] is None and same["stage"]["key"] == "scheduled"
          and same["stage"]["version"] == 1 and len(WRITES) == writes and same["qualification"] == "convertido",
          "fora do gate, desfecho = etapa atual com legado igual: fecha sem escrita (sem pedir mover)")
    moved = close(MANAGER, 14, close_body("non_converted", 1, "op-close-0004", reason="price"))
    check(moved["stage"]["key"] == "non_converted" and moved["stage"]["reason"]["key"] == "price"
          and doc("wa_contacts", 14)["qualification"] == "nao_convertido"
          and doc("crm_activities", moved["activity_id"])["data"]["via"] == "close",
          "fora do gate com mover_etapa_funil: troca o desfecho e o legado")
    # Desfecho = etapa atual com legado divergente: so o legado (sem Activity).
    bump("wa_contacts", 14, qualification="nao_qualificado")
    AUDIT.clear()
    writes = len(WRITES)
    activities = len([key for key in DATA if key[1] == "crm_activities"])
    keep = close(BOB, 14, close_body("non_converted", 2, "op-close-0005"))
    c14 = doc("wa_contacts", 14)
    check(keep["applied"] and keep["activity_id"] is None and keep["stage"]["version"] == 2
          and keep["stage"]["reason"]["key"] == "price" and c14["qualification"] == "nao_convertido"
          and c14[fc.F_VERSION] == 2 and len(WRITES) == writes + 1 and WRITES[-1]["fields"] == ["qualification"]
          and len([key for key in DATA if key[1] == "crm_activities"]) == activities,
          "mantem Nao convertido sem informar motivo (o modal nao pede): so sincroniza o legado, motivo fica")
    check(AUDIT == [(TENANT, 2, "CONTACT_QUALIFY", "Contato 14: nao_convertido (no encerramento, via funil)")],
          "sync do legado auditado")
    again = close(BOB, 14, close_body("non_converted", 2, "op-close-0006", reason="price"))
    check(again["activity_id"] is None and len(WRITES) == writes + 1, "mesmo motivo informado: mesma etapa, nada a gravar")
    expect(403, "permission_denied", lambda: close(BOB, 14, close_body("non_converted", 2, "op-close-0007", reason="distance")),
           "fora do gate: corrigir o motivo tambem exige mover_etapa_funil")
    bump("wa_contacts", 14, qualification="em_atendimento")                   # legado reaberto: gate
    fix = close(BOB, 14, close_body("non_converted", 2, "op-close-0008", reason="distance"))
    fix_doc = doc("crm_activities", fix["activity_id"])
    check(fix_doc["event_type"] == fc.EVENT_REASON_CHANGED and fix_doc["data"]["via"] == "close"
          and fix["stage"]["reason"]["key"] == "distance" and doc("wa_contacts", 14)["qualification"] == "nao_convertido",
          "gate pelo legado aberto: correcao de motivo no encerramento sem mover_etapa_funil")
    react = close(BOB, 24, close_body("scheduled", 1, "op-close-0009"))
    check(doc("crm_activities", react["activity_id"])["entry_kind"] == "reactivation"
          and doc("wa_contacts", 24)["qualification"] == "convertido",
          "etapa de desfecho com legado aberto (gate): Bob reativa para Cliente Agendado")
    entry = close(BOB, 17, close_body("awaiting_followup", 0, "op-close-0010"))
    c17 = doc("wa_contacts", 17)
    check(entry["stage"]["key"] == "awaiting_followup" and c17[fc.F_ENTERED_AT] == c17["first_seen_at"]
          and c17["qualification"] == "nao_convertido"
          and doc("crm_activities", entry["activity_id"])["entry_kind"] == "triage",
          "contato fora do funil: o desfecho inclui no funil (triagem) com o legado equivalente")
    # Corrida: gate calculado com o doc do endpoint; o legado vira terminal
    # (outro request no /qualify) antes da transacao, sem bump de versao.
    BEFORE_TRANSACTION.append(lambda: bump("wa_contacts", 61, qualification="nao_qualificado"))
    writes = len(WRITES)
    expect(409, "context_changed", lambda: close(BOB, 61, close_body("non_converted", 1, "op-close-0011", reason="price")),
           "corrida: gate deixou de valer dentro da transacao = 409 (quem nao pode mover nao passa)")
    check(len(WRITES) == writes and doc("wa_contacts", 61)[fc.F_STAGE] == "disqualified", "corrida nao grava nada")
    BEFORE_TRANSACTION.append(lambda: bump("wa_contacts", 62, qualification="nao_qualificado"))
    raced = close(MANAGER, 62, close_body("non_converted", 1, "op-close-0012", reason="price"))
    check(raced["stage"]["key"] == "non_converted", "mesma corrida com mover_etapa_funil: segue")
    # Backup e arquivado: fora do funil, o legado vale como no modal antigo.
    writes = len(WRITES)
    for cid, thread, label in ((15, None, "contato backup"), (16, None, "contato arquivado"),
                               (13, {"id": "4__13", "contact_id": 13, "is_backup": True}, "thread de backup")):
        out = close(BOB, cid, close_body("scheduled", 1, "op-close-1%03d" % cid), conversation=thread)
        check(out == {"applied": False, "stage": None, "qualification": "convertido", "replayed": False,
                      "activity_id": None}, "%s: applied=False com o legado equivalente" % label)
    expect(422, "reason_required", lambda: close(BOB, 15, close_body("non_converted", 1, "op-close-1999")),
           "backup: desfecho ainda validado (motivo obrigatorio)")
    check(len(WRITES) == writes and doc("wa_contacts", 15) == start[(TENANT, "wa_contacts", "15")],
          "backup/arquivado: o funil nao grava nada")
    for target in ("in_service", "new", "unclassified", "bogus"):
        expect(422, "stage_not_allowed", lambda t=target: close(BOB, 13, close_body(t, 1, "op-close-2%s" % t[:3])),
               "%s nao e desfecho de encerramento" % target)
    secret = "NOTA-CLINICA-" + "z" * 30
    for label, bad in (("sem operation_id", {"to_stage": "scheduled", "expected_version": 1}),
                       ("campo extra", dict(close_body("scheduled", 1, "op-close-3001"), nota=secret)),
                       ("versao texto", close_body("scheduled", "1", "op-close-3002", reason_note=secret)),
                       ("corpo lista", [secret])):
        exc = expect(422, "invalid_payload", lambda b=bad: close(BOB, 13, b), "422 invalid_payload: %s" % label)
        check(secret not in json.dumps(exc.detail, ensure_ascii=False), "422 sem eco (%s)" % label)
    stale = expect(409, "stale_version", lambda: close(BOB, 13, close_body("scheduled", 0, "op-close-3003")),
                   "versao antiga aborta o fechamento")
    check(stale.detail["current"]["stage"] == "awaiting_followup" and stale.detail["current"]["version"] == 1,
          "409 traz a etapa atual (para reaplicar)")
    expect(409, "contact_unavailable", lambda: service_module.FunnelService(
        FunnelRepository(TENANT), copy.deepcopy(BOB), None, CATALOG, clock=lambda: NOW[0]).close_stage(
        16, enriched_contact(16), parse_stage_body(close_body("scheduled", 1, "op-close-3004"))),
        "close_stage direto em arquivado = 409 contact_unavailable")
    writes = len(WRITES)
    config.FEATURE_FUNNEL = False
    expect(409, "funnel_disabled", lambda: close(BOB, 13, close_body("scheduled", 1, "op-close-4001")),
           "flag desligada depois que a tela carregou: 409, nao fecha sem desfecho")
    config.FEATURE_FUNNEL = True
    TENANTS[TENANT]["settings"]["funnel"]["enabled"] = False
    expect(409, "funnel_disabled", lambda: close(BOB, 13, close_body("scheduled", 1, "op-close-4002")),
           "funil do tenant desligado: 409 funnel_disabled")
    TENANTS[TENANT]["settings"]["funnel"]["enabled"] = True
    with common.tenant_context(OTHER_TENANT):
        expect(403, "tenant_mismatch", lambda: close(BOB, 13, close_body("scheduled", 1, "op-close-4003")),
               "contexto de outro tenant")
    expect(403, "tenant_mismatch", lambda: close({**BOB, "tenant_id": OTHER_TENANT}, 13,
                                                 close_body("scheduled", 1, "op-close-4004")), "sessao de outro tenant")
    expect(403, "read_only_session", lambda: close({**BOB, "impersonation": {"sid": "a" * 32}}, 13,
                                                   close_body("scheduled", 1, "op-close-4005")), "Ver como nao encerra")
    bump("users", 2, is_active=0)
    expect(403, "user_inactive", lambda: close(BOB, 13, close_body("scheduled", 1, "op-close-4006")),
           "usuario desativado relido")
    bump("users", 2, is_active=1)
    check(len(WRITES) == writes, "nenhum 409/403/422 grava")
    check_writes_whitelist(start, "encerramento")


def expected_dashboard(month):
    start, end = fc.month_bounds(month)
    contacts = [row for key, row in DATA.items() if key[0] == TENANT and key[1] == "wa_contacts"]
    events = [row for key, row in DATA.items() if key[0] == TENANT and key[1] == "crm_activities"]
    live = live_contacts()
    stages = CATALOG["stages"]
    current = {stage["key"]: sum(1 for row in live if row[fc.F_STAGE] == stage["key"]) for stage in stages}
    with_stage = sum(1 for row in live if row[fc.F_STAGE] > "")
    cohort = [row for row in contacts if row.get(fc.F_COHORT) == month and row.get("is_backup") is False]
    excluded = {stage["key"] for stage in stages if stage["kind"] == fc.KIND_EXCLUDED}
    booked = fc.stage_def(CATALOG, "scheduled")["order"]
    in_month = lambda row: start <= row["occurred_at"] < end
    reached = lambda row, order: isinstance(row.get(fc.F_MAX_ORDER), int) and row[fc.F_MAX_ORDER] >= order
    changes = [row for row in events if row.get("event_type") == fc.EVENT_CHANGED and in_month(row)]
    finals = {"moved": {}, "triage": {}}
    for row in changes:
        if row.get("to_stage") != "non_converted":
            continue
        if row.get("entry_kind") in fc.COUNTED_ENTRY_KINDS:
            finals["moved"][row["id"]] = row["stage_reason"]
        elif row.get("entry_kind") == "triage":
            finals["triage"][row["id"]] = row["stage_reason"]
    for row in sorted((row for row in events if row.get("event_type") == fc.EVENT_REASON_CHANGED
                       and row.get("corrects_month") == month), key=lambda row: row["occurred_at"]):
        for final in finals.values():
            if row.get("corrects_entry_id") in final:
                final[row["corrects_entry_id"]] = row["stage_reason"]
    tallies = {}
    for name, final in finals.items():
        counts = tallies.setdefault(name, {})
        for reason in final.values():
            counts[reason] = counts.get(reason, 0) + 1
    milestones = fc.milestone_stages(CATALOG)
    return {
        "current": current, "with_stage": with_stage, "unknown": with_stage - sum(current.values()),
        "entered": len(cohort),
        "excluded": sum(1 for row in cohort if row.get(fc.F_STAGE) in excluded),
        "lgpd": sum(1 for row in cohort if row.get("lgpd_consent") is True),
        "levels_gross": {stage["key"]: sum(1 for row in cohort if reached(row, stage["order"])) for stage in milestones},
        "levels": {stage["key"]: sum(1 for row in cohort if reached(row, stage["order"])
                                     and row.get(fc.F_STAGE) not in excluded) for stage in milestones},
        "closed": sum(1 for row in cohort if row.get(fc.F_STAGE) == "non_converted"
                      and isinstance(row.get(fc.F_MAX_ORDER), int) and row[fc.F_MAX_ORDER] < booked),
        "moves": {stage["key"]: sum(1 for row in changes if row.get("to_stage") == stage["key"]
                                    and row.get("entry_kind") in fc.COUNTED_ENTRY_KINDS)
                  for stage in stages if stage["manual_target"]},
        "triage": sum(1 for row in changes if row.get("entry_kind") == "triage"),
        "react": sum(1 for row in changes if row.get("entry_kind") == "reactivation"),
        "reasons": tallies["moved"],
        "triage_reasons": tallies["triage"],
    }


def scenario_dashboard():
    title("Painel gerencial: atual, coorte, movimentos e motivos")
    seed()
    sep = lambda day: datetime(2026, 9, day, 15, 0, tzinfo=timezone.utc)
    activity("sep_move_1", 41, fc.EVENT_CHANGED, sep(10), "new", "in_service", "move")
    activity("sep_move_2", 42, fc.EVENT_CHANGED, sep(12), "in_service", "scheduled", "move")
    activity("sep_triage", 43, fc.EVENT_CHANGED, sep(13), "unclassified", "in_service", "triage")
    activity("sep_react", 44, fc.EVENT_CHANGED, sep(14), "non_converted", "in_service", "reactivation", from_reason="price")
    activity("sep_lost_1", 45, fc.EVENT_CHANGED, sep(15), "in_service", "non_converted", "move", reason="price")
    activity("sep_lost_2", 46, fc.EVENT_CHANGED, sep(16), "in_service", "non_converted", "move", reason="price")
    activity("sep_lost_3", 47, fc.EVENT_CHANGED, sep(17), "in_service", "non_converted", "move", reason="no_interest")
    activity("sep_lost_tri", 48, fc.EVENT_CHANGED, sep(18), "unclassified", "non_converted", "triage", reason="financial")
    activity("sep_fix_a", 45, fc.EVENT_REASON_CHANGED, sep(20), "non_converted", "non_converted", reason="insurance_not_accepted",
             from_reason="price", corrects=("sep_lost_1", "2026-09"))
    activity("sep_fix_b", 45, fc.EVENT_REASON_CHANGED, sep(21), "non_converted", "non_converted", reason="financial",
             from_reason="insurance_not_accepted", corrects=("sep_lost_1", "2026-09"))
    activity("oct_fix", 46, fc.EVENT_REASON_CHANGED, datetime(2026, 10, 2, 15, 0, tzinfo=timezone.utc),
             "non_converted", "non_converted", reason="distance", from_reason="price", corrects=("sep_lost_2", "2026-09"))
    activity("sep_fix_tri", 48, fc.EVENT_REASON_CHANGED, sep(25), "non_converted", "non_converted", reason="price",
             from_reason="financial", corrects=("sep_lost_tri", "2026-09"))
    # Descartados: spam que passou por Novo contato/Em andamento (maior etapa
    # monotonica) e um de setembro que chegou a Agendado.
    contact(80, "new", NOW[0] - timedelta(hours=5))
    contact(81, "new", NOW[0] - timedelta(hours=5))
    contact(82, "in_service", NOW[0] - timedelta(hours=6))
    contact(83, "disqualified", sep(20), max_order=40)
    move(ALICE, 10, "in_service", 1, "op-dash-0001")
    lost = move(ALICE, 10, "non_converted", 2, "op-dash-0002", reason="price")
    move(ALICE, 10, "non_converted", 3, "op-dash-0003", reason="no_response")
    move(ALICE, 21, "non_converted", 1, "op-dash-0004", reason="price")
    move(ALICE, 10, "in_service", 4, "op-dash-0005")
    move(ALICE, 17, "new", 0, "op-dash-0006")
    move(ALICE, 18, "in_service", 1, "op-dash-0007")
    move(ALICE, 22, "non_converted", 0, "op-dash-0008", reason="distance")        # triagem (sem etapa)
    move(ALICE, 22, "non_converted", 1, "op-dash-0009", reason="no_interest")     # correcao da triagem
    move(ALICE, 80, "disqualified", 1, "op-dash-0010")
    move(ALICE, 82, "disqualified", 1, "op-dash-0011")
    expect(403, "permission_denied", lambda: svc(ALICE).dashboard(), "operador sem painel")
    expect(403, "permission_denied", lambda: svc(NODASH).dashboard(), "supervisao sem ver_dashboard_funil")
    before = copy.deepcopy(DATA)
    writes = len(WRITES)
    result = svc(MANAGER).dashboard()
    check(result["month"] == "2026-10" and result["previous_month"] == "2026-09" and not result["cached"],
          "mes atual no fuso da clinica e anterior")
    for label, month in (("month", "2026-10"), ("previous", "2026-09")):
        want = expected_dashboard(month)
        cohort = result["cohort"][label]
        check(set(cohort) == {"entered", "excluded", "entered_net", "lgpd_accepted", "levels", "closed_without_booking"}
              and all(set(row) == {"stage", "label", "reached", "reached_gross"} for row in cohort["levels"]),
              "%s: Cohort com excluded, entered_net e degraus liquido/bruto" % label)
        check(cohort["entered"] == want["entered"] and cohort["excluded"] == want["excluded"]
              and cohort["entered_net"] == want["entered"] - want["excluded"]
              and cohort["lgpd_accepted"] == want["lgpd"]
              and {row["stage"]: row["reached"] for row in cohort["levels"]} == want["levels"]
              and {row["stage"]: row["reached_gross"] for row in cohort["levels"]} == want["levels_gross"]
              and cohort["closed_without_booking"] == want["closed"],
              "%s: coorte entered=%d excluded=%d lgpd=%d closed=%d e piramide liquida/bruta batem" % (
                  label, cohort["entered"], cohort["excluded"], cohort["lgpd_accepted"], cohort["closed_without_booking"]))
        check({row["stage"]: row[label] for row in result["movements"]} == want["moves"]
              and result["triage"][label] == want["triage"] and result["reactivations"][label] == want["react"],
              "%s: movimentos, triagem e reativacoes batem" % label)
        check({row["reason"]: row["count"] for row in result["reasons"][label]} == want["reasons"]
              and {row["reason"]: row["count"] for row in result["reasons"][label + "_triage"]} == want["triage_reasons"],
              "%s: motivos %s e da triagem %s com correcoes aplicadas" % (label, want["reasons"], want["triage_reasons"]))
    want = expected_dashboard("2026-10")
    check({row["stage"]: row["count"] for row in result["current"]["stages"]} == {k: v for k, v in want["current"].items()}
          and result["current"]["with_stage"] == want["with_stage"] and result["current"]["unknown_stage"] == 1 == want["unknown"],
          "agora no funil: etapas, with_stage e etapa fora do catalogo")
    check(set(result["reasons"]) == {"month", "previous", "month_triage", "previous_triage", "truncated"}
          and {row["reason"]: row["count"] for row in result["reasons"]["previous"]} == {"financial": 1, "distance": 1, "no_interest": 1}
          and {row["reason"]: row["count"] for row in result["reasons"]["month"]} == {"no_response": 1, "price": 1},
          "correcao feita em outubro corrige setembro; movimento e triagem em listas separadas")
    check({row["reason"]: row["count"] for row in result["reasons"]["previous_triage"]} == {"price": 1}
          and {row["reason"]: row["count"] for row in result["reasons"]["month_triage"]} == {"no_interest": 1},
          "motivos da triagem (antigos/sem etapa) com a correcao aplicada pelo corrects_entry_id")
    month_cohort, previous_cohort = result["cohort"]["month"], result["cohort"]["previous"]
    levels = {row["stage"]: row for row in month_cohort["levels"]}
    previous_levels = {row["stage"]: row for row in previous_cohort["levels"]}
    check(month_cohort["excluded"] == 5 and month_cohort["entered_net"] == month_cohort["entered"] - 5
          and levels["new"]["reached_gross"] - levels["new"]["reached"] == 2
          and levels["in_service"]["reached_gross"] - levels["in_service"]["reached"] == 1
          and levels["scheduled"]["reached_gross"] == levels["scheduled"]["reached"],
          "Descartado sai da base e dos degraus (inclusive o spam que passou por Novo contato)")
    check(previous_cohort["excluded"] == 1
          and previous_levels["scheduled"]["reached_gross"] - previous_levels["scheduled"]["reached"] == 1,
          "coorte anterior: descartado que chegou a Agendado sai do degrau")
    check(doc("crm_activities", lost["activity_id"])["stage_reason"] == "price", "entrada original preservada no historico")
    check(not result["reasons"]["truncated"] and any("Coorte" in note for note in result["notes"])
          and any("primeiro contato" in note and "fechado" in note for note in result["notes"])
          and any("Não qualificado" in note and "base" in note for note in result["notes"]),
          "notas: coorte, antigos no mes do 1o contato (mes fechado cresce) e base sem Nao qualificado")
    check([row["stage"] for row in result["cohort"]["month"]["levels"]] == ["new", "in_service", "scheduled", "loyal"],
          "degraus da coorte = marcos do clinic_v1 (Novo contato, Em atendimento, Cliente Agendado, Paciente em acompanhamento)")
    check(svc(MANAGER).dashboard()["cached"], "cache por (tenant, mes) de 2 min")
    check(not svc(MANAGER).dashboard(refresh=True)["cached"], "refresh=1 ignora o cache")
    previous = svc(MANAGER).dashboard(month="2026-09")
    check(previous["month"] == "2026-09" and previous["previous_month"] == "2026-08", "mes explicito")
    expect(422, "month_invalid", lambda: svc(MANAGER).dashboard(month="2026-13"), "mes invalido")
    TENANTS[TENANT]["settings"]["ai"]["lgpd_by_agent"] = True
    agent = svc(MANAGER).dashboard(refresh=True)
    check(agent["cohort"]["month"]["lgpd_accepted"] is None and any("LGPD" in note for note in agent["notes"]),
          "lgpd_by_agent: degrau do aceite fica nulo e o painel explica")
    TENANTS[TENANT]["settings"]["ai"].pop("lgpd_by_agent")
    service_module.REASON_STREAM_LIMIT, limit = 1, service_module.REASON_STREAM_LIMIT
    try:
        check(svc(MANAGER).dashboard(refresh=True)["reasons"]["truncated"], "stream de motivos limitado sinaliza truncated")
    finally:
        service_module.REASON_STREAM_LIMIT = limit
    check(DATA == before and len(WRITES) == writes, "painel nao grava nada")


def scenario_dashboard_limits():
    title("Painel: faixa do mes, throttle em todo calculo e cache limitado")
    seed()
    for month in ("9999-12", "0001-01", "0000-05", "1999-12", "2019-12", "2026-12", "2027-01"):
        expect(422, "month_invalid", lambda m=month: svc(MANAGER).dashboard(month=m),
               "mes %s fora de 2020-01..mes seguinte = 422 (nunca 500)" % month)
    check(svc(MANAGER).dashboard(month="2020-01")["previous_month"] == "2019-12", "2020-01 e o 1o mes aceito")
    check(svc(MANAGER).dashboard(month="2026-11")["month"] == "2026-11", "mes seguinte ao atual (BR) aceito")
    service_module.reset_rate_limits()
    service_module.reset_dashboard_cache()
    service_module.RATE_LIMIT, original = 3, service_module.RATE_LIMIT
    try:
        for month in ("2026-07", "2026-08", "2026-09"):
            check(not svc(MANAGER).dashboard(month=month)["cached"], "calculo de %s consome o throttle" % month)
        check(svc(MANAGER).dashboard(month="2026-09")["cached"], "cache valido nao consome o throttle")
        expect(429, "rate_limited", lambda: svc(MANAGER).dashboard(month="2026-06"),
               "4o mes distinto sem refresh = 429 (meses distintos nao furam o limite)")
    finally:
        service_module.RATE_LIMIT = original
        service_module.reset_rate_limits()
    service_module.reset_dashboard_cache()
    service_module.DASHBOARD_CACHE_MAX, cap = 3, service_module.DASHBOARD_CACHE_MAX
    try:
        for month in ("2026-05", "2026-06", "2026-07", "2026-08", "2026-09"):
            svc(MANAGER).dashboard(month=month)
        check(len(service_module._DASHBOARD_CACHE) == 3, "cache do painel com teto (os mais antigos saem)")
        check(svc(MANAGER).dashboard(month="2026-09")["cached"] and not svc(MANAGER).dashboard(month="2026-05")["cached"],
              "o mais recente fica, o mais antigo foi despejado")
    finally:
        service_module.DASHBOARD_CACHE_MAX = cap
        service_module.reset_rate_limits()
    service_module.reset_dashboard_cache()
    service_module.DASHBOARD_TTL_SECONDS, ttl = 0.0, service_module.DASHBOARD_TTL_SECONDS
    try:
        for month in ("2026-07", "2026-08", "2026-09"):
            svc(MANAGER).dashboard(month=month)
        check(len(service_module._DASHBOARD_CACHE) == 1, "entradas vencidas expurgadas a cada insercao")
    finally:
        service_module.DASHBOARD_TTL_SECONDS = ttl
        service_module.reset_rate_limits()
        service_module.reset_dashboard_cache()
    check(service_module.DASHBOARD_CACHE_MAX == 64, "teto padrao de 64 entradas")


def scenario_rate():
    title("Throttle por tenant|uid")
    seed()
    service_module.RATE_LIMIT, original = 3, service_module.RATE_LIMIT
    try:
        for _ in range(2):
            svc(ALICE).board()
        svc(ALICE).stage_cards("in_service")
        expect(429, "rate_limited", lambda: svc(ALICE).board(), "4a consulta seguida de quadro/coluna")
        check(svc(BOB).board()["columns"], "limite e por usuario")
    finally:
        service_module.RATE_LIMIT = original
        service_module.reset_rate_limits()


def scenario_index_gate():
    title("Gate estatico de indices (firestore.indexes.json): matriz montada pelo repositorio")
    seed()
    with open(os.path.join(ROOT, "firestore.indexes.json"), encoding="utf-8") as handle:
        indexes = json.load(handle)["indexes"]

    def fields_of(index):
        return tuple((item["fieldPath"], item.get("order")) for item in index["fields"])

    def covering(shape, available=None):
        sort = list(shape["orders"]) or [(shape["range"][0], "ASCENDING")]
        if shape["range"]:
            if len(shape["range"]) != 1 or sort[0][0] != shape["range"][0]:
                return None
        equality = set(shape["equality"])
        for index in (indexes if available is None else available):
            if index.get("collectionGroup") != shape["collection"] or index.get("queryScope") != "COLLECTION":
                continue
            fields = list(fields_of(index))
            head, tail = fields[:len(equality)], fields[len(equality):]
            if (len(fields) == len(equality) + len(sort) and {name for name, _ in head} == equality
                    and all(order == "ASCENDING" for _, order in head) and tail == sort):
                return tuple(fields)
        return None

    def key_of(shape):
        return (shape["collection"], shape["equality"], shape["range"], shape["orders"])

    def describe(shape):
        return "%s eq=%s range=%s order=%s" % (shape["collection"], list(shape["equality"]), list(shape["range"]),
                                               [o[0] + " " + o[1][:4] for o in shape["orders"]])

    # Matriz: o repositorio monta TODA combinacao direto (nao depende do que
    # os cenarios chegaram a exercitar, como o quadro asc do privilegiado).
    repo = FunnelRepository(TENANT)
    now = NOW[0]
    matrix = []

    def record(label, fn):
        mark = len(repository_module.QUERY_SHAPES)
        fn()
        shapes = repository_module.QUERY_SHAPES[mark:]
        if not shapes:
            raise AssertionError("matriz: %s nao montou consulta pelo repositorio" % label)
        matrix.extend(shapes)
        return shapes

    cuts = {}
    for stage in CATALOG["stages"]:
        cut = fc.stale_cutoff(stage, now)
        if cut:
            cuts.setdefault(stage["stale"]["kind"], (stage["key"], cut))
    check(set(cuts) == {fc.STALE_PATIENT_SILENCE},
          "clinic_v1 tem corte de parado por silencio do paciente (Novo contato, Em atendimento)")
    # A regra "tempo na etapa" segue suportada pelo repositorio/servico (outro
    # template ou settings futuros): a matriz monta o shape dela direto.
    time_rule = {"key": "in_service", "stale": {"kind": fc.STALE_TIME_IN_STAGE, "days": 5}}
    cuts[fc.STALE_TIME_IN_STAGE] = ("in_service", fc.stale_cutoff(time_rule, now))
    check(cuts[fc.STALE_TIME_IN_STAGE][1][0] == fc.F_CHANGED_AT, "corte por tempo na etapa usa crm_stage_changed_at")
    owners = (("tenant", None), ("in", ("in", ["alice", ""])), ("==", ("==", "alice")))
    pages = {}
    for owner_label, owner in owners:
        for order in ("desc", "asc"):
            pages[(owner_label, order)] = record("pagina %s %s" % (owner_label, order), lambda o=owner, d=(order == "desc"): (
                repo.stage_page("in_service", o, d, None, 2), repo.stage_page("in_service", o, d, (now, "30"), 2)))
        record("total %s" % owner_label, lambda o=owner: repo.count_stage("in_service", o))
        for kind, (stage_key, cut) in sorted(cuts.items()):
            record("parados %s %s" % (owner_label, kind),
                   lambda o=owner, s=stage_key, c=cut: repo.count_stage(s, o, stale=c))
    month = fc.cohort_month(now)
    start, end = fc.month_bounds(month)
    lost = [stage["key"] for stage in CATALOG["stages"] if stage["kind"] == fc.KIND_LOST][0]
    excluded = [stage["key"] for stage in CATALOG["stages"] if stage["kind"] == fc.KIND_EXCLUDED][0]
    record("agora no funil", repo.count_with_stage)
    record("coorte: entraram", lambda: repo.count_cohort(month))
    record("coorte: aceite LGPD", lambda: repo.count_cohort(month, lgpd_accepted=True))
    record("coorte: degrau", lambda: repo.count_cohort(month, min_order=10))
    record("coorte: fechou sem agendar", lambda: repo.count_cohort(month, stage=lost, below_order=40))
    record("coorte: descartados", lambda: repo.count_cohort(month, stage=excluded))
    record("coorte: descartados por degrau", lambda: repo.count_cohort(month, stage=excluded, min_order=10))
    record("eventos: movimentos", lambda: repo.count_changes(start, end, entry_kinds=fc.COUNTED_ENTRY_KINDS,
                                                             to_stage="in_service"))
    record("eventos: triagem", lambda: repo.count_changes(start, end, entry_kind=fc.ENTRY_KIND_TRIAGE))
    record("eventos: reativacoes", lambda: repo.count_changes(start, end, entry_kind=fc.ENTRY_KIND_REACTIVATION))
    record("eventos: motivos", lambda: repo.stream_entries(lost, service_module.REASON_ENTRY_KINDS, start, end, 5))
    record("eventos: correcoes", lambda: repo.stream_corrections(month, 5))
    record("historico", lambda: (repo.history_page(10, None, 21), repo.history_page(10, (now, "h1"), 21)))
    tasks = record("tarefas", lambda: (repo.pending_tasks([10, 11], limit=5),
                                       repo.pending_tasks([10, 11], limit=5, after=(now, "T1"))))
    record("recibo", lambda: repo.operation_rows("alice", "op-gate-0001"))

    for (owner_label, order), shapes in sorted(pages.items()):
        direction = "DESCENDING" if order == "desc" else "ASCENDING"
        found = covering(shapes[0])
        names = {name for name, _ in found or ()}
        check(len({key_of(shape) for shape in shapes}) == 1 and found is not None
              and found[-1] == (fc.F_CHANGED_AT, direction) and ("assigned_to_uid" in names) == (owner_label != "tenant"),
              "pagina %s %s (com e sem cursor) tem o seu indice de pagina" % (owner_label, order))
    tenant_asc = pages[("tenant", "asc")][0]
    without = [index for index in indexes if fields_of(index) != covering(tenant_asc)]
    check(covering(tenant_asc, without) is None, "sem o indice dela, a pagina asc do privilegiado fica descoberta")
    check(len({key_of(shape) for shape in tasks}) == 1
          and covering(tasks[0]) == (("status", "ASCENDING"), ("contact_id", "ASCENDING"), ("due_at", "ASCENDING")),
          "tarefas (com e sem cursor) no indice existente status,contact_id,due_at")

    # Toda shape com range/ordem (matriz + cenarios) precisa de indice exato.
    every = {key_of(shape): shape for shape in repository_module.QUERY_SHAPES if shape["range"] or shape["orders"]}
    for key in sorted(every, key=str):
        check(covering(every[key]) is not None, "indice para " + describe(every[key]))
    check(covering({"collection": "wa_contacts", "equality": ("crm_stage",), "range": (),
                    "orders": (("last_message_at", "DESCENDING"),)}) is None, "gate acusa shape sem indice")
    matrix_used = {covering(shape) for shape in matrix if shape["range"] or shape["orders"]}
    funnel_fields = {"crm_stage", "crm_cohort_month", "entry_kind", "event_type"}
    new_indexes = [fields_of(index) for index in indexes if index.get("queryScope") == "COLLECTION"
                   and ({item["fieldPath"] for item in index["fields"]} & funnel_fields)]
    check(len(new_indexes) == 12 and set(new_indexes) <= matrix_used,
          "os 12 indices do funil cobertos pela matriz do repositorio (nenhum indice novo)")


def run():
    print("Funil comercial: repository/service reais, Firestore em memoria (sem ADC/rede)")
    token = common.set_tenant_context(TENANT)
    try:
        for scenario in (scenario_fake, scenario_catalog, scenario_board, scenario_visibility, scenario_pagination,
                         scenario_tasks, scenario_task_truncation, scenario_display_names, scenario_stage_check,
                         scenario_moves, scenario_legacy_sync, scenario_concurrency, scenario_context,
                         scenario_settings, scenario_close, scenario_dashboard, scenario_dashboard_limits,
                         scenario_rate, scenario_index_gate):
            scenario()
    finally:
        common.reset_tenant_context(token)
    print("\n%d verificacoes passaram; nenhuma rede ou credencial utilizada." % CHECKS[0])


if __name__ == "__main__":
    try:
        run()
    except Exception:
        traceback.print_exc()
        print("\nFALHA depois de %d verificacoes." % CHECKS[0])
        sys.exit(1)
