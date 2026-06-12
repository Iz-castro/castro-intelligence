# -*- coding: utf-8 -*-

import logging
import time
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta

from google.api_core import exceptions as gcloud_exceptions
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
        "coex_authorized": user.get("coex_authorized", 0),
        "coex_phone": user.get("coex_phone", ""),
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
        "coex_authorized": row.get("coex_authorized", 0),
        "coex_phone": row.get("coex_phone", ""),
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
        "coex_authorized": 0,
        "coex_phone": "",
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


def set_coex_authorization(user_id, phone, authorized=True):
    """Marca/desmarca um usuario como autorizado a fazer Embedded Signup
    coexistence do proprio numero.

    `phone` e o numero pre-autorizado pelo admin (guardado so com digitos,
    canonico); o /exchange compara com o numero conectado no signup. Setar
    authorized=False revoga a autorizacao e limpa o numero.
    """
    phone_clean = "".join(ch for ch in str(phone or "") if ch.isdigit())
    fields = {
        "coex_authorized": 1 if authorized else 0,
        "coex_phone": phone_clean if authorized else "",
    }
    document("users", user_id).set(fields, merge=True)
    updated = _get_doc("users", user_id)
    if updated:
        _sync_operator_profile_from_user(updated)
    return get_user_by_id(user_id)


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

class ConversationIdError(ValueError):
    """Raise quando channel_id ou wa_id nao podem gerar conversation_id
    deterministico. Webhook handlers devem capturar e enfileirar em
    pending_webhook_events em vez de salvar mensagem com id sintetico
    (default__) que nao casa com selectedThreadId do frontend."""


def _make_conversation_id(channel_id, wa_id):
    """Gera id deterministico de conversation '{channel_id}__{wa_id}'.

    Falha-loud com ConversationIdError se channel_id ou wa_id estiverem
    ausentes. O fallback antigo ('default__{wa_id}') gerava ids que o
    frontend nunca encontrava (selectedThreadId usa channel_id real),
    deixando mensagens orfas invisiveis ao operador.

    Normaliza wa_id (nono digito BR) defesa-em-profundidade — callers
    como save_wa_message reusam contact.wa_id de docs antigos que
    podem estar em forma 12-dig sem 9. Sem normalizar aqui, mensagem
    nova sai com conversation_id divergente do que o frontend espera.
    """
    if channel_id is None or channel_id == "":
        raise ConversationIdError(
            f"_make_conversation_id requer channel_id (wa_id={wa_id!r})"
        )
    if not wa_id:
        raise ConversationIdError(
            f"_make_conversation_id requer wa_id (channel_id={channel_id!r})"
        )
    return f"{channel_id}__{normalize_br_phone(wa_id)}"


def upsert_wa_conversation(
    contact_id,
    wa_id,
    channel_id=None,
    source_channel_type="",
    phone_number_id="",
    auto_assign_user_id=None,
    direction_for_unread=None,
    message_at=None,
):
    """Cria ou atualiza a conversation correspondente a (channel_id, wa_id).

    Retorna conversation_id (string deterministica). Se a conversation
    ja existe, atualiza last_message_at e demais timestamps, alem de
    auto-assign quando aplicavel.

    direction_for_unread: 'inbound' incrementa unread_count, outras
    direcoes nao mexem. None nao mexe (uso pelo upsert_wa_contact).

    message_at: data REAL da mensagem (timestamp_wa). Replay de history/
    backup chega horas/meses depois — sem isto a conversa "sobe" pro topo
    da sidebar com a data da gravacao. last_message_at e monotonico: so
    avanca, nunca recua.

    Normaliza o nono digito BR antes de calcular o conversation_id —
    determinismo de id depende de wa_id canonico para nao criar
    threads duplicadas pra mesmo cliente.
    """
    if wa_id is None or wa_id == "":
        raise ValueError("wa_id obrigatorio para upsert_wa_conversation")
    wa_id = normalize_br_phone(wa_id)
    conversation_id = _make_conversation_id(channel_id, wa_id)
    now = utcnow()
    msg_at = _coerce_timestamp(message_at)
    if not isinstance(msg_at, datetime):
        msg_at = now

    # Denormaliza dados do canal no doc do Atendimento para a UI. No modo
    # snapshot o frontend nao faz join com o canal (e operador comum nem
    # recebe /api/admin/channels), entao sem isto a faixa de contexto mostra
    # "Conversa no numero: —". Canal fora do cache = inativo/removido — mesma
    # semantica do envio (get_send_credentials falha quando get_channel e None).
    _ch_fields: dict = {}
    try:
        from channel_service import get_channel as _get_channel, refresh_channels as _refresh_channels
        _ch = _get_channel(channel_id) if channel_id is not None else None
        if _ch is None and channel_id is not None:
            # Cache de canais defasado (canal recem-criado, cold start de
            # instancia, ou cross-instance no Cloud Run com TTL de 60s) faria a
            # conversa nascer "canal removido" (channel_active=False) mesmo o
            # canal estando ativo. Forca um refresh e tenta de novo antes de
            # marcar inativo — so marca False se o canal sumiu de fato.
            _refresh_channels()
            _ch = _get_channel(channel_id)
        if _ch:
            _ch_fields = {
                "channel_phone_number": _ch.get("display_phone_number", ""),
                "channel_label": _ch.get("label", ""),
                "channel_type": _ch.get("channel_type", ""),
                "channel_active": True,
            }
        elif channel_id is not None:
            _ch_fields = {"channel_active": False}
    except Exception:
        _ch_fields = {}

    ref = document("wa_conversations", conversation_id)
    snap = ref.get()
    existing = snap.to_dict() if snap.exists else None

    if existing:
        updates = {**_ch_fields}
        _cur_lma = _coerce_timestamp(existing.get("last_message_at"))
        try:
            _advances = not isinstance(_cur_lma, datetime) or msg_at >= _cur_lma
        except TypeError:
            _advances = True
        if _advances:
            updates["last_message_at"] = msg_at
        if direction_for_unread == "inbound":
            updates["last_inbound_at"] = msg_at
            updates["unread_count"] = int(existing.get("unread_count", 0)) + 1
        elif direction_for_unread == "outbound":
            updates["last_outbound_at"] = msg_at
        if direction_for_unread in ("inbound", "outbound"):
            # Atividade reabre um atendimento fechado (Fase 4 — ciclo de vida).
            updates["attendance_status"] = "aberto"
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
        "attendance_status": "aberto",
        "created_at": now,
        "last_message_at": msg_at,
        "last_inbound_at": msg_at if direction_for_unread == "inbound" else None,
        "last_outbound_at": msg_at if direction_for_unread == "outbound" else None,
        **_ch_fields,
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


