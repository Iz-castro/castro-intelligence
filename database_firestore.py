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
from rbac import default_perfil_for_role

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
        "perfil_acesso_id": user.get("perfil_acesso_id")
            or default_perfil_for_role(user.get("role", "operador")),
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


def get_user_raw_by_firebase_uid_or_email(firebase_uid, email):
    """Lookup RAW (SEM filtro is_active) por firebase_uid e depois por email.

    Offboarding (M-A4b): get_user_by_* filtram is_active, entao um doc
    DESATIVADO aparece como "inexistente" e um login com AUTO_PROVISION o
    ressuscitaria como doc NOVO ativo, re-emitindo o claim e anulando a
    desativacao. Este lookup enxerga o desativado para o login poder NEGAR.
    Retorna o doc normalizado (com is_active) ou None.
    """
    row = None
    if firebase_uid:
        row = _get_first_by_field("users", "firebase_uid", firebase_uid)
    if not row and email:
        row = _get_first_by_field("users", "email", email.strip().lower())
    return normalize_record(row) if row else None


def get_user_raw_by_id(user_id):
    """Doc do usuario SEM filtro is_active (get_user_by_id filtra desativados).

    Usado no offboarding idempotente (M-A4b): agir sobre um usuario JA
    desativado (repetir DELETE re-tenta clear/revoke em vez de 404).
    """
    row = _get_doc("users", user_id)
    return normalize_record(row) if row else None


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
        "perfil_acesso_id": row.get("perfil_acesso_id", ""),
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
        "perfil_acesso_id": default_perfil_for_role(role),
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


def update_user(user_id, display_name=None, department_id=None, role=None, perfil_acesso_id=None):
    fields = {}
    if display_name is not None:
        fields["display_name"] = display_name
    if department_id is not None:
        fields["department_id"] = department_id if department_id else None
    if role is not None:
        fields["role"] = role
        if perfil_acesso_id is None:
            # Re-alinha o perfil ao seed APENAS quando a role de fato MUDA
            # (ex-admin rebaixado nao pode manter perfil_admin). Payload que
            # apenas ECOA a role atual (UI sempre envia role; bootstrap
            # re-passa a cada boot) NAO pode resetar um perfil customizado —
            # seria downgrade silencioso sem audit a cada edicao/deploy.
            existing = _get_doc("users", user_id)
            if existing is not None and existing.get("role") != role:
                fields["perfil_acesso_id"] = default_perfil_for_role(role)
    if perfil_acesso_id is not None:
        fields["perfil_acesso_id"] = perfil_acesso_id
    if not fields:
        return False
    document("users", user_id).set(fields, merge=True)
    updated = _get_doc("users", user_id)
    if updated:
        _sync_operator_profile_from_user(updated)
    return True


