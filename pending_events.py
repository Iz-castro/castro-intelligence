# -*- coding: utf-8 -*-

"""
Fila de webhooks pendentes — eventos da Meta que chegaram antes do canal
correspondente estar indexado no Firestore (race entre Embedded Signup
finalizar e o primeiro webhook chegar) ou cujo phone_number_id nao bate
com nenhum canal cadastrado.

Garantia: zero perda. Retornamos 200 imediatamente para a Meta nao
penalizar o endpoint, persistimos o payload bruto + motivo, e expomos
via UI admin pra retry/intervencao humana.

A colecao e GLOBAL (fora de tenants/) porque o tenant_id e desconhecido
ate o canal ser resolvido — esse e exatamente o motivo do evento estar
pendente.

Schema:
    {
        "id": str,                     # auto-id do Firestore (era int sequencial)
        "received_at": datetime,
        "change_field": str,           # "messages"/"smb_message_echoes"/etc
        "phone_number_id": str,        # do payload, pode estar vazio
        "reason": str,                 # "no_channel"/"no_default_channel"/...
        "status": "pending"|"resolved"|"failed",
        "attempts": int,
        "last_attempt_at": datetime|None,
        "last_error": str,
        "payload": dict,               # payload bruto da Meta
    }
"""

import logging
from datetime import datetime, timezone

from firestore_common import (
    global_collection,
    global_document,
    utcnow,
    normalize_record,
)

logger = logging.getLogger("castro_crm.pending_events")

PENDING_COLLECTION = "pending_webhook_events"

STATUS_PENDING = "pending"
STATUS_RESOLVED = "resolved"
STATUS_FAILED = "failed"


def enqueue_pending_event(payload: dict, change_field: str,
                          phone_number_id: str, reason: str) -> str:
    """Persiste um evento pendente. Retorna event_id (auto-id do Firestore, string).

    Chamada do webhook quando o canal nao puder ser resolvido pra um
    change especifico. payload e o dict completo do webhook (entry+changes),
    nao apenas o change pendente — facilita retry posterior reusando
    process_webhook_payload.

    Usa auto-id do Firestore (nao next_sequence): a colecao e flat/global, mas
    next_sequence lia o contador do tenant do contexto (webhook ja setou o
    contexto) -> com 2+ tenants o event_id colidia e o tenant B sobrescrevia o
    doc do tenant A (ADR 0007 risco 3). Auto-id elimina a colisao.
    """
    ref = global_collection(PENDING_COLLECTION).document()
    event_id = ref.id
    doc = {
        "id": event_id,
        "received_at": utcnow(),
        "change_field": str(change_field or ""),
        "phone_number_id": str(phone_number_id or ""),
        "reason": str(reason or ""),
        "status": STATUS_PENDING,
        "attempts": 0,
        "last_attempt_at": None,
        "last_error": "",
        "payload": payload,
    }
    ref.set(doc)
    logger.warning(
        "[PENDING] Evento enfileirado | id=%s field=%s phone_id=%s reason=%s",
        event_id, change_field, phone_number_id, reason,
    )
    return event_id


def list_pending_events(status: str | None = None, limit: int = 100) -> list[dict]:
    """Lista eventos pendentes (mais recentes primeiro)."""
    q = global_collection(PENDING_COLLECTION)
    if status:
        q = q.where("status", "==", status)
    rows = []
    for snap in q.stream():
        data = snap.to_dict() or {}
        if "id" not in data:
            try:
                data["id"] = int(snap.id)
            except (TypeError, ValueError):
                data["id"] = snap.id
        rows.append(data)
    rows.sort(
        key=lambda r: r.get("received_at") or datetime.fromtimestamp(0, tz=timezone.utc),
        reverse=True,
    )
    if limit:
        rows = rows[:limit]
    return [normalize_record(r) for r in rows]


def get_pending_event(event_id: str) -> dict | None:
    snap = global_document(PENDING_COLLECTION, event_id).get()
    if not snap.exists:
        return None
    data = snap.to_dict() or {}
    if "id" not in data:
        data["id"] = event_id
    return normalize_record(data)


def mark_event_attempt(event_id: str, success: bool, error: str = "") -> None:
    """Atualiza contador de tentativas e status final."""
    snap = global_document(PENDING_COLLECTION, event_id).get()
    if not snap.exists:
        return
    current = snap.to_dict() or {}
    attempts = int(current.get("attempts", 0)) + 1
    updates = {
        "attempts": attempts,
        "last_attempt_at": utcnow(),
        "last_error": "" if success else (error or "")[:500],
        "status": STATUS_RESOLVED if success else STATUS_PENDING,
    }
    global_document(PENDING_COLLECTION, event_id).set(updates, merge=True)


def mark_event_failed(event_id: str, error: str) -> None:
    """Marca um evento como definitivamente falho (nao retentar)."""
    global_document(PENDING_COLLECTION, event_id).set(
        {
            "status": STATUS_FAILED,
            "last_attempt_at": utcnow(),
            "last_error": (error or "")[:500],
        },
        merge=True,
    )


def delete_pending_event(event_id: str) -> bool:
    snap = global_document(PENDING_COLLECTION, event_id).get()
    if not snap.exists:
        return False
    global_document(PENDING_COLLECTION, event_id).delete()
    return True


def count_pending() -> int:
    """Conta eventos com status='pending'. Usado em badges/health."""
    count = 0
    for _ in global_collection(PENDING_COLLECTION).where("status", "==", STATUS_PENDING).stream():
        count += 1
    return count
