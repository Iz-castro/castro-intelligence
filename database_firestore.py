# -*- coding: utf-8 -*-

import logging
from contextlib import contextmanager
from datetime import datetime, timezone

from google.cloud import firestore

from firestore_common import (
    collection,
    document,
    get_firestore_client,
    next_sequence,
    normalize_record,
    utcnow,
)

logger = logging.getLogger("castro_crm.database")


def _coerce_timestamp(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    return value


def _raw_doc(snapshot):
    if not snapshot.exists:
        return None
    data = snapshot.to_dict() or {}
    if "id" not in data:
        try:
            data["id"] = int(snapshot.id)
        except ValueError:
            data["id"] = snapshot.id
    return data


def _all_docs(name):
    return [_raw_doc(snapshot) for snapshot in collection(name).stream()]


def _get_doc(name, doc_id):
    return _raw_doc(document(name, doc_id).get())


def _get_first_by_field(name, field_name, value):
    query = collection(name).where(field_name, "==", value).limit(1)
    for snapshot in query.stream():
        return _raw_doc(snapshot)
    return None


def _sort_records(records, field_name, reverse=False):
    return sorted(
        records,
        key=lambda item: item.get(field_name) or datetime.fromtimestamp(0, tz=timezone.utc),
        reverse=reverse,
    )


_user_cache = {}
_department_cache = {}


def _user_map(user_ids):
    unique_ids = {uid for uid in user_ids if uid}
    missing = unique_ids - _user_cache.keys()
    for user_id in missing:
        user = _get_doc("users", user_id)
        if user:
            _user_cache[user_id] = user
    return {uid: _user_cache[uid] for uid in unique_ids if uid in _user_cache}


def _department_map(department_ids):
    unique_ids = {did for did in department_ids if did}
    missing = unique_ids - _department_cache.keys()
    for department_id in missing:
        department = _get_doc("departments", department_id)
        if department:
            _department_cache[department_id] = department
    return {did: _department_cache[did] for did in unique_ids if did in _department_cache}


def invalidate_caches():
    _user_cache.clear()
    _department_cache.clear()


def _prefer_wa_msg_type(existing_type, new_type):
    existing = (existing_type or "").strip().lower()
    incoming = (new_type or "").strip().lower()
    weak = {"", "unknown", "unsupported"}
    if incoming == "gif" and existing == "video":
        return incoming
    if incoming not in weak and existing in weak:
        return incoming
    if incoming in weak:
        return existing or incoming
    return existing or incoming


def _prefer_wa_content(existing_content, new_content):
    existing = (existing_content or "").strip()
    incoming = (new_content or "").strip()
    placeholders = {"[unknown]", "[unsupported]"}
    if not incoming:
        return existing
    if existing.lower() in placeholders and incoming.lower() not in placeholders:
        return incoming
    if incoming.lower() in placeholders and existing:
        return existing
    return incoming or existing


def _operator_profile_ref(firebase_uid):
    return document("operator_profiles", firebase_uid)


def _operator_profile_doc(firebase_uid):
    if not firebase_uid:
        return None
    return _raw_doc(_operator_profile_ref(firebase_uid).get())


def _sync_operator_profile_from_user(user):
    firebase_uid = (user or {}).get("firebase_uid")
    if not firebase_uid:
        return
    _operator_profile_ref(firebase_uid).set({
        "uid": firebase_uid,
        "user_id": user["id"],
        "email": user.get("email", ""),
        "display_name": user.get("display_name", ""),
        "role": user.get("role", "operador"),
        "department_id": user.get("department_id"),
        "is_active": user.get("is_active", 1),
        "updated_at": utcnow(),
    }, merge=True)


def _normalize_many(records):
    return [normalize_record(record) for record in records]


def _internal_unread_doc_id(receiver_id, sender_id):
    return f"{receiver_id}_{sender_id}"


def get_connection():
    return get_firestore_client()


@contextmanager
def db_session():
    yield None


def init_database():
    document("_meta", "counters").set({}, merge=True)
    logger.info("Firestore inicializado")


VALID_BOT_KEYS = {"comercial", "financeiro", "administrativo", "sac"}
_SENTINEL = object()


def _normalize_bot_key(value):
    if value is None:
        return None
    v = str(value).strip().lower()
    if not v:
        return None
    if v not in VALID_BOT_KEYS:
        return None
    return v


def create_department(name, description="", bot_key=None):
    existing = _get_first_by_field("departments", "name", name)
    if existing:
        return existing["id"]

    department_id = next_sequence("departments")
    document("departments", department_id).set({
        "id": department_id,
        "name": name,
        "description": description or "",
        "bot_key": _normalize_bot_key(bot_key),
        "is_active": 1,
        "created_at": utcnow(),
    })
    return department_id


def get_all_departments(include_inactive=False):
    if include_inactive:
        rows = [row for row in _all_docs("departments") if row]
    else:
        rows = [row for row in _all_docs("departments") if row and row.get("is_active", 1)]
    rows.sort(key=lambda row: (row.get("sort_order", 0), row.get("name", "").lower()))
    return _normalize_many(rows)


def get_department_by_id(department_id):
    return normalize_record(_get_doc("departments", department_id))


def update_department(department_id, name=None, description=None, is_active=None, sort_order=None, bot_key=_SENTINEL):
    fields = {}
    if name is not None:
        # Verifica duplicata de nome (excluindo o proprio)
        existing = _get_first_by_field("departments", "name", name)
        if existing and existing["id"] != department_id:
            return False, "Ja existe um departamento com este nome"
        fields["name"] = name
    if description is not None:
        fields["description"] = description
    if is_active is not None:
        fields["is_active"] = 1 if is_active else 0
    if sort_order is not None:
        fields["sort_order"] = sort_order
    if bot_key is not _SENTINEL:
        fields["bot_key"] = _normalize_bot_key(bot_key)
    if not fields:
        return False, "Nenhum campo para atualizar"
    fields["updated_at"] = utcnow()
    document("departments", department_id).set(fields, merge=True)
    _department_cache.pop(department_id, None)
    return True, None


def deactivate_department(department_id):
    document("departments", department_id).set({
        "is_active": 0,
        "updated_at": utcnow(),
    }, merge=True)
    _department_cache.pop(department_id, None)
    return True


def get_user_by_username(username):
    row = _get_first_by_field("users", "username", username)
    if not row or not row.get("is_active", 1):
        return None
    return normalize_record(row)


def get_user_by_email(email):
    if not email:
        return None
    row = _get_first_by_field("users", "email", email.strip().lower())
    if not row or not row.get("is_active", 1):
        return None
    return normalize_record(row)


def get_user_by_firebase_uid(firebase_uid):
    if not firebase_uid:
        return None
    row = _get_first_by_field("users", "firebase_uid", firebase_uid)
    if not row or not row.get("is_active", 1):
        return None
    return normalize_record(row)


def get_operator_profile_by_uid(firebase_uid):
    row = _operator_profile_doc(firebase_uid)
    if not row or not row.get("is_active", 1):
        return None
    return normalize_record(row)


def get_user_by_id(user_id):
    row = _get_doc("users", user_id)
    if not row or not row.get("is_active", 1):
        return None
    department_id = row.get("department_id")
    department_name = ""
    if department_id:
        department = _get_doc("departments", department_id)
        if department:
            department_name = department.get("name", "")
    return normalize_record({
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "department_id": department_id,
        "department_name": department_name,
        "role": row.get("role", "operador"),
        "is_active": row.get("is_active", 1),
        "email": row.get("email", ""),
        "firebase_uid": row.get("firebase_uid", ""),
        "auth_provider": row.get("auth_provider", "firebase"),
        "created_at": row.get("created_at"),
        "last_login": row.get("last_login"),
        "avatar_path": row.get("avatar_path", ""),
    })


def get_all_users():
    rows = [row for row in _all_docs("users") if row]
    dept_map = _department_map([row.get("department_id") for row in rows])
    rows.sort(key=lambda row: row.get("display_name", "").lower())
    normalized = []
    for row in rows:
        enriched = dict(row)
        department = dept_map.get(row.get("department_id"))
        enriched["department_name"] = department.get("name", "") if department else ""
        normalized.append(enriched)
    return _normalize_many(normalized)


def create_user(username, display_name, password_hash, department_id=None, role="operador"):
    existing = _get_first_by_field("users", "username", username)
    if existing:
        return None

    user_id = next_sequence("users")
    document("users", user_id).set({
        "id": user_id,
        "username": username,
        "display_name": display_name,
        "password_hash": password_hash,
        "department_id": department_id,
        "role": role,
        "email": "",
        "firebase_uid": "",
        "auth_provider": "firebase",
        "avatar_path": "",
        "is_active": 1,
        "created_at": utcnow(),
        "last_login": None,
        "failed_attempts": 0,
        "locked_until": None,
    })
    return user_id


def update_user(user_id, display_name=None, department_id=None, role=None):
    fields = {}
    if display_name is not None:
        fields["display_name"] = display_name
    if department_id is not None:
        fields["department_id"] = department_id if department_id else None
    if role is not None:
        fields["role"] = role
    if not fields:
        return False
    document("users", user_id).set(fields, merge=True)
    updated = _get_doc("users", user_id)
    if updated:
        _sync_operator_profile_from_user(updated)
    return True


def deactivate_user(user_id):
    document("users", user_id).set({"is_active": 0}, merge=True)
    updated = _get_doc("users", user_id)
    if updated:
        _sync_operator_profile_from_user(updated)


def update_last_login(user_id):
    document("users", user_id).set({
        "last_login": utcnow(),
        "failed_attempts": 0,
        "locked_until": None,
    }, merge=True)


def sync_user_identity(user_id, email=None, firebase_uid=None, auth_provider="firebase", display_name=None):
    fields = {
        "auth_provider": auth_provider or "firebase",
    }
    if email is not None:
        fields["email"] = email.strip().lower()
    if firebase_uid is not None:
        fields["firebase_uid"] = firebase_uid
    if display_name:
        fields["display_name"] = display_name
    document("users", user_id).set(fields, merge=True)
    updated = _get_doc("users", user_id)
    if updated:
        _sync_operator_profile_from_user(updated)
    return normalize_record(updated) if updated else None


def upsert_firebase_user(firebase_uid, email, display_name="", role=None, department_id=None):
    email = (email or "").strip().lower()
    existing = get_user_by_firebase_uid(firebase_uid) or get_user_by_email(email)
    if existing:
        sync_user_identity(
            existing["id"],
            email=email,
            firebase_uid=firebase_uid,
            auth_provider="firebase",
            display_name=display_name or existing.get("display_name", ""),
        )
        if department_id is not None or role is not None:
            update_user(existing["id"], display_name=display_name or existing.get("display_name", ""), department_id=department_id, role=role)
        return get_user_by_id(existing["id"])

    base_username = email or firebase_uid or f"user_{next_sequence('usernames')}"
    username = base_username[:50]
    suffix = 1
    while _get_first_by_field("users", "username", username):
        suffix += 1
        username = f"{base_username[: max(1, 47 - len(str(suffix)))]}_{suffix}"[:50]

    user_id = create_user(username, display_name or username, "", department_id, role or "operador")
    if not user_id:
        return None
    sync_user_identity(user_id, email=email, firebase_uid=firebase_uid, auth_provider="firebase", display_name=display_name or username)
    return get_user_by_id(user_id)


def increment_failed_attempts(username, lockout_until=None):
    row = _get_first_by_field("users", "username", username)
    if not row:
        return
    updates = {"failed_attempts": int(row.get("failed_attempts", 0)) + 1}
    if lockout_until is not None:
        updates["locked_until"] = _coerce_timestamp(lockout_until)
    document("users", row["id"]).set(updates, merge=True)


def update_user_avatar(user_id, avatar_path):
    document("users", user_id).set({"avatar_path": avatar_path}, merge=True)


def get_user_avatar(user_id):
    row = _get_doc("users", user_id)
    if row and row.get("is_active", 1):
        return row.get("avatar_path", "") or ""
    return ""


def _conversation_key(user_a, user_b):
    a = int(user_a)
    b = int(user_b)
    return f"{min(a, b)}:{max(a, b)}"


def save_internal_message(sender_id, receiver_id, content, msg_type="text"):
    message_id = next_sequence("messages")
    created_at = utcnow()
    document("messages", message_id).set({
        "id": message_id,
        "sender_id": sender_id,
        "receiver_id": receiver_id,
        "conversation_key": _conversation_key(sender_id, receiver_id),
        "content": content,
        "msg_type": msg_type,
        "is_read": 0,
        "created_at": created_at,
    })
    unread_ref = document("internal_unread", _internal_unread_doc_id(receiver_id, sender_id))
    existing = _raw_doc(unread_ref.get()) or {}
    unread_ref.set({
        "receiver_id": receiver_id,
        "sender_id": sender_id,
        "count": int(existing.get("count", 0)) + 1,
        "last_message_at": created_at,
    })
    return message_id


def get_internal_conversation(user_a, user_b, limit=100, offset=0):
    rows = []
    for snapshot in collection("messages").where("conversation_key", "==", _conversation_key(user_a, user_b)).stream():
        row = _raw_doc(snapshot)
        if row:
            rows.append(row)
    rows = _sort_records(rows, "created_at")
    if offset:
        rows = rows[offset:]
    if limit:
        rows = rows[:limit]
    users = _user_map([row.get("sender_id") for row in rows])
    enriched = []
    for row in rows:
        item = dict(row)
        sender = users.get(row.get("sender_id"))
        item["sender_name"] = sender.get("display_name", "") if sender else ""
        enriched.append(item)
    return _normalize_many(enriched)


def mark_messages_as_read(reader_id, sender_id):
    conversation = get_internal_conversation(reader_id, sender_id, limit=10000, offset=0)
    for message in conversation:
        if message.get("receiver_id") == reader_id and message.get("sender_id") == sender_id and not message.get("is_read"):
            document("messages", message["id"]).set({"is_read": 1}, merge=True)
    document("internal_unread", _internal_unread_doc_id(reader_id, sender_id)).set({
        "receiver_id": reader_id,
        "sender_id": sender_id,
        "count": 0,
        "last_message_at": utcnow(),
    }, merge=True)


def get_unread_count(user_id):
    rows = []
    for snapshot in collection("internal_unread").where("receiver_id", "==", user_id).stream():
        row = _raw_doc(snapshot)
        if row:
            rows.append(row)
    return {int(row["sender_id"]): int(row.get("count", 0)) for row in rows if int(row.get("count", 0)) > 0}


def _resolve_display_name(declared_name, whatsapp_profile_name, phone_formatted):
    """Resolve o nome efetivo para exibicao: declared > whatsapp > phone."""
    return declared_name or whatsapp_profile_name or phone_formatted or ""


# ---------------------------------------------------------------------------
# wa_conversations — sub-threads por canal (Fase 2)
# ---------------------------------------------------------------------------
#
# Para suportar o cenario "mesmo wa_id em mais de um canal", as mensagens
# pertencem a uma `conversation` (par canal+telefone) em vez de ao
# contato direto. O contato continua sendo unico por wa_id (preserva
# nome, notas, qualificacao do cliente), mas thread, assigned_to,
# unread_count etc. ficam na conversation.
#
# conversation_id e deterministico: "{channel_id}__{wa_id}". Garante
# que webhook nunca duplique conversation pro mesmo par.
#
# Esta camada e ADITIVA: as funcoes legadas (upsert_wa_contact,
# save_wa_message, get_wa_conversation) continuam funcionando — apenas
# passam tambem a manter a coleção wa_conversations atualizada e
# denormalizam conversation_id em wa_messages. O frontend ainda
# consome a API por contact_id; quando a Fase 3 do plano for entregue,
# o frontend passa a listar conversations e mostrar badges de canal.

def _make_conversation_id(channel_id, wa_id):
    """Gera id deterministico de conversation. Aceita channel_id None
    (legado) — usa 'default' como prefixo nesse caso."""
    if channel_id is None or channel_id == "":
        prefix = "default"
    else:
        prefix = str(channel_id)
    return f"{prefix}__{wa_id}"


def upsert_wa_conversation(
    contact_id,
    wa_id,
    channel_id=None,
    source_channel_type="",
    phone_number_id="",
    auto_assign_user_id=None,
    direction_for_unread=None,
):
    """Cria ou atualiza a conversation correspondente a (channel_id, wa_id).

    Retorna conversation_id (string deterministica). Se a conversation
    ja existe, atualiza last_message_at e demais timestamps, alem de
    auto-assign quando aplicavel.

    direction_for_unread: 'inbound' incrementa unread_count, outras
    direcoes nao mexem. None nao mexe (uso pelo upsert_wa_contact).
    """
    if wa_id is None or wa_id == "":
        raise ValueError("wa_id obrigatorio para upsert_wa_conversation")
    conversation_id = _make_conversation_id(channel_id, wa_id)
    now = utcnow()
    ref = document("wa_conversations", conversation_id)
    snap = ref.get()
    existing = snap.to_dict() if snap.exists else None

    if existing:
        updates = {
            "last_message_at": now,
        }
        if direction_for_unread == "inbound":
            updates["last_inbound_at"] = now
            updates["unread_count"] = int(existing.get("unread_count", 0)) + 1
        elif direction_for_unread == "outbound":
            updates["last_outbound_at"] = now
        # Auto-assign se nao atribuido (coexistence)
        if auto_assign_user_id and not existing.get("assigned_to"):
            user = _get_doc("users", auto_assign_user_id)
            if user:
                updates["assigned_to"] = auto_assign_user_id
                updates["assigned_to_uid"] = user.get("firebase_uid", "")
                if not existing.get("department_id") and user.get("department_id"):
                    updates["department_id"] = user["department_id"]
        ref.set(updates, merge=True)
        return conversation_id

    # Nova conversation
    new_conv = {
        "id": conversation_id,
        "contact_id": contact_id,
        "wa_id": wa_id,
        "channel_id": channel_id,
        "phone_number_id": phone_number_id or "",
        "source_channel_type": source_channel_type or "",
        "assigned_to": None,
        "assigned_to_uid": "",
        "department_id": None,
        "unread_count": 1 if direction_for_unread == "inbound" else 0,
        "status": "open",
        "created_at": now,
        "last_message_at": now,
        "last_inbound_at": now if direction_for_unread == "inbound" else None,
        "last_outbound_at": now if direction_for_unread == "outbound" else None,
    }
    if auto_assign_user_id:
        user = _get_doc("users", auto_assign_user_id)
        if user:
            new_conv["assigned_to"] = auto_assign_user_id
            new_conv["assigned_to_uid"] = user.get("firebase_uid", "")
            if user.get("department_id"):
                new_conv["department_id"] = user["department_id"]
    ref.set(new_conv)
    return conversation_id


def get_wa_conversation_by_id(conversation_id):
    """Retorna a conversation pelo id deterministico."""
    snap = document("wa_conversations", conversation_id).get()
    if not snap.exists:
        return None
    data = snap.to_dict() or {}
    if "id" not in data:
        data["id"] = conversation_id
    return normalize_record(data)


def get_conversations_by_contact(contact_id):
    """Retorna todas as conversations de um contato (todos os canais)."""
    rows = []
    for snap in collection("wa_conversations").where("contact_id", "==", contact_id).stream():
        data = snap.to_dict() or {}
        if "id" not in data:
            data["id"] = snap.id
        rows.append(data)
    rows.sort(key=lambda r: r.get("last_message_at") or datetime.fromtimestamp(0, tz=timezone.utc), reverse=True)
    return _normalize_many(rows)


def assign_wa_conversation(conversation_id, to_user_id, to_department_id, transferred_by, reason="", summary=""):
    """Transfere uma conversation (thread). Atualiza apenas a conversation
    e contact (assigned_to compartilhado por enquanto). Loga transferencia
    com referencia a conversation_id E contact_id.

    Retorna {from_user_id, to_user_id, contact_id} ou None se nao achar.
    """
    conv = get_wa_conversation_by_id(conversation_id)
    if not conv:
        return None
    contact_id = conv.get("contact_id")
    from_user = conv.get("assigned_to")
    from_dept = conv.get("department_id")
    to_user = _get_doc("users", to_user_id) if to_user_id else None

    document("wa_conversations", conversation_id).set({
        "assigned_to": to_user_id,
        "assigned_to_uid": (to_user or {}).get("firebase_uid", ""),
        "department_id": to_department_id,
    }, merge=True)
    # Espelho no contato pra views legadas que ainda leem dali
    if contact_id is not None:
        document("wa_contacts", contact_id).set({
            "assigned_to": to_user_id,
            "assigned_to_uid": (to_user or {}).get("firebase_uid", ""),
            "department_id": to_department_id,
        }, merge=True)

    transfer_id = next_sequence("wa_transfer_log")
    document("wa_transfer_log", transfer_id).set({
        "id": transfer_id,
        "conversation_id": conversation_id,
        "contact_id": contact_id,
        "contact_doc_id": str(contact_id) if contact_id is not None else "",
        "from_user_id": from_user,
        "to_user_id": to_user_id,
        "to_user_uid": (to_user or {}).get("firebase_uid", ""),
        "from_department_id": from_dept,
        "to_department_id": to_department_id,
        "department_id": to_department_id,
        "reason": reason or "",
        "summary": summary or "",
        "transferred_by": transferred_by,
        "created_at": utcnow(),
    })
    return {"from_user_id": from_user, "to_user_id": to_user_id, "contact_id": contact_id}


def mark_wa_conversation_read_by_id(conversation_id):
    """Marca como lidas as mensagens inbound de uma conversation especifica.
    Usa filtro por conversation_id (Fase 2C) — nao colide entre threads do
    mesmo contato em canais diferentes."""
    q = (
        collection("wa_messages")
        .where("conversation_id", "==", conversation_id)
        .where("direction", "==", "inbound")
        .where("status", "==", "received")
    )
    batch = get_firestore_client().batch()
    count = 0
    total_updated = 0
    for snapshot in q.stream():
        batch.set(snapshot.reference, {"status": "read"}, merge=True)
        count += 1
        total_updated += 1
        if count >= 400:
            batch.commit()
            batch = get_firestore_client().batch()
            count = 0
    if count > 0:
        batch.commit()
    document("wa_conversations", conversation_id).set({"unread_count": 0}, merge=True)
    return total_updated


def upsert_wa_contact(wa_id, display_name="", channel_id=None,
                      phone_number_id="", source_channel_type="",
                      auto_assign_user_id=None):
    """Cria ou atualiza um contato WhatsApp.

    Para canais coexistence, auto_assign_user_id atribui automaticamente
    ao operador dono do numero.
    """
    now = utcnow()
    existing = _get_first_by_field("wa_contacts", "wa_id", wa_id)
    if existing:
        updates = {
            "last_message_at": now,
            "last_inbound_at": now,
        }
        # Atualizar whatsapp_profile_name do webhook sem sobrescrever declared_name
        if display_name:
            updates["whatsapp_profile_name"] = display_name
            # Recalcular display_name efetivo
            declared = existing.get("declared_name", "")
            updates["display_name"] = _resolve_display_name(
                declared, display_name, existing.get("phone_formatted", ""),
            )
        # Atualizar canal se ainda nao definido ou se mudou
        if channel_id is not None and not existing.get("channel_id"):
            updates["channel_id"] = channel_id
            updates["phone_number_id"] = phone_number_id
            updates["source_channel_type"] = source_channel_type
        # Auto-atribuir para coexistence se nao atribuido
        if auto_assign_user_id and not existing.get("assigned_to"):
            user = _get_doc("users", auto_assign_user_id)
            if user:
                updates["assigned_to"] = auto_assign_user_id
                updates["assigned_to_uid"] = user.get("firebase_uid", "")
                if not existing.get("department_id") and user.get("department_id"):
                    updates["department_id"] = user["department_id"]
                if existing.get("qualification") == "novo":
                    updates["qualification"] = "em_atendimento"
        document("wa_contacts", existing["id"]).set(updates, merge=True)
        # Garante que a conversation deste (channel, wa_id) tambem existe.
        _maybe_upsert_conversation_for_existing_contact(
            existing, channel_id, source_channel_type, phone_number_id, auto_assign_user_id,
        )
        return existing["id"]

    phone_formatted = format_phone_br(wa_id)
    contact_id = next_sequence("wa_contacts")
    new_contact = {
        "id": contact_id,
        "wa_id": wa_id,
        "display_name": _resolve_display_name("", display_name, phone_formatted),
        "declared_name": "",
        "whatsapp_profile_name": display_name or "",
        "created_source": "webhook",
        "created_by_user_id": None,
        "phone_formatted": phone_formatted,
        "profile_picture_url": "",
        "contact_avatar_path": "",
        "qualification": "novo",
        "notes": "",
        "assigned_to": None,
        "assigned_to_uid": "",
        "department_id": None,
        "channel_id": channel_id,
        "phone_number_id": phone_number_id,
        "source_channel_type": source_channel_type,
        "original_operator_id": None,
        "converted_by_user_id": None,
        "rating": None,
        "rating_requested_at": None,
        "is_archived": 0,
        "unread_count": 0,
        "first_seen_at": now,
        "last_message_at": now,
        "last_inbound_at": now,
    }
    # Auto-atribuir para coexistence
    if auto_assign_user_id:
        user = _get_doc("users", auto_assign_user_id)
        if user:
            new_contact["assigned_to"] = auto_assign_user_id
            new_contact["assigned_to_uid"] = user.get("firebase_uid", "")
            new_contact["qualification"] = "em_atendimento"
            if user.get("department_id"):
                new_contact["department_id"] = user["department_id"]
    document("wa_contacts", contact_id).set(new_contact)
    # Upsert conversation correspondente (Fase 2 — sub-threads por canal)
    upsert_wa_conversation(
        contact_id=contact_id,
        wa_id=wa_id,
        channel_id=channel_id,
        source_channel_type=source_channel_type,
        phone_number_id=phone_number_id,
        auto_assign_user_id=auto_assign_user_id,
    )
    return contact_id


def _maybe_upsert_conversation_for_existing_contact(existing_contact, channel_id, source_channel_type, phone_number_id, auto_assign_user_id):
    """Helper: ao atualizar contato existente, garante que a conversation
    correspondente (channel + wa_id) tambem exista/seja atualizada."""
    upsert_wa_conversation(
        contact_id=existing_contact["id"],
        wa_id=existing_contact["wa_id"],
        channel_id=channel_id,
        source_channel_type=source_channel_type or existing_contact.get("source_channel_type", ""),
        phone_number_id=phone_number_id or existing_contact.get("phone_number_id", ""),
        auto_assign_user_id=auto_assign_user_id,
    )


def create_manual_wa_contact(declared_name, wa_id, channel_id, user_id, allow_admin_override=False):
    """Cria contato manualmente pelo operador.

    Retorna (contact_id, error_message).

    Regras quando o wa_id ja existe:
      - Se o contato esta atribuido a OUTRO operador (assigned_to != user_id)
        e nao foi arquivado, retorna erro pedindo transferencia.
        allow_admin_override=True permite ignorar essa trava (admin/supervisor).
      - Se o contato pertence ao proprio user_id, ou esta sem dono
        (assigned_to vazio), ou esta arquivado, reabre/assume e retorna
        o id existente.
    """
    existing = _find_contact_by_wa_id_any_variant(wa_id)
    if existing:
        user = _get_doc("users", user_id)
        if not user:
            return None, "Operador nao encontrado"

        existing_assigned = existing.get("assigned_to")
        is_archived = bool(existing.get("is_archived"))
        has_other_owner = bool(existing_assigned) and existing_assigned != user_id and not is_archived

        if has_other_owner and not allow_admin_override:
            owner = _get_doc("users", existing_assigned)
            owner_name = (owner or {}).get("display_name") if owner else ""
            owner_label = owner_name or f"operador #{existing_assigned}"
            return None, (
                f"Este numero ja esta em atendimento por {owner_label}. "
                "Solicite uma transferencia ao inves de criar um novo contato."
            )

        # Admin/supervisor usando override: apenas abre o contato existente
        # sem mexer em assigned_to/department/qualification do dono original.
        # Apenas completa declared_name se estiver vazio (melhoria cosmetica).
        if has_other_owner and allow_admin_override:
            updates: dict = {}
            if declared_name and not existing.get("declared_name"):
                updates["declared_name"] = declared_name
                updates["display_name"] = _resolve_display_name(
                    declared_name,
                    existing.get("whatsapp_profile_name", ""),
                    existing.get("phone_formatted", ""),
                )
            if updates:
                document("wa_contacts", existing["id"]).set(updates, merge=True)
            return existing["id"], None

        # Contato do proprio user, sem dono ou arquivado: reabre/assume.
        updates = {
            "assigned_to": user_id,
            "assigned_to_uid": user.get("firebase_uid", ""),
            "qualification": "em_atendimento",
            "is_archived": 0,
        }
        if declared_name and not existing.get("declared_name"):
            updates["declared_name"] = declared_name
            updates["display_name"] = _resolve_display_name(
                declared_name,
                existing.get("whatsapp_profile_name", ""),
                existing.get("phone_formatted", ""),
            )
        if not existing.get("department_id") and user.get("department_id"):
            updates["department_id"] = user["department_id"]
        document("wa_contacts", existing["id"]).set(updates, merge=True)
        return existing["id"], None

    now = utcnow()
    user = _get_doc("users", user_id)
    if not user:
        return None, "Operador nao encontrado"

    phone_formatted = format_phone_br(wa_id)
    contact_id = next_sequence("wa_contacts")
    new_contact = {
        "id": contact_id,
        "wa_id": wa_id,
        "display_name": _resolve_display_name(declared_name, "", phone_formatted),
        "declared_name": declared_name or "",
        "whatsapp_profile_name": "",
        "created_source": "manual",
        "created_by_user_id": user_id,
        "phone_formatted": phone_formatted,
        "profile_picture_url": "",
        "contact_avatar_path": "",
        "qualification": "em_atendimento",
        "notes": "",
        "assigned_to": user_id,
        "assigned_to_uid": user.get("firebase_uid", ""),
        "department_id": user.get("department_id"),
        "channel_id": channel_id,
        "phone_number_id": "",
        "source_channel_type": "standard",
        "original_operator_id": None,
        "converted_by_user_id": None,
        "rating": None,
        "rating_requested_at": None,
        "is_archived": 0,
        "unread_count": 0,
        "first_seen_at": now,
        "last_message_at": None,
        "last_inbound_at": None,
    }
    document("wa_contacts", contact_id).set(new_contact)
    # Fase 3: cria conversation associada para o contato manual aparecer
    # imediatamente na sidebar (que agora itera por threads, nao contatos).
    try:
        upsert_wa_conversation(
            contact_id=contact_id,
            wa_id=wa_id,
            channel_id=channel_id,
            source_channel_type=new_contact.get("source_channel_type", "standard"),
            phone_number_id="",
            auto_assign_user_id=user_id,
            direction_for_unread=None,
        )
    except Exception as exc:
        logger.warning("Falha ao criar conversation para contato manual %s: %s", contact_id, exc)
    return contact_id, None


def update_wa_contact_declared_name(contact_id, declared_name):
    """Atualiza o nome declarado pelo operador."""
    existing = _get_doc("wa_contacts", contact_id)
    if not existing:
        return False
    phone_formatted = existing.get("phone_formatted", "")
    whatsapp_name = existing.get("whatsapp_profile_name", "")
    document("wa_contacts", contact_id).set({
        "declared_name": declared_name,
        "display_name": _resolve_display_name(declared_name, whatsapp_name, phone_formatted),
    }, merge=True)
    return True


def _enrich_contact(row):
    if not row:
        return None
    users = _user_map([row.get("assigned_to")])
    departments = _department_map([row.get("department_id")])
    enriched = dict(row)
    user = users.get(row.get("assigned_to"))
    department = departments.get(row.get("department_id"))
    enriched["assigned_name"] = user.get("display_name", "") if user else ""
    enriched["assigned_role"] = user.get("role", "") if user else ""
    enriched["assigned_to_uid"] = row.get("assigned_to_uid", "") or (user.get("firebase_uid", "") if user else "")
    enriched["department_name"] = department.get("name", "") if department else ""
    return normalize_record(enriched)


def get_wa_contact(contact_id):
    return _enrich_contact(_get_doc("wa_contacts", contact_id))


def get_all_wa_contacts(include_archived=False):
    rows = [row for row in _all_docs("wa_contacts") if row]
    if not include_archived:
        rows = [row for row in rows if not row.get("is_archived")]
    rows = _sort_records(rows, "last_message_at", reverse=True)

    # Batch: coletar todos IDs unicos antes de enriquecer (evita N+1)
    all_user_ids = [row.get("assigned_to") for row in rows]
    all_dept_ids = [row.get("department_id") for row in rows]
    users = _user_map(all_user_ids)
    departments = _department_map(all_dept_ids)

    enriched = []
    for row in rows:
        item = dict(row)
        user = users.get(row.get("assigned_to"))
        department = departments.get(row.get("department_id"))
        item["assigned_name"] = user.get("display_name", "") if user else ""
        item["assigned_role"] = user.get("role", "") if user else ""
        item["assigned_to_uid"] = row.get("assigned_to_uid", "") or (user.get("firebase_uid", "") if user else "")
        item["department_name"] = department.get("name", "") if department else ""
        enriched.append(normalize_record(item))
    return enriched


def update_wa_contact_qualification(contact_id, qualification, notes=""):
    fields = {"qualification": qualification}
    if notes is not None:
        fields["notes"] = notes
    document("wa_contacts", contact_id).set(fields, merge=True)


def set_attendance_protocol(contact_id, protocol, started_at):
    document("wa_contacts", contact_id).set({
        "attendance_protocol": protocol,
        "attendance_started_at": started_at,
    }, merge=True)


def archive_wa_contact(contact_id):
    document("wa_contacts", contact_id).set({"is_archived": 1}, merge=True)


def restore_wa_contact(contact_id):
    document("wa_contacts", contact_id).set({"is_archived": 0}, merge=True)


def update_contact_avatar(contact_id, avatar_path):
    document("wa_contacts", contact_id).set({"contact_avatar_path": avatar_path}, merge=True)


def assign_wa_contact(contact_id, to_user_id, to_department_id, transferred_by, reason="", summary=""):
    current = _get_doc("wa_contacts", contact_id)
    if not current:
        return None

    from_user = current.get("assigned_to")
    from_dept = current.get("department_id")
    to_user = _get_doc("users", to_user_id) if to_user_id else None
    document("wa_contacts", contact_id).set({
        "assigned_to": to_user_id,
        "assigned_to_uid": (to_user or {}).get("firebase_uid", ""),
        "department_id": to_department_id,
    }, merge=True)

    transfer_id = next_sequence("wa_transfer_log")
    document("wa_transfer_log", transfer_id).set({
        "id": transfer_id,
        "contact_id": contact_id,
        "contact_doc_id": str(contact_id),
        "from_user_id": from_user,
        "to_user_id": to_user_id,
        "to_user_uid": (to_user or {}).get("firebase_uid", ""),
        "from_department_id": from_dept,
        "to_department_id": to_department_id,
        "department_id": to_department_id,
        "reason": reason or "",
        "summary": summary or "",
        "transferred_by": transferred_by,
        "created_at": utcnow(),
    })
    return {"from_user_id": from_user, "to_user_id": to_user_id}


def return_contact_to_bot(contact_id, returned_by_user_id):
    """Devolve o contato para a fila do bot (remove atribuicao)."""
    current = _get_doc("wa_contacts", contact_id)
    if not current:
        return None
    from_user = current.get("assigned_to")
    from_dept = current.get("department_id")
    document("wa_contacts", contact_id).set({
        "assigned_to": None,
        "assigned_to_uid": "",
        "qualification": "novo",
        "bot_completed": False,
        "attendance_protocol": "",
        "attendance_started_at": "",
    }, merge=True)
    # Log na transfer_log
    transfer_id = next_sequence("wa_transfer_log")
    document("wa_transfer_log", transfer_id).set({
        "id": transfer_id,
        "contact_id": contact_id,
        "contact_doc_id": str(contact_id),
        "from_user_id": from_user,
        "to_user_id": None,
        "to_user_uid": "",
        "from_department_id": from_dept,
        "to_department_id": None,
        "department_id": None,
        "reason": "Devolvido ao bot",
        "summary": "Contato devolvido para a fila do bot",
        "transferred_by": returned_by_user_id,
        "created_at": utcnow(),
    })
    return True


def get_contacts_by_assigned_user(user_id):
    """Retorna todos os contatos atribuidos a um usuario."""
    rows = []
    for snapshot in collection("wa_contacts").where("assigned_to", "==", user_id).stream():
        row = _raw_doc(snapshot)
        if row:
            rows.append(row)
    return _normalize_many(rows)


def insert_transfer_system_message(contact_id, content, operator_id=None,
                                   conversation_id=None, channel_id=None):
    return save_wa_message(
        wa_message_id=f"sys_{utcnow().isoformat()}_{contact_id}",
        contact_id=contact_id,
        direction="system",
        msg_type="system",
        content=content,
        status="delivered",
        timestamp_wa=utcnow().isoformat(),
        operator_id=operator_id,
        sender_user_id=operator_id,
        conversation_id=conversation_id,
        channel_id=channel_id,
    )


def get_transfer_history(contact_id, limit=50):
    rows = []
    for snapshot in collection("wa_transfer_log").where("contact_id", "==", contact_id).stream():
        row = _raw_doc(snapshot)
        if row:
            rows.append(row)
    rows = _sort_records(rows, "created_at", reverse=True)[:limit]
    user_ids = []
    department_ids = []
    for row in rows:
        user_ids.extend([row.get("from_user_id"), row.get("to_user_id"), row.get("transferred_by")])
        department_ids.extend([row.get("from_department_id"), row.get("to_department_id")])
    users = _user_map(user_ids)
    departments = _department_map(department_ids)
    enriched = []
    for row in rows:
        item = dict(row)
        item["from_user_name"] = users.get(row.get("from_user_id"), {}).get("display_name", "")
        item["to_user_name"] = users.get(row.get("to_user_id"), {}).get("display_name", "")
        item["transferred_by_name"] = users.get(row.get("transferred_by"), {}).get("display_name", "")
        item["from_dept_name"] = departments.get(row.get("from_department_id"), {}).get("name", "")
        item["to_dept_name"] = departments.get(row.get("to_department_id"), {}).get("name", "")
        enriched.append(item)
    return _normalize_many(enriched)


def save_wa_message(wa_message_id, contact_id, direction, msg_type, content="",
                    media_path="", media_mime="", media_id="",
                    latitude=None, longitude=None, filename="",
                    status="received", timestamp_wa="", operator_id=None,
                    reply_to_message_id=None, reply_to_preview="", reply_to_sender_name="",
                    channel_id=None, phone_number_id="",
                    is_rating_message=False, visibility="all",
                    conversation_id=None,
                    channel_owner_user_id=None, sender_user_id=None,
                    template_category=None, media_size_bytes=0):
    """Persiste mensagem WhatsApp.

    Auditoria coexistence (Fase 2C):
      - `channel_owner_user_id`: dono fisico do numero (ex.: operador X que
        conectou o WhatsApp pessoal dele via coexistence). Vem de
        `channel.owner_user_id` no momento do envio/recebimento.
      - `sender_user_id`: operador que efetivamente digitou/enviou (em
        outbound). None em inbound. Permite distinguir, em transferencias
        coexistence, quem digitou vs quem e o dono do numero.

    `conversation_id` pode ser passado explicitamente (caller ja resolveu
    a thread). Caso contrario, e derivado de (channel_id, contact.wa_id).

    Visibilidade de uso (Fase 2.10.4):
      - `template_category`: 'marketing'/'utility'/'authentication' quando
        msg_type='template'; demais values mapeados pra 'unknown'.
      - `media_size_bytes`: tamanho em bytes do payload de midia outbound.
        Usado pra agregacao mensal em audit_metrics/usage_{YYYY_MM}.
    """
    if wa_message_id:
        existing = _get_first_by_field("wa_messages", "wa_message_id", wa_message_id)
        if existing:
            document("wa_messages", existing["id"]).set({
                "msg_type": _prefer_wa_msg_type(existing.get("msg_type"), msg_type),
                "content": _prefer_wa_content(existing.get("content"), content),
                "media_path": media_path or existing.get("media_path", ""),
                "media_mime": media_mime or existing.get("media_mime", ""),
                "media_id": media_id or existing.get("media_id", ""),
                "latitude": latitude if latitude is not None else existing.get("latitude"),
                "longitude": longitude if longitude is not None else existing.get("longitude"),
                "filename": filename or existing.get("filename", ""),
                "status": status or existing.get("status", "received"),
                "operator_id": operator_id if operator_id is not None else existing.get("operator_id"),
                "timestamp_wa": _coerce_timestamp(timestamp_wa) or existing.get("timestamp_wa"),
                "reply_to_message_id": reply_to_message_id if reply_to_message_id is not None else existing.get("reply_to_message_id"),
                "reply_to_preview": reply_to_preview or existing.get("reply_to_preview", ""),
                "reply_to_sender_name": reply_to_sender_name or existing.get("reply_to_sender_name", ""),
            }, merge=True)
            return existing["id"]

    message_id = next_sequence("wa_messages")
    created_at = utcnow()
    effective_wa_message_id = wa_message_id or f"local_{message_id}"
    contact = _get_doc("wa_contacts", contact_id)
    # Resolve channel/wa_id efetivos pra calcular conversation_id
    eff_channel_id = channel_id if channel_id is not None else (contact or {}).get("channel_id")
    eff_wa_id = (contact or {}).get("wa_id", "")
    eff_phone_number_id = phone_number_id or (contact or {}).get("phone_number_id", "")
    eff_conversation_id = conversation_id or (
        _make_conversation_id(eff_channel_id, eff_wa_id) if eff_wa_id else None
    )
    document("wa_messages", message_id).set({
        "id": message_id,
        "wa_message_id": effective_wa_message_id,
        "contact_id": contact_id,
        "contact_doc_id": str(contact_id),
        "conversation_id": eff_conversation_id,
        "direction": direction,
        "msg_type": msg_type,
        "content": content or "",
        "media_path": media_path or "",
        "media_mime": media_mime or "",
        "media_id": media_id or "",
        "latitude": latitude,
        "longitude": longitude,
        "filename": filename or "",
        "status": status or "received",
        "operator_id": operator_id,
        "sender_user_id": sender_user_id,
        "channel_owner_user_id": channel_owner_user_id,
        "assigned_to": (contact or {}).get("assigned_to"),
        "assigned_to_uid": (contact or {}).get("assigned_to_uid", ""),
        "department_id": (contact or {}).get("department_id"),
        "channel_id": eff_channel_id,
        "phone_number_id": eff_phone_number_id,
        "is_rating_message": is_rating_message,
        "visibility": visibility,
        "timestamp_wa": _coerce_timestamp(timestamp_wa),
        "created_at": created_at,
        "reply_to_message_id": reply_to_message_id,
        "reply_to_preview": reply_to_preview or "",
        "reply_to_sender_name": reply_to_sender_name or "",
    })

    if contact:
        updates = {"last_message_at": created_at}
        if direction == "inbound" and status == "received":
            updates["unread_count"] = int(contact.get("unread_count", 0)) + 1
        document("wa_contacts", contact_id).set(updates, merge=True)

        # Atualiza conversation correspondente (Fase 2 — sub-threads).
        # Se ainda nao existe (mensagem de contato legado pre-Fase 2),
        # cria automaticamente.
        if eff_wa_id:
            try:
                upsert_wa_conversation(
                    contact_id=contact_id,
                    wa_id=eff_wa_id,
                    channel_id=eff_channel_id,
                    source_channel_type=(contact or {}).get("source_channel_type", ""),
                    phone_number_id=eff_phone_number_id,
                    direction_for_unread="inbound" if direction == "inbound" and status == "received" else ("outbound" if direction == "outbound" else None),
                )
            except Exception as exc:
                logger.warning("Falha ao upsert conversation para msg %s: %s", message_id, exc)

    # Atualizar metricas de auditoria (fire-and-forget)
    increment_audit_metrics(
        direction=direction,
        operator_id=operator_id or (contact or {}).get("assigned_to"),
    )
    # Visibilidade de uso mensal (Fase 2.10.4 — usage_{YYYY_MM} per-tenant)
    increment_usage_metrics(
        direction=direction,
        msg_type=msg_type,
        template_category=template_category,
        media_size_bytes=media_size_bytes,
    )
    return message_id


def get_wa_conversation(contact_id, limit=50, offset=0):
    q = (
        collection("wa_messages")
        .where("contact_id", "==", contact_id)
        .order_by("created_at", direction="DESCENDING")
    )
    if limit:
        q = q.limit(limit + offset)

    rows = []
    for snapshot in q.stream():
        row = _raw_doc(snapshot)
        if row:
            rows.append(row)

    if offset:
        rows = rows[offset:]
    # Reverter para ordem cronologica (mais antigo primeiro)
    rows.reverse()

    contact = _get_doc("wa_contacts", contact_id)
    operators = _user_map([row.get("operator_id") for row in rows])
    enriched = []
    for row in rows:
        item = dict(row)
        item["contact_name"] = contact.get("display_name", "") if contact else ""
        item["wa_id"] = contact.get("wa_id", "") if contact else ""
        item["phone_formatted"] = contact.get("phone_formatted", "") if contact else ""
        item["contact_avatar_path"] = contact.get("contact_avatar_path", "") if contact else ""
        item["operator_name"] = operators.get(row.get("operator_id"), {}).get("display_name", "")
        enriched.append(item)
    return _normalize_many(enriched)


def get_wa_message_by_id(message_id: int):
    for snap in collection("wa_messages").where("id", "==", message_id).limit(1).stream():
        return _raw_doc(snap)
    return None


def get_wa_message_by_wa_message_id(wa_message_id):
    if not wa_message_id:
        return None
    for snap in collection("wa_messages").where("wa_message_id", "==", wa_message_id).limit(1).stream():
        return _raw_doc(snap)
    return None


def mark_message_corrected(message_id: int, corrected_by_message_id: int):
    """Marca uma mensagem como corrigida por outra mensagem."""
    msg = get_wa_message_by_id(message_id)
    if not msg:
        return False
    document("wa_messages", message_id).set({
        "is_corrected": True,
        "corrected_by_message_id": corrected_by_message_id,
    }, merge=True)
    return True


def update_wa_message_transcription(db_id: int, transcription: str):
    document("wa_messages", db_id).set({"transcription": transcription}, merge=True)


def update_wa_message_status(wa_message_id, status, timestamp_wa=""):
    target = _get_first_by_field("wa_messages", "wa_message_id", wa_message_id)
    if target:
        document("wa_messages", target["id"]).set({"status": status}, merge=True)

    status_id = next_sequence("wa_message_status")
    document("wa_message_status", status_id).set({
        "id": status_id,
        "wa_message_id": wa_message_id,
        "status": status,
        "timestamp_wa": _coerce_timestamp(timestamp_wa),
        "created_at": utcnow(),
    })


def get_wa_unread_count():
    """Retorna mapa {contact_id: unread_count}.

    Nota: get_all_wa_contacts() ja inclui unread_count nos contatos.
    Esta funcao existe apenas para chamadas avulsas; o endpoint
    /api/wa/contacts NAO precisa mais chamar esta funcao separadamente.
    """
    result = {}
    for snapshot in collection("wa_contacts").where("unread_count", ">", 0).stream():
        row = _raw_doc(snapshot)
        if row:
            result[int(row["id"])] = int(row.get("unread_count", 0))
    return result


def mark_wa_conversation_read(contact_id):
    """Marca mensagens inbound como lidas. Usa query filtrada para ler apenas
    as mensagens que realmente precisam ser atualizadas (em vez de todas)."""
    q = (
        collection("wa_messages")
        .where("contact_id", "==", contact_id)
        .where("direction", "==", "inbound")
        .where("status", "==", "received")
    )
    batch = get_firestore_client().batch()
    count = 0
    total_updated = 0
    for snapshot in q.stream():
        batch.set(snapshot.reference, {"status": "read"}, merge=True)
        count += 1
        total_updated += 1
        if count >= 400:  # Firestore batch limit = 500
            batch.commit()
            batch = get_firestore_client().batch()
            count = 0
    if count > 0:
        batch.commit()
    document("wa_contacts", contact_id).set({"unread_count": 0}, merge=True)
    return total_updated


# ---------------------------------------------------------------------------
# Audit metrics (pre-aggregated daily counters)
# ---------------------------------------------------------------------------

def _audit_metric_doc_id(date_str, user_id=None):
    return f"{date_str}_{user_id}" if user_id else date_str


def increment_audit_metrics(direction, operator_id=None, is_new_lead=False, is_assumed=False):
    """Incrementa metricas diarias. Chamada a cada save_wa_message."""
    now = utcnow()
    date_str = now.strftime("%Y-%m-%d")
    half_hour = f"{now.strftime('%H')}:{('00' if now.minute < 30 else '30')}"

    def _increment(doc_id):
        ref = document("audit_metrics", doc_id)
        snap = ref.get()
        data = snap.to_dict() if snap.exists else {}

        updates = {
            "date": date_str,
            "updated_at": now,
        }

        if direction == "inbound":
            updates["total_messages_inbound"] = int(data.get("total_messages_inbound", 0)) + 1
        elif direction == "outbound":
            updates["total_messages_outbound"] = int(data.get("total_messages_outbound", 0)) + 1

        if is_new_lead:
            updates["total_leads_received"] = int(data.get("total_leads_received", 0)) + 1
        if is_assumed:
            updates["total_leads_assumed"] = int(data.get("total_leads_assumed", 0)) + 1

        # Messages by half hour
        by_half = data.get("messages_by_half_hour", {})
        by_half[half_hour] = int(by_half.get(half_hour, 0)) + 1
        updates["messages_by_half_hour"] = by_half

        # Activity tracking
        if not data.get("first_activity_at"):
            updates["first_activity_at"] = now
        updates["last_activity_at"] = now

        ref.set(updates, merge=True)

    try:
        # Global aggregate
        _increment(_audit_metric_doc_id(date_str))
        # Per-operator aggregate
        if operator_id:
            _increment(_audit_metric_doc_id(date_str, operator_id))
    except Exception as exc:
        logger.warning("Falha ao atualizar audit_metrics: %s", exc)


def get_audit_metrics(date_from, date_to):
    """Retorna metricas agregadas (daily/per-operator) para o periodo.

    Pula docs com prefix `usage_` (agregacao mensal — get_monthly_usage).
    """
    rows = []
    for snap in collection("audit_metrics").stream():
        if snap.id.startswith("usage_"):
            continue
        data = snap.to_dict() or {}
        date_str = data.get("date", "")
        if date_from <= date_str <= date_to:
            data["doc_id"] = snap.id
            rows.append(normalize_record(data))
    return rows


# ---------------------------------------------------------------------------
# Usage metrics mensal per-tenant (Fase 2.10.4)
# ---------------------------------------------------------------------------
#
# Doc id: `usage_{YYYY-MM}` em tenants/{tid}/audit_metrics/.
# Tenant scoping vem do ContextVar (collection() roteia automaticamente).
# Increment atomico via firestore.Increment evita perda em concorrencia.

def _usage_metrics_doc_id(year_month=None):
    if not year_month:
        year_month = utcnow().strftime("%Y-%m")
    return f"usage_{year_month}"


_VALID_TEMPLATE_CATEGORIES = ("marketing", "utility", "authentication")


def increment_usage_metrics(direction, msg_type="", template_category=None, media_size_bytes=0):
    """Incrementa usage_{YYYY_MM} do tenant atual com Increment atomico.

    Campos atualizados conforme direction/msg_type:
      - inbound  -> inbound_received++
      - outbound + msg_type='template' -> templates_sent.{cat}++ (cat
        normalizada pra marketing/utility/authentication ou 'unknown')
      - outbound + outros msg_type -> free_form_sent++
      - media_size_bytes>0 -> media_uploaded_bytes += bytes
    """
    now = utcnow()
    year_month = now.strftime("%Y-%m")
    doc_id = _usage_metrics_doc_id(year_month)

    updates = {
        "month": year_month,
        "updated_at": now,
    }

    if direction == "inbound":
        updates["inbound_received"] = firestore.Increment(1)
    elif direction == "outbound":
        if msg_type == "template":
            cat = (template_category or "").strip().lower() or "unknown"
            if cat not in _VALID_TEMPLATE_CATEGORIES:
                cat = "unknown"
            updates["templates_sent"] = {cat: firestore.Increment(1)}
        else:
            updates["free_form_sent"] = firestore.Increment(1)

    if media_size_bytes and int(media_size_bytes) > 0:
        updates["media_uploaded_bytes"] = firestore.Increment(int(media_size_bytes))

    try:
        document("audit_metrics", doc_id).set(updates, merge=True)
    except Exception as exc:
        logger.warning("Falha ao atualizar usage_metrics: %s", exc)


def get_monthly_usage(year_month=None):
    """Retorna usage_{YYYY_MM} do tenant atual.

    year_month default = mes corrente (UTC). Retorna esqueleto zerado se
    o doc ainda nao existe (mes sem trafego).
    """
    if not year_month:
        year_month = utcnow().strftime("%Y-%m")
    doc_id = _usage_metrics_doc_id(year_month)
    snap = document("audit_metrics", doc_id).get()
    if not snap.exists:
        return {
            "month": year_month,
            "templates_sent": {},
            "free_form_sent": 0,
            "inbound_received": 0,
            "media_uploaded_bytes": 0,
        }
    data = snap.to_dict() or {}
    data.setdefault("month", year_month)
    data.setdefault("templates_sent", {})
    data.setdefault("free_form_sent", 0)
    data.setdefault("inbound_received", 0)
    data.setdefault("media_uploaded_bytes", 0)
    return normalize_record(data)


def get_usage_history(months=3):
    """Retorna ultimos N meses de usage do tenant atual (mes corrente primeiro).

    months e clampeado em [1, 24].
    """
    months = max(1, min(int(months or 3), 24))
    now = utcnow()
    rows = []
    for offset in range(months):
        year = now.year
        month = now.month - offset
        while month <= 0:
            month += 12
            year -= 1
        ym = f"{year:04d}-{month:02d}"
        rows.append(get_monthly_usage(ym))
    return rows


def get_all_ratings(date_from=None, date_to=None):
    """Retorna contatos convertidos com rating."""
    rows = []
    for snap in collection("wa_contacts").where("qualification", "==", "convertido").stream():
        data = _raw_doc(snap)
        if not data or data.get("rating") is None:
            continue
        if date_from or date_to:
            rated_at = str(data.get("rating_received_at", ""))[:10]
            if date_from and rated_at < date_from:
                continue
            if date_to and rated_at > date_to:
                continue
        rows.append(normalize_record(data))
    return rows


def log_audit(user_id, action, detail="", ip_address=""):
    audit_id = next_sequence("audit_log")
    document("audit_log", audit_id).set({
        "id": audit_id,
        "user_id": user_id,
        "action": action,
        "detail": detail or "",
        "ip_address": ip_address or "",
        "created_at": utcnow(),
    })


def format_phone_br(wa_id):
    s = str(wa_id)
    if len(s) == 13 and s.startswith("55"):
        return f"+55 ({s[2:4]}) {s[4:9]}-{s[9:]}"
    if len(s) == 12 and s.startswith("55"):
        return f"+55 ({s[2:4]}) {s[4:8]}-{s[8:]}"
    return f"+{s}" if not s.startswith("+") else s


def normalize_br_phone(wa_id):
    s = str(wa_id)
    if len(s) == 12 and s.startswith("55"):
        ddd = s[2:4]
        local = s[4:]
        if local and local[0] in ("6", "7", "8", "9"):
            return f"55{ddd}9{local}"
    return s


def wa_id_variants(wa_id):
    """Gera todas as variantes equivalentes de um wa_id brasileiro.

    Celulares BR tem o '9' na frente desde 2012, mas numeros cadastrados
    antes (ou recebidos via webhook de clientes antigos) podem chegar sem.
    Retorna lista com o wa_id original e a variante com/sem 9 para
    cruzamento ao buscar contato existente.
    """
    s = str(wa_id).strip()
    if not s:
        return []
    variants = [s]
    # Celular BR com 9 (13 digitos, ex: 5531982779779) -> adiciona variante sem 9
    if len(s) == 13 and s.startswith("55") and len(s) > 4 and s[4] == "9":
        variants.append(s[:4] + s[5:])
    # Celular BR sem 9 (12 digitos, ex: 553182779779) -> adiciona variante com 9
    elif len(s) == 12 and s.startswith("55") and len(s) > 4 and s[4] in ("6", "7", "8", "9"):
        variants.append(s[:4] + "9" + s[4:])
    return variants


def _find_contact_by_wa_id_any_variant(wa_id):
    """Busca contato por wa_id testando tambem a variante com/sem 9.

    Retorna o primeiro match encontrado ou None.
    """
    for variant in wa_id_variants(wa_id):
        found = _get_first_by_field("wa_contacts", "wa_id", variant)
        if found:
            return found
    return None


# ---------------------------------------------------------------------------
# Configuracoes do sistema e do usuario
# ---------------------------------------------------------------------------

_DEFAULT_SYSTEM_SETTINGS = {
    "chat_prefix_enabled": False,
    "chat_prefix_roles": ["admin", "supervisor", "operador"],
    "quick_message_max": 20,
    "quick_messages_global": [],
    "notification_sound_enabled": True,
    "alarm_enabled": True,
    "alarm_threshold_minutes": 5,
    "alarm_department_ids": [],
    "alarm_sound_path": "",
    "notification_sound_path": "",
    "bot_enabled": False,
}


def get_system_settings():
    doc = _get_doc("system_settings", "chat")
    if not doc:
        return dict(_DEFAULT_SYSTEM_SETTINGS)
    result = dict(_DEFAULT_SYSTEM_SETTINGS)
    result.update({k: v for k, v in doc.items() if k in _DEFAULT_SYSTEM_SETTINGS})
    return result


def save_system_settings(settings: dict):
    allowed = set(_DEFAULT_SYSTEM_SETTINGS.keys())
    filtered = {k: v for k, v in settings.items() if k in allowed}
    filtered["updated_at"] = utcnow()
    document("system_settings", "chat").set(filtered, merge=True)
    return get_system_settings()


def get_user_settings(user_id: int):
    doc = _get_doc("user_settings", user_id)
    defaults = {
        "chat_prefix_enabled": False,
        "chat_prefix_name": "",
        "quick_messages": [],
    }
    if not doc:
        return defaults
    result = dict(defaults)
    result.update({k: v for k, v in doc.items() if k in defaults})
    return result


def save_user_settings(user_id: int, settings: dict):
    allowed = {"chat_prefix_enabled", "chat_prefix_name", "quick_messages"}
    filtered = {k: v for k, v in settings.items() if k in allowed}
    filtered["updated_at"] = utcnow()
    document("user_settings", user_id).set(filtered, merge=True)
    return get_user_settings(user_id)


# ---------------------------------------------------------------------------
# Google Chat - Comunicacao interna
# ---------------------------------------------------------------------------

def _active_gc_participants():
    participants = {
        str((row or {}).get("email") or "").strip().lower()
        for row in _all_docs("users")
        if row and row.get("is_active", 1)
    }
    participants.discard("")
    return sorted(participants)


def _gc_unread_recipients(conversation):
    recipients = set(_active_gc_participants())
    recipients.update(
        str(participant or "").strip().lower()
        for participant in (conversation or {}).get("participants", [])
        if str(participant or "").strip()
    )
    recipients.update(
        str(identifier or "").strip().lower()
        for identifier in ((conversation or {}).get("unread_count", {}) or {}).keys()
        if str(identifier or "").strip()
    )
    recipients.discard("")
    return sorted(recipients)


def upsert_gc_conversation(space_id, space_name=""):
    """Cria ou atualiza conversa do Google Chat. Retorna conversation_id."""
    now = utcnow()
    existing = _get_first_by_field("gc_conversations", "space_id", space_id)
    participants = _active_gc_participants()
    if existing:
        updates = {"last_message_at": now, "participants": participants}
        if space_name:
            updates["space_name"] = space_name
        document("gc_conversations", existing["id"]).set(updates, merge=True)
        return existing["id"]

    conversation_id = next_sequence("gc_conversations")
    document("gc_conversations", conversation_id).set({
        "id": conversation_id,
        "space_id": space_id,
        "space_name": space_name or space_id,
        "participants": participants,
        "last_message": "",
        "last_message_at": now,
        "unread_count": {},
        "created_at": now,
    })
    return conversation_id


def get_gc_conversation(conversation_id):
    """Retorna uma conversa pelo ID."""
    return normalize_record(_get_doc("gc_conversations", conversation_id))


def get_gc_conversation_by_space(space_id):
    """Retorna conversa pelo space_id do Google Chat."""
    row = _get_first_by_field("gc_conversations", "space_id", space_id)
    return normalize_record(row) if row else None


def get_all_gc_conversations():
    """Lista todas as conversas do Google Chat."""
    rows = [row for row in _all_docs("gc_conversations") if row]
    rows = _sort_records(rows, "last_message_at", reverse=True)
    return _normalize_many(rows)


def save_gc_message(conversation_id, gchat_message_id, sender_email, sender_name,
                    msg_type="text", content="", media_path="", media_mime="",
                    source="google_chat", create_time=""):
    """Salva mensagem do Google Chat no Firestore."""
    existing = _get_first_by_field("gc_messages", "gchat_message_id", gchat_message_id)
    if existing:
        return existing["id"]

    message_id = next_sequence("gc_messages")
    now = utcnow()
    document("gc_messages", message_id).set({
        "id": message_id,
        "conversation_id": conversation_id,
        "gchat_message_id": gchat_message_id,
        "sender_email": sender_email,
        "sender_name": sender_name,
        "msg_type": msg_type,
        "content": content or "",
        "media_path": media_path or "",
        "media_mime": media_mime or "",
        "source": source,
        "create_time": _coerce_timestamp(create_time),
        "created_at": now,
    })

    # Atualizar preview e timestamp na conversa
    conversation = _get_doc("gc_conversations", conversation_id)
    if conversation:
        participants = _gc_unread_recipients(conversation)
        sender_key = str(sender_email or "").strip().lower()
        preview = content[:100] if content else f"[{msg_type}]"
        updates = {
            "last_message": preview,
            "last_message_at": now,
            "participants": participants,
        }
        unread = conversation.get("unread_count", {}) or {}
        for participant_id in participants:
            unread.setdefault(participant_id, 0)
            if participant_id != sender_key:
                unread[participant_id] = int(unread.get(participant_id, 0)) + 1
        updates["unread_count"] = unread
        document("gc_conversations", conversation_id).set(updates, merge=True)

    return message_id


def get_gc_messages(conversation_id, limit=50, offset=0):
    """Retorna mensagens de uma conversa do Google Chat."""
    q = (
        collection("gc_messages")
        .where("conversation_id", "==", conversation_id)
        .order_by("created_at", direction="DESCENDING")
    )
    if limit:
        q = q.limit(limit + offset)

    rows = []
    for snapshot in q.stream():
        row = _raw_doc(snapshot)
        if row:
            rows.append(row)

    if offset:
        rows = rows[offset:]
    rows.reverse()
    return _normalize_many(rows)


def mark_gc_conversation_read(conversation_id, user_identifier):
    """Reseta o contador de nao-lidas para um usuario em uma conversa."""
    conversation = _get_doc("gc_conversations", conversation_id)
    if not conversation:
        return
    unread = conversation.get("unread_count", {}) or {}
    uid = str(user_identifier or "").strip().lower()
    if not uid:
        return
    unread[uid] = 0
    document("gc_conversations", conversation_id).set({"unread_count": unread}, merge=True)


# ---------------------------------------------------------------------------
# Contador de assumidas sem resposta (operador)
# ---------------------------------------------------------------------------

_ASSUME_COUNTER_MIN = -2
_ASSUME_COUNTER_MAX = 0


def get_assume_counter(user_id: int) -> int:
    """Retorna o contador de assumidas sem resposta do operador (entre -2 e 0)."""
    doc = _get_doc("operator_assume_counters", user_id)
    if not doc:
        return 0
    return max(_ASSUME_COUNTER_MIN, min(_ASSUME_COUNTER_MAX, doc.get("counter", 0)))


@firestore.transactional
def _transactional_decrement(transaction, ref, user_id):
    snapshot = ref.get(transaction=transaction)
    data = snapshot.to_dict() or {} if snapshot.exists else {}
    current = max(_ASSUME_COUNTER_MIN, min(_ASSUME_COUNTER_MAX, data.get("counter", 0)))
    new_val = max(_ASSUME_COUNTER_MIN, current - 1)
    transaction.set(ref, {"user_id": user_id, "counter": new_val, "updated_at": utcnow()}, merge=True)
    return new_val


def decrement_assume_counter(user_id: int) -> int:
    """Decrementa o contador ao assumir sem ter respondido. Usa transacao atomica."""
    ref = document("operator_assume_counters", user_id)
    client = get_firestore_client()
    return _transactional_decrement(client.transaction(), ref, user_id)


@firestore.transactional
def _transactional_increment(transaction, ref, user_id):
    snapshot = ref.get(transaction=transaction)
    data = snapshot.to_dict() or {} if snapshot.exists else {}
    current = max(_ASSUME_COUNTER_MIN, min(_ASSUME_COUNTER_MAX, data.get("counter", 0)))
    new_val = min(_ASSUME_COUNTER_MAX, current + 1)
    transaction.set(ref, {"user_id": user_id, "counter": new_val, "updated_at": utcnow()}, merge=True)
    return new_val


def increment_assume_counter(user_id: int) -> int:
    """Incrementa o contador ao responder uma conversa assumida. Usa transacao atomica."""
    ref = document("operator_assume_counters", user_id)
    client = get_firestore_client()
    return _transactional_increment(client.transaction(), ref, user_id)


def mark_contact_pending_response(contact_id: int):
    """Marca o contato como pendente de resposta do operador apos assumir."""
    document("wa_contacts", contact_id).set({
        "assume_pending_response": True,
    }, merge=True)


def clear_contact_pending_response(contact_id: int):
    """Remove a flag de pendente de resposta apos o operador responder."""
    document("wa_contacts", contact_id).set({
        "assume_pending_response": False,
    }, merge=True)


def reset_assume_counter(user_id: int):
    """Reseta o contador de assumidas sem resposta para 0."""
    document("operator_assume_counters", user_id).set({
        "user_id": user_id,
        "counter": 0,
        "updated_at": utcnow(),
    }, merge=True)
