# -*- coding: utf-8 -*-
"""Persistencia do funil comercial, sempre com tenant explicito.

Nao depende do contexto implicito de requests nem de main.py: toda leitura
e escrita usa tenant_collection/tenant_document. Escritas (todas em
transacao, com as leituras antes das escritas):
- commit_stage: campos crm_* do contato + o desfecho legado equivalente
  (qualification/converted_by_user_id, decisao do PO de 28/10) em merge +
  1 Activity (recibo idempotente) no mesmo commit;
- commit_legacy: so o desfecho legado, quando o encerramento confirma a
  etapa atual e o legado divergia (sem Activity: a etapa nao mudou);
- save_overrides: nomes e textos que a clinica edita
  (system_settings/funnel), com versao.

Hook de teste: com RECORD_SHAPES ligado, cada consulta montada registra o
seu "shape" (colecao, igualdades/in, range, order_by) em QUERY_SHAPES; o
simulador monta a matriz de consultas direto por aqui (escopo x ordem x
parados, coorte, eventos, historico e tarefas) e confere cada shape com
range/ordem contra firestore.indexes.json.
"""

import hashlib
import re

from fastapi import HTTPException
from google.cloud import firestore

from firestore_common import get_firestore_client, tenant_collection, tenant_document
from funnel_catalog import (
    EVENT_CHANGED, EVENT_REASON_CHANGED, F_ACTIVITY, F_CHANGED_AT, F_COHORT,
    F_MAX_ORDER, F_STAGE, F_VERSION, STAGE_EVENTS,
)

RECORD_SHAPES = False
QUERY_SHAPES = []

# Campos usados pela autorizacao, revalidados dentro da transacao.
CONTACT_GUARD_FIELDS = ("assigned_to", "assigned_to_uid", "is_backup", "is_archived")
USER_GUARD_FIELDS = ("is_active", "firebase_uid", "role", "perfil_acesso_id")
# Unicos campos fora de crm_* que a etapa grava no contato (desfecho legado
# equivalente, so em mudanca MANUAL; ver funnel_catalog).
LEGACY_FIELDS = ("qualification", "converted_by_user_id")
# Doc tenant-scoped com os nomes/textos que a clinica edita na tela "Etapas".
OVERRIDES_COLLECTION = "system_settings"
OVERRIDES_DOC = "funnel"
# get_all em blocos (o lote e por pagina, nunca por linha).
_BATCH = 100
_DOC_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")


class StageConflict(Exception):
    """Conflito detectado dentro da transacao; o servico traduz para HTTP.

    code: operation_reused | not_found | context_changed | stale_version.
    `contact` = doc atual lido na transacao (detalhe do stale_version)."""

    def __init__(self, code, contact=None):
        super().__init__(code)
        self.code = code
        self.contact = contact


def _row(snapshot):
    if not snapshot.exists:
        return None
    result = snapshot.to_dict() or {}
    result.setdefault("id", snapshot.id)
    return result


def _contact_row(snapshot):
    """Contato com id inteiro do proprio path (o doc id e a fonte)."""
    row = _row(snapshot)
    if row is not None:
        row["id"] = int(snapshot.id) if str(snapshot.id).isdigit() else snapshot.id
    return row


def stage_version(contact):
    """crm_stage_version como int (ausente ou lixo = 0)."""
    value = (contact or {}).get(F_VERSION)
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _record_shape(name, equality, ranges, orders):
    if not RECORD_SHAPES:
        return
    QUERY_SHAPES.append({
        "collection": name,
        "equality": tuple(sorted(set(equality))),
        "range": tuple(dict.fromkeys(ranges)),
        "orders": tuple((field, direction) for field, direction in orders if field != "__name__"),
    })