def backfill_perfil_acesso_ids():
    """Preenche users.perfil_acesso_id derivado da role onde falta (M-B2
    fase 1). Idempotente: escreve apenas docs sem o campo; ajustes manuais
    de perfil nunca sao sobrescritos. Roda no bootstrap do tenant.

    Sem log_audit por usuario de proposito: o campo derivado e identico ao
    fallback de role do dual-check — permissao EFETIVA de ninguem muda."""
    updated = 0
    for row in _all_docs("users"):
        if not row or row.get("perfil_acesso_id"):
            continue
        perfil_id = default_perfil_for_role(row.get("role", "operador"))
        if not perfil_id:
            continue
        document("users", row["id"]).set({"perfil_acesso_id": perfil_id}, merge=True)
        # Espelha sem re-ler: a unica mudanca e o campo recem-derivado.
        row = dict(row)
        row["perfil_acesso_id"] = perfil_id
        _sync_operator_profile_from_user(row)
        updated += 1
    if updated:
        logger.info("Backfill perfil_acesso_id | users=%d", updated)
    return updated


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
    advance_recency=True,
    human_outbound_at=None,
    reopen_attendance=True,
):
    """Cria ou atualiza a conversation correspondente a (channel_id, wa_id).

    reopen_attendance=False: NAO aplica a regra "atividade reabre atendimento
    fechado" — uso do recibo de fechamento (revisao 2026-09-01: o proprio
    recibo outbound reabria o attendance_status que o request acabou de
    fechar) e de cliques de controle (avaliacao).

    Retorna conversation_id (string deterministica). Se a conversation
    ja existe, atualiza last_message_at e demais timestamps, alem de
    auto-assign quando aplicavel.

    direction_for_unread: 'inbound' incrementa unread_count, outras
    direcoes nao mexem. None nao mexe (uso pelo upsert_wa_contact).

    message_at: data REAL da mensagem (timestamp_wa). Replay de history/
    backup chega horas/meses depois — sem isto a conversa "sobe" pro topo
    da sidebar com a data da gravacao. last_message_at e monotonico: so
    avanca, nunca recua.

    human_outbound_at: data da mensagem quando ela foi enviada por um OPERADOR
    (outbound com sender_user_id). Carimba last_human_outbound_at, que o
    auto-close usa pra saber se a thread da pool ja teve resposta humana neste
    ciclo — ver _reception_handoff_unattended. Mensagem do bot nao passa por
    aqui (last_outbound_at sobe com bot tambem, por isso o campo separado).

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
        if _advances and advance_recency:
            updates["last_message_at"] = msg_at
        if direction_for_unread == "inbound":
            updates["last_inbound_at"] = msg_at
            updates["unread_count"] = int(existing.get("unread_count", 0)) + 1
        elif direction_for_unread == "outbound":
            updates["last_outbound_at"] = msg_at
        if human_outbound_at is not None:
            updates["last_human_outbound_at"] = human_outbound_at
        if direction_for_unread in ("inbound", "outbound") and reopen_attendance:
            # Atividade reabre um atendimento fechado (Fase 4 — ciclo de vida).
            # reopen_attendance=False: recibo de fechamento e cliques de
            # controle nao sao "atividade" (revisao 2026-09-01).
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
        # Ciclo de atendimento da pool (Modo Recepcao): handoff_at e gravado
        # pelo bot no handoff; last_human_outbound_at, por envio de operador.
        "handoff_at": None,
        "last_human_outbound_at": human_outbound_at,
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


def _graduate_backup_messages(conversation_id, owner_uid=""):
    """Gradua as mensagens historicas (is_backup=True) de uma conversa que saiu
    do Backup: vira is_backup=False + carimba o dono, para o novo dono conseguir
    ler (a rule de wa_messages bloqueia is_backup p/ nao-privilegiado). Backup
    NAO graduado (parado na caixa) fica is_backup=True -> segue admin-only.
    Idempotente. Retorna a quantidade graduada."""
    if not conversation_id:
        return 0
    batch = get_firestore_client().batch()
    count = 0
    total = 0
    for snapshot in collection("wa_messages").where("conversation_id", "==", conversation_id).stream():
        d = snapshot.to_dict() or {}
        if not d.get("is_backup"):
            continue
        batch.set(snapshot.reference, {"is_backup": False, "assigned_to_uid": owner_uid or ""}, merge=True)
        count += 1
        total += 1
        if count >= 400:
            batch.commit()
            batch = get_firestore_client().batch()
            count = 0
    if count > 0:
        batch.commit()
    return total


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
        # Badge de transferencia: bumpa o unread da thread p/ o novo dono ver
        # que ha algo a tratar, mesmo sem msg nova do cliente. Acende os DOIS
        # badges (a bolinha da conversa le unread_count; a aba "Meus" soma os
        # unread_count das conversas dela). Limpa no mark-read ao abrir.
        "unread_count": int(conv.get("unread_count", 0) or 0) + 1,
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
    # Graduacao completa: as mensagens historicas (is_backup) da conversa tambem
    # saem do gate admin-only, senao o novo dono abre a thread e ve zero
    # historico (rule de wa_messages bloqueia is_backup p/ nao-privilegiado).
    if was_backup:
        _graduate_backup_messages(conversation_id, (to_user or {}).get("firebase_uid", ""))

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


def _reception_handoff_unattended(conv, unattended_release_days):
    """True se a thread da pool ainda espera o PRIMEIRO atendimento humano do
    ciclo aberto pelo handoff do bot — nesse caso o auto-close NAO fecha.

    Por que: em reception, fechar devolve o lead ao agente de IA
    (release_lead_to_bot), que zera bot_completed. O filtro da aba Recepcao
    EXIGE bot_completed, e a aba Bot so e renderizada pra admin/supervisor —
    entao a thread sumia da fila de quem atende. Lead que chegava no fim de
    semana ficava invisivel na segunda e a Val o atendia do zero, como se o
    handoff nunca tivesse acontecido (incidente 2026-08-09).

    Ciclo detectado por COMPARACAO de timestamps, sem reset: um handoff novo
    grava um handoff_at mais recente e invalida sozinho o carimbo humano do
    ciclo anterior (lead atendido -> devolvido ao bot -> voltou a conversar ->
    handoff de novo fica protegido). Zerar last_human_outbound_at exigiria
    acertar TODOS os pontos de fim de ciclo (release_lead_to_bot,
    return_contact_to_bot, bulk-reassign, fechamento manual) — esquecer um
    seria landmine silenciosa.

    Degrada pro comportamento anterior (False = pode fechar) em qualquer
    duvida: doc legado sem handoff_at, timestamp corrompido, ou espera acima
    do teto — lead morto nao pode ficar preso em bot_completed=True pra
    sempre, senao o bot nunca mais responde e ninguem sabe que ele existe."""
    handoff_at = _coerce_timestamp(conv.get("handoff_at"))
    if not isinstance(handoff_at, datetime):
        return False
    human_at = _coerce_timestamp(conv.get("last_human_outbound_at"))
    if isinstance(human_at, datetime):
        try:
            if human_at > handoff_at:
                return False  # ja teve resposta humana NESTE ciclo
        except TypeError:
            return False  # naive vs aware: nao segura a thread por duvida
    try:
        if (utcnow() - handoff_at) > timedelta(days=unattended_release_days):
            return False  # teto: espera longa demais, devolve pro bot
    except TypeError:
        return False
    return True


def _reception_unattended_release_due(conv, unattended_release_days):
    """True quando a VALVULA do Modo Recepcao deve soltar a thread: handoff
    que NUNCA teve resposta humana e cuja espera estourou o teto de dias.

    Complemento de _reception_handoff_unattended, usado quando o fechamento
    por inatividade esta desligado (auto_close_enabled=False): nesse modo SO
    o orfao estourado fecha (decisao do PO 2026-09-01 — thread atendida nunca
    fecha sozinha, mas lead morto nao pode ficar preso em bot_completed=True
    pra sempre). Em duvida (sem handoff_at, timestamp corrompido) retorna
    False = nao fecha, o conservador quando a inatividade esta OFF."""
    handoff_at = _coerce_timestamp(conv.get("handoff_at"))
    if not isinstance(handoff_at, datetime):
        return False
    human_at = _coerce_timestamp(conv.get("last_human_outbound_at"))
    if isinstance(human_at, datetime):
        try:
            if human_at > handoff_at:
                return False  # ja teve resposta humana neste ciclo
        except TypeError:
            return False
    try:
        return (utcnow() - handoff_at) > timedelta(days=unattended_release_days)
    except TypeError:
        return False


def close_stale_attendances(max_idle_hours, unattended_release_days=7,
                            inactivity_enabled=True):
    """Fecha (attendance_status='fechado_inatividade') atendimentos ATRIBUIDOS
    ociosos ha mais de max_idle_hours (sem mensagem). Reabre sozinho na proxima
    mensagem (upsert_wa_conversation). Opera no tenant_context atual. Retorna
    lista de {conversation_id, contact_id, assigned_to}. (Fase 4.)

    unattended_release_days: teto da espera por atendimento humano no Modo
    Recepcao (ver _reception_handoff_unattended). O cron passa o valor de
    config (RECEPTION_UNATTENDED_RELEASE_DAYS); o default aqui so cobre caller
    que nao passa (simuladores).

    inactivity_enabled: toggle por tenant (system_settings.auto_close_enabled,
    lido pelo cron via is_auto_close_enabled). False = fechamento por
    inatividade DESLIGADO: thread com dono nunca fecha, thread da pool so
    fecha se for orfao estourado (_reception_unattended_release_due) — a
    valvula continua ativa por decisao do PO 2026-09-01."""
    from datetime import timedelta
    cutoff = utcnow() - timedelta(hours=max_idle_hours)
    closed = []
    # Filtro server-side attendance_status == "aberto": exclui backups
    # (fechado_inatividade) e ja-fechados (fechado_*), cortando a leitura de
    # ~toda a colecao (full scan que rodava a cada 30min no cron) para so os
    # atendimentos abertos. Igualdade em campo string -> indice single-field
    # automatico, sem indice composto. assigned_to e last_message_at continuam
    # filtrados em Python: assigned_to pra evitar 2o campo no indice;
    # last_message_at porque pode estar como str OU Timestamp em docs
    # legados/backup, e um range server-side erraria por tipo.
    # NOTA: docs abertos SEM o campo attendance_status (legado pre-Fase 4) nao
    # entram mais aqui — recebem o campo (e voltam a ser elegiveis) na proxima
    # mensagem via upsert_wa_conversation.
    # Modo Recepcao (ADR 0010): threads da POOL (sem dono, bot finalizado)
    # tambem fecham por inatividade — senao nunca fecham e o protocolo nunca
    # sai. Thread ainda no fluxo do bot continua fora (fila/bot nao fecham).
    _reception = is_reception_mode()
    for snap in collection("wa_conversations").where("attendance_status", "==", "aberto").stream():
        conv = snap.to_dict() or {}
        if not conv.get("assigned_to") and not _reception:
            continue  # so atendimentos atribuidos (fila/bot nao fecham)
        if conv.get("assigned_to") and not inactivity_enabled:
            # Toggle do tenant OFF: atendimento com dono so fecha pela
            # VALVULA — handoff que NUNCA teve resposta humana e estourou o
            # teto. "Assumir" sem responder NAO e atendimento (revisao
            # 2026-09-01: sem esta excecao o lead assumido-e-abandonado
            # ficava preso pra sempre — bot mudo, dono ausente, sem caminho
            # automatico de volta). Release_due primeiro: e so timestamp,
            # nao gasta read; o contato so e lido no candidato real.
            if (not _reception or conv.get("is_backup")
                    or not _reception_unattended_release_due(conv, unattended_release_days)):
                continue
            _ctc_v = _get_doc("wa_contacts", conv.get("contact_id")) if conv.get("contact_id") is not None else None
            if not _ctc_v or not _ctc_v.get("bot_completed"):
                continue
            # Cai no fluxo normal (stale check + fechamento/release).
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
        if not conv.get("assigned_to"):
            # Reception: so fecha thread da pool com bot ja finalizado (le o
            # contato apenas dos candidatos stale — 1 read por candidato).
            if conv.get("is_backup"):
                continue
            _ctc = _get_doc("wa_contacts", conv.get("contact_id")) if conv.get("contact_id") is not None else None
            if not _ctc or not _ctc.get("bot_completed"):
                continue
            # Handoff que NINGUEM atendeu nao fecha: fechar devolveria o lead
            # ao bot e sumiria com ele da aba Recepcao (ver helper). A thread
            # segue "aberto" na pool ate alguem responder ou estourar o teto.
            if _reception_handoff_unattended(conv, unattended_release_days):
                continue
            if not inactivity_enabled and not _reception_unattended_release_due(conv, unattended_release_days):
                # Toggle OFF: thread da pool ja atendida (ou sem handoff
                # rastreavel) nao fecha por inatividade; so a valvula age.
                continue
        # Mesma regra do fechamento manual: legacy reverte pro sale_owner;
        # reception devolve o lead ao agente de IA (release_lead_to_bot).
        _owner_fields = None
        if _reception:
            _owner_fields = release_lead_to_bot(conv.get("contact_id"), cid, "fechado_inatividade")
        if _owner_fields is None:
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
    # Fechamento -> legacy: lead+conversa voltam p/ a dona de origem
    # (sale_owner, ADR 0008). Reception (ADR 0010, PO 2026-08-05): lead
    # volta pro AGENTE DE IA (release_lead_to_bot) — manual e cron.
    if str(status).startswith("fechado"):
        _owner_fields = None
        if not conv.get("is_backup") and is_reception_mode():
            _owner_fields = release_lead_to_bot(conv.get("contact_id"), conversation_id, status)
        if _owner_fields is None:
            _owner_fields = revert_lead_to_sale_owner(conv.get("contact_id"))
        if _owner_fields:
            updates.update(_owner_fields)
    document("wa_conversations", conversation_id).set(updates, merge=True)
    return get_wa_conversation_by_id(conversation_id)


def mark_wa_conversation_read_by_id(conversation_id, contact_id=None):
    """Marca como lidas as mensagens inbound de uma conversation especifica.
    Usa filtro por conversation_id (Fase 2C) — nao colide entre threads do
    mesmo contato em canais diferentes. `contact_id` (opcional) evita reler
    o doc da conversa so pra achar o contato (ADR 0011: resync do contato)."""
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
    # Contador do CONTATO e DERIVADO das threads: re-sincroniza aqui. Antes so
    # a conversation zerava e wa_contacts.unread_count ficava preso pra sempre
    # (so o endpoint legado por contato zerava) — beep/alarme do frontend liam
    # esse campo e tocavam sem nada na tela (diagnostico 2026-08-21, 1.691
    # contatos presos no hubloc). Nao-fatal: o read da thread ja valeu.
    try:
        if contact_id is None:
            conv = _get_doc("wa_conversations", conversation_id)
            contact_id = (conv or {}).get("contact_id")
        if contact_id is not None:
            recompute_wa_contact_unread(int(contact_id))
    except Exception as exc:
        # Sem conversation_id no log: ele embute o wa_id (telefone) do cliente.
        logger.warning("mark_wa_conversation_read_by_id: resync do contato falhou contact_id=%s: %s", contact_id, exc)
    return total_updated


def recompute_wa_contact_unread(contact_id, current=None):
    """Recalcula wa_contacts.unread_count como a SOMA do unread_count das
    threads (wa_conversations) do contato e grava se mudou (ADR 0011).

    Fonte da verdade do nao-lido = THREAD (e o que o badge da sidebar le).
    O campo do contato existe por compat (resposta de /api/wa/contacts,
    endpoint legado por contato) e NAO pode divergir das threads: inbound
    incrementa os dois, read por thread zera a thread e chama isto.
    `current` = valor atual ja conhecido pelo chamador (evita 1 read).
    Contato inexistente: nao cria doc fantasma. Retorna o total calculado.
    """
    total = 0
    for snapshot in collection("wa_conversations").where("contact_id", "==", contact_id).stream():
        row = snapshot.to_dict() or {}
        total += int(row.get("unread_count", 0) or 0)
    if current is None:
        doc = _get_doc("wa_contacts", contact_id)
        if not doc:
            return total
        current = int(doc.get("unread_count", 0) or 0)
    if int(current) != total:
        # Write so quando muda: write custa ~3x read e re-publica o doc em
        # todo listener cujo target casa (pool = todos os operadores).
        document("wa_contacts", contact_id).set({"unread_count": total}, merge=True)
    return total


def upsert_wa_contact(wa_id, display_name="", channel_id=None,
                      phone_number_id="", source_channel_type="",
                      auto_assign_user_id=None,
                      from_message_event=True,
                      skip_conversation_upsert=False,
                      control_click=False):
    """Cria ou atualiza um contato WhatsApp.

    Para canais coexistence, auto_assign_user_id atribui automaticamente
    ao operador dono do numero.

    control_click=True (clique de avaliacao do recibo v2, revisao
    2026-09-01): NAO avanca last_message_at (recencia — bolha admin_only
    invisivel nao pode subir o contato nas views ordenadas) e NAO auto-atribui
    coexistence (mudanca de posse por mensagem de controle). last_inbound_at
    CONTINUA subindo: o clique abre/renova a janela de 24h na Meta de
    verdade, e e ele que alimenta o _check_24h_window.

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

    `skip_conversation_upsert=True`: caller chama save_wa_message logo em
    seguida (que ja upserta a mesma conversation com message_at correto).
    Evita o dobro de read+write de conversation por mensagem.
    """
    wa_id = normalize_br_phone(wa_id)
    now = utcnow()
    existing = _find_contact_by_wa_id_any_variant(wa_id)
    if existing:
        return _update_existing_wa_contact(
            existing, wa_id, display_name, channel_id, phone_number_id,
            source_channel_type, auto_assign_user_id, from_message_event, now,
            skip_conversation_upsert=skip_conversation_upsert,
            control_click=control_click,
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
                skip_conversation_upsert=skip_conversation_upsert,
                control_click=control_click,
            )
        logger.warning(
            "wa_contact_index %s aponta p/ contato inexistente (%s) — recriando",
            wa_id, winner_id,
        )
    document("wa_contacts", contact_id).set(new_contact)
    # Upsert conversation correspondente (Fase 2 — sub-threads por canal).
    # Pulado em state_sync: thread so nasce com mensagem real, pra nao
    # poluir sidebar com 165 contatos da agenda telefonica.
    # Pulado tambem quando o caller upserta via save_wa_message em seguida.
    if from_message_event and not skip_conversation_upsert:
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
                                auto_assign_user_id, from_message_event, now,
                                skip_conversation_upsert=False,
                                control_click=False):
    """Aplica updates a um contato JA existente. Usado pelo caminho normal
    (achado por wa_id) e pelo fallback do claim atomico (corrida perdida).
    Retorna o contact_id.

    `skip_conversation_upsert=True`: caller garante que save_wa_message vem
    logo em seguida (que upserta a MESMA conversation com args mais ricos —
    message_at/direction_for_unread). Evita ler+escrever a conversation 2x
    por mensagem (dieta de reads do webhook, 2026-07-20)."""
    updates = {}
    if from_message_event:
        if not control_click:
            updates["last_message_at"] = now
        # last_inbound_at sobe SEMPRE em evento de mensagem: e a verdade da
        # janela de 24h da Meta (clique de botao tambem abre/renova janela).
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
    # Atualizar whatsapp_profile_name do webhook sem sobrescrever declared_name.
    # So quando MUDOU: o state_sync reenvia a agenda inteira a cada reconexao
    # do celular — regravar o mesmo nome em milhares de contatos era write puro
    # desperdicado (e o gate `if updates` abaixo nao funcionaria nunca).
    if display_name and display_name != existing.get("whatsapp_profile_name", ""):
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
    # Auto-atribuir para coexistence se nao atribuido. Clique de controle
    # (avaliacao) NUNCA muda posse de lead (control_click, revisao 2026-09-01).
    if auto_assign_user_id and not control_click and not existing.get("assigned_to"):
        user = _get_doc("users", auto_assign_user_id)
        if user:
            updates["assigned_to"] = auto_assign_user_id
            updates["assigned_to_uid"] = user.get("firebase_uid", "")
            if not existing.get("department_id") and user.get("department_id"):
                updates["department_id"] = user["department_id"]
            if existing.get("qualification") == "novo":
                updates["qualification"] = "em_atendimento"
    # So escreve se ha mudanca real. state_sync repetido (agenda inteira a
    # cada reconexao do celular) com nada mudado = 0 writes; era 1 write
    # vazio POR CONTATO da agenda (milhares por sync).
    if updates:
        document("wa_contacts", existing["id"]).set(updates, merge=True)
    # Reflete wa_id canonizado no dict local pra _maybe_upsert_conversation
    # propagar a forma certa pra wa_conversations.
    if updates.get("wa_id"):
        existing = dict(existing)
        existing["wa_id"] = updates["wa_id"]
    # Garante que a conversation deste (channel, wa_id) tambem existe.
    # Pulado em state_sync — contato existe sem thread ate ter mensagem.
    # Pulado tambem quando o caller upserta via save_wa_message em seguida.
    if from_message_event and not skip_conversation_upsert:
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


def create_manual_wa_contact(declared_name, wa_id, channel_id, user_id, allow_admin_override=False,
                             auto_assume=True):
    """Cria contato manualmente pelo operador.

    Retorna (contact_id, error_message).

    Regras quando o wa_id ja existe:
      - Se o contato esta atribuido a OUTRO operador (assigned_to != user_id)
        e nao foi arquivado, retorna erro pedindo transferencia.
        allow_admin_override=True permite ignorar essa trava (admin/supervisor).
      - Se o contato pertence ao proprio user_id, ou esta sem dono
        (assigned_to vazio), ou esta arquivado, reabre e (com auto_assume)
        assume, retornando o id existente.

    auto_assume=False (ADR 0010): NAO vira dono — reabre/cria no pool. Usado
    em modo recepcao e para perfil sem o toggle assumir_atendimento; sem
    isso, o picker de novo contato era um bypass do gate do /api/wa/assume
    (lead orfao virava privado por fora, sumindo da pool dos colegas).
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

        # Contato do proprio user, sem dono ou arquivado: reabre e, se o
        # caller permitir, assume. Sem auto_assume so desarquiva (pool).
        updates = {"is_archived": 0}
        if auto_assume:
            updates.update({
                "assigned_to": user_id,
                "assigned_to_uid": user.get("firebase_uid", ""),
                "qualification": "em_atendimento",
            })
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
        "qualification": "em_atendimento" if auto_assume else "novo",
        "notes": "",
        "assigned_to": user_id if auto_assume else None,
        "assigned_to_uid": user.get("firebase_uid", "") if auto_assume else "",
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


