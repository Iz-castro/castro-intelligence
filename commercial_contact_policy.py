# -*- coding: utf-8 -*-

"""Preferencia comercial do contato, independente de LGPD e da retomada.

Nao envia mensagens, altera tarefas ou limpa outros bloqueios. O autorizador
sincrono fornecido pela rota valida acesso atual e a permissao da acao.
"""

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime, timezone

from fastapi import HTTPException
from google.cloud import firestore

from firestore_common import (
    get_firestore_client,
    get_tenant_context,
    tenant_document,
    utcnow,
)


FIELD = "commercial_contact_block"
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
_TENANT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_REASONS = {"patient_request", "patient_reauthorized", "patient_wrote"}
_SOURCE = "operator_recorded"
# Recusa desfeita por mensagem nova do paciente (decisao do PO, 2026-10-18).
_PATIENT_SOURCE = "patient_message"


def _valid_record(value):
    if not isinstance(value, Mapping) or type(value.get("active")) is not bool:
        return False
    version = value.get("version")
    if type(version) is not int or version < 1:
        return False
    return True


def is_commercial_contact_blocked(contact):
    """Predicado puro; ausencia e legado, dado presente invalido nao libera.

    Nao interpreta tags, inbound, reopen_opt_out ou lgpd_revoked. Os demais
    gates precisam ser aplicados independentemente pelo chamador.
    """
    if not isinstance(contact, Mapping):
        return True
    if FIELD not in contact:
        return False
    value = contact[FIELD]
    if not _valid_record(value):
        return True
    return value["active"]


def _identity(tenant_id, contact_id, actor, authorize):
    if not isinstance(tenant_id, str) or not _TENANT.fullmatch(tenant_id):
        raise HTTPException(403, "Tenant explicito obrigatorio.")
    if type(contact_id) is not int or contact_id < 1:
        raise HTTPException(400, "Contato invalido.")
    if not isinstance(actor, Mapping) or actor.get("tenant_id") != tenant_id:
        raise HTTPException(403, "Tenant do usuario divergente.")
    current = get_tenant_context()
    if current != tenant_id:
        raise HTTPException(403, "Contexto de tenant divergente.")
    uid = actor.get("firebase_uid")
    if (type(actor.get("id")) is not int or actor["id"] < 1
            or not isinstance(uid, str) or not uid.strip() or len(uid) > 128
            or not actor.get("is_active", True) or not callable(authorize)):
        raise HTTPException(403, "Usuario ou autorizador invalido.")


def _contact(snapshot, contact_id, tenant_id):
    if not snapshot.exists:
        raise HTTPException(404, "Contato nao encontrado.")
    contact = snapshot.to_dict() or {}
    if contact.get("tenant_id") not in (None, "", tenant_id):
        raise HTTPException(403, "Contato de outro tenant.")
    contact["id"] = contact_id
    return contact


def _authorize(authorize, contact, actor, action):
    # None suporta os predicados existentes que negam por excecao.
    result = authorize(contact, actor, action)
    if result is not None and result is not True:
        raise HTTPException(403, "Acao nao autorizada.")


def _view(contact, strict=False):
    if FIELD not in contact:
        return {"active": False, "version": 0}
    raw = contact[FIELD]
    if not _valid_record(raw):
        if strict:
            raise HTTPException(409, "Preferencia comercial invalida; revisao necessaria.")
        return {"active": True, "version": 0, "invalid": True}
    # Nao devolver campos arbitrarios inseridos no documento.
    view = {"active": raw["active"], "version": raw["version"]}
    stamp = raw.get("updated_at")
    if isinstance(stamp, datetime):
        stamp = stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp
        view["updated_at"] = stamp.astimezone(timezone.utc).isoformat()
    for key in ("updated_by_user_id", "updated_by_uid"):
        if key in raw:
            view[key] = raw[key]
    if raw.get("reason") in _REASONS:
        view["reason"] = raw["reason"]
    if raw.get("source") in (_SOURCE, _PATIENT_SOURCE):
        view["source"] = raw["source"]
    return view


def released_by_patient_message(contact, message_at):
    """Novo estado da recusa quando o PACIENTE escreve depois dela, ou None.

    Decisao do PO (2026-10-18): a recusa comercial geral se desfaz com
    mensagem nova do paciente, como o Encerrar da reabertura (D4). Vale so
    para recusa ativa e valida (registro invalido segue bloqueando ate
    revisao humana) e para mensagem POSTERIOR ao registro: historico
    importado e reentrega de mensagem antiga nao desfazem. Quem chama
    (save_wa_message) ja filtra inbound recebido, sem clique de controle e
    sem reacao.
    """
    if not isinstance(contact, Mapping) or FIELD not in contact:
        return None
    raw = contact[FIELD]
    if not _valid_record(raw) or raw["active"] is not True:
        return None
    stamp = raw.get("updated_at")
    if isinstance(stamp, str):
        try:
            stamp = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(stamp, datetime) or not isinstance(message_at, datetime):
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    if message_at.tzinfo is None:
        message_at = message_at.replace(tzinfo=timezone.utc)
    if message_at <= stamp:
        return None
    # Os campos de autoria anteriores sao zerados: o merge do write manteria
    # o operador que registrou a recusa como autor da liberacao.
    return {"active": False, "version": raw["version"] + 1, "updated_at": utcnow(),
            "updated_by_user_id": None, "updated_by_uid": None,
            "reason": "patient_wrote", "source": _PATIENT_SOURCE}