def assign_wa_conversation(conversation_id, to_user_id, to_department_id, transferred_by, reason="", summary="", also_lead=False):
    """Transfere uma conversation (thread). Atualiza a conversation; o
    contato (Dono do Lead) so e movido junto quando also_lead=True.

    Fase 3B: por padrao NAO espelha no contato — Dono do Atendimento
    (conversation.assigned_to) e Dono do Lead (contact.assigned_to) sao
    distintos. Transferir uma thread nao muda o Lead inteiro. O espelho
    legado virou opt-in (also_lead) e a reatribuicao explicita do Lead usa
    assign_wa_contact (endpoint /api/admin/reassign-lead).

    Retorna {from_user_id, to_user_id, contact_id} ou None se nao achar.
    """
    conv = get_wa_conversation_by_id(conversation_id)
    if not conv:
        return None
    contact_id = conv.get("contact_id")
    from_user = conv.get("assigned_to")
    from_dept = conv.get("department_id")
    to_user = _get_doc("users", to_user_id) if to_user_id else None
    was_backup = bool(conv.get("is_backup"))

    document("wa_conversations", conversation_id).set({
        "assigned_to": to_user_id,
        "assigned_to_uid": (to_user or {}).get("firebase_uid", ""),
        "department_id": to_department_id,
        "is_backup": False,  # atribuir GRADUA a conversa: sai da caixa Backup
        # Transferencia explicita SUPERA takeover temporario: sem isto, um
        # 'pending' herdado (lead de outrem escreveu no numero coex) bloqueia
        # o envio do NOVO dono com 403 (incidente roberta 2026-06-12 13:02).
        "takeover_status": None,
        "takeover_user_id": None,
    }, merge=True)
    # Espelho no contato (Dono do Lead) — opt-in pos-Fase 3B.
    if also_lead and contact_id is not None:
        document("wa_contacts", contact_id).set({
            "assigned_to": to_user_id,
            "assigned_to_uid": (to_user or {}).get("firebase_uid", ""),
            "department_id": to_department_id,
            "is_backup": False,
        }, merge=True)
    # Graduacao de backup: a 1a atribuicao define a dona de origem (sale_owner),
    # igual a um assume. Handoff normal (nao-backup) NAO mexe no sale_owner.
    if was_backup and to_user_id and contact_id is not None:
        set_sale_owner(contact_id, to_user_id)

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


def flag_conversation_takeover(conversation_id, lead_owner_user_id, handler_user_id):
    """Marca a conversa como 'pending' takeover temporario.

    Cenario: a mensagem chegou no canal de handler_user_id (dono do numero),
    mas o lead ja pertence a lead_owner_user_id (outro operador). A UI oferece
    "assumir temporariamente" sem roubar o lead. Idempotente — NAO reverte uma
    sessao ja 'active' (operador ja assumiu).
    """
    conv = get_wa_conversation_by_id(conversation_id)
    if not conv:
        return False
    if conv.get("takeover_status") == "active":
        return False
    document("wa_conversations", conversation_id).set({
        "takeover_status": "pending",
        "lead_owner_user_id": lead_owner_user_id,
        "takeover_handler_user_id": handler_user_id,
    }, merge=True)
    return True


def set_conversation_takeover_active(conversation_id, handler_user_id):
    """O operador dono do numero (handler) assume o atendimento temporario."""
    conv = get_wa_conversation_by_id(conversation_id)
    if not conv:
        return None
    document("wa_conversations", conversation_id).set({
        "takeover_status": "active",
        "takeover_handler_user_id": handler_user_id,
        "takeover_started_at": utcnow(),
    }, merge=True)
    return get_wa_conversation_by_id(conversation_id)


def clear_conversation_takeover(conversation_id):
    """Encerra a sessao temporaria e devolve o lead ao dono (status -> 'none').
    O historico fica atrelado ao contato; proximas mensagens nesse canal
    reabrem como 'pending'."""
    conv = get_wa_conversation_by_id(conversation_id)
    if not conv:
        return None
    document("wa_conversations", conversation_id).set({
        "takeover_status": "none",
        "takeover_started_at": None,
    }, merge=True)
    return get_wa_conversation_by_id(conversation_id)