def get_wa_contacts_visible_to(user_id, department_id=None, include_archived=False, see_all=False):
    """Contatos visiveis a um usuario, com o mesmo enriquecimento/ordenacao de
    get_all_wa_contacts.

    Escopo amplo (ver tudo) e decidido SEMPRE pelo caller via `see_all` — no
    M-B2 o main.py passa rbac.can_see_all_tenant(user) (toggle
    ver_todos_leads + teto de role, mesmo criterio das rules/frontend).
    Default e o escopo restrito. Operador comum ve apenas o proprio escopo
    (atribuidos a si ou sem dono/pool) — espelha as Firestore rules do
    caminho de snapshot e evita varrer/expor a agenda inteira do tenant
    (milhares de contatos da agenda coex) no fallback de polling do
    frontend. NAO inclui contatos de colegas do mesmo departamento
    (isolamento LGPD).
    """
    if see_all:
        rows = _all_docs("wa_contacts")
    else:
        rows = get_wa_contacts_scoped_for_user(user_id, department_id)
    return _enrich_and_sort_contacts(rows, include_archived=include_archived)


def update_wa_contact_qualification(contact_id, qualification, notes=None):
    # Guarda: qualification vazia NAO sobrescreve a existente (o endpoint
    # aceita "" pra "salvar so as notas"; antes gravava literalmente "" e o
    # lead sumia do filtro por qualificacao do frontend). Nenhum caller
    # legitimo limpa a qualificacao.
    # notes default None (revisao 2026-09-01): o default antigo "" fazia o
    # caller que omitia notes (reroute de convertido no webhook) APAGAR as
    # notas do contato — incluindo o desfecho que o gate A3 exigiu e a trilha
    # "Atendimento iniciado" do A2. None = nao toca nas notas.
    fields = {}
    if qualification:
        fields["qualification"] = qualification
    if notes is not None:
        fields["notes"] = notes
    if not fields:
        return
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