class FunnelRepository:
    def __init__(self, tenant_id):
        if not isinstance(tenant_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", tenant_id):
            raise HTTPException(403, detail={"code": "tenant_mismatch", "message": "Tenant do funil inválido."})
        self.tenant_id = tenant_id

    def collection(self, name):
        return tenant_collection(self.tenant_id, name)

    def reference(self, name, doc_id):
        return tenant_document(self.tenant_id, name, doc_id)

    def get(self, name, doc_id):
        return _row(self.reference(name, doc_id).get())

    def user(self, user_id):
        return self.get("users", user_id)

    def get_many(self, name, ids):
        """Lote por id via get_all ({id: doc}); ausentes ficam de fora."""
        unique = sorted({str(value) for value in ids
                         if value not in (None, "") and _DOC_ID.match(str(value))})
        result = {}
        for start in range(0, len(unique), _BATCH):
            refs = [self.reference(name, doc_id) for doc_id in unique[start:start + _BATCH]]
            for snapshot in get_firestore_client().get_all(refs):
                row = _contact_row(snapshot) if name == "wa_contacts" else _row(snapshot)
                if row is not None:
                    result[str(snapshot.id)] = row
        return result

    # -- consultas (todas com limite, ou count() agregado) -------------------

    def _query(self, name, equals=(), ins=(), ranges=(), orders=()):
        q = self.collection(name)
        for field, value in equals:
            q = q.where(field, "==", value)
        for field, values in ins:
            q = q.where(field, "in", list(values))
        for field, operator, value in ranges:
            q = q.where(field, operator, value)
        for field, direction in orders:
            q = q.order_by(field, direction=direction)
        _record_shape(name, [f for f, _ in equals] + [f for f, _ in ins],
                      [f for f, _, _ in ranges], orders)
        return q

    @staticmethod
    def _count(query):
        result = query.count(alias="n").get()
        return int(result[0][0].value)

    @staticmethod
    def _contact_filters(stage, owner):
        """Igualdades fixas do quadro + escopo: None (tenant), ("in", [uid, ""])
        (operador: proprios + pool) ou ("==", uid) (so meus / dono)."""
        equals = [(F_STAGE, stage), ("is_archived", 0), ("is_backup", False)]
        ins = []
        if owner is not None:
            operator, value = owner
            if operator == "in":
                ins.append(("assigned_to_uid", list(value)))
            else:
                equals.append(("assigned_to_uid", value))
        return equals, ins

    def stage_page(self, stage, owner, descending=True, after=None, limit=21):
        direction = "DESCENDING" if descending else "ASCENDING"
        equals, ins = self._contact_filters(stage, owner)
        q = self._query("wa_contacts", equals, ins,
                        orders=[(F_CHANGED_AT, direction), ("__name__", direction)])
        if after:
            q = q.start_after({F_CHANGED_AT: after[0], "__name__": self.reference("wa_contacts", after[1])})
        return [_contact_row(s) for s in q.limit(limit).stream()]

    def count_stage(self, stage, owner=None, stale=None):
        """Total da coluna; com `stale` = (campo, corte) conta so os parados."""
        equals, ins = self._contact_filters(stage, owner)
        ranges = [(stale[0], "<", stale[1])] if stale else []
        return self._count(self._query("wa_contacts", equals, ins, ranges))

    def count_with_stage(self):
        return self._count(self._query("wa_contacts", [("is_archived", 0), ("is_backup", False)],
                                       ranges=[(F_STAGE, ">", "")]))

    def count_cohort(self, month, stage=None, lgpd_accepted=False, min_order=None, below_order=None):
        equals = [(F_COHORT, month), ("is_backup", False)]
        if stage:
            equals.append((F_STAGE, stage))
        if lgpd_accepted:
            equals.append(("lgpd_consent", True))
        ranges = []
        if min_order is not None:
            ranges.append((F_MAX_ORDER, ">=", min_order))
        if below_order is not None:
            ranges.append((F_MAX_ORDER, "<", below_order))
        return self._count(self._query("wa_contacts", equals, ranges=ranges))

    def _event_query(self, start, end, entry_kinds=None, entry_kind=None, to_stage=None):
        equals = [("event_type", EVENT_CHANGED)]
        ins = []
        if entry_kind:
            equals.append(("entry_kind", entry_kind))
        if entry_kinds:
            ins.append(("entry_kind", list(entry_kinds)))
        if to_stage:
            equals.append(("to_stage", to_stage))
        return self._query("crm_activities", equals, ins,
                           ranges=[("occurred_at", ">=", start), ("occurred_at", "<", end)])

    def count_changes(self, start, end, entry_kinds=None, entry_kind=None, to_stage=None):
        return self._count(self._event_query(start, end, entry_kinds, entry_kind, to_stage))

    def stream_entries(self, to_stage, entry_kinds, start, end, limit):
        q = self._event_query(start, end, entry_kinds=entry_kinds, to_stage=to_stage)
        return [_row(s) for s in q.limit(limit).stream()]

    def stream_corrections(self, month, limit):
        q = self._query("crm_activities", [("event_type", EVENT_REASON_CHANGED), ("corrects_month", month)])
        return [_row(s) for s in q.limit(limit).stream()]

    def history_page(self, contact_id, after=None, limit=21):
        q = self._query("crm_activities", [("contact_id", contact_id)], [("event_type", list(STAGE_EVENTS))],
                        orders=[("occurred_at", "DESCENDING"), ("__name__", "DESCENDING")])
        if after:
            q = q.start_after({"occurred_at": after[0], "__name__": self.reference("crm_activities", after[1])})
        return [_row(s) for s in q.limit(limit).stream()]

    def pending_tasks(self, contact_ids, limit=200, after=None):
        """Pendentes de ate 30 contatos numa consulta (indice status,contact_id,due_at).
        `after` = (due_at, id) da ultima linha de um lote cortado: continua
        dali. __name__ explicito: cursor por dict so usa os campos ordenados."""
        q = self._query("crm_tasks", [("status", "pending")], [("contact_id", list(contact_ids))],
                        orders=[("due_at", "ASCENDING"), ("__name__", "ASCENDING")])
        if after:
            q = q.start_after({"due_at": after[0], "__name__": self.reference("crm_tasks", after[1])})
        return [_row(s) for s in q.limit(limit).stream()]

    def operation_rows(self, actor_uid, operation_id, limit=5):
        """Eventos ja gravados com este operation_id pela mesma identidade."""
        q = self._query("crm_activities", [("operation_id", operation_id), ("actor_uid", actor_uid)])
        return [_row(s) for s in q.limit(limit).stream()]

    # -- escrita --------------------------------------------------------------

    def receipt_id(self, actor_uid, contact_id, operation_id):
        value = "\x1f".join([self.tenant_id, "stage", actor_uid, str(contact_id), operation_id])
        return "stage_" + hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _guard(self, transaction, contact, contact_guard, user_guard):
        """Revalida sob a transacao os campos usados pela autorizacao e o
        usuario (mesma leitura nas duas escritas de contato)."""
        if contact is None:
            raise StageConflict("not_found")
        # get_wa_contact deriva UID legado pelo dono, sem backfill. Repete a
        # normalizacao sob a transacao (mesma regra do follow-up): contato
        # com dono nunca vira pool so por faltar o UID no doc.
        normalized_uid = contact.get("assigned_to_uid") or ""
        if not normalized_uid and contact.get("assigned_to") is not None:
            owner = _row(self.reference("users", contact["assigned_to"]).get(transaction=transaction)) or {}
            normalized_uid = owner.get("firebase_uid") or ""
        actual = dict(contact, assigned_to_uid=normalized_uid)
        expected = dict(contact_guard, assigned_to_uid=contact_guard.get("assigned_to_uid") or "")
        if any(actual.get(key) != value for key, value in expected.items()):
            raise StageConflict("context_changed", contact)
        user_id, user_fields = user_guard
        user_row = _row(self.reference("users", user_id).get(transaction=transaction))
        if user_row is None or any(user_row.get(key) != value for key, value in user_fields.items()):
            raise StageConflict("context_changed", contact)

    def commit_stage(self, contact_id, receipt_id, fingerprint, expected_version,
                     contact_guard, user_guard, build):
        """Mudanca de etapa atomica. Le, nesta ordem e antes de escrever:
        recibo, contato, dono legado (normalizacao de UID), usuario e a
        Activity apontada. `build(contact, pointed)` devolve (campos crm_* +
        desfecho legado, activity) sem ler nada. Grava o contato com merge e
        cria a Activity (id = recibo). Nenhum outro documento e tocado."""
        contact_ref = self.reference("wa_contacts", contact_id)
        receipt_ref = self.reference("crm_activities", receipt_id)

        @firestore.transactional
        def apply(transaction):
            receipt = _row(receipt_ref.get(transaction=transaction))
            contact = _row(contact_ref.get(transaction=transaction))
            if receipt:
                if (receipt.get("request_fingerprint") != fingerprint
                        or str(receipt.get("contact_id")) != str(contact_id)):
                    raise StageConflict("operation_reused")
                return {"replayed": True, "contact": contact, "activity": receipt}
            self._guard(transaction, contact, contact_guard, user_guard)
            if stage_version(contact) != expected_version:
                raise StageConflict("stale_version", contact)
            pointer = contact.get(F_ACTIVITY)
            pointed = None
            if isinstance(pointer, str) and _DOC_ID.match(pointer):
                pointed = _row(self.reference("crm_activities", pointer).get(transaction=transaction))
            fields, activity = build(contact, pointed)
            transaction.set(contact_ref, fields, merge=True)
            transaction.create(receipt_ref, activity)
            return {"replayed": False, "contact": dict(contact, **fields), "activity": activity}

        return apply(get_firestore_client().transaction())

    def commit_legacy(self, contact_id, expected_version, expected_stage, contact_guard, user_guard, build):
        """So o desfecho legado (LEGACY_FIELDS), quando o encerramento
        confirma a etapa ATUAL: mesma versao e mesma etapa lidas na
        autorizacao (senao stale_version) e os mesmos guards. `build(contact)`
        devolve os campos ({} = nada a gravar). Sem Activity."""
        contact_ref = self.reference("wa_contacts", contact_id)

        @firestore.transactional
        def apply(transaction):
            contact = _row(contact_ref.get(transaction=transaction))
            self._guard(transaction, contact, contact_guard, user_guard)
            if stage_version(contact) != expected_version or (contact.get(F_STAGE) or None) != expected_stage:
                raise StageConflict("stale_version", contact)
            fields = build(contact)
            if any(key not in LEGACY_FIELDS for key in fields):
                raise ValueError("commit_legacy so grava o desfecho legado")
            if fields:
                transaction.set(contact_ref, fields, merge=True)
            return {"contact": dict(contact, **fields), "fields": dict(fields)}

        return apply(get_firestore_client().transaction())

    # -- textos da clinica (tela "Etapas") ------------------------------------

    def overrides(self):
        return self.get(OVERRIDES_COLLECTION, OVERRIDES_DOC)

    def save_overrides(self, expected_version, build):
        """Grava o doc inteiro (sem merge: chave removida = volta ao padrao)
        se a versao lida for a esperada; senao StageConflict stale_version
        com o doc atual. `build(current)` devolve o doc novo."""
        ref = self.reference(OVERRIDES_COLLECTION, OVERRIDES_DOC)

        @firestore.transactional
        def apply(transaction):
            current = _row(ref.get(transaction=transaction)) or {}
            version = current.get("version")
            version = version if isinstance(version, int) and not isinstance(version, bool) else 0
            if version != expected_version:
                raise StageConflict("stale_version", current)
            doc = build(current)
            transaction.set(ref, doc)
            return doc

        return apply(get_firestore_client().transaction())