def get_commercial_contact_preference(tenant_id, contact_id, actor, authorize):
    """Le somente a preferencia apos validar tenant e acesso ao contato."""
    _identity(tenant_id, contact_id, actor, authorize)
    snapshot = tenant_document(tenant_id, "wa_contacts", contact_id).get()
    contact = _contact(snapshot, contact_id, tenant_id)
    _authorize(authorize, contact, actor, "read")
    return {"contact_id": contact_id, FIELD: _view(contact)}


@firestore.transactional
def _set_preference_transaction(transaction, contact_ref, audit_ref, *, tenant_id,
                                contact_id, actor, active, expected_version,
                                fingerprint, operation_key, authorize):
    contact = _contact(contact_ref.get(transaction=transaction), contact_id, tenant_id)
    _authorize(authorize, contact, actor, "block" if active else "unblock")
    receipt = audit_ref.get(transaction=transaction)
    current = _view(contact, strict=True)
    if receipt.exists:
        previous = receipt.to_dict() or {}
        if previous.get("commercial_operation_fingerprint") != fingerprint:
            raise HTTPException(409, "Operacao ja utilizada com outro conteudo.")
        # Replay antigo nunca desfaz alteracao posterior nem regride a UI.
        return {"contact_id": contact_id, FIELD: current, "replayed": True,
                "operation_version": previous["commercial_policy_version"]}
    if current["version"] != expected_version:
        raise HTTPException(409, "Preferencia alterada por outra pessoa; atualize os dados.")

    stamp = utcnow()
    version = current["version"] + 1
    preference = {
        "active": active, "version": version, "updated_at": stamp,
        "updated_by_user_id": actor["id"], "updated_by_uid": actor["firebase_uid"],
        "reason": "patient_request" if active else "patient_reauthorized",
        "source": _SOURCE,
    }
    # Mesmo audit_log existente; recibo e preferencia confirmam juntos.
    # Nao usar log_audit best-effort apos commit: deixaria lacuna/replay duplo.
    transaction.set(contact_ref, {FIELD: preference}, merge=True)
    transaction.create(audit_ref, {
        "id": audit_ref.id, "user_id": actor["id"],
        "action": "COMMERCIAL_CONTACT_BLOCK" if active else "COMMERCIAL_CONTACT_UNBLOCK",
        "detail": "contact_id=%s active=%s version=%s" % (contact_id, int(active), version),
        "ip_address": "", "created_at": stamp,
        "commercial_operation_key": operation_key,
        "commercial_operation_fingerprint": fingerprint,
        "commercial_policy_version": version,
    })
    return {"contact_id": contact_id, FIELD: _view({FIELD: preference}),
            "replayed": False, "operation_version": version}


def set_commercial_contact_preference(tenant_id, contact_id, actor, *, active,
                                     expected_version, operation_id,
                                     patient_request_confirmed, authorize):
    """Registra pedido expresso ou reautorizacao expressa, sem efeitos laterais.

    authorize(contact, actor, action) precisa checar o acesso atual e a
    permissao de read/block/unblock. False nega; None/True autorizam.
    O mesmo operation_id so pode repetir o mesmo comando/autora/versao.
    """
    _identity(tenant_id, contact_id, actor, authorize)
    if type(active) is not bool or type(expected_version) is not int or expected_version < 0:
        raise HTTPException(400, "Estado ou versao invalida.")
    if not isinstance(operation_id, str) or not _TOKEN.fullmatch(operation_id):
        raise HTTPException(400, "operation_id invalido.")
    if patient_request_confirmed is not True:
        raise HTTPException(400, "Confirme a manifestacao explicita do paciente.")
    operation_key = hashlib.sha256((str(contact_id) + ":" + operation_id).encode()).hexdigest()
    command = [tenant_id, contact_id, actor["id"], actor["firebase_uid"],
               active, expected_version, patient_request_confirmed]
    fingerprint = hashlib.sha256(json.dumps(command, separators=(",", ":")).encode()).hexdigest()
    return _set_preference_transaction(
        get_firestore_client().transaction(),
        tenant_document(tenant_id, "wa_contacts", contact_id),
        tenant_document(tenant_id, "audit_log", "commercial_contact_" + operation_key),
        tenant_id=tenant_id, contact_id=contact_id, actor=actor, active=active,
        expected_version=expected_version, fingerprint=fingerprint,
        operation_key=operation_key, authorize=authorize,
    )