def ensure_daily_attendance(contact_id, setor=None, contact=None):
    """Get-or-create do Atendimento diario. Trigger: 1o inbound do dia (chamado
    de save_wa_message). Reabre se estava fechado PRESERVANDO
    protocolo_informado (regra do retorno-zumbi). Espelha o id em
    wa_contacts.attendance_protocol. Retorna o protocol_id ou None.

    `contact`: dict ja lido pelo caller (save_wa_message acabou de ler o
    mesmo doc) — evita re-ler wa_contacts por inbound. None = le aqui."""
    if contact is None:
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


def set_attendance_department(contact_id, department_id, contact=None):
    """Carimba o SETOR real no Atendimento do dia depois que o bot decide o
    departamento (o protocolo nasce no 1o inbound, quando ainda nao ha setor
    -> campo/sufixo "GERAL"). Relatorio por setor deve agrupar pelo CAMPO
    `setor`/`department_id`, nunca pelo sufixo do id.

    O ID do protocolo e IMUTAVEL de proposito: ele e um identificador que o
    cliente pode ter recebido ("Seu protocolo e ...") e esta denormalizado em
    wa_messages.protocol_id. Uma versao anterior deste fix MOVIA o doc para um
    id novo (copy+delete+redenorm) — revisao adversarial 2026-07-30 achou 3
    falhas reais: corrida com ensure_daily_attendance de um inbound
    concorrente (dois protocolos no mesmo dia, doc bom orfanado), doc fantasma
    ressuscitado por set(merge=True) quando o move falhava no meio, e TOCTOU
    no guard protocolo_informado. Um unico merge idempotente nao tem nada
    disso.

    Idempotente e best-effort. Retorna o protocol_id atualizado ou None."""
    if contact is None:
        contact = _get_doc("wa_contacts", contact_id)
    if not contact:
        return None
    pid = str(contact.get("attendance_protocol") or "").strip()
    today = _today_br_str()
    # So o Atendimento de HOJE: protocolo de dia anterior ja fechou o ciclo.
    if not pid or not pid.startswith(today + "-"):
        return None
    setor = _setor_code(department_id)
    document("attendances_daily", pid).set(
        {"setor": setor, "department_id": department_id}, merge=True,
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
    # Backup graduado via reassign-lead: gradua tambem as conversas historicas
    # do contato + suas mensagens (senao o novo dono ve o contato mas threads
    # vazias). Escopo backup-only — nao mexe em contato vivo multi-canal (3B).
    if current.get("is_backup"):
        _owner_uid = (to_user or {}).get("firebase_uid", "")
        for _snap in collection("wa_conversations").where("contact_id", "==", contact_id).stream():
            _cd = _snap.to_dict() or {}
            if not _cd.get("is_backup"):
                continue
            _snap.reference.set({
                "is_backup": False,
                "assigned_to": to_user_id,
                "assigned_to_uid": _owner_uid,
                "department_id": to_department_id,
                # Badge de transferencia (mesmo criterio do assign_wa_conversation):
                # a thread graduada chega ao novo dono com unread > 0.
                "unread_count": int(_cd.get("unread_count", 0) or 0) + 1,
            }, merge=True)
            _graduate_backup_messages(_snap.id, _owner_uid)

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


def assign_orphan_threads_to_lead_owner(contact_id, user_id):
    """Apos o assume: toda thread NAO-backup do contato que esta SEM dono herda
    o Dono do Lead — mesma invariante do auto-assign em upsert_wa_conversation
    (via save_wa_message), so que EXPLICITA: aquele caminho so alcanca a thread
    derivada de contact.channel_id (grudado no 1o canal) e roda dentro de um
    try/except que engole falha, entao um lead multi-canal podia ficar com a
    thread da pool orfa depois do assume (visivel pra todo operador). Threads
    que JA tem dono (coex de outro operador, takeover) NAO sao tocadas.
    Idempotente. Retorna a quantidade de threads carimbadas."""
    if contact_id is None or not user_id:
        return 0
    user = _get_doc("users", user_id)
    if not user:
        return 0
    owner_uid = user.get("firebase_uid", "")
    count = 0
    for snap in collection("wa_conversations").where("contact_id", "==", contact_id).stream():
        data = snap.to_dict() or {}
        if data.get("is_backup") or data.get("assigned_to"):
            continue
        updates = {"assigned_to": user_id, "assigned_to_uid": owner_uid}
        if not data.get("department_id") and user.get("department_id"):
            updates["department_id"] = user["department_id"]
        snap.reference.set(updates, merge=True)
        count += 1
    return count


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
    # Modo Recepcao (ADR 0010): fechamento NAO re-gruda o lead na dona de
    # origem (sale_owner inerte) e tambem NAO mexe no dono atual — decisao
    # do PO (canario 2026-08-05): fechamento, principalmente o automatico
    # do cron, nunca muda posse. Devolver a pool e acao EXPLICITA do menu
    # da conversa (return_contact_to_pool).
    if is_reception_mode():
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
    """Devolve o contato para a fila do bot (remove atribuicao do lead E das
    threads). Sem limpar a conversation, ela continua "dona" do operador
    anterior e o lead nunca entra na pool — o filtro 'novos' do frontend exige
    conv.assigned_to vazio (espelha o que assign_wa_contact faz nas threads)."""
    current = _get_doc("wa_contacts", contact_id)
    if not current:
        return None
    from_user = current.get("assigned_to")
    from_dept = current.get("department_id")
    document("wa_contacts", contact_id).set({
        "assigned_to": None,
        "assigned_to_uid": "",
        "department_id": None,
        "qualification": "novo",
        "bot_completed": False,
        "attendance_protocol": "",
        "attendance_started_at": "",
    }, merge=True)
    # Espelha a remocao de dono/setor nas threads (wa_conversations) do contato.
    # Exceto backup (historico importado nao volta para o bot).
    for _snap in collection("wa_conversations").where("contact_id", "==", contact_id).stream():
        _cd = _snap.to_dict() or {}
        if _cd.get("is_backup"):
            continue
        _snap.reference.set({
            "assigned_to": None,
            "assigned_to_uid": "",
            "department_id": None,
        }, merge=True)
    # Estado do bot CX: o contato volta pro inicio do funil, entao o ciclo
    # anterior nao pode contaminar o proximo. Limpa SO os campos cx_*/
    # human_active — o doc inteiro nao pode ser apagado porque guarda a prova
    # de aceite da LGPD (lgpd_status), e o cliente tomaria o aviso de novo.
    try:
        document("bot_states", contact_id).set({
            "cx_snapshot": None,
            "cx_summary_emitted": None,
            "cx_summary_emitted_pid": None,
            "cx_fail_count": 0,
            "human_active": False,
        }, merge=True)
    except Exception as exc:
        logger.warning("return_contact_to_bot: falha ao limpar bot_state %s: %s", contact_id, exc)
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


def return_contact_to_pool(contact_id, returned_by_user_id):
    """Devolve o lead a POOL da recepcao (ADR 0010) — acao explicita do menu.

    Zera o dono do contato E das threads nao-backup, e SO isso: preserva
    bot_completed, qualification, department_id, protocolo e sale_owner
    (inerte em reception). Diferente de return_contact_to_bot, o lead NAO
    volta pro funil do bot — cai direto na aba Recepcao de todos.
    """
    current = _get_doc("wa_contacts", contact_id)
    if not current:
        return None
    from_user = current.get("assigned_to")
    document("wa_contacts", contact_id).set({
        "assigned_to": None,
        "assigned_to_uid": "",
    }, merge=True)
    for _snap in collection("wa_conversations").where("contact_id", "==", contact_id).stream():
        _cd = _snap.to_dict() or {}
        if _cd.get("is_backup"):
            continue
        _snap.reference.set({"assigned_to": None, "assigned_to_uid": ""}, merge=True)
    transfer_id = next_sequence("wa_transfer_log")
    document("wa_transfer_log", transfer_id).set({
        "id": transfer_id,
        "contact_id": contact_id,
        "contact_doc_id": str(contact_id),
        "from_user_id": from_user,
        "to_user_id": None,
        "to_user_uid": "",
        "from_department_id": current.get("department_id"),
        "to_department_id": current.get("department_id"),
        "department_id": current.get("department_id"),
        "reason": "Devolvido a recepcao",
        "summary": "Lead devolvido para a pool compartilhada",
        "transferred_by": returned_by_user_id,
        "created_at": utcnow(),
    })
    return True


def mark_contact_bot_done(contact_id):
    """Carimba bot_completed=True no contato (ADR 0010, canario #4).

    Engajamento humano REAL numa orfa da pool tira o contato do funil do
    bot: sem o carimbo, thread orfa de contato mid-bot/pos-release fica
    INVISIVEL na aba Recepcao (o filtro exige bot_completed) — o operador
    envia o template de reabertura e a conversa some das colegas. O
    release_lead_to_bot re-arma o bot no proximo fechamento. Best-effort.
    """
    try:
        document("wa_contacts", contact_id).set({"bot_completed": True}, merge=True)
        return True
    except Exception as exc:
        logger.warning("mark_contact_bot_done: falha p/ contato %s: %s", contact_id, exc)
        return False


def release_lead_to_bot(contact_id, closed_conversation_id=None, close_status=None):
    """Fechamento devolve o lead ao AGENTE DE IA (Fase 2 do PLANO_MODELOS,
    antecipada com gate por pool_mode=reception — decisao do PO 2026-08-05).

    NAO reusa return_contact_to_bot (clobberaria qualification/protocolo/
    department_id). Preserva por omissao: sale_owner, lead_temperature,
    lgpd_*, attendance_protocol/started_at, department_id, qualification.
    Ordem commit-point: periferia primeiro, CONTATO por ultimo. Retorna os
    campos pro caller carimbar NA CONVERSA FECHADA (sem dono + takeover
    limpo), ou None (guards) — caller cai no revert legado.
    """
    contact = _get_doc("wa_contacts", contact_id)
    if not contact or contact.get("is_backup"):
        return None
    # Guard J-3 (D8, forward-compatible): contato com consentimento revogado
    # NUNCA volta pro funil do bot automaticamente.
    if contact.get("lgpd_revoked"):
        return None
    # Passo 1 — bot_states: zera ciclo CX anterior + human_active (sem isso o
    # CX ficaria mudo pra sempre — gate do human_active). Preserva lgpd_*.
    try:
        document("bot_states", contact_id).set({
            "cx_snapshot": None,
            "cx_summary_emitted": None,
            "cx_summary_emitted_pid": None,
            "cx_fail_count": 0,
            "human_active": False,
        }, merge=True)
    except Exception as exc:
        logger.warning("release_lead_to_bot: falha ao limpar bot_state %s: %s", contact_id, exc)
    # Passo 2 — threads nao-backup: sem dono (mantem department_id).
    for _snap in collection("wa_conversations").where("contact_id", "==", contact_id).stream():
        _cd = _snap.to_dict() or {}
        if _cd.get("is_backup"):
            continue
        _snap.reference.set({"assigned_to": None, "assigned_to_uid": ""}, merge=True)
    # Passo 3 — system message (best-effort; recencia nao infla).
    try:
        insert_transfer_system_message(
            contact_id, "Atendimento devolvido ao assistente virtual.",
            None, conversation_id=closed_conversation_id, advance_recency=False,
        )
    except Exception as exc:
        logger.warning("release_lead_to_bot: system message falhou %s: %s", contact_id, exc)
    # Passo 4 — CONTATO (commit point): bot volta a atender no proximo turno.
    document("wa_contacts", contact_id).set({
        "bot_completed": False,
        "assigned_to": None,
        "assigned_to_uid": "",
    }, merge=True)
    return {
        "assigned_to": None,
        "assigned_to_uid": "",
        "takeover_status": "none",
        "takeover_started_at": None,
    }


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


def count_wa_contacts_scoped_for_user(user_id):
    """Contador BARATO da agenda do operador comum — espelha as mesmas
    queries de get_wa_contacts_scoped_for_user, mas com aggregate count()
    (1 read por 1000 docs) em vez de stream (1 read POR DOC). Usado pelo
    header da sidebar (count_only=1), que so precisa do numero — pra
    carteira grande (aline/danielle, ~3k docs) corta ~3k reads por
    page-load pra ~3.

    Aproximacoes conscientes (contador e cosmetico):
    - Nao deduplica entre as queries: os conjuntos sao disjuntos por
      definicao (assigned_to_uid = <uid> / "" / None sao mutuamente
      exclusivos por doc).
    - Nao subtrai is_archived (0 docs arquivados em prod hoje).
    - O sentinela "__backup__" fica de fora naturalmente (nao casa ""/None).
    """
    col = collection("wa_contacts")
    queries = []
    if user_id is not None:
        queries.append(col.where("assigned_to", "==", user_id))
    queries.append(col.where("assigned_to_uid", "==", ""))
    queries.append(col.where("assigned_to_uid", "==", None))
    total = 0
    for query in queries:
        res = query.count(alias="n").get()
        total += int(res[0][0].value)
    return total


def insert_transfer_system_message(contact_id, content, operator_id=None,
                                   conversation_id=None, channel_id=None,
                                   advance_recency=True):
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
        advance_recency=advance_recency,
    )


