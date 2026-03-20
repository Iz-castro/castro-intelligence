# -*- coding: utf-8 -*-

import logging
from contextlib import contextmanager
from datetime import datetime, timezone

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


def _user_map(user_ids):
    result = {}
    for user_id in {uid for uid in user_ids if uid}:
        user = _get_doc("users", user_id)
        if user:
            result[user_id] = user
    return result


def _department_map(department_ids):
    result = {}
    for department_id in {did for did in department_ids if did}:
        department = _get_doc("departments", department_id)
        if department:
            result[department_id] = department
    return result


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


def create_department(name, description=""):
    existing = _get_first_by_field("departments", "name", name)
    if existing:
        return existing["id"]

    department_id = next_sequence("departments")
    document("departments", department_id).set({
        "id": department_id,
        "name": name,
        "description": description or "",
        "is_active": 1,
        "created_at": utcnow(),
    })
    return department_id


def get_all_departments():
    rows = [row for row in _all_docs("departments") if row and row.get("is_active", 1)]
    rows.sort(key=lambda row: row.get("name", "").lower())
    return _normalize_many(rows)


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
    return normalize_record({
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "department_id": row.get("department_id"),
        "role": row.get("role", "operador"),
        "is_active": row.get("is_active", 1),
        "email": row.get("email", ""),
        "firebase_uid": row.get("firebase_uid", ""),
        "auth_provider": row.get("auth_provider", "legacy"),
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
        "auth_provider": "legacy",
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


def upsert_wa_contact(wa_id, display_name=""):
    now = utcnow()
    existing = _get_first_by_field("wa_contacts", "wa_id", wa_id)
    if existing:
        document("wa_contacts", existing["id"]).set({
            "display_name": display_name or "",
            "last_message_at": now,
        }, merge=True)
        return existing["id"]

    contact_id = next_sequence("wa_contacts")
    document("wa_contacts", contact_id).set({
        "id": contact_id,
        "wa_id": wa_id,
        "display_name": display_name or "",
        "phone_formatted": format_phone_br(wa_id),
        "profile_picture_url": "",
        "contact_avatar_path": "",
        "qualification": "novo",
        "notes": "",
        "assigned_to": None,
        "assigned_to_uid": "",
        "department_id": None,
        "is_archived": 0,
        "unread_count": 0,
        "first_seen_at": now,
        "last_message_at": now,
    })
    return contact_id


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
    return [_enrich_contact(row) for row in rows]


def update_wa_contact_qualification(contact_id, qualification, notes=""):
    fields = {"qualification": qualification}
    if notes is not None:
        fields["notes"] = notes
    document("wa_contacts", contact_id).set(fields, merge=True)


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


def insert_transfer_system_message(contact_id, content, operator_id=None):
    return save_wa_message(
        wa_message_id=f"sys_{utcnow().isoformat()}_{contact_id}",
        contact_id=contact_id,
        direction="system",
        msg_type="system",
        content=content,
        status="delivered",
        timestamp_wa=utcnow().isoformat(),
        operator_id=operator_id,
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
                    status="received", timestamp_wa="", operator_id=None):
    if wa_message_id:
        existing = _get_first_by_field("wa_messages", "wa_message_id", wa_message_id)
        if existing:
            return existing["id"]

    message_id = next_sequence("wa_messages")
    created_at = utcnow()
    effective_wa_message_id = wa_message_id or f"local_{message_id}"
    contact = _get_doc("wa_contacts", contact_id)
    document("wa_messages", message_id).set({
        "id": message_id,
        "wa_message_id": effective_wa_message_id,
        "contact_id": contact_id,
        "contact_doc_id": str(contact_id),
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
        "assigned_to": (contact or {}).get("assigned_to"),
        "assigned_to_uid": (contact or {}).get("assigned_to_uid", ""),
        "department_id": (contact or {}).get("department_id"),
        "timestamp_wa": _coerce_timestamp(timestamp_wa),
        "created_at": created_at,
    })

    if contact:
        updates = {"last_message_at": created_at}
        if direction == "inbound" and status == "received":
            updates["unread_count"] = int(contact.get("unread_count", 0)) + 1
        document("wa_contacts", contact_id).set(updates, merge=True)
    return message_id


def get_wa_conversation(contact_id, limit=200, offset=0):
    rows = []
    for snapshot in collection("wa_messages").where("contact_id", "==", contact_id).stream():
        row = _raw_doc(snapshot)
        if row:
            rows.append(row)
    rows = _sort_records(rows, "created_at")
    if offset:
        rows = rows[offset:]
    if limit:
        rows = rows[:limit]

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
    rows = [row for row in _all_docs("wa_contacts") if row]
    return {int(row["id"]): int(row.get("unread_count", 0)) for row in rows if int(row.get("unread_count", 0)) > 0}


def mark_wa_conversation_read(contact_id):
    rows = []
    for snapshot in collection("wa_messages").where("contact_id", "==", contact_id).stream():
        row = _raw_doc(snapshot)
        if row:
            rows.append(row)
    for row in rows:
        if row.get("direction") == "inbound" and row.get("status") == "received":
            document("wa_messages", row["id"]).set({"status": "read"}, merge=True)
    document("wa_contacts", contact_id).set({"unread_count": 0}, merge=True)


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
