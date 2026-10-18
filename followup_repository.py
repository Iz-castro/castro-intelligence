# -*- coding: utf-8 -*-
"""Persistencia do follow-up humano, sempre com tenant explicito."""

import hashlib
import re

from fastapi import HTTPException
from google.cloud import firestore

from firestore_common import get_firestore_client, global_document, tenant_collection, tenant_document


def _row(snapshot):
    if not snapshot.exists:
        return None
    result = snapshot.to_dict() or {}
    result.setdefault("id", snapshot.id)
    return result


class FollowupRepository:
    """Nao depende do contexto implicito de requests ou de main.py."""

    def __init__(self, tenant_id):
        if not isinstance(tenant_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", tenant_id):
            raise HTTPException(403, "Tenant do follow-up inválido")
        self.tenant_id = tenant_id

    def collection(self, name):
        return tenant_collection(self.tenant_id, name)

    def reference(self, name, doc_id):
        return tenant_document(self.tenant_id, name, doc_id)

    def get(self, name, doc_id):
        return _row(self.reference(name, doc_id).get())

    def task(self, task_id):
        return self.get("crm_tasks", task_id)

    def user(self, user_id):
        return self.get("users", user_id)

    def settings(self):
        return self.get("system_settings", "followup")

    def operation_key(self, actor_uid, operation_id):
        value = "\x1f".join((self.tenant_id, actor_uid, operation_id))
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def operation(self, actor_uid, operation_id):
        return self.get("crm_activities", "op_" + self.operation_key(actor_uid, operation_id))

    def commit(self, task_id, expected_version, actor_uid, operation_id,
               fingerprint, task, activities, guards=(), companions=()):
        """Task, eventos e recibo idempotente no primeiro evento sao atomicos.

        Guards revalidam os campos usados pela autorizacao antes do commit.
        Nenhum documento de contato, conversa ou bot e escrito aqui.
        """
        task_ref = self.reference("crm_tasks", task_id)
        op_key = self.operation_key(actor_uid, operation_id)
        op_ref = self.reference("crm_activities", "op_" + op_key)

        @firestore.transactional
        def apply(transaction):
            old_op = _row(op_ref.get(transaction=transaction))
            current = _row(task_ref.get(transaction=transaction))
            if old_op:
                if old_op.get("request_fingerprint") != fingerprint or old_op.get("task_id") != task_id:
                    raise HTTPException(409, "operation_id já utilizado para outra operação")
                return {"task": current, "replayed": True,
                        "applied_version": old_op.get("result_version")}
            if expected_version is None:
                if current:
                    raise HTTPException(409, "Tarefa já existe")
            elif not current:
                raise HTTPException(404, "Tarefa não encontrada")
            elif current.get("version") != expected_version:
                raise HTTPException(409, "A tarefa mudou. Atualize a tela antes de continuar.")

            for other in companions:
                other_current = _row(self.reference("crm_tasks", other["task"]["id"]).get(transaction=transaction))
                if not other_current or other_current.get("version") != other["version"]:
                    raise HTTPException(409, "Uma das tarefas vinculadas mudou. Atualize a tela.")

            for name, doc_id, fields in guards:
                reference = global_document("channels", doc_id) if name == "__global_channels" else self.reference(name, doc_id)
                actual = _row(reference.get(transaction=transaction))
                if actual is not None and name == "wa_contacts":
                    # get_wa_contact deriva UID legado pelo dono, sem backfill.
                    # Repete essa normalizacao sob a transacao, nunca tratando
                    # contato com dono como pool so por faltar o UID no doc.
                    normalized_uid = actual.get("assigned_to_uid") or ""
                    if not normalized_uid and actual.get("assigned_to") is not None:
                        owner = _row(self.reference("users", actual["assigned_to"]).get(transaction=transaction)) or {}
                        normalized_uid = owner.get("firebase_uid") or ""
                    actual = dict(actual, assigned_to_uid=normalized_uid)
                    fields = dict(fields, assigned_to_uid=fields.get("assigned_to_uid") or "")
                if actual is None or any(actual.get(key) != value for key, value in fields.items()):
                    raise HTTPException(409, "O acesso ou contexto mudou. Atualize a tela.")

            transaction.set(task_ref, task)
            all_activities = list(activities)
            for other in companions:
                transaction.set(self.reference("crm_tasks", other["task"]["id"]), other["task"])
                all_activities.extend(other["activities"])
            for index, activity in enumerate(all_activities):
                event_id = "op_" + op_key if index == 0 else "op_" + op_key + "_" + str(index)
                record = dict(activity, id=event_id, operation_id=operation_id)
                if index == 0:
                    record.update(request_fingerprint=fingerprint, result_version=task["version"])
                transaction.create(self.reference("crm_activities", event_id), record)
            return {"task": task, "replayed": False, "applied_version": task["version"]}

        return apply(get_firestore_client().transaction())

    def save_settings(self, settings, expected_version):
        ref = self.reference("system_settings", "followup")

        @firestore.transactional
        def apply(transaction):
            current = _row(ref.get(transaction=transaction)) or {}
            if int(current.get("version", 0)) != expected_version:
                raise HTTPException(409, "Os horários mudaram. Atualize a configuração.")
            transaction.set(ref, settings)
            return settings

        return apply(get_firestore_client().transaction())

    def task_page(self, filters, after=None, limit=50):
        q = self.collection("crm_tasks").where("status", "==", filters["status"])
        if filters.get("contact_id") is not None:
            q = q.where("contact_id", "==", filters["contact_id"])
        if filters.get("due_from") is not None:
            q = q.where("due_at", ">=", filters["due_from"])
        if filters.get("due_until") is not None:
            q = q.where("due_at", "<", filters["due_until"])
        q = q.order_by("due_at").order_by("__name__")
        if after:
            q = q.start_after({"due_at": after[0], "__name__": self.reference("crm_tasks", after[1])})
        return [_row(s) for s in q.limit(limit).stream()]

    def activity_page(self, field, value, after=None, limit=50):
        q = (self.collection("crm_activities").where(field, "==", value)
             .order_by("recorded_at", direction="DESCENDING")
             .order_by("__name__", direction="DESCENDING"))
        if after:
            q = q.start_after({"recorded_at": after[0], "__name__": self.reference("crm_activities", after[1])})
        return [_row(s) for s in q.limit(limit).stream()]

    def response_page(self, contact_id, conversation_id, anchor, limit=12):
        q = (self.collection("wa_messages").where("contact_id", "==", contact_id)
             .where("direction", "==", "inbound").where("timestamp_wa", ">", anchor))
        if conversation_id:
            q = q.where("conversation_id", "==", conversation_id)
        q = q.order_by("timestamp_wa", direction="DESCENDING").order_by("__name__", direction="DESCENDING")
        return [_row(s) for s in q.limit(limit).stream()]