def insert_internal_note(contact_id, content, sender_user_id, conversation_id=None, channel_id=None, sent_by_name=""):
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
        sent_by_name=sent_by_name,
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
                    sent_by_name="",
                    template_category=None, media_size_bytes=0,
                    advance_recency=True, contact=None,
                    promote_qualification=True,
                    reopen_attendance=True,
                    control_message=False,
                    human_outbound=True):
    """Persiste mensagem WhatsApp.

    human_outbound=False: outbound com operador identificado que NAO conta
    como atencao humana (uso: template da reabertura em lote — carimbar
    last_human_outbound_at desarmaria a valvula/auto-close do Modo Recepcao
    em massa; revisao adversarial C2). Autoria/auditoria seguem normais.

    reopen_attendance=False: a mensagem nao conta como "atividade" pro ciclo
    de vida — nao reabre attendance_status fechado (uso: recibo de
    fechamento; revisao 2026-09-01).

    control_message=True (clique de avaliacao do recibo v2): mensagem de
    CONTROLE solicitada pelo sistema, invisivel ao operador comum — nao
    incrementa nao-lido (contato nem thread), nao cria/reabre o Atendimento
    diario, nao avanca recencia e nao reabre o atendimento. Sem isto o clique
    acendia badge/alarme de uma bolha admin_only que ninguem ve (classe do
    incidente ADR 0011) e reabria protocolo/thread recem-fechados.

    Auditoria coexistence (Fase 2C):
      - `channel_owner_user_id`: dono fisico do numero (ex.: operador X que
        conectou o WhatsApp pessoal dele via coexistence). Vem de
        `channel.owner_user_id` no momento do envio/recebimento.
      - `sender_user_id`: operador que efetivamente digitou/enviou (em
        outbound). None em inbound. Permite distinguir, em transferencias
        coexistence, quem digitou vs quem e o dono do numero.
      - `sent_by_name`: display_name denormalizado de quem enviou (ADR 0010,
        Modo Recepcao): no snapshot mode o frontend le o doc direto e nao tem
        o join REST de operator_name — sem o nome no doc, a bolha mostra so
        "Equipe". Vazio em inbound/bot/legado (fallback no frontend).

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

    # `contact` pode vir pre-lido do caller (webhook le 1x e reaproveita em
    # save + daily attendance + takeover + gate do bot) — dieta de reads.
    if contact is None:
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
        if direction == "inbound" and not control_message:
            try:
                protocol_id = ensure_daily_attendance(contact_id, contact=contact)
            except Exception as exc:
                logger.warning("ensure_daily_attendance falhou contact=%s: %s", contact_id, exc)
        else:
            # Outbound/system e cliques de CONTROLE leem o protocolo atual sem
            # criar/reabrir (clique de avaliacao nao e atendimento novo).
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
        "sent_by_name": sent_by_name or "",
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
        updates = {"last_message_at": _eff_msg_at} if (_lma_advances and advance_recency and not control_message) else {}
        if direction == "inbound" and status == "received" and not control_message:
            updates["unread_count"] = int(contact.get("unread_count", 0)) + 1
        # Reforma de qualificacoes (2026-09): a 1a interacao HUMANA promove o
        # lead "novo" a "em_atendimento" e deixa rastro na nota. Mesmo sinal
        # do last_human_outbound_at (outbound com operador identificado) —
        # bot (sender None), inbound e system ficam de fora. O recibo de
        # protocolo do fechamento passa promote_qualification=False (texto de
        # sistema no encerramento nao e inicio de atendimento).
        if (
            promote_qualification
            and direction == "outbound"
            and sender_user_id is not None
            and (contact.get("qualification") or "novo") == "novo"
        ):
            # Data REAL da mensagem (_eff_msg_at), nao relogio de parede:
            # replay de history/backup carimbaria "iniciado hoje" numa
            # conversa de meses atras (revisao 2026-09-01 — mesmo motivo do
            # guard monotonico logo acima).
            _started_at = _eff_msg_at
            if _started_at.tzinfo is None:
                _started_at = _started_at.replace(tzinfo=timezone.utc)
            _started_br = _started_at.astimezone(_BR_TZ).strftime("%d/%m/%Y %H:%M")
            _note_line = f"Atendimento iniciado em {_started_br}"
            _cur_notes = str(contact.get("notes") or "").strip()
            updates["qualification"] = "em_atendimento"
            updates["first_human_contact_at"] = _eff_msg_at
            updates["notes"] = f"{_cur_notes}\n{_note_line}" if _cur_notes else _note_line
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
                    direction_for_unread=None if control_message else ("inbound" if direction == "inbound" and status == "received" else ("outbound" if direction == "outbound" else None)),
                    # Conversa herda o Dono do Lead (contact.assigned_to). O guard
                    # de orfa em upsert_wa_conversation (so atribui se a thread NAO
                    # tem dono) garante que isto nunca pisa em transferencia de
                    # thread nem em takeover ativo. [LGPD: thread orfa e legivel
                    # por qualquer operador via canSeeContactScoped; herdar o dono
                    # fecha esse vetor].
                    auto_assign_user_id=(contact or {}).get("assigned_to"),
                    message_at=_eff_msg_at,
                    # control_message: recencia da THREAD nao avanca (a
                    # ordenacao visivel da sidebar e por thread; o contato ja
                    # subiu no upsert_wa_contact pre-parse, inocuo — so
                    # afeta a janela de hidratacao, nao a ordem das linhas).
                    advance_recency=advance_recency and not control_message,
                    # Resposta HUMANA ao cliente: outbound com operador
                    # identificado. Fica de fora mensagem do bot
                    # (sender_user_id None), system message e nota interna
                    # (direction != outbound — o cliente nem ve). E o sinal
                    # que o auto-close usa pra nao devolver ao bot um handoff
                    # que ninguem atendeu.
                    human_outbound_at=(
                        _eff_msg_at
                        if direction == "outbound" and sender_user_id is not None
                        and human_outbound
                        else None
                    ),
                    reopen_attendance=reopen_attendance and not control_message,
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
    # ADR 0011: a THREAD e a fonte da verdade — este endpoint e cross-canal
    # por definicao, entao zera tambem todas as threads do contato (senao a
    # soma das threads volta a divergir do contato no proximo recompute).
    for snapshot in collection("wa_conversations").where("contact_id", "==", contact_id).stream():
        if int((snapshot.to_dict() or {}).get("unread_count", 0) or 0) > 0:
            snapshot.reference.set({"unread_count": 0}, merge=True)
    document("wa_contacts", contact_id).set({"unread_count": 0}, merge=True)
    return total_updated


# ---------------------------------------------------------------------------
# Audit metrics (pre-aggregated daily counters)
# ---------------------------------------------------------------------------

def _audit_metric_doc_id(date_str, user_id=None):
    return f"{date_str}_{user_id}" if user_id else date_str


def increment_audit_metrics(direction, operator_id=None, is_new_lead=False, is_assumed=False):
    """Incrementa metricas diarias. Chamada a cada save_wa_message.

    Usa firestore.Increment (atomico, SEM read) nos contadores — elimina o
    read-modify-write nao-atomico que perdia incrementos sob concorrencia (mesmo
    padrao ja adotado em increment_usage_metrics). Cada chamada vira 1 write por
    doc e ZERO reads.

    last_activity_at e gravado a cada chamada (last-write-wins, correto e de
    graca no merge). first_activity_at NAO e mais gravado: mante-lo exato exigiria
    um read (ou um create() que, ao falhar com AlreadyExists, AINDA e cobrado como
    write) — e o campo nao e exibido no frontend (a tabela por operador so mostra
    inbound/outbound/leads_assumed). Docs legados que ja tinham o campo
    permanecem; o consumidor (main.py) trata ausencia como None.
    """
    now = utcnow()
    date_str = now.strftime("%Y-%m-%d")
    half_hour = f"{now.strftime('%H')}:{('00' if now.minute < 30 else '30')}"

    def _increment(doc_id):
        updates = {
            "date": date_str,
            "updated_at": now,
            "last_activity_at": now,
            # Increment aninhado no mapa: incrementa so o slot do half-hour,
            # preservando os irmaos (merge=True faz deep-merge do mapa) — mesmo
            # padrao de templates_sent em increment_usage_metrics.
            "messages_by_half_hour": {half_hour: firestore.Increment(1)},
        }

        if direction == "inbound":
            updates["total_messages_inbound"] = firestore.Increment(1)
        elif direction == "outbound":
            updates["total_messages_outbound"] = firestore.Increment(1)

        if is_new_lead:
            updates["total_leads_received"] = firestore.Increment(1)
        if is_assumed:
            updates["total_leads_assumed"] = firestore.Increment(1)

        document("audit_metrics", doc_id).set(updates, merge=True)

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
    """Retorna contatos com avaliacao registrada. Recibo v2 (2026-09):
    qualquer fechamento avaliado conta, nao so convertidos — a query saiu de
    qualification=='convertido' pra rating>0 (desigualdade em campo unico,
    indice automatico)."""
    rows = []
    for snap in collection("wa_contacts").where("rating", ">", 0).stream():
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
        # Datas REAIS (datetime). String aqui ordena ACIMA de datetime no
        # Firestore -> tomava o top-50 do snapshot de contatos do admin.
        "first_seen_at": _coerce_timestamp(first_seen_at),
        "last_message_at": _coerce_timestamp(last_ts),
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
    """Cria a conversa HISTORICA (backup): is_backup + sentinela, NUNCA 'aberto'.
    Reflete o canal REAL (nao finge removido). Se a conversa ja existe e NAO e
    backup (thread viva), NAO rebaixa. Idempotente."""
    wa_id = normalize_br_phone(wa_id)
    ref = document("wa_conversations", conversation_id)
    snap = ref.get()
    if snap.exists:
        return conversation_id  # ja existe (backup ou viva) — nao mexe
    # Reflete o canal REAL (vivo): backup do 3351-7604 NAO e "canal removido".
    # O isolamento do backup vem de is_backup + aba Backup; fingir o canal
    # inativo confundia a UI e quebrava a resposta apos a graduacao.
    _ch = None
    try:
        from channel_service import get_channel as _get_channel
        _ch = _get_channel(channel_id) if channel_id is not None else None
    except Exception:
        _ch = None
    ref.set({
        "id": conversation_id,
        "contact_id": contact_id,
        "wa_id": wa_id,
        "channel_id": channel_id,
        "phone_number_id": (_ch.get("phone_number_id", "") if _ch else ""),
        "source_channel_type": (_ch.get("channel_type", "standard") if _ch else "standard"),
        "assigned_to": None,
        "assigned_to_uid": BACKUP_ASSIGNED_UID,
        "department_id": None,
        "unread_count": 0,
        "status": "open",
        "attendance_status": "fechado_inatividade",  # NUNCA 'aberto' (sem auto-close/protocolo)
        "is_backup": True,
        "channel_label": (_ch.get("label") if _ch else (channel_label or "Backup (historico)")),
        "channel_phone_number": (_ch.get("display_phone_number", "") if _ch else ""),
        "channel_active": bool(_ch),
        # Datas REAIS (datetime). String aqui ordena ACIMA de datetime no
        # Firestore e tomava o top-300 do snapshot, sumindo as conversas vivas.
        "created_at": _coerce_timestamp(first_ts),
        "last_message_at": _coerce_timestamp(last_ts),
        "last_inbound_at": _coerce_timestamp(last_in),
        "last_outbound_at": _coerce_timestamp(last_out),
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

_POOL_MODE_OPTIONS = ("legacy", "reception")


def _clean_quick_messages(items, label, max_items=None):
    """Normaliza e valida a lista de mensagens rapidas (globais ou pessoais).

    Trava de dados (a UI valida antes, mas a garantia e aqui): atalho e
    mensagem obrigatorios, atalho unico na lista (case-insensitive, com ou
    sem "/"), limite opcional de itens. `title` e opcional — identifica a
    mensagem nas configuracoes e na lista do compositor; nao vai pro cliente.
    Levanta ValueError com texto pro usuario (o endpoint responde 400).
    """
    if items is None:
        return []
    if not isinstance(items, list):
        raise ValueError(f"{label}: formato invalido")
    cleaned, seen = [], set()
    for i, raw in enumerate(items, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"{label}: item {i} invalido")
        shortcut = str(raw.get("shortcut") or "").strip()
        message = str(raw.get("message") or "").strip()
        title = str(raw.get("title") or "").strip()
        if not shortcut or not message:
            raise ValueError(f"{label}: item {i} sem atalho ou sem mensagem")
        key = (shortcut if shortcut.startswith("/") else "/" + shortcut).lower()
        if key in seen:
            raise ValueError(f"{label}: atalho repetido ({key})")
        seen.add(key)
        entry = {"shortcut": shortcut, "message": message}
        if title:
            entry["title"] = title
        cleaned.append(entry)
    if max_items is not None and len(cleaned) > max_items:
        raise ValueError(f"{label}: limite de {max_items} mensagens rapidas")
    return cleaned

# -- Tags de lead (Frente B, 2026-09-02) --------------------------------------
# Vocabulario em DOIS registries no shape das quick messages: tags GLOBAIS do
# tenant (system_settings.tags_global, editadas por quem tem o toggle
# gerenciar_tags_globais — supervisor+admin por seed) e tags PESSOAIS de cada
# operador (user_settings.tags, criadas on-the-fly ao aplicar). O LEAD guarda
# so a lista de SLUGS normalizados (wa_contacts.tags) — licao do legado
# crm_tags: tag gravada sem normalizar obrigava busca brute-force por
# variantes de caixa/acento.

_TAG_SLUG_MAX = 40
_TAG_LABEL_MAX = 60
LEAD_TAGS_MAX = 12


def normalize_tag_slug(raw):
    """Slug canonico: minusculo, sem acento, so [a-z0-9_-]; espaco vira '-'."""
    import unicodedata
    token = str(raw or "").strip().casefold()
    token = unicodedata.normalize("NFKD", token)
    token = "".join(ch for ch in token if not unicodedata.combining(ch))
    token = token.replace(" ", "-")
    token = "".join(ch for ch in token if ch.isalnum() or ch in ("_", "-"))
    return token[:_TAG_SLUG_MAX]


def clean_lead_tags(raw_tags):
    """Normaliza/dedupa as tags de um LEAD (lista de strings -> slugs).

    ValueError com texto pt-BR pro endpoint responder 400. Dedupe e
    case/acento-insensitive por construcao (slug canonico)."""
    if raw_tags is None:
        return []
    if not isinstance(raw_tags, (list, tuple)):
        raise ValueError("Tags: formato invalido (esperada uma lista)")
    out, seen = [], set()
    for raw in raw_tags:
        if not isinstance(raw, str):
            # Revisao B: dict/num virava slug-lixo em silencio (str(dict)).
            raise ValueError("Tags: cada tag deve ser texto")
        slug = normalize_tag_slug(raw)
        if not slug or slug in seen:
            continue
        seen.add(slug)
        out.append(slug)
    if len(out) > LEAD_TAGS_MAX:
        raise ValueError(f"Maximo de {LEAD_TAGS_MAX} tags por lead")
    return out


def _valid_hex_color(color):
    return (len(color) == 7 and color[0] == "#"
            and all(ch in "0123456789abcdefABCDEF" for ch in color[1:]))


def _clean_tag_defs(items, label, max_items=None):
    """Valida um registry de tags ({slug|label, color?}). Mesma disciplina do
    _clean_quick_messages: ValueError com texto de usuario -> 400."""
    if items is None:
        return []
    if not isinstance(items, list):
        raise ValueError(f"{label}: formato invalido")
    cleaned, seen = [], set()
    for i, raw in enumerate(items, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"{label}: item {i} invalido")
        rotulo = str(raw.get("label") or "").strip()
        slug = normalize_tag_slug(raw.get("slug") or rotulo)
        if not slug:
            raise ValueError(f"{label}: item {i} sem nome")
        if len(rotulo) > _TAG_LABEL_MAX:
            raise ValueError(f"{label}: nome da tag excede {_TAG_LABEL_MAX} caracteres")
        if slug in seen:
            raise ValueError(f"{label}: tag repetida ({slug})")
        seen.add(slug)
        entry = {"slug": slug, "label": rotulo or slug}
        color = str(raw.get("color") or "").strip()
        if color:
            if not _valid_hex_color(color):
                raise ValueError(f"{label}: cor invalida em '{entry['label']}' (use #rrggbb)")
            entry["color"] = color
        cleaned.append(entry)
    if max_items is not None and len(cleaned) > max_items:
        raise ValueError(f"{label}: limite de {max_items} tags")
    return cleaned


def update_wa_contact_tags(contact_id, slugs):
    """Grava a lista (ja limpa por clean_lead_tags) no contato."""
    document("wa_contacts", contact_id).set({"tags": list(slugs)}, merge=True)


def scan_reopen_candidates(max_attempts=1, cooldown_hours=24, window_hours=24):
    """Frente C2: varre leads "em_atendimento" e classifica pro lote de
    reabertura. Query server-side por IGUALDADE (indice automatico, sem
    composto — mesma dieta do close_stale_attendances); demais filtros em
    Python. O caller (main) valida canal/template e executa.

    Retorna {"enviaveis": [contatos], "auto_resolve": [contatos],
             "pulados": {motivo: n}, "por_setor": {department_id|0: n}}.

    Regras (PO 2026-09-01/02): publico = em_atendimento; fora da janela de
    24h (janela desconhecida NAO envia — template e conversa paga, so com
    evidencia de janela fechada); cooldown por lead; attempts >= max vira
    AUTO-RESOLVE (fecha sem enviar — "muito importante", PO); exclui opt-out
    (ADR 0009 D2), lgpd_revoked, arquivado e backup."""
    now = utcnow()
    janela_cutoff = now - timedelta(hours=window_hours)
    cooldown_cutoff = now - timedelta(hours=cooldown_hours)

    def _ts(raw):
        if not raw:
            return None
        try:
            dt = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw))
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        except Exception:
            return None

    enviaveis, auto_resolve = [], []
    pulados = {}
    por_setor = {}

    def _skip(motivo):
        pulados[motivo] = pulados.get(motivo, 0) + 1

    for snap in collection("wa_contacts").where("qualification", "==", "em_atendimento").stream():
        c = snap.to_dict() or {}
        c.setdefault("id", snap.id)
        if int(c.get("is_archived") or 0):
            _skip("arquivado")
            continue
        if c.get("is_backup"):
            _skip("backup")
            continue
        if c.get("reopen_opt_out"):
            _skip("opt_out")
            continue
        if c.get("lgpd_revoked"):
            _skip("lgpd_revogado")
            continue
        li = _ts(c.get("last_inbound_at"))
        if li is None:
            _skip("janela_desconhecida")
            continue
        if li > janela_cutoff:
            _skip("janela_aberta")
            continue
        lrt = _ts(c.get("last_reopen_template_at"))
        if lrt is not None and lrt > cooldown_cutoff:
            _skip("cooldown")
            continue
        if int(c.get("reopen_attempts") or 0) >= max_attempts:
            # Auto-resolve e TERMINAL (revisao adversarial C2): o worker
            # carimba reopen_resolved_at ao processar; sem o skip, o mesmo
            # lead voltava ao balde em TODO lote, pra sempre (inbound limpa
            # o carimbo junto com o reset de attempts no webhook).
            if c.get("reopen_resolved_at"):
                _skip("ja_resolvido")
                continue
            auto_resolve.append(c)
            continue
        enviaveis.append(c)
        dep = c.get("department_id") or 0
        por_setor[dep] = por_setor.get(dep, 0) + 1

    return {"enviaveis": enviaveis, "auto_resolve": auto_resolve,
            "pulados": pulados, "por_setor": por_setor}


_DEFAULT_SYSTEM_SETTINGS = {
    "chat_prefix_enabled": False,
    "chat_prefix_roles": ["admin", "supervisor", "operador"],
    "quick_message_max": 20,
    "quick_messages_global": [],
    "tags_global": [],
    "notification_sound_enabled": True,
    "alarm_enabled": True,
    "alarm_threshold_minutes": 5,
    "alarm_department_ids": [],
    "alarm_sound_path": "",
    "notification_sound_path": "",
    "bot_enabled": False,
    # Modo da fila "Novos" (ADR 0010): "legacy" = assumir pra falar (ADR
    # 0008); "reception" = pool compartilhada (operador comum responde thread
    # sem dono, sem virar dono; autoria vai na mensagem). Default no READ —
    # nunca backfill; kill-switch = PUT pool_mode=legacy (sem deploy).
    "pool_mode": "legacy",
    # Fechamento automatico por inatividade (cron). False = atendimento com
    # interacao humana NUNCA fecha sozinho (todo encerramento vira manual);
    # a valvula de orfaos do Modo Recepcao (handoff sem NENHUMA resposta
    # humana alem do teto de dias) continua ativa — decisao do PO 2026-09-01.
    "auto_close_enabled": True,
    # Recibo v2: pergunta de avaliacao (Ruim/Bom/Excelente) junto do
    # protocolo no encerramento manual. Toggle POR TENANT (PO 2026-09-02, no
    # lugar do env global): admin liga/desliga na aba Sistema sem deploy.
    # Default False — liga por decisao explicita de cada empresa.
    "rating_request_enabled": False,
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
    # pool_mode e vocabulario fechado: valor desconhecido degrada pro
    # comportamento legado em vez de gravar lixo no doc.
    if "pool_mode" in filtered and str(filtered.get("pool_mode") or "") not in _POOL_MODE_OPTIONS:
        filtered["pool_mode"] = "legacy"
    # Coercao fechada dos toggles booleanos (revisao 2026-09-01):
    # bool("false") e True — um PUT cru com string (kill-switch de madrugada,
    # JSON a mao) falharia silenciosamente LIGADO. Espirito do pool_mode.
    for _bool_key in ("auto_close_enabled", "rating_request_enabled"):
        if _bool_key in filtered:
            _raw_b = filtered[_bool_key]
            if isinstance(_raw_b, str):
                filtered[_bool_key] = _raw_b.strip().lower() not in (
                    "false", "0", "no", "off", "")
            else:
                filtered[_bool_key] = bool(_raw_b)
    if "quick_messages_global" in filtered:
        filtered["quick_messages_global"] = _clean_quick_messages(
            filtered["quick_messages_global"], "Mensagens globais")
    if "tags_global" in filtered:
        filtered["tags_global"] = _clean_tag_defs(
            filtered["tags_global"], "Tags globais", max_items=200)
    filtered["updated_at"] = utcnow()
    document("system_settings", "chat").set(filtered, merge=True)
    return get_system_settings()


def is_reception_mode() -> bool:
    """True se o tenant atual opera a fila como pool compartilhada.

    Modo Recepcao (ADR 0010): operador comum responde thread SEM dono sem
    assumir. Fail-closed: erro de leitura degrada pro comportamento legado
    ("assumir pra falar", ADR 0008).
    """
    try:
        return get_system_settings().get("pool_mode") == "reception"
    except Exception as exc:
        logger.warning("is_reception_mode: leitura falhou, assumindo legacy: %s", exc)
        return False


def is_rating_request_enabled() -> bool:
    """True se este tenant pergunta avaliacao no encerramento manual (recibo
    v2). Toggle por tenant (PO 2026-09-02). Fail-closed: erro de leitura NAO
    pergunta — avaliacao e opt-in explicito, e fora da janela custa template
    pago."""
    try:
        return bool(get_system_settings().get("rating_request_enabled", False))
    except Exception as exc:
        logger.warning("is_rating_request_enabled: leitura falhou, assumindo OFF: %s", exc)
        return False


def is_auto_close_enabled() -> bool:
    """True se o cron pode fechar atendimentos por INATIVIDADE neste tenant.

    Toggle por tenant (system_settings.auto_close_enabled). Fail-safe: erro
    de leitura mantem o comportamento historico (fecha). A valvula de orfaos
    do Modo Recepcao NAO passa por aqui — continua ativa mesmo com o toggle
    desligado (ver close_stale_attendances)."""
    try:
        return bool(get_system_settings().get("auto_close_enabled", True))
    except Exception as exc:
        logger.warning("is_auto_close_enabled: leitura falhou, assumindo ligado: %s", exc)
        return True


def get_user_settings(user_id: int):
    doc = _get_doc("user_settings", user_id)
    defaults = {
        "chat_prefix_enabled": False,
        "chat_prefix_name": "",
        "quick_messages": [],
        # Tags PESSOAIS do operador (Frente B): criadas on-the-fly ao aplicar
        # uma tag que nao existe nos registries; alimentam so o autocomplete
        # dele (as globais valem pra todos).
        "tags": [],
    }
    if not doc:
        return defaults
    result = dict(defaults)
    result.update({k: v for k, v in doc.items() if k in defaults})
    return result


def save_user_settings(user_id: int, settings: dict):
    allowed = {"chat_prefix_enabled", "chat_prefix_name", "quick_messages", "tags"}
    filtered = {k: v for k, v in settings.items() if k in allowed}
    if "quick_messages" in filtered:
        # Limite por usuario (quick_message_max) agora vale no backend tambem.
        max_items = int(get_system_settings().get("quick_message_max") or 0) or None
        filtered["quick_messages"] = _clean_quick_messages(
            filtered["quick_messages"], "Mensagens rapidas", max_items)
    if "tags" in filtered:
        filtered["tags"] = _clean_tag_defs(filtered["tags"], "Minhas tags", max_items=100)
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