def expire_stale_takeovers(max_idle_hours):
    """Devolve sessoes de takeover 'active' inativas ha mais de max_idle_hours.

    Inatividade TOTAL: usa last_message_at (atualizado em inbound E outbound),
    com fallback pra takeover_started_at. Opera no tenant_context atual. Retorna
    lista de {conversation_id, contact_id, lead_owner_user_id} dos devolvidos.
    """
    from datetime import timedelta
    cutoff = utcnow() - timedelta(hours=max_idle_hours)
    expired = []
    for snap in collection("wa_conversations").where("takeover_status", "==", "active").stream():
        conv = snap.to_dict() or {}
        last = conv.get("last_message_at") or conv.get("takeover_started_at")
        if isinstance(last, str):
            try:
                last = datetime.fromisoformat(last.replace("Z", "+00:00"))
            except ValueError:
                last = None
        try:
            stale = last is not None and last < cutoff
        except TypeError:
            stale = False  # naive vs aware — nao arrisca devolver indevido
        if not stale:
            continue
        cid = snap.id
        document("wa_conversations", cid).set(
            {"takeover_status": "none", "takeover_started_at": None}, merge=True,
        )
        expired.append({
            "conversation_id": cid,
            "contact_id": conv.get("contact_id"),
            "lead_owner_user_id": conv.get("lead_owner_user_id"),
        })
    return expired


def close_stale_attendances(max_idle_hours):
    """Fecha (attendance_status='fechado_inatividade') atendimentos ATRIBUIDOS
    ociosos ha mais de max_idle_hours (sem mensagem). Reabre sozinho na proxima
    mensagem (upsert_wa_conversation). Opera no tenant_context atual. Retorna
    lista de {conversation_id, contact_id, assigned_to}. (Fase 4.)"""
    from datetime import timedelta
    cutoff = utcnow() - timedelta(hours=max_idle_hours)
    closed = []
    for snap in collection("wa_conversations").stream():
        conv = snap.to_dict() or {}
        if not conv.get("assigned_to"):
            continue  # so atendimentos atribuidos (fila/bot nao fecham)
        if conv.get("attendance_status") not in (None, "", "aberto"):
            continue  # ja fechado
        last = conv.get("last_message_at")
        if isinstance(last, str):
            try:
                last = datetime.fromisoformat(last.replace("Z", "+00:00"))
            except ValueError:
                last = None
        try:
            stale = last is not None and last < cutoff
        except TypeError:
            stale = False  # naive vs aware — nao arrisca fechar indevido
        if not stale:
            continue
        cid = snap.id
        # Mesma regra do fechamento manual: lead (contato) E atendimento (esta
        # conversa) voltam p/ a dona de origem (sale_owner).
        _owner_fields = revert_lead_to_sale_owner(conv.get("contact_id"))
        _conv_updates = {"attendance_status": "fechado_inatividade"}
        if _owner_fields:
            _conv_updates.update(_owner_fields)
        document("wa_conversations", cid).set(_conv_updates, merge=True)
        closed.append({
            "conversation_id": cid,
            "contact_id": conv.get("contact_id"),
            "assigned_to": conv.get("assigned_to"),
            "channel_id": conv.get("channel_id"),
        })
    return closed


def set_attendance_status(conversation_id, status, clear_takeover=False):
    """Define o attendance_status manualmente (Fase 4 — fechar/reabrir).
    status: 'aberto' | 'fechado_manual'. clear_takeover encerra a sessao
    temporaria de takeover junto. Retorna a conversation atualizada ou None."""
    conv = get_wa_conversation_by_id(conversation_id)
    if not conv:
        return None
    updates = {"attendance_status": status}
    if clear_takeover:
        updates["takeover_status"] = "none"
        updates["takeover_started_at"] = None
    # Fechamento -> o Dono do Lead (contato) E o Dono do Atendimento (esta
    # conversa) voltam p/ a dona de origem (sale_owner). Assim, ao reabrir no
    # proximo contato, a conversa ja e da vendedora que assumiu (prioridade).
    if str(status).startswith("fechado"):
        _owner_fields = revert_lead_to_sale_owner(conv.get("contact_id"))
        if _owner_fields:
            updates.update(_owner_fields)
    document("wa_conversations", conversation_id).set(updates, merge=True)
    return get_wa_conversation_by_id(conversation_id)


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
                      auto_assign_user_id=None,
                      from_message_event=True):
    """Cria ou atualiza um contato WhatsApp.

    Para canais coexistence, auto_assign_user_id atribui automaticamente
    ao operador dono do numero.

    Normaliza o nono digito BR e busca tambem variantes (com/sem '9')
    como defesa em profundidade contra callers que esquecam de
    normalizar.

    `from_message_event=True` (default): caller veio de evento real de
    mensagem (_process_messages, _process_smb_message_echoes,
    _process_history). Atualiza `last_message_at`/`last_inbound_at` e
    cria/atualiza a `wa_conversation` correspondente.

    `from_message_event=False`: caller e o `_process_smb_app_state_sync`
    (sincronizacao da agenda telefonica do dono). Nao popula timestamps
    de mensagem nem cria conversation — contato fica disponivel pra
    busca/seleção, mas só vira thread quando houver mensagem real.
    """
    wa_id = normalize_br_phone(wa_id)
    now = utcnow()
    existing = _find_contact_by_wa_id_any_variant(wa_id)
    if existing:
        return _update_existing_wa_contact(
            existing, wa_id, display_name, channel_id, phone_number_id,
            source_channel_type, auto_assign_user_id, from_message_event, now,
        )

    phone_formatted = format_phone_br(wa_id)
    contact_id = next_sequence("wa_contacts")
    new_contact = {
        "id": contact_id,
        "wa_id": wa_id,
        "display_name": _resolve_display_name("", display_name, phone_formatted),
        "declared_name": "",
        "whatsapp_profile_name": display_name or "",
        "created_source": "webhook" if from_message_event else "state_sync",
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
        "sale_owner_user_id": None,
        "sale_owner_uid": "",
        "converted_by_user_id": None,
        "rating": None,
        "rating_requested_at": None,
        "is_archived": 0,
        "unread_count": 0,
        "first_seen_at": now,
        # Timestamps de mensagem so populados quando vem de evento real.
        # state_sync (agenda telefonica) deixa null pra contato nao aparecer
        # no orderBy("last_message_at") da sidebar.
        "last_message_at": now if from_message_event else None,
        "last_inbound_at": now if from_message_event else None,
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
    # Garantia anti-duplicata: claim atomico do wa_id num doc-indice
    # (doc id = wa_id canonico). document().create() falha se ja existe —
    # primitiva global e atomica, imune ao lag de query que causava as
    # duplicatas em rajada/concorrencia (inclusive cross-instancia).
    idx_ref = document("wa_contact_index", wa_id)
    try:
        idx_ref.create({"contact_id": contact_id, "created_at": now})
    except gcloud_exceptions.AlreadyExists:
        # Outra request/instancia reivindicou este wa_id concorrentemente.
        # Usa o vencedor (get por id e fortemente consistente, sem lag de
        # query). Janela ms entre claim e gravacao do doc -> retry curto.
        winner_id = (idx_ref.get().to_dict() or {}).get("contact_id")
        winner = None
        for _ in range(5):
            winner = _get_doc("wa_contacts", winner_id) if winner_id is not None else None
            if winner:
                break
            time.sleep(0.1)
        if winner:
            return _update_existing_wa_contact(
                winner, wa_id, display_name, channel_id, phone_number_id,
                source_channel_type, auto_assign_user_id, from_message_event, now,
            )
        logger.warning(
            "wa_contact_index %s aponta p/ contato inexistente (%s) — recriando",
            wa_id, winner_id,
        )
    document("wa_contacts", contact_id).set(new_contact)
    # Upsert conversation correspondente (Fase 2 — sub-threads por canal).
    # Pulado em state_sync: thread so nasce com mensagem real, pra nao
    # poluir sidebar com 165 contatos da agenda telefonica.
    if from_message_event:
        upsert_wa_conversation(
            contact_id=contact_id,
            wa_id=wa_id,
            channel_id=channel_id,
            source_channel_type=source_channel_type,
            phone_number_id=phone_number_id,
            auto_assign_user_id=auto_assign_user_id,
        )
    return contact_id


def _update_existing_wa_contact(existing, wa_id, display_name, channel_id,
                                phone_number_id, source_channel_type,
                                auto_assign_user_id, from_message_event, now):
    """Aplica updates a um contato JA existente. Usado pelo caminho normal
    (achado por wa_id) e pelo fallback do claim atomico (corrida perdida).
    Retorna o contact_id."""
    updates = {}
    if from_message_event:
        updates["last_message_at"] = now
        updates["last_inbound_at"] = now
    # Canonizar wa_id do contato pra forma com 9 (Brasil pos-2012).
    # Se o contato foi achado via variante (ex: 12-dig sem 9 mas o
    # webhook chegou com 13-dig), o doc fica preso na forma antiga e
    # todas as conversations geradas a partir de contact.wa_id ficam
    # com conversation_id divergente do selectedThreadId do frontend.
    # Migra agora pra evitar threads orfas.
    existing_wa = str(existing.get("wa_id", ""))
    if existing_wa and existing_wa != wa_id:
        updates["wa_id"] = wa_id
        updates["phone_formatted"] = format_phone_br(wa_id)
        logger.info(
            "Contato %s migrado wa_id %s -> %s (nono digito BR)",
            existing["id"], existing_wa, wa_id,
        )
    # Atualizar whatsapp_profile_name do webhook sem sobrescrever declared_name
    if display_name:
        updates["whatsapp_profile_name"] = display_name
        # Recalcular display_name efetivo
        declared = existing.get("declared_name", "")
        updates["display_name"] = _resolve_display_name(
            declared, display_name, updates.get("phone_formatted") or existing.get("phone_formatted", ""),
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
    # Reflete wa_id canonizado no dict local pra _maybe_upsert_conversation
    # propagar a forma certa pra wa_conversations.
    if updates.get("wa_id"):
        existing = dict(existing)
        existing["wa_id"] = updates["wa_id"]
    # Garante que a conversation deste (channel, wa_id) tambem existe.
    # Pulado em state_sync — contato existe sem thread ate ter mensagem.
    if from_message_event:
        _maybe_upsert_conversation_for_existing_contact(
            existing, channel_id, source_channel_type, phone_number_id, auto_assign_user_id,
        )
    return existing["id"]


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
        "sale_owner_user_id": None,
        "sale_owner_uid": "",
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


def _enrich_and_sort_contacts(rows, include_archived=False):
    """Aplica filtro is_archived, ordena por last_message_at desc e enriquece
    com nome/role do operador e nome do departamento (batch, sem N+1).
    Compartilhado por get_all_wa_contacts e get_wa_contacts_visible_to."""
    rows = [row for row in rows if row]
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


def get_all_wa_contacts(include_archived=False):
    return _enrich_and_sort_contacts(_all_docs("wa_contacts"), include_archived=include_archived)


def get_wa_contacts_visible_to(user_id, department_id=None, role=None, include_archived=False):
    """Contatos visiveis a um usuario, com o mesmo enriquecimento/ordenacao de
    get_all_wa_contacts.

    Admin/supervisor enxergam todos. Operador comum ve apenas o proprio escopo
    (atribuidos a si ou sem dono/pool) — espelha as Firestore rules do caminho
    de snapshot e evita varrer/expor a agenda inteira do tenant (milhares de
    contatos da agenda coex) no fallback de polling do frontend. NAO inclui
    contatos de colegas do mesmo departamento (isolamento LGPD).
    """
    if role in ("admin", "supervisor"):
        rows = _all_docs("wa_contacts")
    else:
        rows = get_wa_contacts_scoped_for_user(user_id, department_id)
    return _enrich_and_sort_contacts(rows, include_archived=include_archived)


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


# ---------------------------------------------------------------------------
# Fase 5A — Protocolo de Atendimento (1 dia = 1 por Lead). Spec do PO:
# gerado silenciosamente no 1o inbound do dia; enviado ao cliente SO no
# fechamento do atendimento como "recibo"; flag protocolo_informado impede
# reenvio em retorno-zumbi no mesmo dia. Colecao tenant-scoped
# attendances_daily/{YYYYMMDD-{contact_id}-{SETOR}}. Espelha o id em
# wa_contacts.attendance_protocol p/ back-compat com o "Copiar protocolo".
# ---------------------------------------------------------------------------

_BR_TZ = timezone(timedelta(hours=-3))  # BR sem DST desde 2019; fixo -3.


def _today_br_str():
    """YYYYMMDD no horario do Brasil (granularidade do protocolo = dia BR)."""
    return datetime.now(_BR_TZ).strftime("%Y%m%d")


def _setor_code(department_id):
    """3 letras maiusculas ASCII do nome do departamento; fallback GERAL."""
    if not department_id:
        return "GERAL"
    dept = _get_doc("departments", department_id)
    if not dept:
        return "GERAL"
    name = (dept.get("name") or "").strip()
    if not name:
        return "GERAL"
    import unicodedata
    ascii_name = "".join(
        c for c in unicodedata.normalize("NFKD", name)
        if not unicodedata.combining(c)
    )
    letters = "".join(c for c in ascii_name if c.isalpha())[:3].upper()
    return letters or "GERAL"


def ensure_daily_attendance(contact_id, setor=None):
    """Get-or-create do Atendimento diario. Trigger: 1o inbound do dia (chamado
    de save_wa_message). Reabre se estava fechado PRESERVANDO
    protocolo_informado (regra do retorno-zumbi). Espelha o id em
    wa_contacts.attendance_protocol. Retorna o protocol_id ou None."""
    contact = _get_doc("wa_contacts", contact_id)
    if not contact:
        return None
    date_str = _today_br_str()
    if setor is None:
        setor = _setor_code(contact.get("department_id"))
    pid = f"{date_str}-{contact_id}-{setor}"
    now = utcnow()
    ref = document("attendances_daily", pid)
    snap = ref.get()
    if snap.exists:
        existing = snap.to_dict() or {}
        updates = {"ultima_interacao": now}
        if existing.get("status") != "aberto":
            # Retorno-zumbi: reabre status, NAO mexe em protocolo_informado.
            updates["status"] = "aberto"
            updates["fechado_em"] = None
            updates["fechado_por_user_id"] = None
        ref.set(updates, merge=True)
    else:
        ref.set({
            "id": pid,
            "contact_id": contact_id,
            "date": date_str,
            "setor": setor,
            "criado_em": now,
            "ultima_interacao": now,
            "status": "aberto",
            "protocolo_informado": False,
            "fechado_em": None,
            "fechado_por_user_id": None,
        })
    # Espelho no contato (back-compat com "Copiar protocolo" do menu).
    document("wa_contacts", contact_id).set(
        {"attendance_protocol": pid, "attendance_started_at": now}, merge=True,
    )
    return pid


def get_daily_attendance(protocol_id):
    """Le o Atendimento diario pelo id ou None."""
    snap = document("attendances_daily", protocol_id).get()
    if not snap.exists:
        return None
    data = snap.to_dict() or {}
    if "id" not in data:
        data["id"] = protocol_id
    return data


def close_daily_attendance(protocol_id, status, closed_by_user_id=None):
    """status: 'fechado_manual' ou 'fechado_inatividade'. Idempotente."""
    document("attendances_daily", protocol_id).set({
        "status": status,
        "fechado_em": utcnow(),
        "fechado_por_user_id": closed_by_user_id,
    }, merge=True)


def mark_protocol_informed(protocol_id):
    """Sinaliza que o protocolo ja foi enviado ao cliente (semaforo do
    retorno-zumbi). Idempotente."""
    document("attendances_daily", protocol_id).set(
        {"protocolo_informado": True}, merge=True,
    )


def get_current_protocol_id(contact_id):
    """Retorna o protocol_id de hoje do contato SE existe (sem criar) —
    usado p/ denorm de protocol_id em mensagens outbound/internal/system."""
    contact = _get_doc("wa_contacts", contact_id)
    if not contact:
        return None
    pid = contact.get("attendance_protocol") or ""
    today = _today_br_str()
    if pid and pid.startswith(today + "-"):
        return pid
    return None


def get_messages_by_protocol(protocol_id):
    """Mensagens denormalizadas pelo protocol_id (Fase 5A: busca admin/sup).
    Ordena por timestamp_wa ascendente."""
    rows = []
    for snap in collection("wa_messages").where("protocol_id", "==", protocol_id).stream():
        data = snap.to_dict() or {}
        rows.append(data)
    rows.sort(key=lambda r: str(r.get("timestamp_wa") or r.get("created_at") or ""))
    return _normalize_many(rows)


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
        "is_backup": False,  # reatribuir o Lead gradua o contato (sai do Backup)
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


def set_sale_owner(contact_id, user_id):
    """Define/atualiza a 'dona de origem' (sale_owner) do lead — a vendedora a
    quem o lead 'gruda'. Gravada na 1a assuncao; handoff entre operadores NAO
    altera (so o assume inicial e o reassign-lead do admin/supervisor gravam).
    E metadado de roteamento: NAO participa do isolamento/escopo (so
    assigned_to_uid faz). Grava o uid denormalizado p/ o revert no fechamento.
    """
    to_user = _get_doc("users", user_id) if user_id else None
    document("wa_contacts", contact_id).set({
        "sale_owner_user_id": user_id,
        "sale_owner_uid": (to_user or {}).get("firebase_uid", ""),
    }, merge=True)
    return to_user


def revert_lead_to_sale_owner(contact_id):
    """No fechamento do atendimento, o Dono do Lead (contato) volta p/ a dona de
    origem (sale_owner). Reverte o CONTATO aqui e RETORNA {assigned_to,
    assigned_to_uid} p/ o caller reverter tambem o Dono do Atendimento (a
    conversa fechada) — assim, ao reabrir no proximo contato, a conversa ja e da
    vendedora que assumiu (prioridade da venda).

    Salvaguardas: se NAO houver sale_owner (lead nunca assumido) ou ela estiver
    inativa/deletada, retorna None e NAO mexe — nunca inventa dono nem gruda
    lead/atendimento em conta morta (ficaria orfa invisivel). Idempotente.
    """
    if contact_id is None:
        return None
    contact = _get_doc("wa_contacts", contact_id)
    if not contact:
        return None
    owner_id = contact.get("sale_owner_user_id")
    if not owner_id:
        return None  # sem dona de origem -> mantem como esta (pool fica pool)
    owner = _get_doc("users", owner_id)
    if not owner or not owner.get("is_active", 1):
        return None  # dona inativa/deletada -> nao restaura
    fields = {"assigned_to": owner_id, "assigned_to_uid": owner.get("firebase_uid", "")}
    if contact.get("assigned_to") != owner_id:
        document("wa_contacts", contact_id).set(fields, merge=True)  # Dono do Lead
    return fields


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


def get_wa_contacts_scoped_for_user(user_id, department_id=None):
    """Contatos visiveis a um operador comum — espelha canSeeContactScoped
    (firestore.rules) e buildContactSnapshotTargets (frontend): atribuidos
    a si OU sem atribuicao (pool/fila).

    NAO inclui mais o departamento. A query por department_id vazava a agenda
    pessoal (coexistence) de um operador para todos os colegas do mesmo
    departamento — quebra de isolamento LGPD (ex.: agenda da aline visivel
    p/ danielle). `department_id` mantido na assinatura por compat com os
    callers, mas ignorado de proposito.

    Usa queries de igualdade (sem orderBy) — nao exige indice composto e
    evita varrer a colecao inteira do tenant. Dedup por doc id. Retorna dicts
    crus normalizados; o caller aplica filtro is_archived / busca / ordenacao.
    """
    col = collection("wa_contacts")
    seen = {}

    def _collect(query):
        for snapshot in query.stream():
            data = snapshot.to_dict() or {}
            # Backup nunca visivel a operador comum (defesa; o sentinela
            # "__backup__" ja impede que caia nas queries de pool/proprios).
            if not data or data.get("is_backup"):
                continue
            data.setdefault("id", snapshot.id)
            seen[snapshot.id] = data

    if user_id is not None:
        _collect(col.where("assigned_to", "==", user_id))
    # Sem atribuicao (campo "" ou None) — pool/fila visivel a qualquer operador.
    _collect(col.where("assigned_to_uid", "==", ""))
    _collect(col.where("assigned_to_uid", "==", None))
    # department_id intencionalmente NAO consultado (isolamento LGPD acima).

    return [normalize_record(dict(row)) for row in seen.values()]


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


def insert_internal_note(contact_id, content, sender_user_id, conversation_id=None, channel_id=None):
    """Modo 1 (Sussurro): nota interna na thread. Salva como
    direction='internal' — aparece pro operador/managers no chat, NUNCA vai
    pra Meta (o save nao envia) nem conta janela 24h / unread do cliente.
    id sintetico (sem wa_message_id da Meta)."""
    return save_wa_message(
        wa_message_id=f"int_{utcnow().isoformat()}_{contact_id}",
        contact_id=contact_id,
        direction="internal",
        msg_type="internal",
        content=content,
        status="delivered",
        timestamp_wa=utcnow().isoformat(),
        operator_id=sender_user_id,
        sender_user_id=sender_user_id,
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

    # Anti-duplicata ATOMICO (rajada/concorrencia/reentrega): claim do wamid num
    # doc-indice (doc id = wamid sanitizado). document().create() falha se ja
    # existe — primitiva atomica, imune ao lag de query que deixava 2 entregas
    # concorrentes do mesmo wamid passarem ambas pelo query-miss acima e criarem
    # 2 docs. Espelha wa_contact_index. So p/ wamid real (local_/system tem id
    # unico via next_sequence, sem corrida).
    if wa_message_id:
        _idx_key = str(wa_message_id).replace("/", "_").replace("\\", "_")
        _idx_ref = document("wa_message_index", _idx_key)
        try:
            _idx_ref.create({"message_id": message_id, "created_at": created_at})
        except gcloud_exceptions.AlreadyExists:
            # Entrega concorrente ja reivindicou este wamid -> retorna o vencedor
            # (get por id e fortemente consistente; retry curto p/ a janela ms
            # entre claim e gravacao do doc). NAO recria nem re-roda protocolo/
            # metricas/conversation.
            _winner_mid = (_idx_ref.get().to_dict() or {}).get("message_id")
            for _ in range(5):
                if _winner_mid is not None and _get_doc("wa_messages", _winner_mid):
                    return _winner_mid
                time.sleep(0.1)
            # Vencedor ainda nao visivel (lag extremo) — segue criando com o
            # message_id ja alocado; a query-dedup do proximo evento reconcilia.

    contact = _get_doc("wa_contacts", contact_id)
    # Resolve channel/wa_id efetivos pra calcular conversation_id
    eff_channel_id = channel_id if channel_id is not None else (contact or {}).get("channel_id")
    eff_wa_id = (contact or {}).get("wa_id", "")
    eff_phone_number_id = phone_number_id or (contact or {}).get("phone_number_id", "")
    if conversation_id:
        eff_conversation_id = conversation_id
    else:
        try:
            eff_conversation_id = _make_conversation_id(eff_channel_id, eff_wa_id)
        except ConversationIdError as exc:
            # Mensagem que nao pode ter conversation_id deterministico
            # ficaria invisivel pro frontend (filtra por selectedThreadId).
            # Quem nos chama (webhook) deve enfileirar em
            # pending_webhook_events. Mensagens system internas (transfer,
            # etc.) podem pular o filtro com direction='system'.
            if direction != "system":
                logger.error(
                    "save_wa_message abortado: %s | contact=%s direction=%s",
                    exc, contact_id, direction,
                )
                raise
            eff_conversation_id = None
    # Fase 5A: denorm do protocol_id (1 dia = 1 por Lead). Inbound dispara o
    # ensure (cria/reabre o Atendimento diario); outras direcoes leem o
    # atual sem criar.
    protocol_id = None
    if contact_id is not None:
        if direction == "inbound":
            try:
                protocol_id = ensure_daily_attendance(contact_id)
            except Exception as exc:
                logger.warning("ensure_daily_attendance falhou contact=%s: %s", contact_id, exc)
        else:
            try:
                protocol_id = get_current_protocol_id(contact_id)
            except Exception:
                protocol_id = None
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
        "protocol_id": protocol_id,
        "is_rating_message": is_rating_message,
        "visibility": visibility,
        "timestamp_wa": _coerce_timestamp(timestamp_wa),
        "created_at": created_at,
        "reply_to_message_id": reply_to_message_id,
        "reply_to_preview": reply_to_preview or "",
        "reply_to_sender_name": reply_to_sender_name or "",
    })

    if contact:
        # Data REAL da mensagem (timestamp_wa) — replay de history/backup nao
        # pode "subir" o contato na sidebar com a data da gravacao. Monotonico:
        # so avanca (mensagem ao vivo sempre avanca; replay antigo nao recua).
        _eff_msg_at = _coerce_timestamp(timestamp_wa)
        if not isinstance(_eff_msg_at, datetime):
            _eff_msg_at = created_at
        _cur_lma = _coerce_timestamp(contact.get("last_message_at"))
        try:
            _lma_advances = not isinstance(_cur_lma, datetime) or _eff_msg_at >= _cur_lma
        except TypeError:
            _lma_advances = True
        updates = {"last_message_at": _eff_msg_at} if _lma_advances else {}
        if direction == "inbound" and status == "received":
            updates["unread_count"] = int(contact.get("unread_count", 0)) + 1
        if updates:
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
                    # Conversa herda o Dono do Lead (contact.assigned_to). O guard
                    # de orfa em upsert_wa_conversation (so atribui se a thread NAO
                    # tem dono) garante que isto nunca pisa em transferencia de
                    # thread nem em takeover ativo. [LGPD: thread orfa e legivel
                    # por qualquer operador via canSeeContactScoped; herdar o dono
                    # fecha esse vetor].
                    auto_assign_user_id=(contact or {}).get("assigned_to"),
                    message_at=_eff_msg_at,
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


def get_wa_conversation(contact_id, limit=50, offset=0, conversation_id=None):
    """Retorna mensagens do contato em ordem cronologica real.

    Ordena por `timestamp_wa` (quando a mensagem realmente aconteceu),
    nao `created_at` (quando foi salva). Critico pro history sync —
    mensagens antigas chegam horas/dias depois mas devem aparecer no
    fundo da timeline, nao no topo.

    Se conversation_id for passado, filtra apenas a thread (canal+wa_id)
    correspondente — preserva isolamento entre canais (coexistence vs
    standard) que o filtro legado por contact_id misturava.
    """
    q = collection("wa_messages").where("contact_id", "==", contact_id)
    if conversation_id:
        q = q.where("conversation_id", "==", conversation_id)
    q = q.order_by("timestamp_wa", direction="DESCENDING")
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
    # Atualiza o status vigente na propria mensagem. A colecao-historico
    # wa_message_status foi descontinuada: era write-only (sem leitor em
    # backend/scripts/frontend) e cada webhook de status (sent/delivered/
    # read) custava +1 transacao next_sequence +1 escrita — mesmo padrao de
    # contencao de contador do incidente do audit_log, multiplicado por ~3x
    # por mensagem enviada. Transicoes detalhadas, quando necessarias, ficam
    # disponiveis via GET /{Message-History-ID}/events da Graph API.
    target = _get_first_by_field("wa_messages", "wa_message_id", wa_message_id)
    if target:
        document("wa_messages", target["id"]).set({"status": status}, merge=True)


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
    # ID auto-gerado pelo Firestore (nao sequencial). O contador via
    # next_sequence() era um documento unico e virava hotspot de escrita:
    # sob rajada de requests a transacao abortava por contencao (409) e
    # estourava 500. O id do audit nunca e lido como sequencial em lugar
    # algum, entao doc-id automatico remove o hotspot.
    # Best-effort: uma falha de auditoria nunca deve derrubar o request que
    # a originou — loga warning e segue.
    try:
        ref = collection("audit_log").document()
        ref.set({
            "id": ref.id,
            "user_id": user_id,
            "action": action,
            "detail": detail or "",
            "ip_address": ip_address or "",
            "created_at": utcnow(),
        })
    except Exception:
        logger.warning(
            "log_audit falhou (nao-fatal): action=%s user_id=%s",
            action, user_id, exc_info=True,
        )


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
# Importacao de backup (caixa "Backup" — historico de conversas)
# ---------------------------------------------------------------------------
# Sentinela do dono: mantem conversas/contatos de backup FORA do pool do
# operador (snapshot target == '' e rule canSeeContactScoped), visiveis so a
# admin/supervisor (via aba Backup). NUNCA usar como uid real de um usuario.
BACKUP_ASSIGNED_UID = "__backup__"


def create_backup_contact(wa_id, display_name, channel_id, first_seen_at, last_ts=None):
    """Cria um contato HISTORICO (backup). NAO usa upsert_wa_contact (que dispara
    timestamps/conversation ao vivo). Se ja existir contato (vivo) p/ o wa_id,
    reusa SEM rebaixar p/ backup. Retorna contact_id."""
    wa_id = normalize_br_phone(wa_id)
    existing = _find_contact_by_wa_id_any_variant(wa_id)
    if existing:
        return existing["id"]  # contato vivo/ja importado — nao mexe
    phone_formatted = format_phone_br(wa_id)
    contact_id = next_sequence("wa_contacts")
    new_contact = {
        "id": contact_id,
        "wa_id": wa_id,
        "display_name": _resolve_display_name("", display_name, phone_formatted),
        "declared_name": "",
        "whatsapp_profile_name": display_name or "",
        "created_source": "backup_import",
        "created_by_user_id": None,
        "phone_formatted": phone_formatted,
        "profile_picture_url": "",
        "contact_avatar_path": "",
        "qualification": "novo",
        "notes": "",
        "assigned_to": None,
        "assigned_to_uid": BACKUP_ASSIGNED_UID,
        "department_id": None,
        "channel_id": channel_id,
        "phone_number_id": "",
        "source_channel_type": "standard",
        "original_operator_id": None,
        "sale_owner_user_id": None,
        "sale_owner_uid": "",
        "converted_by_user_id": None,
        "rating": None,
        "rating_requested_at": None,
        "is_archived": 0,
        "unread_count": 0,
        "is_backup": True,
        "first_seen_at": first_seen_at,
        "last_message_at": last_ts,
        "last_inbound_at": None,
    }
    idx_ref = document("wa_contact_index", wa_id)
    try:
        idx_ref.create({"contact_id": contact_id, "created_at": utcnow()})
    except gcloud_exceptions.AlreadyExists:
        return (idx_ref.get().to_dict() or {}).get("contact_id")
    document("wa_contacts", contact_id).set(new_contact)
    return contact_id


def upsert_backup_conversation(conversation_id, contact_id, wa_id, channel_id,
                               first_ts, last_ts, last_in, last_out, channel_label=""):
    """Cria a conversa HISTORICA (backup): is_backup + sentinela, NUNCA 'aberto',
    read-only (channel_active=False). Se a conversa ja existe e NAO e backup
    (thread viva), NAO rebaixa. Idempotente."""
    wa_id = normalize_br_phone(wa_id)
    ref = document("wa_conversations", conversation_id)
    snap = ref.get()
    if snap.exists:
        return conversation_id  # ja existe (backup ou viva) — nao mexe
    ref.set({
        "id": conversation_id,
        "contact_id": contact_id,
        "wa_id": wa_id,
        "channel_id": channel_id,
        "phone_number_id": "",
        "source_channel_type": "standard",
        "assigned_to": None,
        "assigned_to_uid": BACKUP_ASSIGNED_UID,
        "department_id": None,
        "unread_count": 0,
        "status": "open",
        "attendance_status": "fechado_inatividade",  # NUNCA 'aberto' (sem auto-close/protocolo)
        "is_backup": True,
        "channel_label": channel_label or "Backup (historico)",
        "channel_active": False,  # read-only ate o cliente voltar / ser atribuido
        "created_at": first_ts,
        "last_message_at": last_ts,
        "last_inbound_at": last_in,
        "last_outbound_at": last_out,
    })
    return conversation_id


def write_backup_message(wa_message_id, contact_id, conversation_id, direction,
                         msg_type, content, timestamp_wa, channel_id,
                         media_path="", media_mime="", filename="", status="read"):
    """Grava mensagem HISTORICA (backup). NAO dispara protocolo, metricas, unread
    nem reabre atendimento. Denormaliza is_backup + sentinela na propria msg p/
    fechar o Vetor B (rule de wa_messages). Idempotente por wa_message_id."""
    if wa_message_id:
        existing = _get_first_by_field("wa_messages", "wa_message_id", wa_message_id)
        if existing:
            return existing["id"]
    message_id = next_sequence("wa_messages")
    ts = _coerce_timestamp(timestamp_wa)
    document("wa_messages", message_id).set({
        "id": message_id,
        "wa_message_id": wa_message_id or f"local_{message_id}",
        "contact_id": contact_id,
        "contact_doc_id": str(contact_id),
        "conversation_id": conversation_id,
        "direction": direction,
        "msg_type": msg_type,
        "content": content or "",
        "media_path": media_path or "",
        "media_mime": media_mime or "",
        "media_id": "",
        "latitude": None,
        "longitude": None,
        "filename": filename or "",
        "status": status,
        "operator_id": None,
        "sender_user_id": None,
        "channel_owner_user_id": None,
        "assigned_to": None,
        "assigned_to_uid": BACKUP_ASSIGNED_UID,
        "department_id": None,
        "channel_id": channel_id,
        "phone_number_id": "",
        "protocol_id": None,
        "is_rating_message": False,
        "visibility": "all",
        "is_backup": True,
        "timestamp_wa": ts,
        "created_at": ts or utcnow(),
        "reply_to_message_id": None,
        "reply_to_preview": "",
        "reply_to_sender_name": "",
    })
    return message_id


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
